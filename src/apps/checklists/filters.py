"""Фильтры для управления поиском в шаблонах и результатах чек-листов."""
from datetime import datetime, time

import django_filters
from django.utils.timezone import make_aware

from apps.checklists.models import ChecklistResult, Template


class TemplateFilter(django_filters.FilterSet):
    """
    Класс фильтрации для списка шаблонов чек-листов.

    Обеспечивает поиск по точным совпадениям дат (игнорируя время),
    а также по основным идентификаторам оборудования.
    """

    created_date_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        label='Создано с (Дата)'
    )
    updated_date_from = django_filters.DateFilter(
        field_name='updated_at',
        lookup_expr='gte',
        label='Обновлено с (Дата)'
    )

    created_date_to = django_filters.DateFilter(
        method='filter_end_of_day',
        field_name='created_at',
        label='Создано по (Дата)'
    )
    updated_date_to = django_filters.DateFilter(
        method='filter_end_of_day',
        field_name='updated_at',
        label='Обновлено по (Дата)'
    )

    class Meta:
        model = Template
        fields = ['equipment_uid', 'checklist_type', 'is_deprecated']

    def filter_end_of_day(self, queryset, name, value):
        """Превращает дату в конец дня: YYYY-MM-DD 23:59:59.999999."""
        end_of_day = make_aware(datetime.combine(value, time.max))
        return queryset.filter(**{f"{name}__lte": end_of_day})


class ChecklistResultFilter(django_filters.FilterSet):
    """
    Класс фильтрации для заполненных анкет (результатов).

    Позволяет фильтровать анкеты по UID оборудования через связанную
    модель шаблона, а также по метаданным заполнения.
    """

    equipment_uid = django_filters.CharFilter(
        field_name='template__equipment_uid', lookup_expr='exact'
    )
    created_date_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        label='Заполнено с (Дата)'
    )
    updated_date_from = django_filters.DateFilter(
        field_name='updated_at',
        lookup_expr='gte',
        label='Обновлено с (Дата)'
    )

    created_date_to = django_filters.DateFilter(
        method='filter_end_of_day',
        field_name='created_at',
        label='Заполнено по (Дата)'
    )
    updated_date_to = django_filters.DateFilter(
        method='filter_end_of_day',
        field_name='updated_at',
        label='Обновлено по (Дата)'
    )

    class Meta:
        model = ChecklistResult
        fields = [
            'user_uid',
            'equipment_uid',
            'external_id',
            'source_service',
            'shift_number',
            'is_draft',
            'is_completed',
            'is_deprecated',
            'has_violations',
        ]

    def filter_end_of_day(self, queryset, name, value):
        """Превращает дату в конец дня для использования индексов БД."""
        end_of_day = make_aware(datetime.combine(value, time.max))
        return queryset.filter(**{f"{name}__lte": end_of_day})
