from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.db.database import engine
from app.api.routes import router
from app.api.auth import router as auth_router
from app.services.storage import ensure_bucket_exists
from app.core.limiter import limiter
from app.core.middleware import LimitUploadSizeMiddleware
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
  await ensure_bucket_exists()

  yield 

  await engine.dispose()


app = FastAPI(title="Transcoding Pipeline", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["http://localhost:3000"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
  LimitUploadSizeMiddleware,
  max_upload_size=settings.max_upload_size_bytes
)

app.include_router(auth_router)
app.include_router(router)

@app.get("/health")
@limiter.limit("5/minute")
async def health_check(request: Request):
  return {"status": "healthy"}