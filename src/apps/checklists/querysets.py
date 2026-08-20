from django.db import models
from django.db.models import Q


class TemplateQuerySet(models.QuerySet):
    """Кастомный QuerySet для шаблонов, позволяющий строить цепочки (chaining)."""

    def active(self):
        """Возвращает только активные (не устаревшие) шаблоны."""
        return self.filter(is_deprecated=False)

    def deprecated(self):
        return self.filter(is_deprecated=True)

    def for_equipment(self, equipment_uid: str, checklist_type: str):
        return self.filter(equipment_uid=equipment_uid,
                           checklist_type=checklist_type)

    def with_full_hierarchy(self):
        """Оптимизирует SQL-запросы, сразу подтягивая группы, поля и варианты."""
        return self.prefetch_related('groups__fields__choices')


class ChecklistResultQuerySet(models.QuerySet):
    """Кастомный QuerySet для анкет."""

    def active(self):
        return self.filter(is_deprecated=False)

    def deprecated(self):
        return self.filter(is_deprecated=True)

    def related_history(self, origin_id: int):
        return self.filter(Q(id=origin_id) | Q(origin_id=origin_id))

    def with_full_hierarchy(self):
        return self.select_related('template').prefetch_related(
            'answers__field', 'signatures')