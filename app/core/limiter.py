from slowapi import Limiter
from slowapi.util import get_remote_address
import redis.asyncio as aioredis
from app.core.config import settings

redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

limiter = Limiter(
  key_func=get_remote_address,
  storage_uri=settings.REDIS_URL
)