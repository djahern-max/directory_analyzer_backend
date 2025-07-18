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

        # Get fresh user data from database (don't rely on JWT for premium status)
        from app.core.database import get_db
        from app.models.database import User

        # We need to get a database session
        db_gen = get_db()
        db = next(db_gen)

        try:
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                logger.error(f"User not found in database: {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )

            logger.info(
                f"Premium check for user {email}: has_premium={user.has_premium}, status={user.subscription_status}"
            )

            user_info = {
                "id": user_id,
                "email": email,
                "has_premium": user.has_premium,
                "subscription_status": user.subscription_status,
            }

            # Check if user has premium subscription
            if not user.has_premium or user.subscription_status != "active":
                logger.warning(
                    f"Premium access denied for user {email}: has_premium={user.has_premium}, status={user.subscription_status}"
                )
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "premium_subscription_required",
                        "message": "Premium subscription required for this feature",
                        "subscription_status": user.subscription_status,
                        "billing_url": "/pricing",
                    },
                )

            logger.info(f"Premium user {email} authenticated successfully")
            return user_info

        finally:
            db.close()

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
