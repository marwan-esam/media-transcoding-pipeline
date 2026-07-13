import aioboto3
from fastapi import UploadFile
from app.core.config import settings

session = aioboto3.Session()

def get_s3_client():
  return session.client(
    's3',
    endpoint_url=settings.MINIO_ENDPOINT,
    aws_access_key_id=settings.MINIO_ROOT_USER,
    aws_secret_access_key=settings.MINIO_ROOT_PASSWORD
  )


async def ensure_bucket_exists():
  async with get_s3_client() as s3:
    try:
      await s3.head_bucket(Bucket=settings.MINIO_BUCKET_NAME)
      await s3.head_bucket(Bucket=settings.MINIO_PROCESSED_BUCKET_NAME)
    except Exception:
      await s3.create_bucket(Bucket=settings.MINIO_BUCKET_NAME)
      await s3.create_bucket(Bucket=settings.MINIO_PROCESSED_BUCKET_NAME)


async def stream_upload_to_s3(file: UploadFile, s3_key: str) -> str:
  async with get_s3_client() as s3:
    mpu = await s3.create_multipart_upload(Bucket=settings.MINIO_BUCKET_NAME, Key=s3_key)
    mpu_id = mpu["UploadId"]

    parts = []
    part_number = 1
    chunk_size = 5 * 1024 * 1024

    try:
      while True:
        chunk = await file.read(chunk_size)

        if not chunk:
          break

        part = await s3.upload_part(
          Body=chunk,
          Bucket=settings.MINIO_BUCKET_NAME,
          Key=s3_key,
          PartNumber=part_number,
          UploadId=mpu_id
        )

        parts.append({"PartNumber": part_number, "ETag": part["ETag"]})
        part_number += 1
      
      await s3.complete_multipart_upload(
        Bucket=settings.MINIO_BUCKET_NAME,
        Key=s3_key,
        UploadId=mpu_id,
        MultipartUpload={"Parts": parts}
      )

      return s3_key
    except Exception as e:
      await s3.abort_multipart_upload(Bucket=settings.MINIO_BUCKET_NAME, Key=s3_key, UploadId=mpu_id)
      raise e
    

async def delete_s3_files(video_id: str, s3_key: str):
  async with get_s3_client() as s3:
    try:
      await s3.delete_object(
        Bucket=settings.MINIO_BUCKET_NAME,
        Key=s3_key
      )
    
      paginator = s3.get_paginator("list_objects_v2")
      prefix = f"{video_id}/"

      async for page in paginator.paginate(Bucket=settings.MINIO_PROCESSED_BUCKET_NAME, Prefix=prefix):
        if "Contents" in page:
          objects_to_delete = [{"Key": obj["Key"]} for obj in page["Contents"]]

          if objects_to_delete:
            await s3.delete_objects(
              Bucket=settings.MINIO_PROCESSED_BUCKET_NAME,
              Delete={"Objects": objects_to_delete}
            )

      print(f"[{video_id}] Sucessfully wiped all files from storage")
    except Exception as e:
      print(f"[{video_id}] Failed to delete files from storage: {str(e)}")
      