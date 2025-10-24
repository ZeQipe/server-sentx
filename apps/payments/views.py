import stripe
from django.conf import settings
from rest_framework import status, views, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BillingPlan, Subscription
from .serializers import BillingPlanSerializer, SubscriptionSerializer
from .service import PaymentService, StripeService


class BillingPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BillingPlan.objects.all()
    serializer_class = BillingPlanSerializer

    @action(detail=False, methods=["post"])
    def create_billing_plan(self, request):
        """Create a billing plan"""
        BillingPlan.objects.create(
            name="Pro",
            price=3000,
            description="Pro Monthly Plan",
            interval="month",
        )

        BillingPlan.objects.create(
            name="Pro",
            price=30000,
            description="Pro Yearly Plan",
            interval="year",
        )

        return Response({"message": "Billing plans created"}, status=status.HTTP_200_OK)


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Subscription.objects.none()
        return Subscription.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def create_checkout_session(self, request):
        """Create a checkout session for subscribing to a plan"""
        payment_service = PaymentService()

        try:
            success_url = request.data.get("success_url")
            cancel_url = request.data.get("cancel_url")
            plan_id = request.data.get("plan_id")

            if not all([success_url, cancel_url, plan_id]):
                return Response(
                    {"error": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create checkout session
            checkout_url = payment_service.get_checkout_session_url(
                user_email=request.user.email,
                billing_plan_id=plan_id,
                success_url=success_url,
                cancel_url=cancel_url,
            )

            return Response({"checkout_url": checkout_url}, status=status.HTTP_200_OK)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def create_portal_session(self, request):
        """Create a customer portal session for managing subscriptions"""
        payment_service = PaymentService()

        try:
            return_url = request.data.get("return_url")

            if not return_url:
                return Response(
                    {"error": "Missing return_url"}, status=status.HTTP_400_BAD_REQUEST
                )

            if not request.user.stripe_customer_id:
                return Response(
                    {"error": "User has no Stripe customer ID"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create portal session
            portal_url = payment_service.get_portal_session_url(
                customer_id=request.user.stripe_customer_id, return_url=return_url
            )

            return Response({"portal_url": portal_url}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """Cancel a subscription"""
        subscription = self.get_object()
        payment_service = PaymentService()

        try:
            payment_service.cancel_subscription(subscription.id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StripeWebhookView(views.APIView):
    permission_classes = []  # No authentication for webhooks

    def post(self, request, format=None):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

            # Handle the event
            stripe_service = StripeService()
            print('Wow')
            stripe_service.handle_webhook_event(event)

            # Print event type for logging
            print(f"Webhook received: {event['type']}")

            return Response({"status": "success"}, status=status.HTTP_200_OK)
        except stripe.error.SignatureVerificationError:
            return Response(
                {"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST
            )
