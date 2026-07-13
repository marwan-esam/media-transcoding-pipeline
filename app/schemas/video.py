from pydantic import BaseModel, ConfigDict, computed_field
from datetime import datetime
from uuid import UUID
from app.core.config import settings

class VideoResponse(BaseModel):
  id: UUID
  title: str
  filename: str
  status: str
  duration: float | None
  created_at: datetime

  model_config = ConfigDict(from_attributes=True)

  @computed_field
  def stream_url(self) -> str | None:
    if self.status == "completed":
      domain = settings.MINIO_ENDPOINT.replace("http://minio:9000", "http://localhost:9000")
      return f"{domain}/{settings.MINIO_PROCESSED_BUCKET_NAME}/{self.id}/master.m3u8"
    
    return None
  
  @computed_field
  def thumbnail_url(self) -> str | None:
    if self.status == "completed":
      domain = settings.MINIO_ENDPOINT.replace("http://minio:9000", "http://localhost:9000")
      return f"{domain}/{settings.MINIO_PROCESSED_BUCKET_NAME}/{self.id}/thumbnail.jpg"
    
    return None