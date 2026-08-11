from django.contrib import admin

from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup,
)


class TemplateFieldGroupInline(admin.StackedInline):
    model = TemplateFieldGroup
    extra = 0
    show_change_link = True


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'equipment_uid',
        'checklist_type',
        'is_deprecated',
        'created_at',
        'updated_at',
    )
    list_filter = ('checklist_type', 'is_deprecated')
    search_fields = ('equipment_uid',)
    inlines = [TemplateFieldGroupInline]
    readonly_fields = ('created_at', 'updated_at')


class TemplateFieldInline(admin.TabularInline):
    model = TemplateField
    extra = 0
    show_change_link = True


@admin.register(TemplateFieldGroup)
class TemplateFieldGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'template', 'order')
    list_filter = ('template__checklist_type',)
    search_fields = ('name', 'template__equipment_uid')
    inlines = [TemplateFieldInline]


class FieldChoiceInline(admin.TabularInline):
    model = FieldChoice
    extra = 0


@admin.register(TemplateField)
class TemplateFieldAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'group', 'field_type', 'is_required', 'order')
    list_filter = ('field_type', 'is_required', 'group__template__checklist_type')
    search_fields = ('name', 'group__template__equipment_uid')
    inlines = [FieldChoiceInline]


class ChecklistSignatureInline(admin.TabularInline):
    model = ChecklistSignature
    extra = 0
    readonly_fields = ('role', 'user_uid', 'signed_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ChecklistAnswerInline(admin.TabularInline):
    model = ChecklistAnswer
    extra = 0
    readonly_fields = ('field', 'value', 'comment')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChecklistResult)
class ChecklistResultAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'get_equipment',
        'user_uid',
        'shift_number',
        'is_completed',
        'is_deprecated',
        'origin_id',
        'created_at',
    )

    list_filter = (
        'is_completed',
        'is_deprecated',
        'shift_number',
        'template__checklist_type',
    )
    search_fields = ('user_uid', 'template__equipment_uid')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('template', 'origin')

    inlines = [ChecklistSignatureInline, ChecklistAnswerInline]

    @admin.display(description='Оборудование', ordering='template__equipment_uid')
    def get_equipment(self, obj):
        return obj.template.equipment_uid
