from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .serializers import OrderCreateSerializer, OrderOutSerializer


class OrderCreateThrottle(AnonRateThrottle):
    rate = "20/hour"


class OrderCreate(APIView):
    """POST /api/orders/ — place an order. Prices are recalculated on the server."""

    throttle_classes = [OrderCreateThrottle]

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderOutSerializer(order).data, status=status.HTTP_201_CREATED)
