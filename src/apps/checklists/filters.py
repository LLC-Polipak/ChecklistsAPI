import django_filters

from apps.checklists.models import ChecklistResult, Template


class ChecklistResultFilter(django_filters.FilterSet):
    """
    Фильтр для заполненного чек-листа.
    Фильтрует по UID оборудования и UID пользователя.
    """

    equipment_uid = django_filters.CharFilter(
        field_name='template__equipment_uid', lookup_expr='exact'
    )
    created_date = django_filters.DateFilter(field_name='created_at',
                                             lookup_expr='date',
                                             label='Дата заполнения')
    updated_date = django_filters.DateFilter(field_name='updated_at',
                                             lookup_expr='date',
                                             label='Дата обновления')

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
            'is_deprecated'
        ]


class TemplateFilter(django_filters.FilterSet):
    """
    Фильтр для шаблона чек-листа.
    Фильтрует по UID оборудования и типу чек-листа.
    """

    created_date = django_filters.DateFilter(field_name='created_at',
                                             lookup_expr='date',
                                             label='Дата создания')
    updated_date = django_filters.DateFilter(field_name='updated_at',
                                             lookup_expr='date',
                                             label='Дата обновления')

    class Meta:
        model = Template
        fields = ['equipment_uid', 'checklist_type', 'is_deprecated']
