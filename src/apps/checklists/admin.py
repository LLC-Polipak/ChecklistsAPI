import nested_admin
from django.contrib import admin, messages
from django.db import models
from django.forms import Textarea, TextInput
from django.utils.safestring import mark_safe

from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistAttachment,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup,
    TemplateQCMetadata,
)
from apps.checklists.services import TemplateService


class TemplateQCMetadataInline(nested_admin.NestedStackedInline):
    """Вложенный интерфейс для управления метаданными контроля качества (ПКК)."""

    model = TemplateQCMetadata
    extra = 0
    can_delete = False


class FieldChoiceInline(nested_admin.NestedTabularInline):
    """Вложенный интерфейс для управления вариантами ответов поля."""

    model = FieldChoice
    extra = 0
    classes = ['collapse']


class TemplateFieldInline(nested_admin.NestedTabularInline):
    """Вложенный интерфейс для управления полями внутри группы шаблона."""

    model = TemplateField
    extra = 0
    fields = ('name', 'field_type', 'is_required', 'order', 'default_value', 'metadata')
    inlines = [FieldChoiceInline]

    formfield_overrides = {
        models.TextField: {
            'widget': TextInput(attrs={'size': '15', 'placeholder': 'Значение...'})
        },
        models.JSONField: {
            'widget': Textarea(attrs={'rows': 5, 'cols': 25, 'placeholder': '{}'})
        },
    }


class TemplateFieldGroupInline(nested_admin.NestedStackedInline):
    """Вложенный интерфейс для управления группами полей шаблона."""

    model = TemplateFieldGroup
    extra = 0
    inlines = [TemplateFieldInline]


@admin.action(description='Сделать копию (Черновик) выбранных шаблонов')
def clone_templates_action(modeladmin, request, queryset):
    """Кастомное действие для глубокого копирования шаблонов."""
    count = 0
    for template in queryset:
        new_uid = f'{template.equipment_uid}-COPY-{template.id}'
        TemplateService.clone_template(template, new_equipment_uid=new_uid)
        count += 1

    modeladmin.message_user(
        request, f'Успешно создано {count} копий шаблонов.', messages.SUCCESS
    )


@admin.register(Template)
class TemplateAdmin(nested_admin.NestedModelAdmin):
    """Административный интерфейс для модели шаблонов чек-листов."""

    list_display = (
        'id',
        'name',
        'checklist_type',
        'get_is_fillable',
        'get_is_draft',
        'get_is_deprecated',
        'created_at',
        'updated_at',
    )
    list_filter = (
        'is_draft',
        'is_fillable',
        'checklist_type',
        'is_deprecated',
        'created_at',
        'updated_at',
    )
    search_fields = ('name', 'equipment_uid')

    inlines = [TemplateQCMetadataInline, TemplateFieldGroupInline]

    readonly_fields = ('created_at', 'updated_at')
    ordering = ['is_deprecated', '-created_at']

    date_hierarchy = 'created_at'

    actions = [clone_templates_action]

    @admin.display(description='Заполнение', ordering='is_fillable')
    def get_is_fillable(self, obj):
        """Форматирует отображение статуса возможности заполнения чек-листа по шаблону."""
        if obj.is_fillable:
            return mark_safe('<span style="color: #16A34A;">Доступно✍</span>')
        return mark_safe(
            '<span style="color: #6B7280; font-style: italic;">Справочник📋</span>'
        )

    @admin.display(description='Черновик', ordering='is_draft')
    def get_is_draft(self, obj):
        """Форматирует отображение статуса черновика шаблона."""
        if obj.is_draft:
            return mark_safe(
                '<span style="color: #D97706; font-weight: bold;">📝 Да</span>'
            )
        return 'Нет'

    @admin.display(description='Актуальность', ordering='is_deprecated')
    def get_is_deprecated(self, obj):
        """Форматирует отображение статуса неактуальности шаблона."""
        if obj.is_deprecated:
            return mark_safe('<span style="color: #9CA3AF;">Устарел❌(В архиве)</span>')
        return mark_safe('<span style="color: #16A34A;">Актуальный</span>')


@admin.register(TemplateFieldGroup)
class TemplateFieldGroupAdmin(admin.ModelAdmin):
    """Самостоятельный интерфейс управления группами шаблонов.

    Полезен для массового редактирования и сквозного поиска.
    """

    list_display = ('name', 'template', 'order', 'page_break')
    list_filter = ('template__checklist_type', 'page_break')
    search_fields = ('name', 'template__name', 'template__equipment_uid')
    raw_id_fields = ('template',)


