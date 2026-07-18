import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from alembic.config import Config
from alembic import command
from app.main import app

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
  alembic_cfg = Config("alembic.ini")
  command.upgrade(alembic_cfg, "head")
  yield

@pytest.fixture(scope="session")
def anyio_backend():
  return "asyncio"

@pytest_asyncio.fixture()
async def async_client():
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    yield client