from django.db.models import Q, QuerySet
from django.utils.timezone import now

from apps.checklists.interfaces import IResultRepository, ITemplateRepository
from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup,
)


class DjangoTemplateRepository(ITemplateRepository):
    """Реализация хранилища шаблонов с использованием Django ORM."""

    def get_active_template(
        self, equipment_uid: str, checklist_type: str
    ) -> Template | None:
        return (
            Template.objects.prefetch_related('groups__fields__choices')
            .filter(
                equipment_uid=equipment_uid,
                checklist_type=checklist_type,
                is_deprecated=False,
            )
            .first()
        )

    def deprecate_templates(self, equipment_uid: str, checklist_type: str) -> None:
        Template.objects.filter(
            equipment_uid=equipment_uid,
            checklist_type=checklist_type,
            is_deprecated=False,
        ).update(is_deprecated=True)

    def save_template_hierarchy(
        self, template_data: dict, groups_data: list
    ) -> Template:
        template = Template.objects.create(**template_data)
        for group_data in groups_data:
            fields_data = group_data.pop('fields', [])
            group = TemplateFieldGroup.objects.create(template=template, **group_data)

            for field_data in fields_data:
                choices_data = field_data.pop('choices', [])
                field = TemplateField.objects.create(group=group, **field_data)

                if choices_data:
                    FieldChoice.objects.bulk_create([
                        FieldChoice(field=field, **c) for c in choices_data
                    ])
        return template

    def get_unique_equipments(self) -> list[str]:
        return list(
            Template.objects.filter(is_deprecated=False)
            .values_list('equipment_uid', flat=True)
            .distinct()
        )

    def get_template_history(self, equipment_uid: str, checklist_type: str) -> QuerySet:
        return (
            Template.objects.filter(
                equipment_uid=equipment_uid, checklist_type=checklist_type
            )
            .prefetch_related('groups__fields__choices')
            .order_by('-created_at')
        )

    def delete_template(self, template: Template) -> None:
        template.delete()

    def restore_latest_deprecated_template(
        self, equipment_uid: str, checklist_type: str
    ) -> None:
        active_exists = Template.objects.filter(
            equipment_uid=equipment_uid,
            checklist_type=checklist_type,
            is_deprecated=False,
        ).exists()

        if not active_exists:
            latest_deprecated = (
                Template.objects.filter(
                    equipment_uid=equipment_uid,
                    checklist_type=checklist_type,
                    is_deprecated=True,
                )
                .order_by('-created_at')
                .first()
            )

            if latest_deprecated:
                latest_deprecated.is_deprecated = False
                latest_deprecated.save(update_fields=['is_deprecated'])


class DjangoResultRepository(IResultRepository):
    """Реализация хранилища анкет с использованием Django ORM."""

    def get_result_by_id(self, result_id: int) -> ChecklistResult:
        return ChecklistResult.objects.get(id=result_id)

    def save_result_with_answers(
        self, result_data: dict, answers_data: list
    ) -> ChecklistResult:
        result = ChecklistResult.objects.create(**result_data)
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
        return result

    def deprecate_result(self, result: ChecklistResult) -> None:
        result.is_deprecated = True
        result.save(update_fields=['is_deprecated'])

    def upsert_signature(
        self, result: ChecklistResult, role: str, user_uid: str
    ) -> tuple[ChecklistSignature, bool]:
        signature, created = ChecklistSignature.objects.get_or_create(
            result=result, role=role, defaults={'user_uid': user_uid}
        )
        if not created:
            signature.user_uid = user_uid
            signature.signed_at = now()
            signature.save(update_fields=['user_uid', 'signed_at'])
        return signature, created

    def get_result_history(self, origin_id: int) -> QuerySet:
        return (
            ChecklistResult.objects.filter(Q(id=origin_id) | Q(origin_id=origin_id))
            .select_related('template')
            .prefetch_related('answers__field')
            .order_by('-created_at')
        )

    def delete_result(self, result: ChecklistResult) -> None:
        result.delete()

    def restore_latest_deprecated_result(self, origin_id: int) -> None:
        active_exists = ChecklistResult.objects.filter(
            Q(id=origin_id) | Q(origin_id=origin_id), is_deprecated=False
        ).exists()

        if not active_exists:
            latest_deprecated = (
                ChecklistResult.objects.filter(
                    Q(id=origin_id) | Q(origin_id=origin_id), is_deprecated=True
                )
                .order_by('-created_at')
                .first()
            )

            if latest_deprecated:
                latest_deprecated.is_deprecated = False
                latest_deprecated.save(update_fields=['is_deprecated'])
