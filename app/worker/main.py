from uuid import UUID
import asyncio
import json
import os
import tempfile
import aio_pika
from sqlalchemy import update
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Video
from app.services.storage import get_s3_client

async def process_video(video_id: str, s3_key: str):

  with tempfile.TemporaryDirectory() as tmpdir:
    input_path = os.path.join(tmpdir, f"input_{s3_key}")
    output_path = os.path.join(tmpdir, f"output_{s3_key}")

    async with get_s3_client() as s3:
      print(f"[{video_id}] Downloading {s3_key}...")
      await s3.download_file(settings.MINIO_BUCKET_NAME, s3_key, input_path)

      print(f"[{video_id}] Transcoding {s3_key} to 720p...")
      process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", input_path, "-vf", "scale=-2:720", output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
      )

      stdout, stderr = await process.communicate()

      if process.returncode != 0:
        print(f"FFmpeg Error: {stderr.decode()}")
        raise Exception("FFmpeg processing failed")
      
      print(f"[{video_id}] Uploading processed video...")
      processed_key = f"720_{s3_key}"
      await s3.upload_file(output_path, settings.MINIO_PROCESSED_BUCKET_NAME, processed_key)
      print(f"[{video_id}] Success!")


async def update_video_status(video_id: str, new_status: str):
  async with AsyncSessionLocal() as session:
    stmt = update(Video).where(Video.id == UUID(video_id)).values(status=new_status)
    await session.execute(stmt)
    await session.commit()


async def main():

  print(f"Worker starting... Connecting to RabbitMQ")

  connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)

  async with connection:
    channel = await connection.channel()

    await channel.set_qos(prefetch_count=1)

    dlx = await channel.declare_exchange(
      "video_dlx",
      aio_pika.ExchangeType.DIRECT,
      durable=True
    )

    dlq = await channel.declare_queue("transcode_dlq", durable=True)

    await dlq.bind(dlx, routing_key="transcode.failed")


    main_exchange = await channel.declare_exchange(
      "video_exchange",
      aio_pika.ExchangeType.DIRECT,
      durable=True
    )

    queue_args = {
      "x-dead-letter-exchange": "video_dlx",
      "x-dead-letter-routing-key": "transcode.failed"
    }

    main_queue = await channel.declare_queue(
      "transcode_queue",
      durable=True,
      arguments=queue_args
    )

    await main_queue.bind(main_exchange, routing_key="task.transcode")


    print("Worker is now listening for tasks...")

    async with main_queue.iterator() as queue_iter:
      async for message in queue_iter:
        async with message.process(ignore_processed=True):
          payload = json.loads(message.body.decode())
          video_id = payload.get("video_id")
          s3_key = payload.get("s3_key")

          print(f"\n--- Picked up Task: {video_id} ---")

          try:

            await update_video_status(video_id, "processing")

            await process_video(video_id, s3_key)

            await update_video_status(video_id, "completed")

            await message.ack()

          except Exception as e:
            print(f"Task Failed: {str(e)}")

            await update_video_status(video_id, "failed")

            await message.reject(requeue=False)


if __name__ == "__main__":
  asyncio.run(main())