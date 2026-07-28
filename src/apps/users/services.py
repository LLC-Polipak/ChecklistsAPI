from datetime import datetime, timedelta, timezone

from django.conf import settings

from .models import User


def generate_jwt_token(user: User) -> str:
    """
    Генерирует JWT токен для пользователя (Service Layer).
    """

    import jwt

    payload = {
        'user_id': user.id,
        'exp': datetime.now(timezone.utc) + timedelta(hours=24),
        'iat': datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    return token
