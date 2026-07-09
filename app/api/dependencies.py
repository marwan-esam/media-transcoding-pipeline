import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID
from app.db.database import get_db
from app.db.models import User
from app.core.config import settings

class TokenPayload(BaseModel):
  sub: UUID
  exp: int


cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db), token_str: str = Depends(cookie_scheme)) -> User:

  if not token_str or not token_str.startswith("Bearer "):
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Not authenticated. Please log in"
    )
  
  token = token_str.split(" ")[1]
  
  try:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    user_id_str: str = payload.get("sub")
    if user_id_str is None:
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    
    data = TokenPayload(**payload)
    user_id = data.sub
  except jwt.ExpiredSignatureError:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
  except (jwt.InvalidTokenError, ValueError):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
  
  user_result = await db.execute(select(User).where(User.id == user_id))
  user = user_result.scalar_one_or_none()

  if not user:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
  
  return user