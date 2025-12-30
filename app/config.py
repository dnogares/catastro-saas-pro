import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    CAPAS_DIR: str = os.getenv("CAPAS_DIR", "/app/app/capas")
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "/app/app/outputs")
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/app/app/temp")
    
    API_TITLE: str = "Catastro SaaS Pro"
    API_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    CORS_ORIGINS: list = ["*"]

    class Config:
        env_file = ".env"

settings = Settings()
