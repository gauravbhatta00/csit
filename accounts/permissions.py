from rest_framework.permissions import BasePermission
from django.utils import timezone


class IsPremiumUser(BasePermission):
    message = "This content is for premium users only. Please upgrade your plan."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_premium_active()


class IsSingleDeviceAuthenticated(BasePermission):
    message = "Your account is logged in on another device. Please log in again."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            # ✅ request.auth is the ACCESS token — get its jti
            jti = request.auth['jti']
            print(f"DEBUG request jti: {jti}")
            print(f"DEBUG stored jti:  {request.user.active_token}")
            return jti == request.user.active_token
        except Exception as e:
            print(f"DEBUG permission error: {e}")
            return False
