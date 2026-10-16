from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Настройки приложения Core."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Ядро'
