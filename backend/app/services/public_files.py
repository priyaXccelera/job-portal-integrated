"""Safe resolution of publicly served uploaded images (logos, banners, photos)."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from app.config import settings
from app.core.errors import NotFoundError

logger = logging.getLogger(__name__)

PUBLIC_KINDS = frozenset({"logos", "banners", "photos"})


def resolve_public_file(kind: str, filename: str) -> tuple[Path, str]:
    """Return (path, media_type) for a public image or raise NotFoundError.

    ``filename`` must be a plain file name; anything that could escape
    ``<upload_dir>/<kind>`` is rejected as not found.
    """
    if kind not in PUBLIC_KINDS:
        raise NotFoundError("File not found")
    if (
        not filename
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or Path(filename).name != filename
    ):
        raise NotFoundError("File not found")

    base = (Path(settings.upload_dir) / kind).resolve()
    candidate = (base / filename).resolve()
    if candidate.parent != base or not candidate.is_file():
        raise NotFoundError("File not found")

    media_type, _ = mimetypes.guess_type(candidate.name)
    if media_type is None or not media_type.startswith("image/"):
        logger.warning("Refusing to serve non-image public file %s/%s", kind, filename)
        raise NotFoundError("File not found")
    return candidate, media_type
