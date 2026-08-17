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

    class Meta:
        model = ChecklistResult
        fields = ['user_uid', 'equipment_uid', 'created_at']


class TemplateFilter(django_filters.FilterSet):
    """
    Фильтр для шаблона чек-листа.
    Фильтрует по UID оборудования и типу чек-листа.
    """

    class Meta:
        model = Template
        fields = ['equipment_uid', 'checklist_type']
