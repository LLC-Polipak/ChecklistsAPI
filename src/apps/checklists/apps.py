"""Конфигурация Django-приложения для работы с чек-листами."""
from django.apps import AppConfig


class ChecklistsConfig(AppConfig):
    """Настройки приложения Checklists."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.checklists'
