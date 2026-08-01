import re
import asyncio
import json
import os
import tempfile
import aio_pika
import redis.asyncio as aioredis
from uuid import UUID
from sqlalchemy import update
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Video
from app.services.storage import get_s3_client

redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

def parse_time_to_seconds(time_str: str) -> float:
  h, m, s = time_str.split(":")
  return int(h) * 3600 + int(m) * 60 + float(s)

async def publish_progress(video_id: str, status: str):
  channel = f"video_status_{video_id}"
  await redis_client.publish(channel, status)

async def process_video(video_id: str, s3_key: str):

  with tempfile.TemporaryDirectory() as tmpdir:
    input_path = os.path.join(tmpdir, f"input_{s3_key}")

    output_dir = os.path.join(tmpdir, f"output_{video_id}")
    os.makedirs(output_dir, exist_ok=True)

    playlist_path = os.path.join(output_dir, "playlist.m3u8")
    segment_pattern = os.path.join(output_dir, "segment_%03d.ts")

    for i in range(3):
      os.makedirs(os.path.join(output_dir, f"stream_{i}"), exist_ok=True)

    async with get_s3_client() as s3:
      print(f"[{video_id}] Downloading {s3_key}...")
      await s3.download_file(settings.MINIO_BUCKET_NAME, s3_key, input_path)

      print(f"[{video_id}] Transcoding to Adaptive HLS (1080p, 720p, 480p)...")
      process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", input_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex", (
          "[0:v]split=3[v1][v2][v3];"
          "[v1]scale=w=1920:h=1080[v1out];"
          "[v2]scale=w=1280:h=720[v2out];"
          "[v3]scale=w=854:h=480[v3out];"
          "[0:a?]anull[main_audio];"
          "[1:a][main_audio]amix=inputs=2:weights=0 1:normalize=0:dropout_transition=0[clean_audio];"
          "[clean_audio]asplit=3[a1][a2][a3]"
        ),
        "-map", "[v1out]", "-map", "[a1]",
        "-map", "[v2out]", "-map", "[a2]",
        "-map", "[v3out]", "-map", "[a3]",
        "-c:v", "libx264",
        "-b:v:0", "5000k", "-maxrate:v:0", "5300k", "-bufsize:v:0", "7500k",
        "-b:v:1", "2500k", "-maxrate:v:1", "2700k", "-bufsize:v:1", "3750k",
        "-b:v:2", "1000k", "-maxrate:v:2", "1100k", "-bufsize:v:2", "1500k",
        "-c:a", "aac", "-ac", "2",
        "-b:a:0", "192k", "-b:a:1", "128k", "-b:a:2", "96k",
        "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
        "-shortest",
        "-f", "hls",
        "-hls_time", "10",
        "-hls_playlist_type", "vod",
        "-hls_flags", "independent_segments",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", f"{output_dir}/stream_%v/data%03d.ts",
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", "v:0,a:0 v:1,a:1 v:2,a:2",
        f"{output_dir}/stream_%v/playlist.m3u8",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
      )

      duration_regex = re.compile(r"Duration: (\d{2}:\d{2}:\d{2}\.\d{2})")
      time_regex = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")

      total_duration = 0.0
      last_reported_percent = -1
      max_current_time = 0.0
      output_text = ""
      full_log = []
      while True:
        
        chunk = await process.stderr.read(1024)
        if not chunk:
          break

        decoded = chunk.decode("utf-8", errors="ignore")
        output_text += decoded
        full_log.append(output_text)

        if total_duration == 0.0:
          duration_match = duration_regex.search(output_text)
          if duration_match:
            total_duration = parse_time_to_seconds(duration_match.group(1))

        if total_duration > 0.0:
          time_matches = time_regex.findall(output_text)
          if time_matches:
            # current_time = parse_time_to_seconds(time_matches[-1])
            # for match in time_matches:
            #   t_sec = parse_time_to_seconds(match)
            #   if t_sec > max_current_time:
            #     max_current_time = t_sec

            latest_time_str = time_matches[-1]
            t_sec = parse_time_to_seconds(latest_time_str)

            if t_sec > max_current_time:
              max_current_time = t_sec

            percentage = int((max_current_time / total_duration) * 100)

            if percentage > last_reported_percent and percentage <= 100:
              await publish_progress(video_id, f"{percentage}%")
              last_reported_percent = percentage

        if len(output_text) > 2048:
          output_text = output_text[-1024:]

      await process.wait()

      if process.returncode != 0:
        print("".join(full_log[-20:]))
        raise Exception("FFmpeg processing failed")
      
      print(f"[{video_id}] Extracting thumbnail...")
      thumb_path = os.path.join(output_dir, "thumbnail.jpg")
      thumb_time = 2.0 if total_duration >= 2.0 else (total_duration / 2.0)

      thumb_process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-ss", str(thumb_time), "-i", input_path,
        "-vframes", "1", "-q:v", "2", thumb_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
      )

      await thumb_process.wait()
      if thumb_process.returncode != 0:
        print(f"[{video_id}] Warning: Thumbnail extraction failled. Continuing")
      
      print(f"[{video_id}] Uploading Master Playlist and multi-res segments to MinIO...")
      for root, dirs, files in os.walk(output_dir):
        for file_name in files:
          file_path = os.path.join(root, file_name)
          rel_path = os.path.relpath(file_path, output_dir)
          s3_key_processed = f"{video_id}/{rel_path}"

          content_type = "application/octet-stream"
          if file_name.endswith(".m3u8"):
            content_type = "application/vnd.apple.mpegurl"
          elif file_name.endswith(".ts"):
            content_type = "video/mp2t"
          elif file_name.endswith(".jpg"):
            content_type = "image/jpeg"

          await s3.upload_file(
            file_path,
            settings.MINIO_PROCESSED_BUCKET_NAME,
            s3_key_processed,
            ExtraArgs={"ContentType": content_type}
          )
      print(f"[{video_id}] Success! Multi-resolution stream ready")
      return total_duration
      

async def update_video_status(video_id: str, new_status: str, duration: float = None):
  async with AsyncSessionLocal() as session:
    update_data = {"status": new_status}
    if duration is not None:
      update_data["duration"] = duration
    stmt = update(Video).where(Video.id == UUID(video_id)).values(**update_data)
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
            await publish_progress(video_id, "processing")

            duration = await process_video(video_id, s3_key)

            await update_video_status(video_id, "completed", duration=duration)
            await publish_progress(video_id, "completed")

            await message.ack()

          except Exception as e:
            print(f"Task Failed: {str(e)}")

            await update_video_status(video_id, "failed")
            await publish_progress(video_id, "failed")

            await message.reject(requeue=False)


if __name__ == "__main__":
  asyncio.run(main())