@admin.register(TemplateField)
class TemplateFieldAdmin(admin.ModelAdmin):
    """Самостоятельный интерфейс управления отдельными полями шаблона."""

    list_display = (
        'name',
        'get_template_name',
        'group',
        'field_type',
        'get_is_required',
    )
    list_filter = ('field_type', 'is_required', 'group__template__checklist_type')
    search_fields = ('name', 'group__name', 'group__template__name')
    raw_id_fields = ('group',)

    @admin.display(description='Шаблон', ordering='group__template__name')
    def get_template_name(self, obj):
        """Возвращает имя шаблона, к которому привязано поле."""
        return obj.group.template.name

    @admin.display(description='Обязатеное поле')
    def get_is_required(self, obj):
        """Возвращает имя шаблона, к которому привязано поле."""
        return 'Да' if obj.is_required else 'Нет'


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
    readonly_fields = ('field', 'get_is_violation', 'value', 'comment')
    fields = ('field', 'value', 'comment', 'get_is_violation')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        """Запретить ручное добавление ответов через админку."""
        return False

    @admin.display(description='Отклонение')
    def get_is_violation(self, obj):
        """Форматирует отображение метки отклонений у поля ответа."""
        if obj.is_violation:
            return mark_safe(
                '<span style="color: #DC2626; font-weight: bold;">⚠️ Да</span>'
            )
        return mark_safe('<span style="color: #16A34A;">Нет</span>')


class ChecklistAttachmentInline(admin.TabularInline):
    """Интерфейс для вывода прикрепленных файлов в админке."""

    model = ChecklistAttachment
    extra = 0
    readonly_fields = ('uploaded_at',)


@admin.register(ChecklistResult)
class ChecklistResultAdmin(admin.ModelAdmin):
    """Интерфейс администрирования Заполненных Анкет.

    Использует raw_id_fields для оптимизации SQL-запросов при большом количестве связей.
    """

    list_display = (
        'id',
        'get_template_name',
        'source_service',
        'shift_number',
        'get_is_draft',
        'is_completed',
        'get_is_deprecated',
        'get_has_violations',
        'created_at',
    )
    list_filter = (
        'is_draft',
        'is_completed',
        'has_violations',
        'is_deprecated',
        'source_service',
        'shift_number',
        'template__checklist_type',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'user_uid',
        'template__name',
        'template__equipment_uid',
        'external_id',
        'source_service',
    )
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('template', 'origin')
    inlines = [
        ChecklistSignatureInline,
        ChecklistAnswerInline,
        ChecklistAttachmentInline,
    ]

    list_select_related = ('template',)

    ordering = ['is_deprecated', '-created_at']

    date_hierarchy = 'created_at'

    @admin.display(description='Название шаблона', ordering='template__name')
    def get_template_name(self, obj):
        """Получить название из связанного шаблона."""
        return obj.template.name

    @admin.display(description='Отклонения', ordering='has_violations')
    def get_has_violations(self, obj):
        """Метод для понятной простому человеку отрисовки отклонений в анкете."""
        if obj.has_violations:
            return mark_safe(
                '<span style="color: #DC2626; font-weight: bold;">⚠️ Да</span>'
            )
        return mark_safe('<span style="color: #16A34A;">Нет</span>')

    @admin.display(description='Черновик', ordering='is_draft')
    def get_is_draft(self, obj):
        """Метод для понятной простому человеку отрисовки статуса черновика анкеты."""
        if obj.is_draft:
            return mark_safe(
                '<span style="color: #D97706; font-weight: bold;">📝 Да</span>'
            )
        return 'Нет (Чистовик)'

    @admin.display(description='Актуальность', ordering='is_deprecated')
    def get_is_deprecated(self, obj):
        """Метод для понятной простому человеку отрисовки неактуальности анкеты."""
        if obj.is_deprecated:
            return mark_safe('<span style="color: #9CA3AF;">Устарел (В архиве)</span>')
        return mark_safe('<span style="color: #16A34A;">Актуальный</span>')


@admin.register(ChecklistAnswer)
class ChecklistAnswerAdmin(admin.ModelAdmin):
    """Самостоятельный интерфейс для просмотра ответов пользователей.

    Облегчает аналитикам поиск конкретных ответов на конкретные поля
    по всем анкетам сразу.
    """

    list_display = ('id', 'get_field_name', 'value', 'is_violation', 'get_result_user')
    list_filter = ('is_violation', 'field__field_type')
    search_fields = (
        'value',
        'comment',
        'field__name',
        'result__user_uid',
        'result__external_id',
    )
    raw_id_fields = ('result', 'field')
    readonly_fields = ('result', 'field', 'value', 'comment', 'is_violation')

    @admin.display(description='Поле', ordering='field__name')
    def get_field_name(self, obj):
        """Возвращает имя поля, к которому привязан ответ."""
        return obj.field.name

    @admin.display(description='Пользователь', ordering='result__user_uid')
    def get_result_user(self, obj):
        """Возвращает UID'а пользователя, который заполнил данный чек-лист."""
        return obj.result.user_uid

    def has_add_permission(self, request):
        """Ответы генерируются только через API, запрещаем создание вручную."""
        return False
