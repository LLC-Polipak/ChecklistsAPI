from django.contrib import admin
from apps.checklists.models import Template, TemplateField, FieldChoice, \
    ChecklistResult, ChecklistAnswer


class FieldChoiceInline(admin.TabularInline):
    model = FieldChoice
    extra = 0


class TemplateFieldInline(admin.StackedInline):
    model = TemplateField
    extra = 0
    show_change_link = True
    fields = ('name', 'field_type', 'is_required', 'order')


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'equipment_uid',
        'checklist_type',
        'is_deprecated',
        'created_at',
        'updated_at'
    )
    list_filter = ('checklist_type', 'is_deprecated')
    search_fields = ('equipment_uid',)
    inlines = [TemplateFieldInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TemplateField)
class TemplateFieldAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'template',
        'field_type',
        'is_required',
        'order')
    list_filter = ('field_type', 'is_required', 'template__checklist_type')
    search_fields = ('name', 'template__equipment_uid')
    inlines = [FieldChoiceInline]


class ChecklistAnswerInline(admin.TabularInline):
    model = ChecklistAnswer
    extra = 0
    readonly_fields = ('field', 'value')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChecklistResult)
class ChecklistResultAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'get_equipment',
        'user_uid',
        'is_deprecated',
        'origin_id',
        'created_at'
    )

    list_filter = ('is_deprecated', 'template__checklist_type')
    search_fields = ('user_uid', 'template__equipment_uid')
    readonly_fields = ('created_at', 'updated_at')
    # raw_id_fields = ('template', 'origin')

    inlines = [ChecklistAnswerInline]

    @admin.display(description='Оборудование',
                   ordering='template__equipment_uid')
    def get_equipment(self, obj):
        """
        Так как мы удалили equipment_uid из самой анкеты ради нормализации БД,
        достаем его для отображения в списке через связь с шаблоном.
        """

        return obj.template.equipment_uid
