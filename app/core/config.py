from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  DATABASE_URL: str
  MINIO_ENDPOINT: str
  MINIO_BUCKET_NAME: str
  MINIO_ROOT_USER: str
  MINIO_ROOT_PASSWORD: str

  model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()