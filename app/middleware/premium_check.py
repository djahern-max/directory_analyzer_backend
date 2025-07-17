# app/middleware/premium_check.py

from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import logging
from typing import Optional
from datetime import datetime

# You'll need to import your actual models and services
# from app.models.user import User  # Replace with your actual user model
# from app.services.subscription import subscription_service  # Replace with actual service
from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()


# Simplified version that works with your existing auth system
async def verify_premium_subscription(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Verify user has valid premium subscription"""
    try:
        # Decode JWT token
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = payload.get("user_id")
        email = payload.get("email")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )

        # For now, return user info - you can extend this later
        user_info = {
            "id": user_id,
            "email": email,
            "has_premium": payload.get("has_premium", False),  # Add this to your JWT
            "subscription_status": payload.get("subscription_status", "free"),
        }

        # Check if user has premium subscription
        if not user_info.get("has_premium", False):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "premium_subscription_required",
                    "message": "Premium subscription required for this feature",
                    "subscription_status": "free",
                    "billing_url": "/pricing",
                },
            )

        logger.info(f"Premium user {email} authenticated successfully")
        return user_info

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )
    except HTTPException:
        # Re-raise HTTP exceptions (like 402 Payment Required)
        raise
    except Exception as e:
        logger.error(f"Premium subscription check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )


# Optional: Basic auth check without premium requirement
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Get current user without premium requirement"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = payload.get("user_id")
        email = payload.get("email")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )

        return {
            "id": user_id,
            "email": email,
            "has_premium": payload.get("has_premium", False),
            "subscription_status": payload.get("subscription_status", "free"),
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )
    except Exception as e:
        logger.error(f"User authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )
