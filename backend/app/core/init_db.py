"""Initialize pgvector extension and indexes."""

from sqlalchemy import text

from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)


async def setup_pgvector() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector_extension_enabled")
