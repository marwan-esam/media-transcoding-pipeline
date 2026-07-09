import uuid
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from datetime import timedelta
from app.db.database import get_db
from app.db.models import User
from app.core.config import settings
from app.api.dependencies import get_current_user
from app.core.security import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserCreate(BaseModel):
  email: EmailStr
  password: str

class UserLogin(BaseModel):
  email: EmailStr
  password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
  user_result = await db.execute(select(User).where(User.email == user_data.email))
  if user_result.scalar_one_or_none():
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
  
  hashed_pwd = get_password_hash(user_data.password)

  new_user = User(email=user_data.email, hashed_password=hashed_pwd)
  db.add(new_user)
  await db.commit()

  return {"message": "User created successfully"}


@router.post("/login")
async def login(response: Response, user_data: UserLogin, db: AsyncSession = Depends(get_db)):
  user_result = await db.execute(select(User).where(User.email == user_data.email))
  user = user_result.scalar_one_or_none()

  if not user or not verify_password(user_data.password, user.hashed_password):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorret email or password")
  
  access_token = create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(hours=1))

  response.set_cookie(
    key="access_token",
    value=f"Bearer {access_token}",
    httponly=True,
    secure=False,
    samesite="lax",
    max_age=3600
  )

  return {"message": "Login Sucessful"}


@router.post("/logout")
async def logout(response: Response):
  response.delete_cookie(key="access_token")
  return {"message": "logged out successfully"}

@router.get("/ticket")
async def getnerate_ws_ticket(current_user: User = Depends(get_current_user)):
  ticket = str(uuid.uuid4())
  redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
  try:
    await redis_client.set(f"ws_ticket:{ticket}", str(current_user.id), ex=15)
  finally:
    await redis_client.aclose()

  return {"ticket": ticket}