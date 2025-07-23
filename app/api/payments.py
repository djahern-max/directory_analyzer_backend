# app/api/payments.py - Complete file with all endpoints and handlers
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
import stripe
import logging
import traceback
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import User
from app.core.database import get_db
from app.middleware.premium_check import get_current_user
import jwt

# Configure Stripe
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

        # Debug: Check Stripe configuration
        logger.info(f"Stripe secret key configured: {bool(settings.stripe_secret_key)}")
        logger.info(
            f"Stripe secret key starts with: {settings.stripe_secret_key[:10] if settings.stripe_secret_key else 'None'}..."
        )

        # Validate Stripe configuration
        if not settings.stripe_secret_key:
            logger.error("Stripe secret key not configured")
            raise HTTPException(status_code=500, detail="Payment system not configured")

        if settings.stripe_secret_key.startswith("your_"):
            logger.error("Stripe secret key appears to be placeholder value")
            raise HTTPException(
                status_code=500, detail="Payment system not properly configured"
            )

        # Check if user already has premium
        user = db.query(User).filter(User.id == current_user["id"]).first()
        if user and user.has_premium and user.subscription_status == "active":
            logger.warning(
                f"User {current_user['email']} already has active subscription"
            )
            raise HTTPException(
                status_code=400, detail="User already has active subscription"
            )

        logger.info("Creating Stripe checkout session...")

        # Create Stripe checkout session with enhanced error handling
        try:
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

            logger.info(f"Successfully created checkout session: {checkout_session.id}")
            logger.info(f"Checkout URL: {checkout_session.url}")

        except stripe.error.InvalidRequestError as e:
            logger.error(f"Stripe InvalidRequestError: {e}")
            logger.error(f"Error details: {e.user_message}")
            raise HTTPException(
                status_code=400, detail=f"Invalid payment request: {e.user_message}"
            )

        except stripe.error.AuthenticationError as e:
            logger.error(f"Stripe AuthenticationError: {e}")
            raise HTTPException(
                status_code=500, detail="Payment system authentication failed"
            )

        except stripe.error.APIConnectionError as e:
            logger.error(f"Stripe APIConnectionError: {e}")
            raise HTTPException(
                status_code=500, detail="Payment system connection failed"
            )

        except stripe.error.StripeError as e:
            logger.error(f"Generic Stripe error: {e}")
            logger.error(f"Stripe error type: {type(e)}")
            raise HTTPException(
                status_code=500, detail=f"Payment system error: {str(e)}"
            )

        return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating checkout session: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Payment setup failed: {str(e)}")


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
            logger.warning(
                f"Session {session_id} does not belong to user {current_user['id']}"
            )
            raise HTTPException(
                status_code=403, detail="Session does not belong to current user"
            )

        # Check if payment was successful
        if session.payment_status == "paid" and session.status == "complete":
            logger.info(f"Payment confirmed for session {session_id}")

            # Update user in database
            user = db.query(User).filter(User.id == current_user["id"]).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Update basic subscription info
            user.stripe_customer_id = session.customer
            user.has_premium = True
            user.subscription_status = "active"
            user.subscription_start_date = datetime.utcnow()

            # If there's a subscription, get more details with error handling
            subscription_details = {}
            if session.subscription:
                try:
                    subscription = stripe.Subscription.retrieve(session.subscription)
                    user.stripe_subscription_id = subscription.id
                    subscription_details["subscription_id"] = subscription.id

                    # Safe access to subscription dates
                    if (
                        hasattr(subscription, "current_period_start")
                        and subscription.current_period_start
                    ):
                        user.current_period_start = datetime.fromtimestamp(
                            subscription.current_period_start
                        )
                        subscription_details["period_start"] = (
                            user.current_period_start.isoformat()
                        )

                    if (
                        hasattr(subscription, "current_period_end")
                        and subscription.current_period_end
                    ):
                        user.current_period_end = datetime.fromtimestamp(
                            subscription.current_period_end
                        )
                        subscription_details["period_end"] = (
                            user.current_period_end.isoformat()
                        )

                    logger.info(
                        f"Retrieved subscription details: {subscription_details}"
                    )

                except Exception as sub_error:
                    logger.warning(
                        f"Could not retrieve subscription details: {sub_error}"
                    )
                    # Continue without subscription details

            # Commit the database changes
            try:
                db.commit()
                db.refresh(user)  # Refresh to get updated data
                logger.info(f"Successfully activated premium for user {user.email}")
            except Exception as commit_error:
                logger.error(f"Database commit failed: {commit_error}")
                db.rollback()
                raise HTTPException(
                    status_code=500, detail="Failed to update subscription status"
                )

            # Generate new JWT token with premium status
            new_token_data = {
                "user_id": str(user.id),
                "email": user.email,
                "has_premium": user.has_premium,  # Should be True now
                "subscription_status": user.subscription_status,  # Should be "active" now
                "stripe_customer_id": user.stripe_customer_id,
                "exp": datetime.utcnow()
                + timedelta(minutes=settings.jwt_expire_minutes),
            }

            new_token = jwt.encode(
                new_token_data,
                settings.jwt_secret_key,
                algorithm=settings.jwt_algorithm,
            )

            logger.info(
                f"Generated new premium token for {user.email}: "
                f"has_premium={user.has_premium}, status={user.subscription_status}"
            )

            # Return success response with new token
            return {
                "success": True,
                "message": "Subscription activated successfully",
                "token": new_token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "has_premium": user.has_premium,
                    "hasPremiumSubscription": user.has_premium,  # Frontend compatibility
                    "subscription_status": user.subscription_status,
                    "stripe_customer_id": user.stripe_customer_id,
                },
                "subscription": subscription_details,
                "session_verified": True,
            }
        else:
            logger.warning(
                f"Payment not completed for session {session_id}: "
                f"status={session.status}, payment_status={session.payment_status}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Payment not completed. Status: {session.status}, Payment: {session.payment_status}",
            )

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error verifying session: {e}")
        raise HTTPException(
            status_code=500, detail=f"Payment verification failed: {str(e)}"
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error verifying payment session: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.get("/subscription-status")
async def get_subscription_status(
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get current subscription status for debugging"""
    try:
        user = db.query(User).filter(User.id == current_user["id"]).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user_id": str(user.id),
            "email": user.email,
            "has_premium": user.has_premium,
            "subscription_status": user.subscription_status,
            "stripe_customer_id": user.stripe_customer_id,
            "stripe_subscription_id": user.stripe_subscription_id,
            "subscription_start_date": (
                user.subscription_start_date.isoformat()
                if user.subscription_start_date
                else None
            ),
            "current_period_start": (
                user.current_period_start.isoformat()
                if user.current_period_start
                else None
            ),
            "current_period_end": (
                user.current_period_end.isoformat() if user.current_period_end else None
            ),
        }

    except Exception as e:
        logger.error(f"Error getting subscription status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


# ===== WEBHOOK HANDLING =====


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
        logger.error(f"Webhook traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=str(e))


# ===== WEBHOOK HANDLERS =====


async def handle_checkout_completed(session, db: Session):
    """Handle successful checkout completion with better error handling"""
    try:
        user_id = session["metadata"].get("user_id")
        user_email = session["metadata"].get("user_email")

        logger.info(
            f"Processing checkout completion for user_id: {user_id}, email: {user_email}"
        )

        if not user_id:
            logger.error("No user_id in session metadata")
            return

        # Start a new transaction
        try:
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                logger.error(f"User not found with ID: {user_id}")
                return

            logger.info(
                f"Found user: {user.email}, current premium status: {user.has_premium}"
            )

            # Update user with subscription info
            user.stripe_customer_id = session["customer"]
            user.has_premium = True
            user.subscription_status = "active"
            user.subscription_start_date = datetime.utcnow()

            logger.info(
                f"Updated user {user.email} - setting has_premium=True, status=active"
            )

            # If there's a subscription, get the subscription details
            if session.get("subscription"):
                try:
                    subscription = stripe.Subscription.retrieve(session["subscription"])
                    user.stripe_subscription_id = subscription.id

                    if (
                        hasattr(subscription, "current_period_start")
                        and subscription.current_period_start
                    ):
                        user.current_period_start = datetime.fromtimestamp(
                            subscription.current_period_start
                        )

                    if (
                        hasattr(subscription, "current_period_end")
                        and subscription.current_period_end
                    ):
                        user.current_period_end = datetime.fromtimestamp(
                            subscription.current_period_end
                        )

                    logger.info(
                        f"Retrieved subscription details for {user.email}: {subscription.id}"
                    )

                except stripe.error.StripeError as e:
                    logger.warning(f"Could not retrieve subscription details: {e}")
                    # Continue without subscription details
                except Exception as e:
                    logger.warning(f"Unexpected error retrieving subscription: {e}")

            # Commit the transaction
            db.commit()

            # Verify the commit worked
            db.refresh(user)
            logger.info(
                f"Successfully activated premium for user {user.email} (ID: {user_id}) - "
                f"Verified: has_premium={user.has_premium}, status={user.subscription_status}"
            )

        except Exception as db_error:
            logger.error(f"Database error during checkout completion: {db_error}")
            logger.error(f"Rolling back transaction...")
            db.rollback()

            # Try to reactivate the user in a new transaction
            try:
                logger.info("Attempting recovery transaction...")
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.has_premium = True
                    user.subscription_status = "active"
                    user.stripe_customer_id = session["customer"]
                    user.subscription_start_date = datetime.utcnow()
                    db.commit()
                    logger.info(f"Recovery successful for user {user.email}")
                else:
                    logger.error(f"User {user_id} not found during recovery")
            except Exception as recovery_error:
                logger.error(f"Recovery transaction also failed: {recovery_error}")
                db.rollback()

    except Exception as e:
        logger.error(f"Error handling checkout completion: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        try:
            db.rollback()
        except:
            pass


async def handle_subscription_updated(subscription, db: Session):
    """Handle subscription updates with better error handling"""
    try:
        customer_id = subscription["customer"]
        logger.info(f"Processing subscription update for customer: {customer_id}")

        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

        if user:
            # Update subscription status
            status = subscription["status"]
            old_status = user.subscription_status
            old_premium = user.has_premium

            user.subscription_status = status
            user.has_premium = status in ["active", "trialing"]

            # Update subscription timing if available
            if subscription.get("current_period_start"):
                user.current_period_start = datetime.fromtimestamp(
                    subscription["current_period_start"]
                )
            if subscription.get("current_period_end"):
                user.current_period_end = datetime.fromtimestamp(
                    subscription["current_period_end"]
                )

            user.stripe_subscription_id = subscription["id"]

            db.commit()

            logger.info(
                f"Updated subscription for user {user.email}: "
                f"status {old_status} -> {status}, "
                f"premium {old_premium} -> {user.has_premium}"
            )
        else:
            logger.warning(f"User not found for customer_id: {customer_id}")

    except Exception as e:
        logger.error(f"Error handling subscription update: {e}")
        try:
            db.rollback()
        except:
            pass


async def handle_subscription_deleted(subscription, db: Session):
    """Handle subscription cancellation with better error handling"""
    try:
        customer_id = subscription["customer"]
        logger.info(f"Processing subscription deletion for customer: {customer_id}")

        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

        if user:
            old_status = user.subscription_status

            user.has_premium = False
            user.subscription_status = "cancelled"
            user.subscription_end_date = datetime.utcnow()

            db.commit()

            logger.info(
                f"Cancelled subscription for user {user.email}: "
                f"status {old_status} -> cancelled, premium -> False"
            )
        else:
            logger.warning(f"User not found for customer_id: {customer_id}")

    except Exception as e:
        logger.error(f"Error handling subscription deletion: {e}")
        try:
            db.rollback()
        except:
            pass


async def handle_payment_succeeded(invoice, db: Session):
    """Handle successful payment"""
    try:
        logger.info(f"Payment succeeded for customer {invoice['customer']}")
        # You can add additional logic here if needed
    except Exception as e:
        logger.error(f"Error handling payment success: {e}")


async def handle_payment_failed(invoice, db: Session):
    """Handle failed payment"""
    try:
        logger.error(f"Payment failed for customer {invoice['customer']}")
        # You can add logic to handle failed payments (e.g., send notifications)
    except Exception as e:
        logger.error(f"Error handling payment failure: {e}")
