from rest_framework.permissions import BasePermission


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
            return request.auth["jti"] == request.user.active_token
        except (KeyError, TypeError):
            return False
