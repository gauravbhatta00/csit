# payments/urls.py
from django.urls import path
from .views import InitiatePaymentView, VerifyPaymentView

urlpatterns = [
    path('initiate/', InitiatePaymentView.as_view()),
    path('verify/', VerifyPaymentView.as_view()),
]