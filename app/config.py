from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
   """Application configuration settings"""
   
   # Application settings
   app_name: str = "Construction Directory Analyzer"
   debug: bool = True
   host: str = "0.0.0.0"
   port: int = 8000
   
   # API Configuration
   api_v1_prefix: str = "/api/v1"
   
   # Anthropic API
   anthropic_api_key: str
   anthropic_model: str = "claude-3-sonnet-20240229"
   anthropic_max_tokens: int = 300
   anthropic_timeout: int = 60
   anthropic_max_retries: int = 3
   
   # File processing
   max_file_size_mb: int = 50
   allowed_file_extensions: list = ["pdf", "PDF"]
   max_text_sample_length: int = 2000
   
   # Analysis configuration
   estimated_cost_per_document: float = 0.02
   estimated_time_per_document: float = 2.0
   
   # Logging
   log_level: str = "INFO"
   log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
   
   class Config:
       env_file = ".env"
       case_sensitive = False


# Global settings instance
settings = Settings()
