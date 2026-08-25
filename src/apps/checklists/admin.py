"""Конфигурация административной панели для управления шаблонами и результатами."""

from django.contrib import admin

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


class TemplateFieldGroupInline(admin.StackedInline):
    """Интерфейс для вложенного управления группами полей из окна шаблона."""

    model = TemplateFieldGroup
    extra = 0
    show_change_link = True


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    """
    Интерфейс администрирования Шаблонов.

    Позволяет управлять метаданными шаблонов и их вложенными группами.
    """

    list_display = (
        'id',
        'equipment_uid',
        'checklist_type',
        'is_deprecated',
        'created_at',
    )
    list_filter = ('checklist_type', 'is_deprecated')
    search_fields = ('equipment_uid',)
    inlines = [TemplateFieldGroupInline]
    readonly_fields = ('created_at', 'updated_at')
    ordering = ['is_deprecated', '-created_at']


class TemplateFieldInline(admin.TabularInline):
    """Интерфейс для вложенного добавления полей внутрь группы."""

    model = TemplateField
    extra = 0
    show_change_link = True
    fields = ('name', 'field_type', 'is_required', 'order', 'default_value', 'metadata')


@admin.register(TemplateFieldGroup)
class TemplateFieldGroupAdmin(admin.ModelAdmin):
    """Интерфейс управления Группами полей (промежуточный слой иерархии)."""

    list_display = ('id', 'name', 'get_template_info', 'order')
    list_filter = ('template__checklist_type', 'template__equipment_uid')
    search_fields = ('name', 'template__equipment_uid')
    inlines = [TemplateFieldInline]

    list_select_related = ('template',)

    @admin.display(
        description='Шаблон (Оборудование / Тип)', ordering='template__equipment_uid'
    )
    def get_template_info(self, obj):
        """Получить строковое представление шаблона для списка."""
        return f'{obj.template.equipment_uid} ({obj.template.get_checklist_type_display()})'


class FieldChoiceInline(admin.TabularInline):
    """Интерфейс для добавления вариантов ответов (только для CHOICE)."""

    model = FieldChoice
    extra = 0


@admin.register(TemplateField)
class TemplateFieldAdmin(admin.ModelAdmin):
    """Интерфейс управления конкретными Полями анкеты."""

    list_display = (
        'id',
        'name',
        'get_group_name',
        'get_template_info',
        'field_type',
        'is_required',
        'default_value',
        'order',
    )
    list_filter = ('field_type', 'is_required', 'group__template__checklist_type')
    search_fields = ('name', 'group__template__equipment_uid')
    inlines = [FieldChoiceInline]

    list_select_related = ('group', 'group__template')

    @admin.display(description='Группа', ordering='group__name')
    def get_group_name(self, obj):
        """Получить имя группы, к которой принадлежит поле."""
        return obj.group.name

    @admin.display(description='Шаблон', ordering='group__template__equipment_uid')
    def get_template_info(self, obj):
        """Получить информацию о шаблоне через группу."""
        return f'{obj.group.template.equipment_uid} ({obj.group.template.get_checklist_type_display()})'


class ChecklistSignatureInline(admin.TabularInline):
    """Интерфейс для вывода списка подписей в режиме только для чтения."""

    model = ChecklistSignature
    extra = 0
    readonly_fields = ('role', 'user_uid', 'signed_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        """Запретить ручное добавление подписей через админку."""
        return False


class ChecklistAnswerInline(admin.TabularInline):
    """Интерфейс для вывода ответов пользователя в режиме только для чтения."""

    model = ChecklistAnswer
    extra = 0
    readonly_fields = ('field',)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        """Запретить ручное добавление ответов через админку."""
        return False


class ChecklistAttachmentInline(admin.TabularInline):
    """Интерфейс для вывода прикрепленных файлов в админке."""

    model = ChecklistAttachment
    extra = 0
    readonly_fields = ('uploaded_at',)


@admin.register(ChecklistResult)
class ChecklistResultAdmin(admin.ModelAdmin):
    """
    Интерфейс администрирования Заполненных Анкет.

    Использует raw_id_fields для оптимизации SQL-запросов при большом количестве связей.
    """

    list_display = (
        'id',
        'get_equipment',
        'user_uid',
        'source_service',
        'shift_number',
        'is_draft',
        'is_completed',
        'is_deprecated',
        'created_at',
    )
    list_filter = (
        'is_draft',
        'is_completed',
        'is_deprecated',
        'source_service',
        'shift_number',
        'template__checklist_type',
    )
    search_fields = (
        'user_uid',
        'template__equipment_uid',
        'external_id',
        'source_service',
    )
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('template', 'origin')
    inlines = [ChecklistSignatureInline, ChecklistAnswerInline, ChecklistAttachmentInline]

    list_select_related = ('template',)

    ordering = ['is_deprecated', '-created_at']

    @admin.display(description='Оборудование', ordering='template__equipment_uid')
    def get_equipment(self, obj):
        """Получить UID оборудования из связанного шаблона."""
        return obj.template.equipment_uid
