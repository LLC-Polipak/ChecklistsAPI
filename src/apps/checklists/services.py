"""Сервисы для управления бизнес-логикой шаблонов и результатов чек-листов."""
import datetime

from django.db import transaction
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError

from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistAttachment,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup,
)


class TemplateService:
    """
    Сервис управления бизнес-логикой Шаблонов чек-листов.

    Отвечает за версионирование (создание новых версий поверх старых)
    и проверку целостности данных при редактировании.
    """

    @classmethod
    @transaction.atomic
    def create_template(cls, validated_data: dict) -> Template:
        """
        Создать новую версию шаблона.

        Бизнес-правила:
        1. Если для данного оборудования и типа проверки уже существовал шаблон,
        он помечается как устаревший (Soft Delete / Deprecation).
        2. Иерархия (Группы -> Поля -> Варианты выбора) сохраняется атомарно.
        """
        groups_data = validated_data.pop('groups', [])
        is_draft = validated_data.get('is_draft', False)

        if not is_draft:
            Template.objects.deprecate_all(
                validated_data.get('equipment_uid'),
                validated_data.get('checklist_type')
            )

        template = Template.objects.create(**validated_data)
        cls._save_hierarchy(template, groups_data)
        return template

    @classmethod
    @transaction.atomic
    def update_template(cls, instance: Template, validated_data: dict) -> Template:
        """
        Полностью перезаписать иерархию полей существующего шаблона.

        Шаблон категорически запрещено изменять, если по нему уже заполнялись анкеты,
        так как это нарушит структуру исторических данных. Для изменения нужно
        создавать новую версию шаблона через метод create_template.
        """
        if instance.results.exists():
            raise ValidationError(
                "Невозможно изменить шаблон, по нему уже есть анкеты.")

        groups_data = validated_data.pop('groups', None)
        was_draft = instance.is_draft

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        is_draft = instance.is_draft

        if was_draft and not is_draft:
            Template.objects.deprecate_all(
                instance.equipment_uid,
                instance.checklist_type,
                exclude_id=instance.id
            )

        instance.save()

        if groups_data is not None:
            instance.groups.all().delete()
            cls._save_hierarchy(instance, groups_data)

        return instance

    @classmethod
    @transaction.atomic
    def delete_template(cls, instance):
        """
        Удалить шаблон с возможностью отката версии.

        Бизнес-правила:
        1. Нельзя удалить шаблон, если по нему есть заполненные результаты.
        2. При удалении текущего активного шаблона система попытается "воскресить"
        предыдущую устаревшую версию, чтобы оборудование не осталось без бланка проверки.
        """
        eq_uid = instance.equipment_uid
        c_type = instance.checklist_type
        instance.delete()
        Template.objects.restore_latest_deprecated(eq_uid, c_type)

    @classmethod
    def _save_hierarchy(cls, template: Template, groups_data: list):
        """Выполнить сохранение дерева структуры шаблона."""
        for group_data in groups_data:
            fields_data = group_data.pop('fields', [])
            group = TemplateFieldGroup.objects.create(template=template, **group_data)

            for field_data in fields_data:
                choices_data = field_data.pop('choices', [])
                field = TemplateField.objects.create(group=group, **field_data)

                if choices_data:
                    FieldChoice.objects.bulk_create(
                        [FieldChoice(field=field, **c) for c in choices_data]
                    )


