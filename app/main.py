from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.database import engine
from app.api.routes import router
from app.services.storage import ensure_bucket_exists

@asynccontextmanager
async def lifespan(app: FastAPI):
  await ensure_bucket_exists()

  yield 

  await engine.dispose()


app = FastAPI(title="Transcoding Pipeline", lifespan=lifespan)

app.include_router(router)

@app.get("/health")
async def health_check():
  return {"status": "healthy"}