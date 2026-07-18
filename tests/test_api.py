import pytest
from httpx import AsyncClient
from uuid import uuid4

@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
  response = await async_client.get("/health")
  assert response.status_code == 200
  assert response.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_user_registration(async_client: AsyncClient):
  test_email = f"test_user_{uuid4().hex[:8]}@example.com"
  test_password = "SecurePassword123!"

  payload = {
    "email": test_email,
    "password": test_password
  }

  response = await async_client.post("/auth/register", json=payload)
  assert response.status_code == 201
  assert response.json() == {"message": "User created successfully"}

  duplicate_response = await async_client.post("/auth/register", json=payload)
  assert duplicate_response.status_code == 400
  assert duplicate_response.json()["detail"] == "Email already registered"