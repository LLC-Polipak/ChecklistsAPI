from django.apps import AppConfig


class ChecklistsConfig(AppConfig):
    """Настройки приложения Checklists."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.checklists'
    verbose_name = 'Чек-листы'
