"""Webhook delivery outbox repository."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import WebhookDeliveryStatus
from app.db.models.webhook_delivery import WebhookDelivery


class WebhookDeliveryRepository:
    """Data access for webhook delivery outbox records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        payment_id: uuid.UUID,
        url: str,
        payload: dict[str, Any],
        next_attempt_at: datetime,
    ) -> None:
        """Insert a pending webhook delivery or ignore duplicate payment_id.

        Args:
            payment_id: Payment UUID to notify about.
            url: Client webhook URL.
            payload: Serialized webhook body.
            next_attempt_at: Earliest time the dispatcher may deliver.
        """
        stmt = (
            insert(WebhookDelivery)
            .values(
                payment_id=payment_id,
                url=url,
                payload=payload,
                status=WebhookDeliveryStatus.PENDING,
                attempts=0,
                next_attempt_at=next_attempt_at,
            )
            .on_conflict_do_nothing(index_elements=["payment_id"])
        )
        await self._session.execute(stmt)

    async def get_due_batch(
        self,
        *,
        limit: int,
        now: datetime,
    ) -> list[WebhookDelivery]:
        """Fetch due pending deliveries with row-level lock.

        Args:
            limit: Maximum number of records to return.
            now: Current timestamp for due-time comparison.

        Returns:
            Due pending webhook deliveries ordered by next_attempt_at.
        """
        stmt = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_delivered(
        self,
        delivery_id: uuid.UUID,
        *,
        processed_at: datetime,
        status_code: int,
    ) -> None:
        """Mark webhook delivery as successfully delivered.

        Args:
            delivery_id: Webhook delivery record UUID.
            processed_at: Timestamp when delivery completed.
            status_code: HTTP response status code.
        """
        await self._session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(
                status=WebhookDeliveryStatus.DELIVERED,
                processed_at=processed_at,
                last_status_code=status_code,
                last_error=None,
            ),
        )

    async def mark_failed(
        self,
        delivery_id: uuid.UUID,
        *,
        processed_at: datetime,
        status_code: int | None,
        error: str,
    ) -> None:
        """Mark webhook delivery as permanently failed.

        Args:
            delivery_id: Webhook delivery record UUID.
            processed_at: Timestamp when processing stopped.
            status_code: Last HTTP response status code, if any.
            error: Last error message.
        """
        await self._session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(
                status=WebhookDeliveryStatus.FAILED,
                processed_at=processed_at,
                last_status_code=status_code,
                last_error=error,
            ),
        )

    async def reschedule(
        self,
        delivery_id: uuid.UUID,
        *,
        attempts: int,
        next_attempt_at: datetime,
        status_code: int | None,
        error: str,
    ) -> None:
        """Schedule a retry for a pending webhook delivery.

        Args:
            delivery_id: Webhook delivery record UUID.
            attempts: Updated attempt counter.
            next_attempt_at: Next scheduled delivery time.
            status_code: Last HTTP response status code, if any.
            error: Last error message.
        """
        await self._session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(
                attempts=attempts,
                next_attempt_at=next_attempt_at,
                last_status_code=status_code,
                last_error=error,
            ),
        )
