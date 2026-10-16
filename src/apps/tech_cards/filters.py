import django_filters

from apps.tech_cards.models import TechCard


class TechCardFilter(django_filters.FilterSet):
    """Фильтры для технологических карт.

    Позволяет фильтровать по точным совпадениям, частичным вхождениям,
    диапазонам дат и кастомному статусу архивации.
    """

    equipment_uid = django_filters.CharFilter(lookup_expr='icontains')
    article = django_filters.CharFilter(lookup_expr='icontains')
    equipment_seq_num = django_filters.CharFilter(lookup_expr='exact')

    created_after = django_filters.DateTimeFilter(
        field_name='created_at', lookup_expr='gte'
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at', lookup_expr='lte'
    )

    updated_after = django_filters.DateTimeFilter(
        field_name='updated_at', lookup_expr='gte'
    )
    updated_before = django_filters.DateTimeFilter(
        field_name='updated_at', lookup_expr='lte'
    )

    is_archived = django_filters.BooleanFilter(method='filter_is_archived')

    class Meta:
        model = TechCard
        fields = ['equipment_uid', 'article', 'equipment_seq_num']

    def filter_is_archived(self, queryset, name, value):
        """Логика кастомного фильтра статуса.

        Args:
            queryset (QuerySet): Текущий набор данных.
            name (str): Имя поля фильтра.
            value (bool): Значение, переданное клиентом (True/False).

        Returns:
            QuerySet: Отфильтрованный набор данных.
        """
        if value is True:
            return queryset.filter(status='archived')
        if value is False:
            return queryset.filter(status='active')
        return queryset
