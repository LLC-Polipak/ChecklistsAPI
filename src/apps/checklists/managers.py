"""Менеджеры моделей для инкапсуляции бизнес-логики запросов к БД."""

from django.db import models


class TemplateManager(models.Manager):
    """
    Менеджер для модели Template.

    Предоставляет высокоуровневые команды для работы с шаблонами,
    скрывая детали реализации фильтрации.
    """

    def get_active(self, equipment_uid: str, checklist_type: str):
        """
        Найти актуальный шаблон для заполнения анкеты.

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
        Мягко удалить (Soft Delete) все активные шаблоны указанного типа.

        Используется при создании новой версии шаблона для сохранения историчности.
        """
        (
            self.get_queryset()
            .active()
            .for_equipment(equipment_uid, checklist_type)
            .update(is_deprecated=True)
        )

    def get_unique_equipments(self):
        """Получить список уникальных идентификаторов оборудования."""
        return list(
            self.get_queryset()
            .active()
            .values_list('equipment_uid', flat=True)
            .distinct()
        )

    def restore_latest_deprecated(self, equipment_uid: str, checklist_type: str):
        """
        Выполнить откат удаления (Rollback).

        Если активных шаблонов не осталось, находит самую свежую
        устаревшую версию и делает её активной.
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
        """Вернуть хронологическую историю всех версий шаблона."""
        return (
            self.get_queryset()
            .for_equipment(equipment_uid, checklist_type)
            .with_full_hierarchy()
            .order_by('-created_at')
        )


class ChecklistResultManager(models.Manager):
    """Менеджер для управления результатами заполнения чек-листов."""

    def deprecate(self, result):
        """Пометить конкретную анкету как устаревшую при редактировании."""
        result.is_deprecated = True
        result.save(update_fields=['is_deprecated'])

    def restore_latest_deprecated(self, origin_id: int):
        """
        Восстановить предыдущую версию ответов.

        Срабатывает, если текущая активная версия анкеты была удалена.
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
        """Вернуть историю изменений конкретной анкеты от новых к старым."""
        return (
            self.get_queryset()
            .related_history(origin_id)
            .with_full_hierarchy()
            .order_by('-created_at')
        )
