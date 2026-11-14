from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import ExpiringTokenAuthentication
from config.security import EnquiryThrottle, OrderThrottle

from .serializers import EnquirySerializer, OrderCreateSerializer, OrderOutSerializer


class OrderCreate(APIView):
    """POST /api/orders/ — place an order. Prices are recalculated on the server."""

    throttle_classes = [OrderThrottle]
    authentication_classes = [ExpiringTokenAuthentication]  # optional: guests can order too

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save(user=request.user if request.user.is_authenticated else None)
        if request.user.is_authenticated:
            _remember_delivery_details(request.user, order)
        return Response(OrderOutSerializer(order).data, status=status.HTTP_201_CREATED)


def _remember_delivery_details(user, order):
    """First order while signed in: save phone and address to the account for next time."""
    from accounts.models import Profile
    profile, _ = Profile.objects.get_or_create(user=user)
    if not (profile.phone or profile.address):
        profile.phone, profile.address, profile.city, profile.region = order.phone, order.address, order.city, order.region
        profile.save()


class EnquiryCreate(APIView):
    """POST /api/enquiries/ — a message or wig request from the website. Shows up in the admin under Enquiries."""

    throttle_classes = [EnquiryThrottle]
    authentication_classes = []

    def post(self, request):
        serializer = EnquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("website"):
            # Spam bot filled in the hidden field: pretend it worked, save nothing.
            return Response({"ok": True}, status=status.HTTP_201_CREATED)
        serializer.save()
        return Response({"ok": True}, status=status.HTTP_201_CREATED)
