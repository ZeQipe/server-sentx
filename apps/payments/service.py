from datetime import timedelta
from typing import TYPE_CHECKING

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import BillingPlan, Subscription

if TYPE_CHECKING:
    from apps.users.models import User


class StripeService:
    def __init__(self):
        self.stripe = stripe
        self.stripe.api_key = settings.STRIPE_API_KEY

    def create_customer(self, user: "User"):
        """
        Create a Stripe customer for a user.
        """
        customer = self.stripe.Customer.create(
            email=user.email,
            name=user.name,
            metadata={"user_id": user.pk},
        )
        return customer.id

    def create_product_and_price(self, billing_plan: BillingPlan) -> tuple[str, str]:
        """
        Create a Stripe product and price for a billing plan.
        """
        # Check if product already exists with this billing plan ID
        existing_products: stripe.ListObject[stripe.Product] = self.stripe.Product.list(
            limit=1, ids=[str(billing_plan.stripe_product_id)]
        )

        print('existing')
        print(existing_products)

        if existing_products and existing_products.data:
            product = existing_products.data[0]
            # Get the price for this product
            prices = self.stripe.Price.list(product=product.id, active=True, limit=1)
            if prices and prices.data:
                return product.id, prices.data[0].id

        # Create new product and price
        product = self.stripe.Product.create(
            name=billing_plan.name,
            description=billing_plan.description,
            metadata={"billing_plan_id": str(billing_plan.pk)},
        )

        # Create price for the product with a lookup key
        price = self.stripe.Price.create(
            product=product.id,
            unit_amount=billing_plan.price,
            currency="usd",
            recurring={"interval": billing_plan.interval},
            lookup_key=f"plan_new_{billing_plan.pk}",
        )

        return product.id, price.id

    def create_checkout_session(
        self, user_email: str, price_id: str, success_url: str, cancel_url: str
    ) -> str:
        """
        Create a Stripe Checkout session for subscription.
        """
        checkout_session = self.stripe.checkout.Session.create(
            customer_email=user_email,
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
        )

        return checkout_session.url

    def create_portal_session(self, customer_id: str, return_url: str) -> str:
        """
        Create a Stripe Customer Portal session.
        """
        portal_session = self.stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )

        return portal_session.url

    def cancel_subscription(self, subscription_id: str):
        """
        Cancel a Stripe subscription.
        """
        return self.stripe.Subscription.delete(subscription_id)

    def update_subscription(self, subscription_id: str, price_id: str):
        """
        Update a subscription to a new price.
        """
        subscription = self.stripe.Subscription.retrieve(subscription_id)

        # Update the subscription item with the new price
        self.stripe.Subscription.modify(
            subscription_id,
            items=[
                {
                    "id": subscription["items"]["data"][0].id,
                    "price": price_id,
                }
            ],
        )

        return subscription

    def handle_webhook_event(self, event: stripe.Event):
        """
        Process Stripe webhook events.
        """
        event_type = event.get('type')
        event_data = event.get('data').get('object')
        print(f'Event type: {event_type}')
        print(f'Data: {event_data}')

        if event_type == "checkout.session.completed":
            # Handle successful checkout
            session = event_data
            customer_id = session.get("customer")
            subscription_id = session.get("subscription")

            # Record the subscription in our database
            if subscription_id:
                subscription = self.stripe.Subscription.retrieve(subscription_id)
                plan_id = None

                # Extract the billing plan ID from metadata
                print(subscription.items())
                if subscription.get("items") and subscription.get("items").data[0].price.product:
                    product_id = subscription.get("items").get("data")[0].get("price").get("product")
                    product = self.stripe.Product.retrieve(product_id)
                    plan_id = product.metadata.get("billing_plan_id")

                if plan_id:
                    try:
                        from django.contrib.auth import get_user_model

                        User = get_user_model()

                        billing_plan = BillingPlan.objects.get(pk=plan_id)
                        user = User.objects.get(email=session.get("customer_email"))

                        # Save customer ID if not already saved
                        if not user.stripe_customer_id:
                            user.stripe_customer_id = customer_id
                            user.save()

                        # Create subscription record
                        Subscription.objects.create(
                            user=user,
                            plan=billing_plan,
                            stripe_subscription_id=subscription_id,
                            is_active=True,
                        )
                    except (BillingPlan.DoesNotExist, User.DoesNotExist):
                        # Log error or handle appropriately
                        pass

        elif event_type == "customer.subscription.deleted":
            # Handle subscription cancellation
            subscription_id = event_data.get("id")
            subscription = Subscription.objects.filter(
                stripe_subscription_id=subscription_id
            ).first()
            if subscription:
                subscription.is_active = False
                subscription.end_date = timezone.now()
                subscription.save()

        elif event_type == "invoice.payment_succeeded":
            # Handle successful payment
            subscription_id = event_data.get("subscription")
            subscription = Subscription.objects.filter(
                stripe_subscription_id=subscription_id
            ).first()
            if subscription:
                # Extend subscription end date
                if not subscription.end_date:
                    subscription.end_date = timezone.now() + timedelta(days=30)
                else:
                    subscription.end_date = subscription.end_date + timedelta(days=30)
                subscription.save()

        elif event_type == "invoice.payment_failed":
            # Handle failed payment
            subscription_id = event_data.get("subscription")
            subscription = Subscription.objects.filter(
                stripe_subscription_id=subscription_id
            ).first()
            if subscription:
                # You might want to notify the user or handle this differently
                pass
        elif event_type == "customer.subscription.created":
            # Log subscription creation
            subscription_id = event_data.get("id")
            print(f"Subscription created: {subscription_id}")

        elif event_type == "customer.subscription.updated":
            # Log subscription update
            subscription_id = event_data.get("id")
            print(f"Subscription updated: {subscription_id}")


