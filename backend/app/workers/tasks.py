"""Background worker tasks."""

import asyncio

from app.workers.celery_app import celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.summarize_async", bind=True, max_retries=3)
def summarize_async(self, text: str, max_words: int = 150) -> str:
    from app.services.ollama_service import OllamaService

    async def _summarize():
        ollama = OllamaService()
        return await ollama.summarize(text, max_words=max_words)

    try:
        return _run_async(_summarize())
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.workers.tasks.create_embeddings_batch", bind=True, max_retries=3)
def create_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
    from app.services.ollama_service import OllamaService

    async def _embed():
        ollama = OllamaService()
        return await ollama.create_embeddings_batch(texts)

    try:
        return _run_async(_embed())
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.workers.tasks.ingest_rag_document", bind=True, max_retries=3)
def ingest_rag_document(
    self, content: str, collection_id: str = "default", source: str | None = None
) -> int:
    from app.core.database import AsyncSessionLocal
    from app.services.rag_service import RAGService

    async def _ingest():
        async with AsyncSessionLocal() as session:
            rag = RAGService(session)
            count = await rag.ingest(content, collection_id=collection_id, source=source)
            await session.commit()
            return count

    try:
        return _run_async(_ingest())
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.workers.tasks.cleanup_old_logs")
def cleanup_old_logs(days: int = 30) -> int:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    from app.core.database import AsyncSessionLocal
    from app.models import RequestLog

    async def _cleanup():
        cutoff = datetime.now(UTC) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(RequestLog).where(RequestLog.created_at < cutoff)
            )
            await session.commit()
            return result.rowcount

    return _run_async(_cleanup())
