import redis.asyncio as aioredis
from typing import Annotated
from uuid import uuid4, UUID
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import StringConstraints
from app.db.database import get_db
from app.schemas.video import VideoResponse
from app.db.models import Video
from app.core.config import settings
from app.services.storage import stream_upload_to_s3, delete_s3_files
from app.services.queue import publish_transcode_task
from app.api.dependencies import get_current_user
from app.db.models import User

router = APIRouter(prefix="/videos", tags=["Videos"])

CleanTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3)]
@router.post("/upload", status_code=status.HTTP_201_CREATED, response_model=VideoResponse)
async def upload_video(
  file: UploadFile = File(...), 
  title: CleanTitle | None = Form(None),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user)
):
  if not file.filename.endswith(('mp4', '.mkv', '.avi')):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid video format")
  
  file_ext = file.filename.split('.')[-1]
  s3_key = f"{uuid4().hex}.{file_ext}"

  final_title = title if title else ".".join(file.filename.split(".")[:-1])

  try:

    await stream_upload_to_s3(file, s3_key)

    new_video = Video(
      title=final_title,
      filename=file.filename,
      s3_key=s3_key,
      status="queued",
      user_id=current_user.id
    )

    db.add(new_video)
    await db.commit()
    await db.refresh(new_video)

    await publish_transcode_task(new_video.id, s3_key)

    return new_video

  except Exception as e:
    await db.rollback()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload failed: {str(e)}")
  

@router.websocket("/{video_id}/ws")
async def video_status_websocket(websocket: WebSocket, video_id: str, db: AsyncSession = Depends(get_db), ticket: str = Query(...)):
  await websocket.accept()

  redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
  pubsub = redis_client.pubsub()
  channel_name = f"video_status_{video_id}"

  try:
    ticket_key = f"ws_ticket:{ticket}"
    user_id_str = await redis_client.get(ticket_key)

    if not user_id_str:
      await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired ticket")
      return
    
    await redis_client.delete(ticket_key)

    current_user_id = UUID(user_id_str)

    try:
      valid_uuid = UUID(video_id)
    except ValueError:
      await websocket.send_json({"error": "Invalid video ID format"})
      await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
      return

    video_result = await db.execute(select(Video).where(Video.id == valid_uuid, Video.user_id == current_user_id))
    video_record = video_result.scalar_one_or_none()

    if not video_record:
      await websocket.send_json({"error": "Video not found"})
      await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
      return
    
    if video_record.status in ["completed", "failed"]:
      await websocket.send_json({"video_id": video_id, "status": video_record.status})
      await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
      return
    

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


@router.get("", status_code=status.HTTP_200_OK, response_model=list[VideoResponse])
async def list_videos(limit: int = 50, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
  videos_result = await db.execute(select(Video).where(Video.user_id == current_user.id).order_by(desc(Video.created_at)).limit(limit))
  return videos_result.scalars().all()


@router.get("/{video_id}", status_code=status.HTTP_200_OK, response_model=VideoResponse)
async def get_video_details(video_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
  try:
    valid_uuid = UUID(video_id)
  except ValueError:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid video ID format")
  
  video_result = await db.execute(select(Video).where(Video.id == valid_uuid, Video.user_id == current_user.id))
  video_record = video_result.scalar_one_or_none()

  if not video_record:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
  
  return video_record


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
  video_id: str,
  background_tasks: BackgroundTasks,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user)
):
  try:
    valid_uuid = UUID(video_id)
  except ValueError:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid video ID format")
  
  video_result = await db.execute(select(Video).where(Video.id == valid_uuid, Video.user_id == current_user.id))
  video_record = video_result.scalar_one_or_none()

  if not video_record:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
  
  video_uuid_str = str(valid_uuid)
  s3_key_to_delete = video_record.s3_key

  await db.delete(video_record)
  await db.commit()

  background_tasks.add_task(delete_s3_files, video_id=video_uuid_str, s3_key=s3_key_to_delete)

  return None