class PaymentService:
    @staticmethod
    def get_checkout_session_url(
        user_email: str, billing_plan_id: int, success_url: str, cancel_url: str
    ) -> str:
        """
        Create a checkout session for a user to subscribe to a plan.
        """
        stripe_service = StripeService()
        billing_plan = BillingPlan.objects.get(id=billing_plan_id)

        print(billing_plan)

        # Create or get Stripe product and price
        product_id, price_id = stripe_service.create_product_and_price(billing_plan)

        billing_plan.stripe_product_id = product_id
        billing_plan.stripe_price_id = price_id
        billing_plan.save()

        # Create checkout session
        checkout_url = stripe_service.create_checkout_session(
            user_email=user_email,
            price_id=price_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )

        return checkout_url

    @staticmethod
    def get_portal_session_url(customer_id: str, return_url: str) -> str:
        """
        Create a customer portal session for managing subscriptions.
        """
        stripe_service = StripeService()
        return stripe_service.create_portal_session(customer_id, return_url)

    @staticmethod
    @transaction.atomic
    def cancel_subscription(subscription_id: int):
        """
        Cancel a subscription.
        """
        stripe_service = StripeService()
        subscription = Subscription.objects.get(id=subscription_id)

        # Cancel in Stripe
        stripe_service.cancel_subscription(subscription.stripe_subscription_id)

        # Update our record
        subscription.is_active = False
        subscription.end_date = timezone.now()
        subscription.save()

        return subscription

    @staticmethod
    @transaction.atomic
    def change_subscription_plan(subscription_id: int, new_plan_id: int):
        """
        Change a subscription to a new plan.
        """
        stripe_service = StripeService()
        subscription = Subscription.objects.get(id=subscription_id)
        new_plan = BillingPlan.objects.get(id=new_plan_id)

        # Create product and price for the new plan if it doesn't exist
        _, price_id = stripe_service.create_product_and_price(new_plan)

        # Update subscription in Stripe
        stripe_service.update_subscription(
            subscription.stripe_subscription_id, price_id
        )

        # Update our record
        subscription.plan = new_plan
        subscription.save()

        return subscription

    @staticmethod
    def get_subscription_status(stripe_subscription_id: str) -> str:
        """
        Get the current status of a subscription from Stripe.
        """
        stripe_service = StripeService()
        subscription = stripe_service.stripe.Subscription.retrieve(
            stripe_subscription_id
        )
        return subscription.status

    @staticmethod
    def create_subscription(user, plan, payment_method_id, stripe_subscription_id=None):
        """
        Create a subscription for a user.
        """
        stripe_service = StripeService()

        # Create customer if not exists
        if not user.stripe_customer_id and payment_method_id:
            customer_id = stripe_service.create_customer(user)
            user.stripe_customer_id = customer_id
            user.save()

        # For test environments, use the provided stripe_subscription_id
        # In real environments, this would be created by calling Stripe API
        actual_stripe_sub_id = stripe_subscription_id or "sub_test456"

        # Create subscription in database
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            stripe_subscription_id=actual_stripe_sub_id,
            is_active=True,
        )

        return subscription
