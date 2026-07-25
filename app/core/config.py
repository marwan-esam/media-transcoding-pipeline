from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  DATABASE_URL: str
  MINIO_ENDPOINT: str
  PUBLIC_MINIO_URL: str
  MINIO_BUCKET_NAME: str
  MINIO_PROCESSED_BUCKET_NAME: str
  MINIO_ROOT_USER: str
  MINIO_ROOT_PASSWORD: str
  RABBITMQ_URL: str
  REDIS_URL: str
  SECRET_KEY: str
  MAX_UPLOAD_SIZE_MB: int = 500

  @property
  def max_upload_size_bytes(self) -> int:
    return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

  model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()