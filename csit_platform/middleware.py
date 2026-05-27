from django.conf import settings
from django.http import HttpResponse


class SimpleCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin')
        is_allowed_origin = origin in settings.CORS_ALLOWED_ORIGINS

        if request.method == 'OPTIONS' and is_allowed_origin:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if is_allowed_origin:
            response['Access-Control-Allow-Origin'] = origin
            response['Vary'] = self._append_vary(response.get('Vary'), 'Origin')
            response['Access-Control-Allow-Methods'] = ', '.join(
                settings.CORS_ALLOWED_METHODS
            )
            response['Access-Control-Allow-Headers'] = ', '.join(
                settings.CORS_ALLOWED_HEADERS
            )
            response['Access-Control-Max-Age'] = str(settings.CORS_PREFLIGHT_MAX_AGE)

            if settings.CORS_ALLOW_CREDENTIALS:
                response['Access-Control-Allow-Credentials'] = 'true'

        return response

    @staticmethod
    def _append_vary(current_value, new_value):
        if not current_value:
            return new_value

        values = [value.strip() for value in current_value.split(',')]
        if new_value in values:
            return current_value

        return f'{current_value}, {new_value}'
