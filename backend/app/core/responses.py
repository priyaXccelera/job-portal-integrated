"""Success envelope helpers, JSON encoding, pagination and CSV export."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.config import settings


def format_datetime(value: datetime) -> str:
    """UTC ISO-8601 with trailing 'Z'; naive datetimes are treated as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def to_jsonable(obj: Any) -> Any:
    """Recursively convert Python values into JSON-safe primitives."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, Enum):
        return to_jsonable(obj.value)
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return obj if obj == obj and obj not in (float("inf"), float("-inf")) else None
    if isinstance(obj, datetime):
        return format_datetime(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            return None
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, BaseModel):
        return to_jsonable(obj.model_dump(by_alias=True))
    if isinstance(obj, dict):
        return {str(to_jsonable(k)): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def ok(data: Any = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": True, "data": to_jsonable(data)})


def paged(
    items: Iterable[Any],
    page: int,
    page_size: int,
    total: int,
    facets: dict[str, Any] | None = None,
) -> JSONResponse:
    meta: dict[str, Any] = {"page": page, "pageSize": page_size, "total": total}
    if facets is not None:
        meta["facets"] = to_jsonable(facets)
    return JSONResponse(
        status_code=200,
        content={"success": True, "data": to_jsonable(list(items)), "meta": meta},
    )


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(
        settings.default_page_size, ge=1, alias="pageSize", description="Items per page (capped server-side)"
    ),
) -> PageParams:
    return PageParams(page=page, page_size=min(page_size, settings.max_page_size))


def paginate(db: Session, stmt: Select[Any], params: PageParams) -> tuple[list[Any], int]:
    """Run a DB-level count + LIMIT/OFFSET page of ``stmt``.

    Single-entity / single-column selects return scalars, otherwise Row objects.
    """
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())
    page_stmt = stmt.limit(params.page_size).offset(params.offset)
    if len(stmt.column_descriptions) == 1:
        rows = list(db.scalars(page_stmt).all())
    else:
        rows = list(db.execute(page_stmt).all())
    return rows, total


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    value = to_jsonable(value) if not isinstance(value, str) else value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value  # neutralise spreadsheet formula injection
    return value


def csv_response(filename: str, header: list[str], rows: Iterable[list[Any]]) -> StreamingResponse:
    def generate() -> Iterator[str]:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        yield buf.getvalue()
        for row in rows:
            buf.seek(0)
            buf.truncate(0)
            writer.writerow([_csv_cell(v) for v in row])
            yield buf.getvalue()

    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or "export.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
