"""Data access repositories."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PromptFingerprint, RequestLog, SemanticMemory


class RequestLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, log: RequestLog) -> RequestLog:
        self.db.add(log)
        await self.db.flush()
        return log

    async def get_recent(self, limit: int = 20) -> list[RequestLog]:
        stmt = (
            select(RequestLog)
            .order_by(RequestLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class MemoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, memory: SemanticMemory) -> SemanticMemory:
        self.db.add(memory)
        await self.db.flush()
        return memory

    async def get_by_id(self, memory_id: uuid.UUID) -> SemanticMemory | None:
        stmt = select(SemanticMemory).where(SemanticMemory.id == memory_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def increment_access(self, memory_id: uuid.UUID) -> None:
        await self.db.execute(
            update(SemanticMemory)
            .where(SemanticMemory.id == memory_id)
            .values(
                access_count=SemanticMemory.access_count + 1,
                updated_at=datetime.now(UTC),
            )
        )


class FingerprintRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_fingerprint(self, fingerprint: str) -> PromptFingerprint | None:
        stmt = select(PromptFingerprint).where(
            PromptFingerprint.fingerprint == fingerprint
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_hit(self, fingerprint: str, content_hash: str) -> PromptFingerprint:
        existing = await self.get_by_fingerprint(fingerprint)
        if existing:
            existing.hit_count += 1
            existing.last_accessed = datetime.now(UTC)
            await self.db.flush()
            return existing

        fp = PromptFingerprint(
            id=uuid.uuid4(),
            fingerprint=fingerprint,
            content_hash=content_hash,
        )
        self.db.add(fp)
        await self.db.flush()
        return fp
