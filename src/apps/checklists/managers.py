from django.db import models


class TemplateManager(models.Manager):
    """
    Менеджер для модели Template, предоставляющий высокоуровневые бизнес-команды.
    Скрывает от контроллеров и сервисов сложную логику работы с базой данных.
    """

    def get_active(self, equipment_uid: str, checklist_type: str):
        """
        Находит актуальный шаблон для заполнения анкеты.

        Returns:
            Объект Template со всей загруженной иерархией полей, либо None.
        """
        return (
            self.get_queryset()
            .active()
            .for_equipment(equipment_uid, checklist_type)
            .with_full_hierarchy()
            .first()
        )

    def deprecate_all(self, equipment_uid: str, checklist_type: str):
        """
        Мягко удаляет (Soft Delete) все активные шаблоны указанного типа и оборудования.
        Используется при создании новой версии шаблона для сохранения историчности.
        """
        (
            self.get_queryset()
            .active()
            .for_equipment(equipment_uid, checklist_type)
            .update(is_deprecated=True)
        )

    def get_unique_equipments(self):
        """
        Мягко удаляет (Soft Delete) все активные шаблоны указанного типа и оборудования.
        Используется при создании новой версии шаблона для сохранения историчности.
        """
        return list(
            self.get_queryset()
            .active()
            .values_list('equipment_uid', flat=True)
            .distinct()
        )

    def restore_latest_deprecated(self, equipment_uid: str, checklist_type: str):
        """
        Откат удаления (Rollback).
        Если для данного оборудования не осталось активных шаблонов (например, при ошибочном удалении),
        находит самую свежую устаревшую версию и делает её активной.
        """
        active_exists = (
            self.get_queryset()
            .active()
            .for_equipment(equipment_uid, checklist_type)
            .exists()
        )

        if not active_exists:
            latest = (
                self.get_queryset()
                .deprecated()
                .for_equipment(equipment_uid, checklist_type)
                .order_by('-created_at')
                .first()
            )

            if latest:
                latest.is_deprecated = False
                latest.save(update_fields=['is_deprecated'])

    def get_history(self, equipment_uid: str, checklist_type: str):
        """Возвращает хронологическую историю всех версий шаблона (от новых к старым)."""
        return (
            self.get_queryset()
            .for_equipment(equipment_uid, checklist_type)
            .with_full_hierarchy()
            .order_by('-created_at')
        )


class ChecklistResultManager(models.Manager):
    """Менеджер для модели ChecklistResult (Заполненные анкеты)."""

    def deprecate(self, result):
        """Помечает конкретную анкету как устаревшую (используется при редактировании ответов)."""
        result.is_deprecated = True
        result.save(update_fields=['is_deprecated'])

    def restore_latest_deprecated(self, origin_id: int):
        """
        Восстанавливает предыдущую версию ответов пользователя, если текущая (последняя)
        версия анкеты была удалена администратором.
        """
        active_exists = self.get_queryset().active().related_history(origin_id).exists()

        if not active_exists:
            latest = (
                self.get_queryset()
                .deprecated()
                .related_history(origin_id)
                .order_by('-created_at')
                .first()
            )

            if latest:
                latest.is_deprecated = False
                latest.save(update_fields=['is_deprecated'])

    def get_history(self, origin_id: int):
        """Возвращает историю изменений конкретной анкеты, отсортированную от новых к старым."""
        return (
            self.get_queryset()
            .related_history(origin_id)
            .with_full_hierarchy()
            .order_by('-created_at')
        )
