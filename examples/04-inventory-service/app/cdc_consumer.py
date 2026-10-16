"""TRANSITION-ONLY Debezium CDC consumer (flag-gated, `INVENTORY_CDC_ENABLED`,
default OFF -- see `app/config.py`). Re-authored from the Java sibling's
`InventoryCdcConsumer`/`InventoryCdcWriter` pair onto `aiokafka` + SQLAlchemy
Core's Postgres `ON CONFLICT` upsert.

**Role: backfill + sync during the cutover window, retired after it.** While
the monolith's `public.inventory_items` table is still the system of record
(before the strangler proxy flips `STRANGLER_INVENTORY_ENABLED=true`), a
Debezium Postgres connector on topic `meap.public.inventory_items` lets this
service's OWN `inventory.inventory_items` copy track the monolith's table in
near-real-time: `snapshot.mode=initial` emits one `op=r` ("read") event per
existing row first (the initial backfill), then streams `op=c/u/d` events as
the monolith's table changes. Once cutover is complete and the monolith's
table is decommissioned, this consumer has nothing left to consume and should
be disabled (`INVENTORY_CDC_ENABLED=false`, the default) -- see
`../CUTOVER.md`'s retire runbook. It is NOT used by CI (`uv run pytest`
never sets the flag) and is NOT part of this service's end-state story: the
Alembic seed migration (`migrations/versions/0002_seed_inventory.py`) is
this service's own, independent system of record once cutover completes.

**Envelope shape.** The connector runs with
`key/value.converter.schemas.enable=false` (matching the Java sibling's
`infra/debezium/README.md`), so Kafka Connect's JsonConverter emits the
Debezium envelope FLAT on the wire -- `{"before":...,"after":...,
"source":...,"op":...,"ts_ms":...}` -- with no outer
`{"schema":...,"payload":{...}}` wrapper. `_unwrap_payload` defensively also
accepts a `{"payload": {...}}`-wrapped shape in case `schemas.enable` is ever
flipped back on.

**Idempotency.** All three ops (`r`/`c`/`u` -> upsert, `d` -> delete) funnel
through a single atomic `INSERT ... ON CONFLICT (id) DO UPDATE` / keyed
`DELETE`, so Kafka's at-least-once redelivery never double-applies a change --
same guarantee notification-service's `OrderPlacedConsumer` provides via its
own dedupe, just via a database-native upsert here instead of
check-then-insert (there is no natural "already applied" marker for a row
update the way there is for a notification's `order_id`).

**Known caveat if ever enabled against a service that has already run its own
seed migration:** this service's `id` column is an autoincrementing sequence
owned by Postgres (`app/models.py`'s docstring), not CDC-assigned. Upserting
by the Debezium-sourced `id` (the monolith's own primary key) alongside
locally-seeded rows risks a primary-key collision or a sequence that no
longer reflects the table's actual max id. This consumer is intended to run
against an otherwise-empty `inventory.inventory_items` table during the
transition window, not alongside the Alembic seed -- an honest limitation
documented here rather than solved with additional reconciliation machinery
that would be speculative infrastructure for a flag this project does not
turn on.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from aiokafka import AIOKafkaConsumer
from sqlalchemy import delete as sa_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models import InventoryItem

logger = logging.getLogger("inventory_service.cdc_consumer")

# Debezium represents a Postgres TIMESTAMP column as either epoch MILLIS
# (io.debezium.time.Timestamp) or epoch MICROS (io.debezium.time.MicroTimestamp)
# depending on column precision -- serialized as a bare JSON number once
# schemas.enable=false strips the field-schema metadata that would otherwise
# disambiguate the two. Any value larger than this ceiling (epoch millis for
# roughly the year 5138) cannot be a sane millis timestamp, so it is treated
# as micros instead. Same heuristic as the Java sibling's InventoryCdcConsumer.
_EPOCH_MILLIS_CEILING = 100_000_000_000_000


def _unwrap_payload(envelope: dict) -> dict:
    return envelope.get("payload", envelope)


def _parse_debezium_timestamp(value: int | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    # value > ceiling => it's epoch MICROS (divide by 1_000_000 for seconds);
    # otherwise it's epoch MILLIS (divide by 1_000 for seconds). Same
    # heuristic/branching as the Java sibling's InventoryCdcConsumer.
    seconds = value / 1_000_000.0 if value > _EPOCH_MILLIS_CEILING else value / 1_000.0
    return datetime.fromtimestamp(seconds, tz=UTC)


async def _upsert(session: AsyncSession, after: dict) -> None:
    stmt = pg_insert(InventoryItem).values(
        id=after["id"],
        sku=after["sku"],
        name=after["name"],
        price_cents=after["price_cents"],
        quantity_on_hand=after["quantity_on_hand"],
        updated_at=_parse_debezium_timestamp(after.get("updated_at")),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[InventoryItem.id],
        set_={
            "sku": stmt.excluded.sku,
            "name": stmt.excluded.name,
            "price_cents": stmt.excluded.price_cents,
            "quantity_on_hand": stmt.excluded.quantity_on_hand,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)
    await session.commit()
    logger.info(
        "inventory-cdc: upserted id=%s sku=%s quantityOnHand=%s",
        after["id"],
        after["sku"],
        after["quantity_on_hand"],
    )


async def _delete(session: AsyncSession, before: dict) -> None:
    item_id = before["id"]
    await session.execute(sa_delete(InventoryItem).where(InventoryItem.id == item_id))
    await session.commit()
    logger.info("inventory-cdc: deleted id=%s", item_id)


class InventoryCdcConsumer:
    """Lifecycle wrapper around an `AIOKafkaConsumer` subscribed to the
    Debezium `inventory_items` change-stream topic, applying each record
    directly (no intermediate service-layer indirection -- this is a thin,
    transition-only adapter, not a long-lived domain concern)."""

    def __init__(
        self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._settings.inventory_cdc_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.inventory_cdc_group,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop(), name="inventory-cdc-consumer")
        logger.info(
            "inventory-cdc consumer started (topic=%s, group=%s, bootstrap=%s)",
            self._settings.inventory_cdc_topic,
            self._settings.inventory_cdc_group,
            self._settings.kafka_bootstrap_servers,
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        logger.info("inventory-cdc consumer stopped")

    async def _consume_loop(self) -> None:
        assert self._consumer is not None
        async for record in self._consumer:
            try:
                await self._handle_record(record.value)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A single malformed/unprocessable record must not kill the
                # background task -- log and keep consuming subsequent
                # records (same posture as notification-service's
                # OrderPlacedConsumer._consume_loop).
                logger.exception(
                    "inventory-cdc: failed to process record at offset %s", record.offset
                )

    async def _handle_record(self, raw: bytes | None) -> None:
        if not raw:
            # Debezium tombstone (null value, published after a delete once
            # the log-compaction key is processed). Guarded defensively, as
            # this connector is not configured to emit tombstones.
            return

        try:
            root = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.exception("inventory-cdc: failed to parse Debezium envelope JSON")
            return

        envelope = _unwrap_payload(root)
        op = envelope.get("op")
        if op is None:
            logger.warning("inventory-cdc: envelope missing 'op', skipping")
            return

        async with self._session_factory() as session:
            if op in ("r", "c", "u"):
                after = envelope.get("after")
                if not after:
                    logger.warning("inventory-cdc: upsert op with no 'after' payload, skipping")
                    return
                await _upsert(session, after)
            elif op == "d":
                before = envelope.get("before")
                if not before or before.get("id") is None:
                    logger.warning("inventory-cdc: delete op with no 'before.id', skipping")
                    return
                await _delete(session, before)
            else:
                logger.warning("inventory-cdc: unhandled Debezium op '%s', skipping", op)
