from __future__ import annotations

import os
import sys
import typing as t
from dataclasses import dataclass
from functools import wraps

import pytest
import pytest_check_links.plugin as plugin
from pytest_check_links.plugin import BrokenLinkError
from requests import exceptions as requests_exceptions

DEFAULT_REQUEST_TIMEOUT = "20"
DEFAULT_TRANSIENT_STATUS_CODES = "408 429 503 504"
CACHEABLE_STATUS_CODES = tuple(range(200, 400))
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RuntimeSettings:
    """Runtime controls for external link checks."""

    request_timeout: float | None
    transient_status_codes: set[int]
    fail_on_transient: bool
    cacheable_status_codes: tuple[int, ...] = CACHEABLE_STATUS_CODES


def parse_status_codes(spec: str, default: t.Iterable[int]) -> set[int]:
    """Parse space/comma-separated status codes and ranges."""
    if not spec.strip():
        return set(default)

    codes: set[int] = set()
    for token in spec.replace(",", " ").split():
        if "-" in token:
            start, end = [int(part) for part in token.split("-", 1)]
            if start > end:
                msg = f"Invalid HTTP status range: {token}"
                raise ValueError(msg)
            codes.update(range(start, end + 1))
        else:
            codes.add(int(token))

    invalid = [code for code in codes if code < 100 or code > 599]
    if invalid:
        msg = f"Invalid HTTP status code(s): {invalid}"
        raise ValueError(msg)
    return codes


def parse_bool(value: str) -> bool:
    """Parse a GitHub Action boolean input."""
    return value.strip().lower() in TRUE_VALUES


def parse_timeout(value: str) -> float | None:
    """Parse the request timeout."""
    value = value.strip()
    if not value:
        return None
    timeout = float(value)
    if timeout <= 0:
        msg = "request_timeout must be greater than 0"
        raise ValueError(msg)
    return timeout


def get_runtime_settings() -> RuntimeSettings:
    """Read runtime controls from the environment."""
    return RuntimeSettings(
        request_timeout=parse_timeout(
            os.environ.get("CHECK_LINKS_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)
        ),
        transient_status_codes=parse_status_codes(
            os.environ.get("CHECK_LINKS_TRANSIENT_STATUS_CODES", DEFAULT_TRANSIENT_STATUS_CODES),
            parse_status_codes(DEFAULT_TRANSIENT_STATUS_CODES, ()),
        ),
        fail_on_transient=parse_bool(os.environ.get("CHECK_LINKS_FAIL_ON_TRANSIENT", "false")),
    )


def configure_session(session: t.Any, settings: RuntimeSettings) -> t.Any:
    """Configure a pytest-check-links requests session."""
    if getattr(session, "_maintainer_tools_configured", False):
        return session

    if hasattr(session, "settings"):
        session.settings.allowable_codes = settings.cacheable_status_codes

    purged = purge_disallowed_cache(session, settings.cacheable_status_codes)
    if purged:
        print(f"Purged {purged} failed link response(s) from cache", file=sys.stderr)

    original_request = session.request

    @wraps(original_request)
    def request_with_timeout(*args: t.Any, **kwargs: t.Any) -> t.Any:
        if settings.request_timeout is not None and kwargs.get("timeout") is None:
            kwargs["timeout"] = settings.request_timeout
        return original_request(*args, **kwargs)

    session.request = request_with_timeout
    session._maintainer_tools_configured = True
    return session


def purge_disallowed_cache(session: t.Any, cacheable_status_codes: t.Iterable[int]) -> int:
    """Remove previously cached responses that should not be cached."""
    cache = getattr(session, "cache", None)
    if cache is None or not hasattr(cache, "filter"):
        return 0

    allowed = set(cacheable_status_codes)
    keys: list[str] = []
    for response in cache.filter():
        status_code = getattr(response, "status_code", None)
        if status_code in allowed:
            continue

        key = getattr(response, "cache_key", None)
        request = getattr(response, "request", None)
        if key is None and request is not None and hasattr(cache, "create_key"):
            key = cache.create_key(request)
        if key is not None:
            keys.append(key)

    if keys:
        cache.delete(*keys)
    return len(keys)


def handle_transient_failure(url: str, error: str, settings: RuntimeSettings) -> t.NoReturn:
    """Fail or skip a transient link check."""
    message = f"transient link check failure: {error}"
    if settings.fail_on_transient:
        raise BrokenLinkError(url, message)
    pytest.skip(f"{message} for {url}")


def fetch_with_retries(self: t.Any, url: str, retries: int = 3) -> t.Any:
    """Fetch a URL, treating configured transient failures separately."""
    settings = get_runtime_settings()
    url_no_anchor = url.split("#", maxsplit=1)[0]
    session = self.parent.requests_session
    if session is None:
        msg = "No session!"
        raise RuntimeError(msg)

    try:
        response = session.get(url_no_anchor)
    except requests_exceptions.Timeout as err:
        handle_transient_failure(url, f"timeout: {err}", settings)
    except Exception as err:
        if hasattr(err, "headers") and retries and self.sleep(err.headers):
            self.uncache_url(url_no_anchor)
            return self.fetch_with_retries(url, retries=retries - 1)

        raise BrokenLinkError(url, str(err)) from err

    if response.status_code >= 400:
        if retries and self.sleep(response.headers):
            self.uncache_url(url_no_anchor)
            return self.fetch_with_retries(url, retries=retries - 1)

        self.uncache_url(url_no_anchor)
        error = f"{response.status_code}: {response.reason}"
        if response.status_code in settings.transient_status_codes:
            handle_transient_failure(url, error, settings)
        raise BrokenLinkError(url, error)

    return response


def pytest_configure(config: pytest.Config) -> None:
    """Patch pytest-check-links for deterministic CI behavior."""
    _ = config
    try:
        settings = get_runtime_settings()
    except ValueError as err:
        raise pytest.UsageError(str(err)) from err

    original_ensure = getattr(
        plugin,
        "_maintainer_tools_original_ensure_requests_session",
        plugin.ensure_requests_session,
    )
    plugin._maintainer_tools_original_ensure_requests_session = original_ensure

    def ensure_requests_session(config: pytest.Config) -> t.Any:
        session = original_ensure(config)
        return configure_session(session, settings)

    plugin.ensure_requests_session = ensure_requests_session
    if not hasattr(plugin.LinkItem, "_maintainer_tools_original_fetch_with_retries"):
        plugin.LinkItem._maintainer_tools_original_fetch_with_retries = (
            plugin.LinkItem.fetch_with_retries
        )
    plugin.LinkItem.fetch_with_retries = fetch_with_retries
