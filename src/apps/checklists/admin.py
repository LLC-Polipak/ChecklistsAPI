from django.contrib import admin
from apps.checklists.models import Template, TemplateFieldGroup, TemplateField, FieldChoice, ChecklistResult, \
    ChecklistAnswer, ChecklistSignature


class TemplateFieldGroupInline(admin.StackedInline):
    """Вложенный интерфейс для управления группами полей из окна шаблона."""
    model = TemplateFieldGroup
    extra = 0
    show_change_link = True


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    """
    Интерфейс администрирования Шаблонов.
    Позволяет управлять метаданными шаблонов и их вложенными группами.
    """
    list_display = ('id', 'equipment_uid', 'checklist_type', 'is_deprecated', 'created_at')
    list_filter = ('checklist_type', 'is_deprecated')
    search_fields = ('equipment_uid',)
    inlines = [TemplateFieldGroupInline]
    readonly_fields = ('created_at', 'updated_at')


class TemplateFieldInline(admin.TabularInline):
    """Вложенный интерфейс для добавления полей внутрь группы."""
    model = TemplateField
    extra = 0
    show_change_link = True


@admin.register(TemplateFieldGroup)
class TemplateFieldGroupAdmin(admin.ModelAdmin):
    """Интерфейс управления Группами полей (Промежуточный слой иерархии)."""
    list_display = ('id', 'name', 'template', 'order')
    list_filter = ('template__checklist_type',)
    search_fields = ('name', 'template__equipment_uid')
    inlines = [TemplateFieldInline]


class FieldChoiceInline(admin.TabularInline):
    """Вложенный интерфейс для добавления вариантов ответов (только для CHOICE)."""
    model = FieldChoice
    extra = 0


@admin.register(TemplateField)
class TemplateFieldAdmin(admin.ModelAdmin):
    """Интерфейс управления конкретными Полями анкеты."""
    list_display = ('id', 'name', 'group', 'field_type', 'is_required', 'order')
    list_filter = ('field_type', 'is_required', 'group__template__checklist_type')
    search_fields = ('name', 'group__template__equipment_uid')
    inlines = [FieldChoiceInline]


class ChecklistSignatureInline(admin.TabularInline):
    """Вывод списка подписей в режиме только для чтения."""
    model = ChecklistSignature
    extra = 0
    readonly_fields = ('role', 'user_uid', 'signed_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ChecklistAnswerInline(admin.TabularInline):
    """Вывод всех ответов пользователя в режиме только для чтения."""
    model = ChecklistAnswer
    extra = 0
    readonly_fields = ('field', 'value', 'comment')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChecklistResult)
class ChecklistResultAdmin(admin.ModelAdmin):
    """
    Интерфейс администрирования Заполненных Анкет.
    Использует raw_id_fields для оптимизации SQL-запросов при большом количестве связей.
    """
    list_display = (
        'id', 'get_equipment', 'user_uid', 'shift_number',
        'is_draft', 'is_completed', 'is_deprecated', 'created_at'
    )

    list_filter = ('is_draft', 'is_completed', 'is_deprecated', 'shift_number', 'template__checklist_type')
    search_fields = ('user_uid', 'template__equipment_uid')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('template', 'origin')

    inlines = [ChecklistSignatureInline, ChecklistAnswerInline]

    @admin.display(description='Оборудование', ordering='template__equipment_uid')
    def get_equipment(self, obj):
        """Прокси-метод для отображения UID оборудования из связанного шаблона."""
        return obj.template.equipment_uid
