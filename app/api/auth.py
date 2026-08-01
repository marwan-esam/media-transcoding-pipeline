import uuid
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import timedelta, datetime
from app.db.database import get_db
from app.db.models import User
from app.core.config import settings
from app.api.dependencies import get_current_user
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserCreate(BaseModel):
  email: EmailStr
  password: str

class UserLogin(BaseModel):
  email: EmailStr
  password: str

class UserResponse(BaseModel):
  id: uuid.UUID
  email: EmailStr
  is_active: bool
  created_at: datetime

  model_config = ConfigDict(from_attributes=True)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(request: Request, user_data: UserCreate, db: AsyncSession = Depends(get_db)):
  user_result = await db.execute(select(User).where(User.email == user_data.email))
  if user_result.scalar_one_or_none():
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
  
  hashed_pwd = get_password_hash(user_data.password)

  new_user = User(email=user_data.email, hashed_password=hashed_pwd)
  db.add(new_user)
  await db.commit()

  return {"message": "User created successfully"}


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, response: Response, user_data: UserLogin, db: AsyncSession = Depends(get_db)):
  user_result = await db.execute(select(User).where(User.email == user_data.email))
  user = user_result.scalar_one_or_none()

  if not user or not verify_password(user_data.password, user.hashed_password):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorret email or password")
  
  access_token = create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(hours=1))

  response.set_cookie(
    key="access_token",
    value=f"Bearer {access_token}",
    httponly=True,
    secure=True,
    samesite="none",
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

@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
  return current_user