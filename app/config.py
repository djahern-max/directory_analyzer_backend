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
    
    # Database Configuration
    database_url: str = "postgresql://postgres:password@localhost/analyze_pdf"
    async_database_url: str = "postgresql+asyncpg://postgres:password@localhost/analyze_pdf"
    
    # Security (from your existing .env)
    secret_key: str = "fallback-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # File processing (from your existing .env)
    max_file_size: int = 50000000
    max_file_size_mb: int = 50
    allowed_file_types: str = "pdf,PDF"
    allowed_file_extensions: list = ["pdf", "PDF"]
    max_text_sample_length: int = 2000
    
    # API Keys
    anthropic_api_key: str
    openai_api_key: str = ""  # Optional, from your existing .env
    
    # Anthropic API settings
    anthropic_model: str = "claude-3-sonnet-20240229"
    anthropic_max_tokens: int = 300
    anthropic_timeout: int = 60
    anthropic_max_retries: int = 3
    
    # Google Cloud Vision
    google_cloud_credentials_path: str = ""
    google_application_credentials: str = ""  # From your existing .env
    use_google_vision_ocr: bool = False
    
    # RunPod (from your existing .env)
    runpod_endpoint: str = ""
    runpod_api_key: str = ""
    
    # Encryption (from your existing .env)
    encryption_key: str = ""
    database_encryption_enabled: bool = False
    
    # Analysis configuration
    estimated_cost_per_document: float = 0.02
    estimated_time_per_document: float = 2.0
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        # Allow extra fields to prevent validation errors
        extra = "ignore"


# Global settings instance
settings = Settings()
