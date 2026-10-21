"""Outgoing WhatsApp / SMS messages. Everything that messages a family calls ``send_message``;
only this module knows the provider. Every message is logged with its category; service
messages a family has turned off are logged as skipped and not sent.

- "console": development and tests. Messages are logged and the last few are kept in memory so
  the portal can show the test sign-in code. Never used to reach real families."""

import logging
from collections import deque

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import MessageCategory, MessageLog, MessageStatus

log = logging.getLogger("dojo.messaging")
_outbox: deque[dict] = deque(maxlen=50)


async def service_messages_on(db: AsyncSession, mobile: str) -> bool:
    # Families can turn service messages off from the portal (phase 5); on until then.
    return True


async def send_message(
    db: AsyncSession,
    to: str,
    text: str,
    *,
    category: MessageCategory = MessageCategory.ESSENTIAL,
    kind: str = "",
    member_id: int | None = None,
    channel: str = "whatsapp",
) -> bool:
    """Send (or skip) a message and add it to the caller's transaction's message log."""

    def logged(status: MessageStatus, error: str | None = None) -> None:
        db.add(
            MessageLog(
                to=to,
                channel=channel,
                category=category,
                kind=kind[:40],
                text=text,
                member_id=member_id,
                status=status,
                error=error,
            )
        )

    if category == MessageCategory.SERVICE and not await service_messages_on(db, to):
        logged(MessageStatus.SKIPPED)
        return False
    if get_settings().messaging_backend == "console":
        _outbox.appendleft({"to": to, "text": text, "channel": channel, "kind": kind})
        log.info("[%s to %s] %s", channel, to, text)
        logged(MessageStatus.SENT)
        return True
    logged(MessageStatus.FAILED, "Messaging backend not configured")
    return False


def last_message_to(to: str, kind: str | None = None) -> dict | None:
    """The newest console message to ``to`` (development only)."""
    for message in _outbox:
        if message["to"] == to and (kind is None or message["kind"] == kind):
            return message
    return None


def clear_outbox() -> None:
    _outbox.clear()
