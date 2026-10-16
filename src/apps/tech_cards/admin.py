import nested_admin
from django.contrib import admin

from apps.tech_cards.models import TechCard, TechCardParameter, TechCardSection


class TechCardParameterInline(nested_admin.NestedTabularInline):
    """Inline-форма для параметров внутри раздела.

    Отображается в виде компактной таблицы (Tabular).
    """

    model = TechCardParameter
    extra = 0
    fields = ('order', 'name', 'value', 'unit')
    ordering = ('order', 'id')


class TechCardSectionInline(nested_admin.NestedStackedInline):
    """Inline-форма для разделов внутри технологической карты.

    Отображается в виде блоков (Stacked), внутри которых находятся параметры.
    """

    model = TechCardSection
    extra = 0
    fields = ('order', 'name', 'parent', 'page_number')
    inlines = [TechCardParameterInline]
    ordering = ('order', 'id')


@admin.register(TechCard)
class TechCardAdmin(nested_admin.NestedModelAdmin):
    """Настройка отображения модели TechCard в панели администратора.

    Использует nested_admin для вывода и редактирования древовидной
    структуры 'Карта -> Разделы -> Параметры' на одной странице.
    """

    list_display = (
        'equipment_uid',
        'equipment_seq_num',
        'article',
        'version',
        'status',
        'created_at',
    )
    list_filter = ('status', 'equipment_uid', 'article')

    search_fields = ('equipment_uid', 'article', 'equipment_seq_num')
    readonly_fields = ('created_at', 'updated_at')

    inlines = [TechCardSectionInline]

    def get_queryset(self, request):
        """Оптимизация запросов для списка объектов в админке."""
        qs = super().get_queryset(request)
        return qs.prefetch_related('sections')


@admin.register(TechCardSection)
class TechCardSectionAdmin(nested_admin.NestedModelAdmin):
    """Отдельная админка для разделов (на случай, если нужно управлять ими вне карты)."""

    list_display = ('name', 'card', 'parent', 'order')
    list_filter = ('card__equipment_uid', 'card__article')
    search_fields = ('name', 'card__equipment_uid', 'card__article')
    inlines = [TechCardParameterInline]


@admin.register(TechCardParameter)
class TechCardParameterAdmin(admin.ModelAdmin):
    """Отдельная админка для параметров (удобно для сквозного поиска)."""

    list_display = ('name', 'value', 'unit', 'section')
    search_fields = ('name', 'value')
    list_filter = ('section__card__equipment_uid',)
