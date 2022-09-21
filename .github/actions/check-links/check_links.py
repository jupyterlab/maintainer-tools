import os
import os.path as osp
import sys
from glob import glob
import subprocess
import shlex
import typing as t


def log(*outputs, **kwargs):
    """Log an output to stderr"""
    kwargs.setdefault("file", sys.stderr)
    print(*outputs, **kwargs)


def check_links(ignore_glob, ignore_links, links_expire):
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
        ignored.extend(glob(spec, recursive=True))

    ignore_links = list(ignore_links) + [
        "https://github.com/.*/(pull|issues)/.*",
        "https://github.com/search?",
        "http://localhost.*",
        # https://github.com/github/feedback/discussions/14773
        "https://docs.github.com/.*",
    ]

    for spec in ignore_links:
        cmd += f' --check-links-ignore "{spec}"'

    cmd += " --ignore-glob node_modules"

    # Gather all of the markdown, RST, and ipynb files
    files: t.List[str] = []
    for ext in [".md", ".rst", ".ipynb"]:
        matched = glob(f"**/*{ext}", recursive=True)
        files.extend(m for m in matched if m not in ignored and "node_modules" not in m)

    log("Checking files with options:")
    log(cmd)

    fails = 0
    separator = f"\n\n{'-' * 80}\n"
    for f in files:
        file_cmd = cmd + f' "{f}"'
        file_cmd = shlex.split(file_cmd)
        try:
            log(f"{separator}{f}...")
            subprocess.check_output(file_cmd, shell=False)
        except Exception as e:
            # Return code 5 means no tests were run (no links found)
            if e.returncode != 5:  # type:ignore[attr-defined]
                try:
                    log(f"\n{f} (second attempt)...\n")
                    subprocess.check_output(file_cmd + ["--lf"], shell=False)
                except Exception:
                    fails += 1
                    if fails == 3:
                        raise RuntimeError("Found three failed links, bailing")
    if fails:
        raise RuntimeError(f"Encountered failures in {fails} file(s)")


if __name__ == '__main__':
    ignore_glob = os.environ.get('IGNORE_GLOB', '')
    ignore_glob = ignore_glob.split(' ')
    ignore_links = os.environ.get('IGNORE_LINKS', '')
    ignore_links = ignore_links.split(' ')
    links_expire = os.environ.get('LINKS_EXPIRE', '604800')
    check_links(ignore_glob, ignore_links, links_expire)

