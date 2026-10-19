from django.db import models

from apps.core.constants import DocumentStatus
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

    def archived(self) -> TechCardQuerySet:
        """Прокси-метод для получения архивных карт."""
        return self.get_queryset().archived()

    def with_full_hierarchy(self) -> TechCardQuerySet:
        """Прокси-метод для получения карт с подгруженной иерархией."""
        return self.get_queryset().with_full_hierarchy()

    def available_for(
        self,
        operator_uid: str = None,
        status_filter: DocumentStatus = DocumentStatus.ACTIVE,
    ) -> TechCardQuerySet:
        """Прокси-метод для получения базовой карты и личной карты оператора."""
        return self.get_queryset().available_for(operator_uid, status_filter)
