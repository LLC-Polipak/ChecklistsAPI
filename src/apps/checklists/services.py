from django.db import transaction
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError

from apps.checklists.constants import SignatureRoles
from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup, ChecklistAttachment,
)


class TemplateService:
    """
    Сервис управления бизнес-логикой Шаблонов чек-листов.
    Отвечает за версионирование (создание новых версий поверх старых)
    и проверку целостности данных при редактировании.
    """

    @transaction.atomic
    def create_template(self, validated_data: dict):
        """
        Создает новую версию шаблона.

        Бизнес-правила:
        1. Если для данного оборудования и типа проверки уже существовал шаблон,
        он помечается как устаревший (Soft Delete / Deprecation).
        2. Иерархия (Группы -> Поля -> Варианты выбора) сохраняется атомарно.
        """
        groups_data = validated_data.pop('groups', [])

        Template.objects.deprecate_all(
            validated_data.get('equipment_uid'), validated_data.get('checklist_type')
        )

        template = Template.objects.create(**validated_data)

        self._save_hierarchy(template, groups_data)

        return template

    @transaction.atomic
    def update_template(self, instance, validated_data: dict):
        """
        Полностью перезаписывает иерархию полей существующего шаблона.
        Шаблон категорически запрещено изменять, если по нему уже заполнялись анкеты,
        так как это нарушит структуру исторических данных. Для изменения нужно
        создавать новую версию шаблона через метод create_template.
        """
        if instance.results.exists():
            raise ValidationError(
                'Невозможно изменить шаблон, по нему уже есть анкеты.'
            )

        groups_data = validated_data.pop('groups', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if groups_data is not None:
            instance.groups.all().delete()
            self._save_hierarchy(instance, groups_data)

        return instance

    @transaction.atomic
    def delete_template(self, instance):
        """
        Удаляет шаблон с возможностью отката версии.

        Бизнес-правила:
        1. Нельзя удалить шаблон, если по нему есть заполненные результаты.
        2. При удалении текущего активного шаблона система попытается "воскресить"
        предыдущую устаревшую версию, чтобы оборудование не осталось без бланка проверки.
        """
        if instance.results.exists():
            raise ValidationError(
                'Невозможно удалить шаблон, по нему уже есть заполненные анкеты.'
            )

        eq_uid = instance.equipment_uid
        c_type = instance.checklist_type

        instance.delete()
        Template.objects.restore_latest_deprecated(eq_uid, c_type)

    def _save_hierarchy(self, template: Template, groups_data: list):
        """Вспомогательный метод для сохранения дерева структуры шаблона."""
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

    @transaction.atomic
    def submit_result(self, validated_data: dict):
        """
        Первичное сохранение ответов пользователя.
        Составитель анкеты автоматически подписывает документ ролью AUTHOR.
        """
        answers_data = validated_data.pop('validated_answers')

        validated_data.pop('answers', None)
        validated_data.pop('equipment_uid', None)
        validated_data.pop('checklist_type', None)

        result = ChecklistResult.objects.create(**validated_data)

        self._save_answers(result, answers_data)
        self._upsert_signature(result, SignatureRoles.AUTHOR, result.user_uid)

        return result

    @transaction.atomic
    def update_result(self, instance, validated_data: dict):
        """
        Обновление ответов анкеты с сохранением Аудиторского следа.

        Бизнес-правила:
        1. Утвержденную (закрытую) анкету изменять нельзя.
        2. Вместо перезаписи данных старая анкета помечается как устаревшая (is_deprecated=True),
            и создается её полная копия с новыми ответами.
        3. Все существующие подписи переносятся на новую версию анкеты.
        """
        if instance.is_completed:
            raise ValidationError('Невозможно изменить анкету: она уже утверждена.')

        answers_data = validated_data.pop('validated_answers')

        validated_data.pop('answers', None)
        validated_data.pop('equipment_uid', None)
        validated_data.pop('checklist_type', None)

        ChecklistResult.objects.deprecate(instance)

        validated_data['origin'] = instance.origin if instance.origin else instance
        new_result = ChecklistResult.objects.create(**validated_data)
        self._save_answers(new_result, answers_data)

        for old_sig in instance.signatures.all():
            self._upsert_signature(new_result, old_sig.role, old_sig.user_uid)

        attachments_to_copy = [
            ChecklistAttachment(result=new_result, file=old_att.file)
            for old_att in instance.attachments.all()
        ]
        ChecklistAttachment.objects.bulk_create(attachments_to_copy)

        return new_result

    def sign_result(self, result_id: int, role: str, user_uid: str):
        """
        Добавление электронной подписи к анкете.

        Бизнес-правила:
        1. Черновик (is_draft=True) подписать нельзя.
        2. Устаревшую версию (is_deprecated=True) подписать нельзя.
        3. Если анкета уже закрыта, новую подпись может поставить только Читатель (READER).
        4. Если подпись ставит Утверждающий (APPROVER), анкета переходит в статус Завершено (is_completed=True).
        """
        result = ChecklistResult.objects.get(id=result_id)

        if result.is_draft:
            raise ValidationError(
                'Нельзя подписать черновик. Сначала сохраните анкету как чистовик.'
            )
        if result.is_deprecated:
            raise ValidationError('Нельзя подписать устаревшую анкету.')
        if result.is_completed and role != SignatureRoles.READER:
            raise ValidationError('Анкета закрыта. Разрешены только подписи Читателя.')

        signature, created = self._upsert_signature(result, role, user_uid)
        result.check_and_complete()

        return result, created

    @transaction.atomic
    def delete_result(self, instance):
        """
        Удаление анкеты.
        При удалении активной версии (ошибочное исправление),
        система "воскрешает" предыдущую устаревшую версию.
        """
        origin_id = instance.origin_id or instance.id
        instance.delete()
        ChecklistResult.objects.restore_latest_deprecated(origin_id)

    def add_attachment(self, result_id: int, file_obj) -> ChecklistAttachment:
        """
        Бизнес-логика прикрепления файла к анкете.

        Бизнес-правила (Business Rules):
        1. Запрещено добавлять файлы к историческим (устаревшим) версиям анкеты,
           так как они заморожены для аудита.
        2. Запрещено добавлять файлы к анкете, если она уже полностью утверждена
           и закрыта для изменений (is_completed=True).

        Args:
            result_id (int): Идентификатор анкеты, к которой крепится файл.
            file_obj (File): Объект загруженного файла из request.FILES.

        Returns:
            ChecklistAttachment: Созданный объект вложения.
        """
        result = ChecklistResult.objects.get(id=result_id)

        if result.is_deprecated:
            raise ValidationError(
                "Нельзя добавлять файлы к устаревшей анкете.")
        if result.is_completed:
            raise ValidationError(
                "Анкета закрыта, добавление файлов запрещено.")

        return ChecklistAttachment.objects.create(result=result, file=file_obj)

    def _save_answers(self, result: ChecklistResult, answers_data: list):
        """Вспомогательный метод для сохранения ответов анкеты."""
        answers = [
            ChecklistAnswer(
                result=result,
                field=item['field'],
                value=item['value'],
                comment=item['comment'],
            )
            for item in answers_data
        ]
        ChecklistAnswer.objects.bulk_create(answers)

    def _upsert_signature(self, result: ChecklistResult, role: str, user_uid: str):
        """Вспомогательный метод для подписи"""
        signature, created = ChecklistSignature.objects.get_or_create(
            result=result, role=role, defaults={'user_uid': user_uid}
        )
        if not created:
            signature.user_uid = user_uid
            signature.signed_at = now()
            signature.save(update_fields=['user_uid', 'signed_at'])
        return signature, created
