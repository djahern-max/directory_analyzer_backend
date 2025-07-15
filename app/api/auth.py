from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
import httpx
import jwt
from datetime import datetime, timedelta

from app.config import settings
from app.models.database import User
from app.core.database import get_db

router = APIRouter()


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
async def google_callback(code: str, db=Depends(get_db)):
    """Handle Google OAuth callback"""

    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.google_oauth_redirect_uri,
    }

    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, data=token_data)
        tokens = token_response.json()

        # Get user info
        user_info_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        user_info = user_info_response.json()

    # Create or update user
    user = db.query(User).filter(User.email == user_info["email"]).first()
    if not user:
        user = User(
            email=user_info["email"],
            google_id=user_info["id"],
            name=user_info["name"],
            picture_url=user_info.get("picture"),
            credits_remaining=settings.free_trial_credits,
        )
        db.add(user)
    else:
        user.last_login = datetime.utcnow()

    db.commit()

    # Create JWT token
    token_data = {"user_id": str(user.id), "email": user.email}
    token = jwt.encode(
        {
            **token_data,
            "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    # Redirect to frontend with token
    frontend_url = f"https://pdfcontractanalyzer.com/?token={token}"
    return RedirectResponse(url=frontend_url)
