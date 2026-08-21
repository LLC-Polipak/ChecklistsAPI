import django_filters

from apps.checklists.models import ChecklistResult, Template


class TemplateFilter(django_filters.FilterSet):
    """
    Класс фильтрации для списка шаблонов чек-листов (используется в DRF).

    Обеспечивает поиск по точным совпадениям дат (игнорируя время),
    а также по основным идентификаторам оборудования.
    """

    created_date = django_filters.DateFilter(
        field_name='created_at', lookup_expr='date', label='Дата создания'
    )
    updated_date = django_filters.DateFilter(
        field_name='updated_at', lookup_expr='date', label='Дата обновления'
    )

    class Meta:
        model = Template
        fields = ['equipment_uid', 'checklist_type', 'is_deprecated']


class ChecklistResultFilter(django_filters.FilterSet):
    """
    Класс фильтрации для заполненных анкет (результатов).

    Особенности:
    - Позволяет фильтровать анкеты по UID оборудования, даже несмотря на то,
      что само поле `equipment_uid` находится в связанной таблице `Template`.
    """

    equipment_uid = django_filters.CharFilter(
        field_name='template__equipment_uid', lookup_expr='exact'
    )
    created_date = django_filters.DateFilter(
        field_name='created_at', lookup_expr='date', label='Дата заполнения'
    )
    updated_date = django_filters.DateFilter(
        field_name='updated_at', lookup_expr='date', label='Дата обновления'
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
        ]
