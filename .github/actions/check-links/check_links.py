from __future__ import annotations

import os
import shlex
import subprocess
import sys
import typing as t
from glob import glob


def log(*outputs: str, **kwargs: t.Any) -> None:
    """Log an output to stderr"""
    kwargs.setdefault("file", sys.stderr)
    print(*outputs, **kwargs)


def check_links(ignore_glob: list[str], ignore_links: list[str], links_expire: str) -> None:
    """Check URLs for HTML-containing files."""
    python = sys.executable.replace(os.sep, "/")
    cmd = f"{python} -m pytest --noconftest --check-links --check-links-cache "
    cmd += f"--check-links-cache-expire-after {links_expire} "
    cmd += "-raXs --color yes --quiet "
    # do not run doctests, since they might depend on other state.
    cmd += "-p no:doctest "
    # ignore package pytest configuration,
    # since we aren't running their tests
    cmd += "-c _IGNORE_CONFIG"

    ignored = []
    for spec in ignore_glob:
        cmd += f' --ignore-glob "{spec}"'
        ignored.extend(glob(spec, recursive=True))  # noqa: PTH207

    ignore_links = [
        *list(ignore_links),
        "https://github.com/.*/(pull|issues)/.*",
        "https://github.com/search?",
        "https://github.com/[^/]*$",
        "http://localhost.*",
        # https://github.com/github/feedback/discussions/14773
        "https://docs.github.com/.*",
        "https://npmjs.com(/.*)?",
    ]

    for spec in ignore_links:
        cmd += f' --check-links-ignore "{spec}"'

    cmd += " --ignore-glob node_modules"

    # Gather all of the markdown, RST, and ipynb files
    files: list[str] = []
    for ext in [".md", ".rst", ".ipynb"]:
        matched = glob(f"**/*{ext}", recursive=True)  # noqa: PTH207
        files.extend(m for m in matched if m not in ignored and "node_modules" not in m)

    separator = f"\n\n{'-' * 80}\n"
    log(f"{separator}Checking files with command:")
    log(cmd)

    fails = 0
    for f in files:
        file_cmd_str = cmd + f' "{f}"'
        file_cmd = shlex.split(file_cmd_str)
        try:
            log(f"{separator}{f}...")
            subprocess.check_output(file_cmd, shell=False)  # noqa: S603
        except Exception as e:
            # Return code 5 means no tests were run (no links found)
            if e.returncode != 5:  # type:ignore[attr-defined]
                try:
                    log(f"\n{f} (second attempt)...\n")
                    subprocess.check_output([*file_cmd, "--lf"], shell=False)  # noqa: S603
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
    links_expire = os.environ.get("LINKS_EXPIRE") or "604800"
    check_links(ignore_glob, ignore_links, links_expire)
