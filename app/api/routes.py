from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.db.models import Video
from app.services.storage import stream_upload_to_s3

router = APIRouter(prefix="/videos", tags=["Videos"])

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_video(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
  if not file.filename.endswith(('mp4', '.mkv', '.avi')):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid video format")
  
  file_ext = file.filename.split('.')[-1]
  s3_key = f"{uuid4().hex}.{file_ext}"

  try:

    await stream_upload_to_s3(file, s3_key)

    new_video = Video(
      filename=file.filename,
      s3_key=s3_key,
      status="uploaded"
    )

    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    return {"id": new_video.id, "status": new_video.status, "message": "Upload complete"}
  except Exception as e:
    await db.rollback()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload failed: {str(e)}")