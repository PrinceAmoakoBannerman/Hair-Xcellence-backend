from django.urls import path

from . import views

urlpatterns = [
    path("auth/register/", views.Register.as_view(), name="register"),
    path("auth/login/", views.Login.as_view(), name="login"),
    path("auth/logout/", views.Logout.as_view(), name="logout"),
    path("auth/me/", views.Me.as_view(), name="me"),
    path("auth/orders/", views.MyOrders.as_view(), name="my-orders"),
]
