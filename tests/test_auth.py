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

@pytest.mark.asyncio
async def test_login_and_cookie_assignment(async_client: AsyncClient):
  email = f"login_{uuid4().hex[:8]}@example.com"
  password = "strongpassword1!"
  await async_client.post("/auth/register", json={"email": email, "password": password})

  response = await async_client.post("/auth/login", json={"email": email, "password": password})

  assert response.status_code == 200
  assert "access_token" in response.cookies

@pytest.mark.asyncio
async def test_unauthenticated_access_rejected(async_client: AsyncClient):
  response = await async_client.get("/auth/users/me")
  assert response.status_code == 401

@pytest.mark.asyncio
async def test_authenticated_profile_retrieval(auth_client: AsyncClient):
  response = await auth_client.get("/auth/users/me")
  assert response.status_code == 200
  assert "email" in response.json()
  assert "is_active" in response.json()

@pytest.mark.asyncio
async def test_user_logout(auth_client: AsyncClient):
  response = await auth_client.post("/auth/logout")
  assert response.status_code == 200
  cookie_val = response.cookies.get("access_token")
  assert cookie_val is None or cookie_val == '""'