class ChecklistResultService:
    """
    Сервис управления бизнес-логикой Заполненных Анкет (Результатов).

    Отвечает за Аудиторский след (Audit Trail), проверку подписей и
    отслеживание состояний (Черновик / Чистовик / Завершено).
    """

    @classmethod
    @transaction.atomic
    def submit_result(cls, validated_data: dict):
        """
        Выполнить первичное сохранение ответов пользователя.

        Составитель анкеты автоматически подписывает документ ролью AUTHOR.
        """
        answers_data = validated_data.pop('validated_answers')

        validated_data.pop('answers', None)
        validated_data.pop('equipment_uid', None)
        validated_data.pop('checklist_type', None)

        result = ChecklistResult.objects.create(**validated_data)

        cls._save_answers(result, answers_data)
        cls._upsert_signature(result, "Составитель", result.user_uid)

        return result

    @classmethod
    @transaction.atomic
    def update_result(cls, instance, validated_data: dict):
        """
        Обновить ответы анкеты с сохранением Аудиторского следа.

        Бизнес-правила:
        1. Утвержденную (закрытую) анкету изменять нельзя.
        2. Вместо перезаписи данных старая анкета помечается как устаревшая
           (is_deprecated=True), и создается её полная копия с новыми ответами.
        3. Все существующие подписи переносятся на новую версию анкеты.
        """
        answers_data = validated_data.pop('validated_answers')

        validated_data.pop('answers', None)
        validated_data.pop('equipment_uid', None)
        validated_data.pop('checklist_type', None)

        ChecklistResult.objects.deprecate(instance)

        validated_data['origin'] = instance.origin if instance.origin else instance
        new_result = ChecklistResult.objects.create(**validated_data)
        cls._save_answers(new_result, answers_data)

        for old_sig in instance.signatures.all():
            cls._upsert_signature(new_result, old_sig.role, old_sig.user_uid)

        attachments_to_copy = [
            ChecklistAttachment(result=new_result, file=old_att.file)
            for old_att in instance.attachments.all()
        ]
        ChecklistAttachment.objects.bulk_create(attachments_to_copy)

        return new_result

    @classmethod
    def sign_result(cls, result: ChecklistResult, role: str, user_uid: str, is_closing: bool = False):
        """
        Добавить электронную подпись к анкете.

        Бизнес-правила:
        1. Черновик (is_draft=True) подписать нельзя.
        2. Устаревшую версию (is_deprecated=True) подписать нельзя.
        3. Если анкета уже закрыта, новую подпись может поставить только Читатель.
        4. Если подпись ставит Утверждающий, анкета переходит в статус Завершено.
        """
        signature, created = cls._upsert_signature(result, role, user_uid)

        # Если эта подпись является закрывающей (финальной)
        if is_closing and not result.is_completed:
            result.is_completed = True
            result.save(update_fields=['is_completed'])

        return result, created

    @classmethod
    @transaction.atomic
    def delete_result(cls, instance):
        """
        Удалить анкету.

        При удалении активной версии (ошибочное исправление),
        система "воскрешает" предыдущую устаревшую версию.
        """
        origin_id = instance.origin_id or instance.id
        instance.delete()
        ChecklistResult.objects.restore_latest_deprecated(origin_id)

    @classmethod
    def add_attachment(cls, result_id: int, file_obj) -> ChecklistAttachment:
        """
        Прикрепить файл к анкете.

        Бизнес-правила:
        1. Запрещено добавлять файлы к историческим версиям анкеты.
        2. Запрещено добавлять файлы к анкете, если она уже завершена.

        Args:
            result_id: Идентификатор анкеты, к которой крепится файл.
            file_obj: Объект загруженного файла.

        Returns:
            ChecklistAttachment: Созданный объект вложения.
        """
        result = ChecklistResult.objects.get(id=result_id)

        if result.is_deprecated:
            raise ValidationError('Нельзя добавлять файлы к устаревшей анкете.')
        if result.is_completed:
            raise ValidationError('Анкета закрыта, добавление файлов запрещено.')

        return ChecklistAttachment.objects.create(result=result, file=file_obj)

    @classmethod
    def delete_attachment(cls, attachment: ChecklistAttachment):
        """
        Удалить файл из анкеты.

        Бизнес-правила:
        1. Запрещено удалять файл у завершенной анкеты.
        2. Запрещено удалять файл у исторических версий анкеты.
        """
        if attachment.result.is_deprecated:
            raise ValidationError("Нельзя удалять файлы из устаревшей анкеты.")
        if attachment.result.is_completed:
            raise ValidationError("Анкета закрыта, удаление файлов запрещено.")

        if attachment.file:
            attachment.file.delete(save=False)

        attachment.delete()

    @classmethod
    def _save_answers(cls, result: ChecklistResult, answers_data: list):
        """Выполнить сохранение ответов анкеты и проставить метки отклонений."""
        has_violations = False
        answers = []

        for item in answers_data:
            field = item['field']
            value = item['value']

            is_violation = cls._check_violation(field, value)
            if is_violation:
                has_violations = True

            answers.append(
                ChecklistAnswer(
                    result=result,
                    field=field,
                    value=value,
                    comment=item['comment'],
                    is_violation=is_violation
                )
            )

        ChecklistAnswer.objects.bulk_create(answers)

        if has_violations:
            result.has_violations = True
            result.save(update_fields=['has_violations'])

    @classmethod
    def _upsert_signature(cls, result: ChecklistResult, role: str, user_uid: str):
        """Обновить или создать электронную подпись."""
        signature, created = ChecklistSignature.objects.get_or_create(
            result=result, role=role, user_uid=user_uid
        )

        if not created:
            signature.signed_at = now()
            signature.save(update_fields=['signed_at'])

        return signature, created

    @classmethod
    def _check_violation(cls, field: TemplateField, value: str) -> bool:
        """Анализировать ответ пользователя на предмет отклонений."""
        meta = field.metadata
        if not meta or value == "":
            return False

        handlers = {
            'CHECKBOX': cls._is_bool_violation,
            'RADIO': cls._is_bool_violation,
            'CHOICE': cls._is_choice_violation,
            'NUMBER': cls._is_numeric_violation,
            'DATE': cls._is_date_violation,
            'AUTO_DATE': cls._is_date_violation,
        }

        handler = handlers.get(field.field_type)
        if not handler:
            return False

        try:
            return handler(meta, value)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _is_bool_violation(meta: dict, value: str) -> bool:
        """Проверить отклонение для логических типов."""
        if 'violation_on' in meta:
            return str(value).lower() == str(meta['violation_on']).lower()
        return False

    @staticmethod
    def _is_choice_violation(meta: dict, value: str) -> bool:
        """Проверить отклонение для списков выбора."""
        if 'violation_choices' in meta:
            return value in meta['violation_choices']
        return False

    @staticmethod
    def _is_numeric_violation(meta: dict, value: str) -> bool:
        """Проверить отклонение для числовых значений."""
        num_val = float(value)
        if 'min_valid' in meta and num_val < float(meta['min_valid']):
            return True
        return bool('max_valid' in meta and num_val > float(meta['max_valid']))

    @staticmethod
    def _is_date_violation(meta: dict, value: str) -> bool:
        """Проверить отклонение для дат."""
        answer_date = datetime.date.fromisoformat(value)
        today = datetime.date.today()
        days_diff = (today - answer_date).days

        if 'max_days_ago' in meta and days_diff > int(meta['max_days_ago']):
            return True

        if 'min_days_ahead' in meta:
            days_ahead = -days_diff
            if days_ahead < int(meta['min_days_ahead']):
                return True
        return False
