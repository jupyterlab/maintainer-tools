from __future__ import annotations

import os
import shlex
import subprocess
import sys
import typing as t
from glob import glob
from pathlib import Path

ACTION_PATH = Path(__file__).resolve().parent
DEFAULT_LINKS_EXPIRE = "604800"
DEFAULT_REQUEST_TIMEOUT = "20"
DEFAULT_TRANSIENT_STATUS_CODES = "408 429 500 502 503 504"
DEFAULT_FAIL_ON_TRANSIENT = "false"


def log(*outputs: str, **kwargs: t.Any) -> None:
    """Log an output to stderr"""
    kwargs.setdefault("file", sys.stderr)
    print(*outputs, **kwargs)


def build_pytest_env(
    request_timeout: str,
    transient_status_codes: str,
    fail_on_transient: str,
    *,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the pytest subprocess environment."""
    env = dict(base_env or os.environ)
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(ACTION_PATH) if not pythonpath else f"{ACTION_PATH}{os.pathsep}{pythonpath}"
    )
    env["CHECK_LINKS_REQUEST_TIMEOUT"] = request_timeout
    env["CHECK_LINKS_TRANSIENT_STATUS_CODES"] = transient_status_codes
    env["CHECK_LINKS_FAIL_ON_TRANSIENT"] = fail_on_transient
    return env


def build_base_command(
    ignore_glob: list[str],
    ignore_links: list[str],
    links_expire: str,
) -> tuple[list[str], list[str]]:
    """Build the base pytest command and return ignored files."""
    python = sys.executable.replace(os.sep, "/")
    cmd = [
        python,
        "-m",
        "pytest",
        "--noconftest",
        "--check-links",
        "--check-links-cache",
        "--check-links-cache-expire-after",
        links_expire,
        "-raXs",
        "--color",
        "yes",
        "--quiet",
        # do not run doctests, since they might depend on other state.
        "-p",
        "no:doctest",
        "-p",
        "check_links_runtime",
        # ignore package pytest configuration,
        # since we aren't running their tests
        "-c",
        "_IGNORE_CONFIG",
    ]

    ignored = []
    for spec in ignore_glob:
        cmd.extend(["--ignore-glob", spec])
        ignored.extend(glob(spec, recursive=True))  # noqa: PTH207

    ignore_links = [
        *list(ignore_links),
        "https://github.com/.*/(pull|issues)/.*",
        "https://github.com/search?",
        "https://github.com/[^/]*$",
        "http://localhost.*",
        # https://github.com/github/feedback/discussions/14773
        "https://docs.github.com/.*",
        "https://(www\\.)?npmjs.com(/.*)?",
    ]

    for spec in ignore_links:
        cmd.extend(["--check-links-ignore", spec])

    cmd.extend(["--ignore-glob", "node_modules"])
    return cmd, ignored


def check_links(
    ignore_glob: list[str],
    ignore_links: list[str],
    links_expire: str,
    request_timeout: str,
    transient_status_codes: str,
    fail_on_transient: str,
) -> None:
    """Check URLs for HTML-containing files."""
    cmd, ignored = build_base_command(ignore_glob, ignore_links, links_expire)
    env = build_pytest_env(request_timeout, transient_status_codes, fail_on_transient)

    # Gather all of the markdown, RST, and ipynb files
    files: list[str] = []
    for ext in [".md", ".rst", ".ipynb"]:
        matched = glob(f"**/*{ext}", recursive=True)  # noqa: PTH207
        files.extend(m for m in matched if m not in ignored and "node_modules" not in m)

    separator = f"\n\n{'-' * 80}\n"
    log(f"{separator}Checking files with command:")
    log(shlex.join(cmd))

    fails = 0
    for f in files:
        file_cmd = [*cmd, f]
        try:
            log(f"{separator}{f}...")
            subprocess.check_output(file_cmd, shell=False, env=env)  # noqa: S603
        except Exception as e:
            # Return code 5 means no tests were run (no links found)
            if e.returncode != 5:  # type:ignore[attr-defined]
                try:
                    log(f"\n{f} (second attempt)...\n")
                    subprocess.check_output([*file_cmd, "--lf"], shell=False, env=env)  # noqa: S603
                except subprocess.CalledProcessError as e:
                    log(e.output.decode("utf-8"))
                    fails += 1
                    if fails == 3:
                        msg = "Found three failed links, bailing"
                        raise RuntimeError(msg) from e
    if fails:
        msg = f"Encountered failures in {fails} file(s)"
        raise RuntimeError(msg)


if __name__ == "__main__":
    ignore_glob_str = os.environ.get("IGNORE_GLOB", "")
    ignore_glob = ignore_glob_str.strip().split(" ") if ignore_glob_str else []
    ignore_links_str = os.environ.get("IGNORE_LINKS", "")
    ignore_links = ignore_links_str.split(" ") if ignore_links_str else []
    links_expire = os.environ.get("LINKS_EXPIRE") or DEFAULT_LINKS_EXPIRE
    request_timeout = os.environ.get("REQUEST_TIMEOUT") or DEFAULT_REQUEST_TIMEOUT
    transient_status_codes = (
        os.environ.get("TRANSIENT_STATUS_CODES") or DEFAULT_TRANSIENT_STATUS_CODES
    )
    fail_on_transient = os.environ.get("FAIL_ON_TRANSIENT") or DEFAULT_FAIL_ON_TRANSIENT
    check_links(
        ignore_glob,
        ignore_links,
        links_expire,
        request_timeout,
        transient_status_codes,
        fail_on_transient,
    )
