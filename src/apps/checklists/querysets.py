from django.db import models
from django.db.models import Q


class TemplateQuerySet(models.QuerySet):
    """Кастомный набор запросов (QuerySet) для модели Template.

    Инкапсулирует базовые SQL-фильтры, позволяя строить читаемые цепочки вызовов.
    """

    def active(self):
        """Вернуть только активные (не устаревшие) шаблоны."""
        return self.filter(is_deprecated=False, is_draft=False)

    def drafts(self):
        """Возвращает только черновики."""
        return self.filter(is_draft=True)

    def deprecated(self):
        """Вернуть только устаревшие (находящиеся в архиве) версии шаблонов."""
        return self.filter(is_deprecated=True)

    def for_equipment(
        self, equipment_uid: str, checklist_type: str, article_uid: str = None
    ):
        """Отфильтровать шаблоны по конкретному оборудованию, типу проверки и (опционально) артикулу.

        Args:
            equipment_uid: Уникальный идентификатор оборудования.
            checklist_type: Тип чек-листа (например, 'INSPECTION').
            article_uid: Арктикль продукта (необязателен).
        """
        qs = self.filter(equipment_uid=equipment_uid, checklist_type=checklist_type)

        if article_uid:
            qs = qs.filter(article_uid=article_uid)
        else:
            qs = qs.filter(article_uid__isnull=True)

        return qs

    def with_full_hierarchy(self):
        """Решить проблему N+1 запроса при получении шаблона.

        Предварительно загружает всю иерархию: Группы -> Поля -> Варианты ответов.
        """
        return self.prefetch_related('groups__fields__choices')


class ChecklistResultQuerySet(models.QuerySet):
    """Кастомный набор запросов (QuerySet) для заполненных анкет."""

    def active(self):
        """Вернуть только актуальные (последние) версии заполненных анкет."""
        return self.filter(is_deprecated=False)

    def deprecated(self):
        """Вернуть устаревшие версии анкет (сохраненные до их редактирования)."""
        return self.filter(is_deprecated=True)

    def related_history(self, origin_id: int):
        """Найти всю цепочку истории одной анкеты (Оригинал + Все его исправления).

        Args:
            origin_id: ID самой первой (корневой) версии анкеты.
        """
        return self.filter(Q(id=origin_id) | Q(origin_id=origin_id))

    def with_full_hierarchy(self):
        """Оптимизировать SQL-запросы, загружая связанные ответы, поля и подписи."""
        return self.select_related('template').prefetch_related(
            'answers__field', 'signatures'
        )
