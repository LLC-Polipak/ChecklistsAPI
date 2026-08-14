from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.checklists.interfaces import IResultRepository, ITemplateRepository
from apps.checklists.models import ChecklistSignature


class TemplateService:
    def __init__(self, repo: ITemplateRepository):
        self.repo = repo

    @transaction.atomic
    def create_template(self, validated_data: dict):
        groups_data = validated_data.pop('groups', [])

        self.repo.deprecate_templates(
            validated_data.get('equipment_uid'), validated_data.get('checklist_type')
        )

        return self.repo.save_template_hierarchy(validated_data, groups_data)

    @transaction.atomic
    def update_template(self, instance, validated_data: dict):
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
            self.repo.save_template_hierarchy({'id': instance.id}, groups_data)

        return instance

    @transaction.atomic
    def delete_template(self, instance):
        if instance.results.exists():
            raise ValidationError(
                'Невозможно удалить шаблон, по нему уже есть заполненные анкеты.'
            )

        equipment_uid = instance.equipment_uid
        checklist_type = instance.checklist_type

        self.repo.delete_template(instance)
        self.repo.restore_latest_deprecated_template(equipment_uid, checklist_type)


class ChecklistResultService:
    def __init__(self, repo: IResultRepository):
        self.repo = repo

    @transaction.atomic
    def submit_result(self, validated_data: dict):
        answers_data = validated_data.pop('validated_answers')

        result = self.repo.save_result_with_answers(validated_data, answers_data)

        self.repo.upsert_signature(
            result, ChecklistSignature.Role.AUTHOR, result.user_uid
        )
        return result

    @transaction.atomic
    def update_result(self, instance, validated_data: dict):
        if instance.is_completed:
            raise ValidationError('Невозможно изменить анкету: она уже утверждена.')

        answers_data = validated_data.pop('validated_answers')

        self.repo.deprecate_result(instance)

        validated_data['origin'] = instance.origin or instance
        new_result = self.repo.save_result_with_answers(validated_data, answers_data)

        for old_sig in instance.signatures.all():
            self.repo.upsert_signature(new_result, old_sig.role, old_sig.user_uid)

        return new_result

    def sign_result(self, result_id: int, role: str, user_uid: str):
        result = self.repo.get_result_by_id(result_id)

        if result.is_deprecated:
            raise ValidationError('Нельзя подписать устаревшую анкету.')
        if result.is_completed and role != ChecklistSignature.Role.READER:
            raise ValidationError('Анкета закрыта. Разрешены только подписи Читателя.')

        _signature, created = self.repo.upsert_signature(result, role, user_uid)
        result.check_and_complete()

        return result, created

    @transaction.atomic
    def delete_result(self, instance):
        origin_id = instance.origin_id or instance.id

        self.repo.delete_result(instance)
        self.repo.restore_latest_deprecated_result(origin_id)
