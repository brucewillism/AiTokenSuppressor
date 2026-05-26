"""Redis async client singleton."""

from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings

settings = get_settings()

_pool: ConnectionPool | None = None
_client: Redis | None = None


async def get_redis() -> Redis:
    global _pool, _client
    if _client is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        _client = Redis(connection_pool=_pool)
    return _client


async def close_redis() -> None:
    global _pool, _client
    if _client:
        await _client.aclose()
        _client = None
    if _pool:
        await _pool.disconnect()
        _pool = None
