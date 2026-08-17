from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.checklists.constants import SignatureRoles
from apps.checklists.interfaces import IResultRepository, ITemplateRepository


class TemplateService:
    """
    Сервис управления бизнес-логикой Шаблонов чек-листов.
    Отвечает за версионирование (создание новых версий поверх старых)
    и проверку целостности данных при редактировании.
    """

    def __init__(self, repository: ITemplateRepository):
        self.repository = repository

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

        self.repository.deprecate_templates(
            validated_data.get('equipment_uid'), validated_data.get('checklist_type')
        )

        return self.repository.save_template_hierarchy(validated_data, groups_data)

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
            self.repository.save_template_hierarchy({'id': instance.id}, groups_data)

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

        equipment_uid = instance.equipment_uid
        checklist_type = instance.checklist_type

        self.repository.delete_template(instance)
        self.repository.restore_latest_deprecated_template(equipment_uid, checklist_type)


class ChecklistResultService:
    """
    Сервис управления бизнес-логикой Заполненных Анкет (Результатов).
    Отвечает за Аудиторский след (Audit Trail), проверку подписей и
    отслеживание состояний (Черновик / Чистовик / Завершено).
    """

    def __init__(self, repository: IResultRepository):
        self.repository = repository

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

        result = self.repository.save_result_with_answers(validated_data, answers_data)

        self.repository.upsert_signature(result, SignatureRoles.AUTHOR, result.user_uid)
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

        self.repository.deprecate_result(instance)

        validated_data['origin'] = instance.origin or instance
        new_result = self.repository.save_result_with_answers(validated_data, answers_data)

        for old_sig in instance.signatures.all():
            self.repository.upsert_signature(new_result, old_sig.role, old_sig.user_uid)

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
        result = self.repository.get_result_by_id(result_id)

        if result.is_draft:
            raise ValidationError(
                'Нельзя подписать черновик. Сначала сохраните анкету как чистовик.'
            )

        if result.is_deprecated:
            raise ValidationError('Нельзя подписать устаревшую анкету.')

        if result.is_completed and role != SignatureRoles.READER:
            raise ValidationError('Анкета закрыта. Разрешены только подписи Читателя.')

        _signature, created = self.repository.upsert_signature(result, role, user_uid)
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

        self.repository.delete_result(instance)
        self.repository.restore_latest_deprecated_result(origin_id)
