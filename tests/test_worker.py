import pytest
import re
from unittest.mock import patch, AsyncMock
from app.worker.main import parse_time_to_seconds, process_video

def test_parse_time_to_seconds():
  assert parse_time_to_seconds("01:02:03.45") == 3723.45
  assert parse_time_to_seconds("00:00:10.00") == 10.0

@pytest.mark.asyncio
@patch("app.worker.main.get_s3_client")
@patch("asyncio.create_subprocess_exec")
@patch("app.worker.main.publish_progress")
@patch("os.walk")
async def test_process_video_sucess(mock_os_walk, mock_publish, mock_subprocess, mock_s3_client):
  mock_s3 = AsyncMock()
  mock_s3_client.return_value.__aenter__.return_value = mock_s3

  mock_proc_main = AsyncMock()
  mock_proc_main.returncode = 0

  mock_proc_main.stderr.read.side_effect = [
    b"Duration: 00:00:10.00, start: 0.000000, bitrate: 100 kb/s\n",
    b"frame=  100 fps= 30 q=2.0 size= 2048kB time=00:00:05.00 bitrate= 50.0kbits/s\n",
    b""
  ]

  mock_proc_thumb = AsyncMock()
  mock_proc_thumb.returncode = 0

  mock_subprocess.side_effect = [mock_proc_main, mock_proc_thumb]

  mock_os_walk.return_value = [
    ("/tmp/fake_dir", [], ["playlist.m3u8", "segment_000.ts", "thumbnail.jpg"])
  ]

  duration = await process_video("test-video-id", "test-key.mp4")

  assert duration == 10.0
  mock_s3.download_file.assert_called_once()
  assert mock_subprocess.call_count == 2

  mock_publish.assert_called_with("test-video-id", "50%")

  assert mock_s3.upload_file.call_count == 3

@pytest.mark.asyncio
@patch("app.worker.main.get_s3_client")
@patch("asyncio.create_subprocess_exec")
async def test_process_video_ffmpeg_failure(mock_subprocess, mock_s3_client):
  mock_s3 = AsyncMock()
  mock_s3_client.return_value.__aenter__.return_value = mock_s3

  mock_proc_main = AsyncMock()
  mock_proc_main.returncode = 1
  mock_proc_main.stderr.read.side_effect = [b"Invalid data found when processing input", b""]

  mock_subprocess.return_value = mock_proc_main

  with pytest.raises(Exception, match=re.escape("FFmpeg processing failed")):
    await process_video("test-video-id", "test-key.mp4")