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


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'equipment_uid', 'checklist_type', 'is_deprecated', 'created_at', 'updated_at')
    list_filter = ('checklist_type', 'is_deprecated')
    search_fields = ('equipment_uid',)
    inlines = [TemplateFieldInline]


@admin.register(TemplateField)
class TemplateFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'template', 'field_type', 'order')
    list_filter = ('field_type',)
    inlines = [FieldChoiceInline]


class ResultAnswerInline(admin.TabularInline):
    model = ChecklistAnswer
    extra = 0
    readonly_fields = ('field', 'value')


@admin.register(ChecklistResult)
class ChecklistResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_equipment', 'user_uid', 'created_at', 'updated_at')
    search_fields = ('user_uid', 'template__equipment_uid')
    inlines = [ResultAnswerInline]

    @admin.display(description='Оборудование', ordering='template__equipment_uid')
    def get_equipment(self, obj):
        return obj.template.equipment_uid
