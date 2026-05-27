from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import GoogleLoginView, GoogleCallbackView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/google/', GoogleLoginView.as_view(), name='api-auth-google'),
    path('api/auth/google/callback/', GoogleCallbackView.as_view(), name='api-auth-google-callback'),
    path('api/accounts/', include('accounts.urls')),
    path('api/', include('academics.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
