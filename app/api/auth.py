from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
import jwt
import logging
from datetime import datetime, timedelta

from app.config import settings
from app.models.database import User
from app.core.database import get_db

router = APIRouter()
logger = logging.getLogger("app.api.auth")


def is_premium_user(email: str, db: Session) -> bool:
    """Check if user has premium subscription from database"""
    user = db.query(User).filter(User.email == email).first()
    if user:
        # Check if user has active premium subscription
        return user.has_premium and user.subscription_status == "active"

    # Fallback to test users if not in database yet
    premium_test_users = [
        "danielaherniv@gmail.com",  # Your email
        # Add more emails here for testing
    ]
    return email.lower() in premium_test_users


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
            logger.info(f"Google token response: {tokens}")

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

        # Check premium status from database
        has_premium = is_premium_user(user.email, db)
        logger.info(f"User {user.email} premium status: {has_premium}")

        # Create JWT token with premium information
        token_data = {
            "user_id": str(user.id),
            "email": user.email,
            "has_premium": has_premium,
            "subscription_status": (
                user.subscription_status if user.subscription_status else "free"
            ),
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
            f"Redirecting to frontend with token for user: {user_info['email']} (premium: {has_premium})"
        )
        return RedirectResponse(url=frontend_url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Google callback: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/me")
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user info"""
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
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Return user info including current premium status from database
        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "picture_url": user.picture_url,
            "credits_remaining": float(user.credits_remaining),
            "is_active": user.is_active,
            "has_premium": user.has_premium,
            "subscription_status": user.subscription_status or "free",
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
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
