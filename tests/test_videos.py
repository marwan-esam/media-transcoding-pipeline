import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_upload_invalid_video_format(auth_client: AsyncClient):
  files = {"file": ("document.txt", b"text string payload", 'text/plain')}
  response = await auth_client.post("/videos/upload", files=files)

  assert response.status_code == 400
  assert response.json()["detail"] == "Invalid video format"

@pytest.mark.asyncio
async def test_upload_valid_video_triggers_processing(auth_client: AsyncClient):
  files = {"file": ("test_video.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")}
  data = {"title": "Integration Test Video"}

  response = await auth_client.post("/videos/upload", data=data, files=files)

  assert response.status_code == 201, f"Upload failed with message: {response.json().get('detail')}"
  json_data = response.json()
  assert json_data["title"] == "Integration Test Video"
  assert json_data["status"] == "queued"
  assert "id" in json_data

@pytest.mark.asyncio
async def test_list_videos_returns_array(auth_client: AsyncClient):
  response = await auth_client.get("/videos")
  assert response.status_code == 200
  assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_video_deletion_workflow(auth_client: AsyncClient):
  files = {"file": ("delete_target.mp4", b"video byte string", "video/mp4")}
  data = {"title": "Test Video Deletion"}

  upload_response = await auth_client.post("/videos/upload", data=data, files=files)
  video_id = upload_response.json()["id"]

  delete_response = await auth_client.delete(f"videos/{video_id}")
  assert delete_response.status_code == 204

  get_response = await auth_client.get(f"videos/{video_id}")
  assert get_response.status_code == 404