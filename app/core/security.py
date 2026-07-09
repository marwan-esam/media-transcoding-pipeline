import jwt
from datetime import datetime, timezone, timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.core.config import settings

ph = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)

def get_password_hash(password: str) -> str:
  return ph.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
  try:
    return ph.verify(hashed_password, password)
  except VerifyMismatchError:
    return False
  
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
  to_encode = data.copy()

  if expires_delta:
    expire = datetime.now(timezone.utc) + expires_delta
  else:
    expire = datetime.now(timezone.utc) + timedelta(days=1)

  to_encode.update({"exp": expire})

  encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
  return encoded_jwt