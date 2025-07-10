from pydantic import BaseModel, ConfigDict
from typing import Any, Dict


class BaseAPIModel(BaseModel):
    """Base model for API requests and responses"""
    
    model_config = ConfigDict(
        # Allow extra fields to prevent validation errors
        extra="allow",
        # Validate assignment
        validate_assignment=True,
        # Use enum values
        use_enum_values=True,
        # Populate by name
        populate_by_name=True
    )


class TimestampMixin(BaseModel):
    """Mixin for models that include timestamp information"""
    
    timestamp: str
    
    @classmethod
    def with_timestamp(cls, **data) -> 'TimestampMixin':
        """Create instance with current timestamp"""
        from datetime import datetime
        return cls(timestamp=datetime.utcnow().isoformat(), **data)


class ErrorResponse(BaseAPIModel):
    """Standard error response model"""
    
    error: str
    message: str
    details: Dict[str, Any] = {}
    status_code: int = 400


class SuccessResponse(BaseAPIModel):
    """Standard success response model"""
    
    success: bool = True
    message: str
    data: Dict[str, Any] = {}
