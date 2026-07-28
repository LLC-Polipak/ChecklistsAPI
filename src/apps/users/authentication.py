from django.conf import settings
from django.utils.translation import gettext_lazy as _
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import User


class JWTAuthentication(BaseAuthentication):
    """
    Пользовательский класс аутентификации для проверки JWT-токенов.
    """

    def authenticate(self, request) -> tuple[User, str] | None:
        import jwt

        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user = User.objects.get(id=payload['user_id'])

            if not user.is_active:
                raise AuthenticationFailed(_('Пользователь заблокирован'))

            return (user, token)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed(_('Срок действия токена истек'))
        except jwt.DecodeError:
            raise AuthenticationFailed(_('Недействительный токен'))
        except User.DoesNotExist:
            raise AuthenticationFailed(_('Пользователь не найден'))

    def authenticate_header(self, request) -> str:
        return 'Bearer'


class JWTScheme(OpenApiAuthenticationExtension):
    target_class = 'users.authentication.JWTAuthentication'
    name = 'jwtAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
