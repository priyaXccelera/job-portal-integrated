"""Pluggable email / OTP delivery. The default ``log`` senders only write to the application log.

Dev note: OTP codes and email bodies (verification / reset links) are logged by design so the
flows can be exercised without a real provider. Never pass passwords to these senders.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol, runtime_checkable

from app.config import settings

logger = logging.getLogger(__name__)


class SenderError(Exception):
    """Raised by a sender when delivery fails."""


@runtime_checkable
class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


@runtime_checkable
class OtpSender(Protocol):
    def send(self, mobile: str, code: str) -> None: ...


class LogEmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        logger.info("[email] to=%s subject=%r body=%s", to, subject, body)


class LogOtpSender:
    def send(self, mobile: str, code: str) -> None:
        logger.info("[otp] mobile=%s code=%s", mobile, code)


EMAIL_SENDERS: dict[str, Callable[[], EmailSender]] = {"log": LogEmailSender}
OTP_SENDERS: dict[str, Callable[[], OtpSender]] = {"log": LogOtpSender}


@lru_cache(maxsize=None)
def _email_sender(kind: str) -> EmailSender:
    try:
        return EMAIL_SENDERS[kind]()
    except KeyError as exc:
        raise ValueError(f"Unknown EMAIL_SENDER {kind!r}; available: {sorted(EMAIL_SENDERS)}") from exc


@lru_cache(maxsize=None)
def _otp_sender(kind: str) -> OtpSender:
    try:
        return OTP_SENDERS[kind]()
    except KeyError as exc:
        raise ValueError(f"Unknown OTP_SENDER {kind!r}; available: {sorted(OTP_SENDERS)}") from exc


def get_email_sender() -> EmailSender:
    return _email_sender(settings.email_sender.strip().lower())


def get_otp_sender() -> OtpSender:
    return _otp_sender(settings.otp_sender.strip().lower())
