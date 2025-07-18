# app/api/auth.py - Fixed version that checks database for premium status

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError  # Fixed import
import logging
from datetime import datetime, timedelta

from app.config import settings
from app.models.database import User
from app.core.database import get_db

router = APIRouter()
logger = logging.getLogger("app.api.auth")


def get_user_premium_status(user: User) -> tuple[bool, str]:
    """Get current premium status from database"""
    # Check if user has active premium subscription
    has_premium = user.has_premium and user.subscription_status in [
        "active",
        "trialing",
    ]

    # Return current status from database
    return has_premium, user.subscription_status or "free"


@router.get("/google")
async def google_login():
    """Redirect to Google OAuth"""
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={settings.google_oauth_client_id}&"
        f"redirect_uri={settings.google_oauth_redirect_uri}&"
        f"scope=openid email profile&"
        f"response_type=code&"
        f"access_type=offline"
    )
    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    """Handle Google OAuth callback"""

    try:
        # Exchange code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_oauth_redirect_uri,
        }

        logger.info(
            f"Requesting tokens with redirect_uri: {settings.google_oauth_redirect_uri}"
        )

        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)
            tokens = token_response.json()

            # Log the response for debugging
            logger.info(f"Google token response status: {token_response.status_code}")

            # Check for errors in the response
            if "error" in tokens:
                error_msg = tokens.get(
                    "error_description", tokens.get("error", "Unknown error")
                )
                logger.error(f"Google OAuth error: {error_msg}")
                raise HTTPException(
                    status_code=400, detail=f"Google OAuth error: {error_msg}"
                )

            # Check if access_token exists
            if "access_token" not in tokens:
                logger.error(
                    f"No access_token in Google response. Full response: {tokens}"
                )
                raise HTTPException(
                    status_code=400, detail="Failed to get access token from Google"
                )

            # Get user info
            user_info_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )

            if user_info_response.status_code != 200:
                logger.error(
                    f"Failed to get user info: {user_info_response.status_code} - {user_info_response.text}"
                )
                raise HTTPException(
                    status_code=400, detail="Failed to get user info from Google"
                )

            user_info = user_info_response.json()
            logger.info(f"Got user info for: {user_info.get('email')}")

        # Create or update user
        user = db.query(User).filter(User.email == user_info["email"]).first()
        if not user:
            user = User(
                email=user_info["email"],
                google_id=user_info["id"],
                name=user_info["name"],
                picture_url=user_info.get("picture"),
                credits_remaining=settings.free_trial_credits,
                # Initialize Stripe fields
                has_premium=False,
                subscription_status="free",
            )
            db.add(user)
            logger.info(f"Created new user: {user_info['email']}")
        else:
            user.last_login = datetime.utcnow()
            logger.info(f"Updated existing user: {user_info['email']}")

        db.commit()

        # Refresh user to get latest data from database
        db.refresh(user)

        # Get current premium status from database (FIXED: Always check database)
        has_premium, subscription_status = get_user_premium_status(user)

        logger.info(
            f"User {user.email} premium status from database: {has_premium} (status: {subscription_status})"
        )

        # Create JWT token with CURRENT premium information from database
        token_data = {
            "user_id": str(user.id),
            "email": user.email,
            "has_premium": has_premium,  # Use database value
            "subscription_status": subscription_status,  # Use database value
            "stripe_customer_id": user.stripe_customer_id,  # Include for debugging
            "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
        }

        token = jwt.encode(
            token_data,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        # Redirect to frontend with token
        frontend_url = f"https://pdfcontractanalyzer.com/?token={token}"
        logger.info(
            f"Redirecting to frontend with token for user: {user_info['email']} (premium: {has_premium}, status: {subscription_status})"
        )
        return RedirectResponse(url=frontend_url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Google callback: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


# app/api/auth.py - Enhanced with better logging and error handling


@router.get("/me")
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user info with fresh database data"""
    try:
        # Extract token from Authorization header
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401, detail="Missing or invalid authorization header"
            )

        token = authorization.split(" ")[1]

        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("user_id")

        logger.info(f"Loading user data for user_id: {user_id}")

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error(f"User not found in database: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")

        # Get CURRENT premium status from database (not from token)
        has_premium, subscription_status = get_user_premium_status(user)

        logger.info(
            f"User {user.email} data loaded - Premium: {has_premium}, Status: {subscription_status}"
        )

        # Return user info with CURRENT premium status from database
        user_data = {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "picture_url": user.picture_url,
            "credits_remaining": float(user.credits_remaining or 0),
            "is_active": user.is_active,
            "has_premium": has_premium,  # Fresh from database
            "hasPremiumSubscription": has_premium,  # For frontend compatibility
            "subscription_status": subscription_status,  # Fresh from database
            "stripe_customer_id": user.stripe_customer_id,
            "subscription_start_date": (
                user.subscription_start_date.isoformat()
                if user.subscription_start_date
                else None
            ),
            "subscription_end_date": (
                user.subscription_end_date.isoformat()
                if user.subscription_end_date
                else None
            ),
        }

        logger.info(
            f"Returning user data: {user_data['email']} - premium: {user_data['has_premium']}"
        )
        return user_data

    except ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except InvalidTokenError:
        logger.warning("Invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Unexpected error in /auth/me: {e}")

        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/refresh-premium-status")
async def refresh_premium_status(request: Request, db: Session = Depends(get_db)):
    """Refresh user's premium status and return new token"""
    try:
        # Extract token from Authorization header
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401, detail="Missing or invalid authorization header"
            )

        token = authorization.split(" ")[1]
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("user_id")

        logger.info(f"Refreshing premium status for user_id: {user_id}")

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error(f"User not found during premium refresh: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")

        # Get current premium status from database
        has_premium, subscription_status = get_user_premium_status(user)

        logger.info(
            f"Current premium status for {user.email}: "
            f"has_premium={has_premium}, status={subscription_status}, "
            f"stripe_customer_id={user.stripe_customer_id}"
        )

        # Create new JWT token with current premium status
        new_token_data = {
            "user_id": str(user.id),
            "email": user.email,
            "has_premium": has_premium,
            "subscription_status": subscription_status,
            "stripe_customer_id": user.stripe_customer_id,
            "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
        }

        new_token = jwt.encode(
            new_token_data,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        logger.info(f"Premium status refreshed for {user.email}: {has_premium}")

        return {
            "token": new_token,
            "has_premium": has_premium,
            "hasPremiumSubscription": has_premium,  # Frontend compatibility
            "subscription_status": subscription_status,
            "message": "Premium status refreshed successfully",
            "user_id": str(user.id),
            "email": user.email,
        }

    except ExpiredSignatureError:
        logger.warning("Token expired during premium refresh")
        raise HTTPException(status_code=401, detail="Token expired")
    except InvalidTokenError:
        logger.warning("Invalid token during premium refresh")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error refreshing premium status: {e}")

        raise HTTPException(status_code=500, detail="Internal server error")


# Add a debug endpoint to check what's in the database
@router.get("/debug-user-status")
async def debug_user_status(request: Request, db: Session = Depends(get_db)):
    """Debug endpoint to check user status in database"""
    try:
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing authorization header")

        token = authorization.split(" ")[1]
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("user_id")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user_id": str(user.id),
            "email": user.email,
            "database_fields": {
                "has_premium": user.has_premium,
                "subscription_status": user.subscription_status,
                "stripe_customer_id": user.stripe_customer_id,
                "stripe_subscription_id": user.stripe_subscription_id,
                "subscription_start_date": str(user.subscription_start_date),
                "subscription_end_date": str(user.subscription_end_date),
                "current_period_start": str(user.current_period_start),
                "current_period_end": str(user.current_period_end),
            },
            "computed_status": get_user_premium_status(user),
            "jwt_payload": {
                "has_premium": payload.get("has_premium"),
                "subscription_status": payload.get("subscription_status"),
            },
        }

    except Exception as e:
        logger.error(f"Debug endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
