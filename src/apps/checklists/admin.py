"""Конфигурация административной панели для управления шаблонами и результатами."""
import nested_admin
from django.contrib import admin
from django.utils.html import format_html

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


class FieldChoiceInline(nested_admin.NestedTabularInline):
    """Вложенный интерфейс для управления вариантами ответов поля."""

    model = FieldChoice
    extra = 0
    classes = ['collapse']


class TemplateFieldInline(nested_admin.NestedTabularInline):
    """Вложенный интерфейс для управления полями внутри группы шаблона."""

    model = TemplateField
    extra = 0
    fields = (
        'name',
        'field_type',
        'is_required',
        'order',
        'default_value',
        'metadata'
    )
    inlines = [FieldChoiceInline]


class TemplateFieldGroupInline(nested_admin.NestedStackedInline):
    """Вложенный интерфейс для управления группами полей шаблона."""

    model = TemplateFieldGroup
    extra = 0
    inlines = [TemplateFieldInline]


@admin.register(Template)
class TemplateAdmin(nested_admin.NestedModelAdmin):
    """Административный интерфейс для модели шаблонов чек-листов."""

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

    inlines = [TemplateFieldGroupInline]

    readonly_fields = ('created_at', 'updated_at')
    ordering = ['is_deprecated', '-created_at']


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
    readonly_fields = ('field', 'is_violation')
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
        'has_violations',
        'created_at',
    )
    list_filter = (
        'has_violations',
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

    @admin.display(description='Отклонения', ordering='has_violations')
    def get_has_violations(self, obj):
        """Метод для понятной простому человеку отрисовки отклонений в анкете."""
        if obj.has_violations:
            return format_html(
                '<span style="color: #DC2626; font-weight: bold;">⚠️ Да</span>')
        return format_html('<span style="color: #16A34A;">Нет</span>')

    @admin.display(description='Черновик', ordering='is_draft')
    def get_is_draft(self, obj):
        """Метод для понятной простому человеку отрисовки статуса черновика анкеты."""
        if obj.is_draft:
            return format_html(
                '<span style="color: #D97706; font-weight: bold;">📝 Да</span>')
        return "Нет (Чистовик)"

    @admin.display(description='Устарела', ordering='is_deprecated')
    def get_is_deprecated(self, obj):
        """Метод для понятной простому человеку отрисовки неактуальности анкеты."""
        if obj.is_deprecated:
            return format_html(
                '<span style="color: #9CA3AF;">Да (В архиве)</span>')
        return "Нет"
