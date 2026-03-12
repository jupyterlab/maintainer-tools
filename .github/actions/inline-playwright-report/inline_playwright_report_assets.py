from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import mimetypes
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE64_ASSIGNMENT_PATTERN = re.compile(
    r"(window\.playwrightReportBase64\s*=\s*)([\"'])(.*?)(\2\s*;)",
    re.DOTALL,
)

ASSIGNMENT_PREFIX = 'window.playwrightReportBase64 = "'
ASSIGNMENT_SUFFIX = '";'

INLINE_MEDIA_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".ico",
    ".tif",
    ".tiff",
    ".avif",
    ".webm",
    ".mp4",
    ".ogv",
    ".mov",
    ".m4v",
}


@dataclass
class ProcessZipResult:
    zip_bytes: bytes
    touched_json_files: int
    total_replacements: int
    total_images: int
    inlined_videos: int
    total_videos: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inline image files referenced from Playwright HTML report JSON into "
            "window.playwrightReportBase64 and write a new HTML file."
        )
    )
    parser.add_argument(
        "report_dir",
        type=Path,
        help="Path to Playwright report directory (must contain index.html)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output HTML path (default: output.html in the report directory)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print matched media references",
    )
    parser.add_argument(
        "--max-output-mb",
        type=float,
        default=None,
        help=(
            "Maximum output HTML size in MB. Images are always inlined first, then "
            "videos are added until the cap is reached."
        ),
    )
    return parser.parse_args()


def extract_data_uri_from_html(html: str) -> tuple[str, str]:
    match = BASE64_ASSIGNMENT_PATTERN.search(html)
    if not match:
        message = "Could not find window.playwrightReportBase64 assignment in HTML"
        raise ValueError(message)
    return match.group(0), match.group(3)


def split_data_uri(data_uri: str) -> bytes:
    if not data_uri.startswith("data:"):
        message = "Expected data URI for window.playwrightReportBase64 value"
        raise ValueError(message)

    try:
        header, b64_data = data_uri.split(",", 1)
    except ValueError as exc:
        message = "Malformed data URI"
        raise ValueError(message) from exc

    if ";base64" not in header:
        message = "Expected base64 data URI"
        raise ValueError(message)

    return base64.b64decode(b64_data)


def encode_zip_data_uri(data: bytes) -> str:
    return f"data:application/zip;base64,{base64.b64encode(data).decode('ascii')}"


def build_report_assignment(data_uri: str) -> str:
    return f"{ASSIGNMENT_PREFIX}{data_uri}{ASSIGNMENT_SUFFIX}"


