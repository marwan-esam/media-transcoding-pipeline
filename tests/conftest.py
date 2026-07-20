import pytest
import pytest_asyncio
import redis.asyncio as aioredis
import uuid
from httpx import AsyncClient, ASGITransport
from alembic.config import Config
from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.db.database import AsyncSessionLocal
from app.db.models import User
from app.core.security import get_password_hash
from app.core.config import settings
from app.services.storage import ensure_bucket_exists

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
  alembic_cfg = Config("alembic.ini")
  command.upgrade(alembic_cfg, "head")
  yield

@pytest_asyncio.fixture(scope="session", autouse=True)
async def preparte_storage_buckets():
  await ensure_bucket_exists()

@pytest.fixture(scope="session")
def anyio_backend():
  return "asyncio"

@pytest_asyncio.fixture(autouse=True)
async def clear_redis():
  redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
  await redis.flushdb()
  await redis.aclose()

@pytest_asyncio.fixture()
async def async_client():
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    yield client

@pytest_asyncio.fixture()
async def db_session():
  async with AsyncSessionLocal() as session:
    yield session

@pytest_asyncio.fixture()
async def test_user(db_session: AsyncSession):
  user = User(
    email=f"testuser_{uuid.uuid4().hex[:8]}@example.com",
    hashed_password=get_password_hash("securepass123")
  )

  db_session.add(user)
  await db_session.commit()
  await db_session.refresh(user)
  return user

@pytest_asyncio.fixture()
async def auth_client(async_client: AsyncClient, test_user: User):
  await async_client.post(
    "/auth/login",
    json={"email": test_user.email, "password": "securepass123"}
  )
  return async_client