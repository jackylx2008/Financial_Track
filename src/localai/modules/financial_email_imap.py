from __future__ import annotations

import imaplib
import logging
import time
from datetime import datetime
from typing import Any

from localai.modules.financial_email_config import FinancialEmailConfig


logger = logging.getLogger(__name__)

PROGRESS_LOG_INTERVAL_SEC = 10
PROGRESS_LOG_EVERY_MESSAGES = 20


class FinancialEmailImapClient:
    def __init__(self, config: FinancialEmailConfig) -> None:
        self.config = config
        self._client: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> "FinancialEmailImapClient":
        logger.info("Connecting to IMAP host=%s port=%s user=%s", self.config.host, self.config.port, self.config.user)
        self._client = imaplib.IMAP4_SSL(self.config.host, self.config.port, timeout=30)
        self._client.login(self.config.user, self.config.password)
        self._send_client_id()
        self._select_mailbox()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._client is None:
            return
        try:
            self._client.close()
        except imaplib.IMAP4.error:
            pass
        self._client.logout()

    def fetch_messages(self) -> list[dict[str, Any]]:
        client = self._require_client()
        criteria = self._build_search_criteria()
        logger.info("Searching IMAP mailbox=%s criteria=%s", self.config.mailbox, criteria)
        status, payload = client.uid("search", None, *criteria)
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status} {payload!r}")

        uid_blob = payload[0] if payload else b""
        uids = list(reversed(uid_blob.split()))
        if self.config.max_messages:
            uids = uids[: self.config.max_messages]

        logger.info("IMAP search returned %s messages to fetch after max_messages limit.", len(uids))
        messages: list[dict[str, Any]] = []
        started_at = time.monotonic()
        last_progress_at = started_at
        for uid in uids:
            index = len(messages) + 1
            status, fetched = client.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not fetched:
                logger.warning("Skipping IMAP uid=%s fetch status=%s", uid.decode("ascii", errors="ignore"), status)
                continue
            raw_bytes = _extract_rfc822_bytes(fetched)
            if raw_bytes is None:
                logger.warning("Skipping IMAP uid=%s because RFC822 body was not returned", uid)
                continue
            messages.append({"uid": uid.decode("ascii", errors="ignore"), "raw_bytes": raw_bytes})
            now = time.monotonic()
            if _should_log_progress(len(messages), now, last_progress_at, len(uids)):
                last_progress_at = now
                logger.info(
                    "Fetched IMAP messages %s/%s elapsed=%.1fs last_uid=%s",
                    len(messages),
                    len(uids),
                    now - started_at,
                    uid.decode("ascii", errors="ignore"),
                )
        logger.info("Finished fetching IMAP messages: fetched=%s expected=%s elapsed=%.1fs", len(messages), len(uids), time.monotonic() - started_at)
        return messages

    def _select_mailbox(self) -> None:
        client = self._require_client()
        status, payload = client.select(self.config.mailbox, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Unable to select IMAP mailbox {self.config.mailbox!r}: {payload!r}")

    def _send_client_id(self) -> None:
        client = self._require_client()
        imaplib.Commands["ID"] = ("AUTH", "SELECTED")
        payload = _format_id_payload(self.config.client_id)
        logger.info("Sending IMAP ID command for provider compatibility: %s", payload)
        status, response = client._simple_command("ID", payload)
        if status != "OK":
            logger.warning("IMAP ID command was not accepted: status=%s response=%s", status, response)

    def _build_search_criteria(self) -> list[str]:
        criteria = ["SINCE", _imap_date(self.config.since)]
        if self.config.before:
            criteria.extend(["BEFORE", _imap_date(self.config.before)])
        return criteria

    def _require_client(self) -> imaplib.IMAP4_SSL:
        if self._client is None:
            raise RuntimeError("IMAP client is not connected.")
        return self._client


def _extract_rfc822_bytes(fetched: list[Any]) -> bytes | None:
    for item in fetched:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _should_log_progress(done: int, now: float, last_progress_at: float, total: int) -> bool:
    return (
        done == 1
        or done == total
        or done % PROGRESS_LOG_EVERY_MESSAGES == 0
        or now - last_progress_at >= PROGRESS_LOG_INTERVAL_SEC
    )


def _imap_date(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{parsed.day:02d}-{months[parsed.month - 1]}-{parsed.year:04d}"


def _format_id_payload(client_id: dict[str, str]) -> str:
    items: list[str] = []
    for key, value in client_id.items():
        items.append(f'"{_escape_id_value(key)}" "{_escape_id_value(value)}"')
    return "(" + " ".join(items) + ")"


def _escape_id_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
