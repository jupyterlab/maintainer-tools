# ruff: noqa: S101
from __future__ import annotations

import importlib.util
import sys
import typing as t
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
ACTION_PATH = ROOT / ".github" / "actions" / "check-links"


def load_module(name: str, path: Path) -> t.Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_links = load_module("check_links", ACTION_PATH / "check_links.py")
runtime = load_module("check_links_runtime", ACTION_PATH / "check_links_runtime.py")


def test_build_base_command_uses_runtime_plugin() -> None:
    cmd, ignored = check_links.build_base_command(["docs/api"], ["https://example.test"], "30")

    assert ignored == []
    assert "--check-links-cache-expire-after" in cmd
    assert cmd[cmd.index("--check-links-cache-expire-after") + 1] == "30"
    assert cmd[cmd.index("-p") + 1] == "no:doctest"
    assert "check_links_runtime" in cmd
    assert "https://example.test" in cmd
    assert "https://github.com/.*/(pull|issues)/.*" in cmd
    assert "node_modules" in cmd


def test_build_pytest_env_sets_runtime_controls() -> None:
    env = check_links.build_pytest_env(
        "7",
        "429 503",
        "true",
        base_env={"PYTHONPATH": "existing"},
    )

    assert env["CHECK_LINKS_REQUEST_TIMEOUT"] == "7"
    assert env["CHECK_LINKS_TRANSIENT_STATUS_CODES"] == "429 503"
    assert env["CHECK_LINKS_FAIL_ON_TRANSIENT"] == "true"
    assert env["PYTHONPATH"].startswith(str(ACTION_PATH))
    assert env["PYTHONPATH"].endswith("existing")


def test_parse_status_codes_accepts_lists_and_ranges() -> None:
    assert runtime.parse_status_codes("408, 429 500-502", ()) == {
        408,
        429,
        500,
        501,
        502,
    }


def test_parse_status_codes_rejects_invalid_codes() -> None:
    with pytest.raises(ValueError, match="Invalid HTTP status"):
        runtime.parse_status_codes("99", ())


class CachedResponse:
    def __init__(self, status_code: int, cache_key: str) -> None:
        self.status_code = status_code
        self.cache_key = cache_key


class Cache:
    def __init__(self) -> None:
        self.responses = [
            CachedResponse(200, "ok"),
            CachedResponse(302, "redirect"),
            CachedResponse(403, "forbidden"),
            CachedResponse(429, "rate-limit"),
            CachedResponse(503, "unavailable"),
        ]
        self.deleted: list[str] = []

    def filter(self) -> t.Iterator[CachedResponse]:
        yield from self.responses

    def delete(self, *keys: str) -> None:
        self.deleted.extend(keys)


class Settings:
    allowable_codes: tuple[int, ...] = ()


class Session:
    def __init__(self) -> None:
        self.settings = Settings()
        self.cache = Cache()
        self.request_kwargs: dict[str, object] = {}

    def request(self, *_args: object, **kwargs: object) -> dict[str, object]:
        self.request_kwargs = kwargs
        return kwargs


def test_configure_session_sets_timeout_and_purges_failed_cache() -> None:
    session = Session()
    settings = runtime.RuntimeSettings(
        request_timeout=12,
        transient_status_codes={429, 503},
        fail_on_transient=False,
    )

    runtime.configure_session(session, settings)

    assert session.settings.allowable_codes == tuple(range(200, 400))
    assert session.cache.deleted == ["forbidden", "rate-limit", "unavailable"]
    assert session.request("GET", "https://example.test")["timeout"] == 12
    assert session.request("GET", "https://example.test", timeout=3)["timeout"] == 3


def test_transient_failures_skip_by_default() -> None:
    settings = runtime.RuntimeSettings(
        request_timeout=12,
        transient_status_codes={429},
        fail_on_transient=False,
    )

    with pytest.raises(pytest.skip.Exception, match="transient link check failure"):
        runtime.handle_transient_failure("https://example.test", "429: Too Many Requests", settings)
