from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.security import LOCKED_MESSAGE, AuthThrottle, client_ip, customer_guard

from orders.models import Order
from orders.serializers import OrderOutSerializer

from .authentication import ExpiringTokenAuthentication, fresh_token
from .serializers import AccountSerializer, LoginSerializer, RegisterSerializer


def _session(user):
    return {"token": fresh_token(user).key, "account": AccountSerializer(user).data}


class Register(APIView):
    """POST /api/auth/register/  {name, email, password}"""

    throttle_classes = [AuthThrottle]

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(_session(s.save()), status=status.HTTP_201_CREATED)


class Login(APIView):
    """POST /api/auth/login/  {email, password}"""

    throttle_classes = [AuthThrottle]

    def post(self, request):
        email, ip = str(request.data.get("email", ""))[:254], client_ip(request)
        if customer_guard.is_blocked(email, ip):
            return Response({"detail": LOCKED_MESSAGE}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        s = LoginSerializer(data=request.data)
        if not s.is_valid():
            customer_guard.failed(email, ip)
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        customer_guard.succeeded(email, ip)
        return Response(_session(s.validated_data["user"]))


class SignedIn(APIView):
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]


class Logout(SignedIn):
    """POST /api/auth/logout/ — ends the session on this device."""

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class Me(SignedIn):
    """GET / PATCH /api/auth/me/ — the customer's own details."""

    def get(self, request):
        return Response(AccountSerializer(request.user).data)

    def patch(self, request):
        s = AccountSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(AccountSerializer(request.user).data)


class MyOrders(SignedIn):
    """GET /api/auth/orders/ — orders placed while signed in to this account."""

    def get(self, request):
        orders = Order.objects.filter(user=request.user).prefetch_related("items").order_by("-created_at")
        return Response(OrderOutSerializer(orders, many=True, context={"request": request}).data)
