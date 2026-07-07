import redis.asyncio as aioredis
from uuid import uuid4, UUID
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import Video
from app.core.config import settings
from app.services.storage import stream_upload_to_s3
from app.services.queue import publish_transcode_task

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
      status="queued"
    )

    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    await publish_transcode_task(new_video.id, s3_key)

    return {"id": new_video.id, "status": new_video.status, "message": "Upload complete and task queued"}
  except Exception as e:
    await db.rollback()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload failed: {str(e)}")
  

@router.websocket("/{video_id}/ws")
async def video_status_websocket(websocket: WebSocket, video_id: str, db: AsyncSession = Depends(get_db)):
  await websocket.accept()

  try:
  
    try:
      valid_uuid = UUID(video_id)
    except ValueError:
      await websocket.send_json({"error": "Invalid video ID format"})
      await websocket.close()
      return

    video_result = await db.execute(select(Video).where(Video.id == valid_uuid))
    video_record = video_result.scalar_one_or_none()

    if not video_record:
      await websocket.send_json({"error": "Video not found"})
      await websocket.close()
      return
    
    if video_record.status in ["completed", "failed"]:
      await websocket.send_json({"video_id": video_id, "status": video_record.status})
      await websocket.close()
      return
    
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel_name = f"video_status_{video_id}"

    await pubsub.subscribe(channel_name)

    await websocket.send_json({"video_id": video_id, "status": video_record.status, "message": "Listening for real-time updates..."})

    async for message in pubsub.listen():
      if message["type"] == "message":
        current_status = message["data"]

        await websocket.send_json({"video_id": video_id, "status": current_status})

        if current_status in ["completed", "failed"]:
          break
  
  except WebSocketDisconnect:
    print(f"Client disconnected from video {video_id}")
  finally:
    if "pubsub" in locals():
      await pubsub.unsubscribe(channel_name)
    if "redis_client" in locals():
      await redis_client.aclose()
