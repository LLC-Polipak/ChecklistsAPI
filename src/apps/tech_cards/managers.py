from django.db import models

from apps.tech_cards.querysets import TechCardQuerySet


class TechCardManager(models.Manager):
    """Менеджер для модели TechCard."""

    def get_queryset(self) -> TechCardQuerySet:
        """Возвращает кастомный TechCardQuerySet.

        Returns:
            TechCardQuerySet: Базовый QuerySet с расширенными методами.
        """
        return TechCardQuerySet(self.model, using=self._db)

    def active(self) -> TechCardQuerySet:
        """Прокси-метод для получения активных карт."""
        return self.get_queryset().active()

    def drafts(self) -> TechCardQuerySet:
        """Прокси-метод для получения черновиков."""
        return self.get_queryset().drafts()

    def with_full_hierarchy(self) -> TechCardQuerySet:
        """Прокси-метод для получения карт с подгруженной иерархией."""
        return self.get_queryset().with_full_hierarchy()
