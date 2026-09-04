"""Определение моделей базы данных для системы пользователей."""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Модель пользователя."""
