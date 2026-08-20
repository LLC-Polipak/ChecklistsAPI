from django.db import models
from django.db.models import Q


class TemplateManager(models.Manager):
    """Кастомный менеджер для инкапсуляции сложных SQL-запросов шаблонов."""

    def get_active(self, equipment_uid: str, checklist_type: str):
        return (self.get_queryset()
                .active()
                .for_equipment(equipment_uid, checklist_type)
                .with_full_hierarchy()
                .first())

    def deprecate_all(self, equipment_uid: str, checklist_type: str):
        (self.get_queryset()
         .active()
         .for_equipment(equipment_uid, checklist_type)
         .update(is_deprecated=True))

    def get_unique_equipments(self):
        return list(self.get_queryset()
                    .active()
                    .values_list('equipment_uid', flat=True)
                    .distinct())

    def restore_latest_deprecated(self, equipment_uid: str, checklist_type: str):
        active_exists = (self.get_queryset()
                         .active()
                         .for_equipment(equipment_uid, checklist_type)
                         .exists())

        if not active_exists:
            latest = (self.get_queryset()
                      .deprecated()
                      .for_equipment(equipment_uid, checklist_type)
                      .order_by('-created_at')
                      .first())

            if latest:
                latest.is_deprecated = False
                latest.save(update_fields=['is_deprecated'])

    def get_history(self, equipment_uid: str, checklist_type: str):
        return (self.get_queryset()
                .for_equipment(equipment_uid, checklist_type)
                .with_full_hierarchy()
                .order_by('-created_at'))


class ChecklistResultManager(models.Manager):
    """Кастомный менеджер для анкет."""

    def deprecate(self, result):
        result.is_deprecated = True
        result.save(update_fields=['is_deprecated'])

    def restore_latest_deprecated(self, origin_id: int):
        active_exists = (self.get_queryset()
                         .active()
                         .related_history(origin_id)
                         .exists())

        if not active_exists:
            latest = (self.get_queryset()
                      .deprecated()
                      .related_history(origin_id)
                      .order_by('-created_at')
                      .first())

            if latest:
                latest.is_deprecated = False
                latest.save(update_fields=['is_deprecated'])

    def get_history(self, origin_id: int):
        return (self.get_queryset()
                .related_history(origin_id)
                .with_full_hierarchy()
                .order_by('-created_at'))
