# Create new file: app/api/payments.py
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
import stripe
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import User
from app.core.database import get_db
from app.middleware.premium_check import get_current_user

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter()
logger = logging.getLogger("app.api.payments")


@router.post("/create-checkout-session")
async def create_checkout_session(
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Create Stripe checkout session for premium subscription"""
    try:
        # Create Stripe checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": "Contract Analysis Premium",
                            "description": "Secure contract storage and AI analysis",
                        },
                        "unit_amount": 14900,  # $149.00 in cents
                        "recurring": {
                            "interval": "month",
                        },
                    },
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=f"https://pdfcontractanalyzer.com/?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"https://pdfcontractanalyzer.com/?payment=cancelled",
            customer_email=current_user["email"],
            metadata={
                "user_id": current_user["id"],
                "user_email": current_user["email"],
            },
        )

        logger.info(
            f"Created checkout session for user {current_user['email']}: {checkout_session.id}"
        )

        return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}

    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail=f"Payment setup failed: {str(e)}")


@router.post("/portal-session")
async def create_portal_session(
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Create Stripe customer portal session for subscription management"""
    try:
        # Get user from database to find their Stripe customer ID
        user = db.query(User).filter(User.id == current_user["id"]).first()

        if not user or not user.stripe_customer_id:
            raise HTTPException(status_code=400, detail="No subscription found")

        # Create portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url="https://pdfcontractanalyzer.com/",
        )

        return {"portal_url": portal_session.url}

    except Exception as e:
        logger.error(f"Error creating portal session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhooks"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        # Verify webhook signature (optional for testing, required for production)
        if settings.STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        else:
            # For testing without webhook secret
            import json

            event = json.loads(payload)

        logger.info(f"Received Stripe webhook: {event['type']}")

        # Handle different event types
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            await handle_checkout_completed(session, db)

        elif event["type"] == "customer.subscription.updated":
            subscription = event["data"]["object"]
            await handle_subscription_updated(subscription, db)

        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            await handle_subscription_deleted(subscription, db)

        elif event["type"] == "invoice.payment_succeeded":
            invoice = event["data"]["object"]
            await handle_payment_succeeded(invoice, db)

        elif event["type"] == "invoice.payment_failed":
            invoice = event["data"]["object"]
            await handle_payment_failed(invoice, db)

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


async def handle_checkout_completed(session, db: Session):
    """Handle successful checkout completion"""
    try:
        user_id = session["metadata"]["user_id"]
        user = db.query(User).filter(User.id == user_id).first()

        if user:
            # Update user with subscription info
            user.stripe_customer_id = session["customer"]
            user.has_premium = True
            user.subscription_status = "active"
            user.subscription_start_date = datetime.utcnow()

            db.commit()
            logger.info(f"Activated premium for user {user.email}")

    except Exception as e:
        logger.error(f"Error handling checkout completion: {e}")


async def handle_subscription_updated(subscription, db: Session):
    """Handle subscription updates"""
    try:
        customer_id = subscription["customer"]
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

        if user:
            # Update subscription status
            status = subscription["status"]
            user.subscription_status = status
            user.has_premium = status in ["active", "trialing"]

            db.commit()
            logger.info(f"Updated subscription for user {user.email}: {status}")

    except Exception as e:
        logger.error(f"Error handling subscription update: {e}")


async def handle_subscription_deleted(subscription, db: Session):
    """Handle subscription cancellation"""
    try:
        customer_id = subscription["customer"]
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

        if user:
            user.has_premium = False
            user.subscription_status = "cancelled"
            user.subscription_end_date = datetime.utcnow()

            db.commit()
            logger.info(f"Cancelled subscription for user {user.email}")

    except Exception as e:
        logger.error(f"Error handling subscription deletion: {e}")


async def handle_payment_succeeded(invoice, db: Session):
    """Handle successful payment"""
    logger.info(f"Payment succeeded for customer {invoice['customer']}")


async def handle_payment_failed(invoice, db: Session):
    """Handle failed payment"""
    logger.error(f"Payment failed for customer {invoice['customer']}")


@router.get("/config")
async def get_stripe_config():
    """Get Stripe publishable key for frontend"""
    return {"publishable_key": settings.STRIPE_PUBLISHABLE_KEY}
