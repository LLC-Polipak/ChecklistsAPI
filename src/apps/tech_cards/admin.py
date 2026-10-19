import nested_admin
from django.contrib import admin

from apps.tech_cards.models import TechCard, TechCardParameter, TechCardSection


class ReadOnlyAdminMixin:
    """Миксин для отключения любых мутаций данных через админку.

    Заставляет систему использовать исключительно REST API (Сервисный слой)
    для добавления и изменения данных.
    """

    def has_add_permission(self, request):
        """Запрещает добавление документа через админку Django."""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещает редактирование документа через админку Django."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Запрещает удаление документа через админку Django."""
        return False


class TechCardParameterInline(ReadOnlyAdminMixin, nested_admin.NestedTabularInline):
    """Inline-форма для параметров внутри раздела.

    Отображается в виде компактной таблицы (Tabular).
    """

    model = TechCardParameter
    extra = 0
    fields = ('order', 'name', 'value', 'unit')
    ordering = ('order', 'id')


class TechCardSectionInline(ReadOnlyAdminMixin, nested_admin.NestedStackedInline):
    """Inline-форма для разделов внутри технологической карты.

    Отображается в виде блоков (Stacked), внутри которых находятся параметры.
    """

    model = TechCardSection
    extra = 0
    fields = ('order', 'name', 'parent', 'page_number')
    inlines = [TechCardParameterInline]
    ordering = ('order', 'id')


@admin.register(TechCard)
class TechCardAdmin(ReadOnlyAdminMixin, nested_admin.NestedModelAdmin):
    """Отображение модели Технологической карты в панели администратора.

    Обеспечивает вывод полного дерева документа (Карта -> Разделы -> Параметры)
    с возможностью управления версиями, статусами и просмотра авторов.
    """

    list_display = (
        'equipment_uid',
        'article',
        'equipment_seq_num',
        'card_type',
        'version',
        'status',
        'author_uid',
        'created_at',
    )
    list_filter = ('status', 'card_type', 'equipment_uid', 'article')

    search_fields = ('equipment_uid', 'article', 'equipment_seq_num', 'author_uid')
    readonly_fields = ('created_at', 'updated_at')

    inlines = [TechCardSectionInline]

    def get_queryset(self, request):
        """Переопределяет базовый QuerySet для оптимизации запросов админки.

        Args:
            request (HttpRequest): HTTP-запрос.

        Returns:
            QuerySet: Оптимизированный набор данных с подгруженными связями.
        """
        qs = super().get_queryset(request)
        return qs.prefetch_related('sections')


@admin.register(TechCardSection)
class TechCardSectionAdmin(ReadOnlyAdminMixin, nested_admin.NestedModelAdmin):
    """Отдельная админка для разделов (на случай, если нужно управлять ими вне карты)."""

    list_display = ('name', 'card', 'parent', 'order')
    list_filter = ('card__equipment_uid', 'card__article')
    search_fields = ('name', 'card__equipment_uid', 'card__article')
    inlines = [TechCardParameterInline]


@admin.register(TechCardParameter)
class TechCardParameterAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Отдельная админка для параметров (удобно для сквозного поиска)."""

    list_display = ('name', 'value', 'unit', 'section')
    search_fields = ('name', 'value')
    list_filter = ('section__card__equipment_uid',)
