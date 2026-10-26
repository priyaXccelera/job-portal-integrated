"""Small assertion helpers shared by the test modules (envelope checks)."""

from __future__ import annotations

from typing import Any

import httpx


def assert_ok(resp: httpx.Response, status: int = 200) -> dict[str, Any]:
    """Assert a success envelope ``{success: true, data: ...}`` and return the parsed body."""
    assert resp.status_code == status, f"expected {status}, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["success"] is True, body
    assert "data" in body, body
    assert "error" not in body, body
    return body


def assert_paged(resp: httpx.Response, status: int = 200) -> dict[str, Any]:
    """Assert a paged envelope ``{success, data: [...], meta: {page, pageSize, total}}``."""
    body = assert_ok(resp, status)
    assert isinstance(body["data"], list), body
    meta = body["meta"]
    assert {"page", "pageSize", "total"} <= set(meta), meta
    return body


def assert_error(resp: httpx.Response, status: int, code: str | None = None) -> dict[str, Any]:
    """Assert the shared error envelope and return the ``error`` object."""
    assert resp.status_code == status, f"expected {status}, got {resp.status_code}: {resp.text}"
    assert resp.headers["content-type"].startswith("application/json"), resp.headers
    body = resp.json()
    assert body["success"] is False, body
    error = body["error"]
    assert isinstance(error["code"], str) and error["code"], error
    assert isinstance(error["message"], str) and error["message"], error
    assert isinstance(error["details"], list), error
    if code is not None:
        assert error["code"] == code, error
    return error
