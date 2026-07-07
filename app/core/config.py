from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  DATABASE_URL: str
  MINIO_ENDPOINT: str
  MINIO_BUCKET_NAME: str
  MINIO_PROCESSED_BUCKET_NAME: str
  MINIO_ROOT_USER: str
  MINIO_ROOT_PASSWORD: str
  RABBITMQ_URL: str
  REDIS_URL: str

  model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()