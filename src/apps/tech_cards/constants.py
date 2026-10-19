from django.db import models

MAX_DEPTH = 5  # Максимальная глубина вложенности
MAX_SECTIONS = 300  # Максимальное общее количество разделов


class CardType(models.TextChoices):
    """Перечисление типов технологических карт."""

    BASE = 'base', 'Базовая'
    PERSONAL = 'personal', 'Персональная'