def media_mime_type(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext not in INLINE_MEDIA_EXTENSIONS:
        return None
    mime, _ = mimetypes.guess_type(filename)
    if not mime:
        if ext == ".svg":
            mime = "image/svg+xml"
        elif ext in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        elif ext == ".png":
            mime = "image/png"
        elif ext == ".webm":
            mime = "video/webm"
        elif ext == ".ogv":
            mime = "video/ogg"
        elif ext in {".mp4", ".m4v"}:
            mime = "video/mp4"
        elif ext == ".mov":
            mime = "video/quicktime"
        else:
            mime = "application/octet-stream"
    return mime


def resolve_reference_path(base: str, report_dir: Path) -> Path:
    direct = Path(base)
    if not direct.is_absolute():
        direct = report_dir / direct
    try:
        if direct.exists() and direct.is_file():
            return direct
    except OSError:
        return direct
    return direct


def split_reference(value: str) -> tuple[str, str]:
    cut_indices = [idx for idx in (value.find("?"), value.find("#")) if idx != -1]
    if not cut_indices:
        return value, ""
    cut_at = min(cut_indices)
    return value[:cut_at], value[cut_at:]


def to_data_uri_for_reference(
    value: str,
    report_dir: Path,
    cache: dict[str, str | None],
    allowed_paths: set[str] | None,
) -> str | None:
    if value.startswith("data:"):
        return value

    base, suffix = split_reference(value)
    if media_mime_type(base) is None:
        return None

    if allowed_paths is not None and base not in allowed_paths:
        return None

    if base in cache:
        cached = cache[base]
        return None if cached is None else cached + suffix

    if "://" in base:
        cache[base] = None
        return None

    resolved = resolve_reference_path(base, report_dir)

    mime = media_mime_type(resolved.name)
    if not mime or not resolved.exists() or not resolved.is_file():
        cache[base] = None
        return None

    payload = base64.b64encode(resolved.read_bytes()).decode("ascii")
    data_uri = f"data:{mime};base64,{payload}"
    cache[base] = data_uri
    return data_uri + suffix


def inline_paths_in_json(
    obj: Any,
    report_dir: Path,
    cache: dict[str, str | None],
    replaced_paths: set[str],
    allowed_paths: set[str] | None,
) -> int:
    replaced = 0

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                inlined = to_data_uri_for_reference(value, report_dir, cache, allowed_paths)
                if inlined and inlined != value:
                    obj[key] = inlined
                    replaced += 1
                    base, _ = split_reference(value)
                    replaced_paths.add(base)
            else:
                replaced += inline_paths_in_json(
                    value,
                    report_dir,
                    cache,
                    replaced_paths,
                    allowed_paths,
                )
        return replaced

    if isinstance(obj, list):
        for idx, value in enumerate(obj):
            if isinstance(value, str):
                inlined = to_data_uri_for_reference(value, report_dir, cache, allowed_paths)
                if inlined and inlined != value:
                    obj[idx] = inlined
                    replaced += 1
                    base, _ = split_reference(value)
                    replaced_paths.add(base)
            else:
                replaced += inline_paths_in_json(
                    value,
                    report_dir,
                    cache,
                    replaced_paths,
                    allowed_paths,
                )
        return replaced

    return replaced


def collect_media_paths(obj: Any, report_dir: Path, found_paths: dict[str, str]) -> None:
    if isinstance(obj, dict):
        for value in obj.values():
            collect_media_paths(value, report_dir, found_paths)
        return
    if isinstance(obj, list):
        for value in obj:
            collect_media_paths(value, report_dir, found_paths)
        return
    if not isinstance(obj, str) or obj.startswith("data:"):
        return

    base, _ = split_reference(obj)
    if "://" in base or base in found_paths:
        return

    mime_hint = media_mime_type(base)
    if not mime_hint:
        return

    resolved = resolve_reference_path(base, report_dir)

    mime = media_mime_type(resolved.name) or mime_hint
    if mime and resolved.exists() and resolved.is_file():
        found_paths[base] = mime


def count_media_references(obj: Any, counts: dict[str, int]) -> None:
    if isinstance(obj, dict):
        for value in obj.values():
            count_media_references(value, counts)
        return
    if isinstance(obj, list):
        for value in obj:
            count_media_references(value, counts)
        return
    if not isinstance(obj, str) or obj.startswith("data:"):
        return

    base, _ = split_reference(obj)
    counts[base] = counts.get(base, 0) + 1


def estimated_replacement_growth_bytes(
    base_path: str,
    mime: str,
    report_dir: Path,
    references_count: int,
) -> int:
    resolved = resolve_reference_path(base_path, report_dir)
    if not resolved.exists() or not resolved.is_file():
        return 0
    payload_size = resolved.stat().st_size
    base64_size = 4 * ((payload_size + 2) // 3)
    data_uri_size = len(f"data:{mime};base64,") + base64_size
    per_reference_growth = max(0, data_uri_size - len(base_path))
    return per_reference_growth * references_count


def build_zip_bytes(entries: dict[str, bytes]) -> bytes:
    output_buffer = io.BytesIO()
    with zipfile.ZipFile(output_buffer, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
        for name, data in entries.items():
            output_zip.writestr(name, data)
    return output_buffer.getvalue()


def projected_output_size(
    html: str,
    full_assignment: str,
    zip_bytes: bytes,
) -> int:
    new_value = encode_zip_data_uri(zip_bytes)
    replacement_assignment = build_report_assignment(new_value)
    return (
        len(html.encode("utf-8"))
        - len(full_assignment.encode("utf-8"))
        + len(replacement_assignment.encode("utf-8"))
    )


def inline_docs(
    docs: dict[str, Any],
    report_dir: Path,
    cache: dict[str, str | None],
    allowed_paths: set[str] | None,
    verbose: bool,
) -> tuple[dict[str, bytes], int, int]:
    entries: dict[str, bytes] = {}
    total_replacements = 0
    touched_json_files = 0

    for json_name, doc in docs.items():
        replaced_paths: set[str] = set()
        replacement_count = inline_paths_in_json(
            doc, report_dir, cache, replaced_paths, allowed_paths
        )
        if replacement_count:
            touched_json_files += 1
            total_replacements += replacement_count
            if verbose:
                print(f"[{json_name}] replaced {replacement_count} media reference(s)")
                for original in sorted(replaced_paths):
                    print(f"  - {original}")
        entries[json_name] = json.dumps(doc, separators=(",", ":")).encode("utf-8")

    return entries, touched_json_files, total_replacements


def process_zip_payload(
    zip_bytes: bytes,
    report_dir: Path,
    html: str,
    full_assignment: str,
    verbose: bool,
    max_output_mb: float | None,
) -> ProcessZipResult:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as input_zip:
        input_entries: dict[str, bytes] = {
            info.filename: input_zip.read(info.filename) for info in input_zip.infolist()
        }

    docs: dict[str, Any] = {}
    passthrough_entries: dict[str, bytes] = {}
    for name, data in input_entries.items():
        if not name.endswith(".json"):
            passthrough_entries[name] = data
            continue
        try:
            docs[name] = json.loads(data.decode("utf-8"))
        except Exception:
            passthrough_entries[name] = data

    media_paths: dict[str, str] = {}
    for doc in docs.values():
        collect_media_paths(doc, report_dir, media_paths)

    media_ref_counts: dict[str, int] = {}
    for doc in docs.values():
        count_media_references(doc, media_ref_counts)

    image_paths = [path for path, mime in media_paths.items() if mime.startswith("image/")]
    video_paths = [path for path, mime in media_paths.items() if mime.startswith("video/")]

    selected_paths = set(image_paths)
    cache: dict[str, str | None] = {}
    current_docs = copy.deepcopy(docs)
    current_json_entries, touched_json_files, total_replacements = inline_docs(
        current_docs, report_dir, cache, selected_paths, verbose
    )
    current_entries = {**passthrough_entries, **current_json_entries}
    current_zip = build_zip_bytes(current_entries)

    max_output_bytes = None if max_output_mb is None else int(max_output_mb * 1024 * 1024)
    included_videos = 0

    if max_output_bytes is not None:
        size_after_images = projected_output_size(html, full_assignment, current_zip)
        if size_after_images > max_output_bytes:
            print(
                "Warning: image-only output already exceeds max size; videos will be skipped.",
                file=sys.stderr,
            )
        else:
            headroom = max_output_bytes - size_after_images
            selected_video_paths: list[str] = []
            used_estimated_growth = 0
            for video_path in video_paths:
                mime = media_paths[video_path]
                ref_count = media_ref_counts.get(video_path, 1)
                growth = estimated_replacement_growth_bytes(video_path, mime, report_dir, ref_count)
                if used_estimated_growth + growth <= headroom:
                    selected_video_paths.append(video_path)
                    used_estimated_growth += growth

            if selected_video_paths:
                selected_paths = set(image_paths) | set(selected_video_paths)

                def _rebuild_for_selection() -> tuple[bytes, int, int]:
                    docs_copy = copy.deepcopy(docs)
                    json_entries, touched, replacements = inline_docs(
                        docs_copy,
                        report_dir,
                        {},
                        selected_paths,
                        False,
                    )
                    entries = {**passthrough_entries, **json_entries}
                    return build_zip_bytes(entries), touched, replacements

                current_zip, touched_json_files, total_replacements = _rebuild_for_selection()

                while (
                    selected_video_paths
                    and projected_output_size(html, full_assignment, current_zip) > max_output_bytes
                ):
                    removed = selected_video_paths.pop()
                    selected_paths.remove(removed)
                    current_zip, touched_json_files, total_replacements = _rebuild_for_selection()
                    if verbose:
                        print(f"[trim] removed {removed} to fit max output size")

                included_videos = len(selected_video_paths)
    else:
        selected_paths = set(media_paths.keys())
        current_docs = copy.deepcopy(docs)
        cache = {}
        current_json_entries, touched_json_files, total_replacements = inline_docs(
            current_docs, report_dir, cache, selected_paths, verbose
        )
        current_entries = {**passthrough_entries, **current_json_entries}
        current_zip = build_zip_bytes(current_entries)
        included_videos = len(video_paths)

    return ProcessZipResult(
        zip_bytes=current_zip,
        touched_json_files=touched_json_files,
        total_replacements=total_replacements,
        total_images=len(image_paths),
        inlined_videos=included_videos,
        total_videos=len(video_paths),
    )


def main() -> int:
    args = parse_args()
    report_dir = args.report_dir
    input_path = report_dir / "index.html"
    output_path = args.output or report_dir / "output.html"

    if not report_dir.exists() or not report_dir.is_dir():
        print(f"Report directory not found: {report_dir}", file=sys.stderr)
        return 1

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    html = input_path.read_text(encoding="utf-8")

    try:
        full_assignment, encoded_value = extract_data_uri_from_html(html)
        zip_bytes = split_data_uri(encoded_value)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    result = process_zip_payload(
        zip_bytes,
        input_path.parent,
        html,
        full_assignment,
        args.verbose,
        args.max_output_mb,
    )

    new_value = encode_zip_data_uri(result.zip_bytes)
    replacement_assignment = build_report_assignment(new_value)
    updated_html = html.replace(full_assignment, replacement_assignment, 1)
    output_path.write_text(updated_html, encoding="utf-8")

    print(f"Wrote: {output_path}")
    print(f"JSON files updated: {result.touched_json_files}")
    print(f"Media references inlined: {result.total_replacements}")
    print(f"Images inlined: {result.total_images}/{result.total_images}")
    print(f"Videos inlined: {result.inlined_videos}/{result.total_videos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
