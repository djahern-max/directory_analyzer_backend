from pydantic_settings import BaseSettings
from typing import Optional, List
import os
from dotenv import load_dotenv


class Settings(BaseSettings):
    """Application configuration settings"""

    # Application settings
    app_name: str = "Construction Directory Analyzer"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # API Configuration
    api_v1_prefix: str = "/api/v1"

    # Database Configuration - must be provided via environment variable
    database_url: str
    async_database_url: Optional[str] = None  # Will be auto-generated if not provided

    # Security
    secret_key: str = "fallback-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # File Upload Settings
    max_file_size: int = 50000000  # 50MB in bytes
    max_file_size_mb: int = 50
    allowed_file_types: str = "pdf,PDF"
    allowed_file_extensions: List[str] = ["pdf", "PDF"]
    max_text_sample_length: int = 2000

    # API Keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    runpod_api_key: str = ""

    # Anthropic API settings
    anthropic_model: str = "claude-3-sonnet-20240229"
    anthropic_max_tokens: int = 300
    anthropic_timeout: int = 60
    anthropic_max_retries: int = 3

    # Google Cloud Vision
    google_application_credentials: str = ""
    google_cloud_credentials_path: str = ""
    use_google_vision_ocr: bool = False

    # RunPod Configuration
    runpod_endpoint: str = ""

    # FIXED: Stripe Settings with proper type annotations
    stripe_publishable_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Encryption Settings
    encryption_key: str = ""
    database_encryption_enabled: bool = False

    # Analysis configuration
    estimated_cost_per_document: float = 0.02
    estimated_time_per_document: float = 2.0

    # Billing settings
    anthropic_markup_multiplier: float = 2.0
    minimum_charge: float = 0.01
    free_trial_credits: float = 1.00

    # Google OAuth
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    class Config:
        env_file = ".env"
        case_sensitive = False
        # Allow extra fields to prevent validation errors
        extra = "allow"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Post-init processing
        self._process_file_extensions()
        self._setup_database_urls()
        self._validate_required_keys()

    def _process_file_extensions(self):
        """Process allowed file types string into list"""
        if isinstance(self.allowed_file_types, str):
            self.allowed_file_extensions = [
                ext.strip() for ext in self.allowed_file_types.split(",")
            ]

    def _setup_database_urls(self):
        """Setup async database URL if not explicitly set"""
        if not self.async_database_url and self.database_url:
            # Convert sync URL to async URL
            if self.database_url.startswith("postgresql://"):
                self.async_database_url = self.database_url.replace(
                    "postgresql://", "postgresql+asyncpg://", 1
                )
            else:
                # For other databases, use the same URL
                self.async_database_url = self.database_url

    def _validate_required_keys(self):
        """Validate that required API keys are set for production"""
        if not self.debug:  # Only validate in production
            required_keys = []

            if not self.database_url:
                required_keys.append("DATABASE_URL")

            if not self.anthropic_api_key:
                required_keys.append("ANTHROPIC_API_KEY")

            if not self.secret_key or self.secret_key == "fallback-secret-key":
                required_keys.append("SECRET_KEY")

            if required_keys:
                raise ValueError(
                    f"Required environment variables not set: {', '.join(required_keys)}"
                )

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return not self.debug

    @property
    def database_config(self) -> dict:
        """Get database configuration dictionary"""
        return {
            "url": self.database_url,
            "async_url": self.async_database_url,
            "encryption_enabled": self.database_encryption_enabled,
        }

    @property
    def api_config(self) -> dict:
        """Get API configuration dictionary"""
        return {
            "anthropic": {
                "api_key": self.anthropic_api_key,
                "model": self.anthropic_model,
                "max_tokens": self.anthropic_max_tokens,
                "timeout": self.anthropic_timeout,
                "max_retries": self.anthropic_max_retries,
            },
            "openai": {"api_key": self.openai_api_key},
            "runpod": {
                "endpoint": self.runpod_endpoint,
                "api_key": self.runpod_api_key,
            },
        }

    @property
    def google_config(self) -> dict:
        """Get Google Cloud configuration"""
        return {
            "credentials_path": self.google_cloud_credentials_path,
            "application_credentials": self.google_application_credentials,
            "use_vision_ocr": self.use_google_vision_ocr,
        }

    @property
    def stripe_config(self) -> dict:
        """Get Stripe configuration"""
        return {
            "publishable_key": self.stripe_publishable_key,
            "secret_key": self.stripe_secret_key,
            "webhook_secret": self.stripe_webhook_secret,
        }

    @property
    def jwt_secret(self) -> str:
        """Get JWT secret key (fallback for compatibility)"""
        return self.jwt_secret_key or self.secret_key


# Global settings instance
settings = Settings()
