from django.apps import AppConfig


class TechCardsConfig(AppConfig):
    """Настройки приложения Технических карт."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tech_cards'
    verbose_name = 'Технические карты'
