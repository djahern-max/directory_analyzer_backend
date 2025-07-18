# app/api/payments.py - Updated version
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

# Configure Stripe - Fix the attribute access
stripe.api_key = settings.stripe_secret_key

router = APIRouter()
logger = logging.getLogger("app.api.payments")


@router.post("/create-checkout-session")
async def create_checkout_session(
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Create Stripe checkout session for premium subscription"""
    try:
        logger.info(f"Creating checkout session for user: {current_user['email']}")

        # Validate Stripe configuration
        if not settings.stripe_secret_key:
            logger.error("Stripe secret key not configured")
            raise HTTPException(status_code=500, detail="Payment system not configured")

        # Check if user already has premium
        user = db.query(User).filter(User.id == current_user["id"]).first()
        if user and user.has_premium and user.subscription_status == "active":
            raise HTTPException(
                status_code=400, detail="User already has active subscription"
            )

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
                "user_id": str(current_user["id"]),
                "user_email": current_user["email"],
            },
        )

        logger.info(
            f"Created checkout session for user {current_user['email']}: {checkout_session.id}"
        )

        return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail=f"Payment system error: {str(e)}")
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

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating portal session: {e}")
        raise HTTPException(status_code=500, detail=f"Payment system error: {str(e)}")
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
        if settings.stripe_webhook_secret:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
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


# Replace the webhook functions in your app/api/payments.py


async def handle_checkout_completed(session, db: Session):
    """Handle successful checkout completion"""
    try:
        user_id = session["metadata"].get("user_id")
        user_email = session["metadata"].get("user_email")

        logger.info(
            f"Processing checkout completion for user_id: {user_id}, email: {user_email}"
        )

        if not user_id:
            logger.error("No user_id in session metadata")
            return

        user = db.query(User).filter(User.id == user_id).first()

        if user:
            # Update user with subscription info
            user.stripe_customer_id = session["customer"]
            user.has_premium = True
            user.subscription_status = "active"
            user.subscription_start_date = datetime.utcnow()

            # If there's a subscription, get the subscription details
            if session.get("subscription"):
                try:
                    subscription = stripe.Subscription.retrieve(session["subscription"])
                    user.stripe_subscription_id = subscription.id
                    user.current_period_start = datetime.fromtimestamp(
                        subscription.current_period_start
                    )
                    user.current_period_end = datetime.fromtimestamp(
                        subscription.current_period_end
                    )
                except Exception as e:
                    logger.warning(f"Could not retrieve subscription details: {e}")

            db.commit()
            logger.info(
                f"Successfully activated premium for user {user.email} (ID: {user_id})"
            )
        else:
            logger.error(f"User not found with ID: {user_id}")

    except Exception as e:
        logger.error(f"Error handling checkout completion: {e}")
        db.rollback()


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

            # Update subscription timing
            user.current_period_start = datetime.fromtimestamp(
                subscription["current_period_start"]
            )
            user.current_period_end = datetime.fromtimestamp(
                subscription["current_period_end"]
            )
            user.stripe_subscription_id = subscription["id"]

            db.commit()
            logger.info(f"Updated subscription for user {user.email}: {status}")
        else:
            logger.warning(f"User not found for customer_id: {customer_id}")

    except Exception as e:
        logger.error(f"Error handling subscription update: {e}")
        db.rollback()


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
        else:
            logger.warning(f"User not found for customer_id: {customer_id}")

    except Exception as e:
        logger.error(f"Error handling subscription deletion: {e}")
        db.rollback()


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
    return {"publishable_key": settings.stripe_publishable_key}


@router.post("/verify-session")
async def verify_payment_session(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify Stripe checkout session and update user subscription status"""
    try:
        session_id = request.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="Missing session_id")

        logger.info(
            f"Verifying payment session {session_id} for user {current_user['email']}"
        )

        # Retrieve the session from Stripe
        session = stripe.checkout.Session.retrieve(session_id)

        # Verify this session belongs to the current user
        if session.metadata.get("user_id") != str(current_user["id"]):
            raise HTTPException(
                status_code=403, detail="Session does not belong to current user"
            )

        # Check if payment was successful
        if session.payment_status == "paid" and session.status == "complete":
            # Update user in database
            user = db.query(User).filter(User.id == current_user["id"]).first()
            if user:
                user.stripe_customer_id = session.customer
                user.has_premium = True
                user.subscription_status = "active"
                user.subscription_start_date = datetime.utcnow()

                # If there's a subscription, get more details
                if session.subscription:
                    subscription = stripe.Subscription.retrieve(session.subscription)
                    user.stripe_subscription_id = subscription.id
                    user.current_period_start = datetime.fromtimestamp(
                        subscription.current_period_start
                    )
                    user.current_period_end = datetime.fromtimestamp(
                        subscription.current_period_end
                    )

                db.commit()

                logger.info(f"Successfully activated premium for user {user.email}")

                return {
                    "success": True,
                    "message": "Subscription activated successfully",
                    "user": {
                        "has_premium": user.has_premium,
                        "subscription_status": user.subscription_status,
                    },
                }
            else:
                raise HTTPException(status_code=404, detail="User not found")
        else:
            logger.warning(
                f"Payment not completed for session {session_id}: status={session.status}, payment_status={session.payment_status}"
            )
            raise HTTPException(status_code=400, detail="Payment not completed")

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error verifying session: {e}")
        raise HTTPException(
            status_code=500, detail=f"Payment verification failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error verifying payment session: {e}")
        raise HTTPException(status_code=500, detail=str(e))
