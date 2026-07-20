import jwt
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings

def test_password_hashing():
  raw_password = "test_password_123"
  hashed = get_password_hash(raw_password)

  assert raw_password != hashed
  assert verify_password(raw_password, hashed) is True
  assert verify_password("incorrect_password", hashed) is False

def test_create_access_token():
  payload_data = {"sub": "123e4567-e89b-12d3-a456-426614174000"}
  token = create_access_token(payload_data)

  decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
  assert decoded["sub"] == "123e4567-e89b-12d3-a456-426614174000"
  assert "exp" in decoded