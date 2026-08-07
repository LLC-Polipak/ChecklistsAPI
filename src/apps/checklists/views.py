from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.checklists.filters import TemplateFilter, ChecklistResultFilter
from apps.checklists.models import ChecklistResult, Template
from apps.checklists.serializers import ChecklistResultCreateSerializer, \
    ChecklistResultListSerializer, TemplateSerializer


class TemplateViewSet(viewsets.ModelViewSet):
    """
    Управление шаблонами чек-листов (CRUD).

    Обеспечивает создание, чтение, обновление и удаление структуры шаблонов.
    """

    queryset = Template.objects.filter(is_deprecated=False).prefetch_related(
        'fields__choices')
    serializer_class = TemplateSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_class = TemplateFilter

    def destroy(self, request, *args, **kwargs):
        """
        Отвечает за удаление шаблона.

        Returns:
            HTTP 204: Удаление шаблон прошло успешно.
            HTTP 400: Если на шаблон есть заполненный чек-лист и его удаление невозможно.
            HTTP 404: Шаблон с таким параметром не найден.
        """

        instance = self.get_object()

        if instance.results.exists():
            return Response(
                {
                    "error": "Невозможно удалить шаблон, так как по нему уже есть заполненные анкеты."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Возвращает историю изменений для данного шаблона.
        (Находит все устаревшие и текущую версию для этого оборудования и типа).
        """

        current_template = self.get_object()

        history_queryset = Template.objects.filter(
            equipment_uid=current_template.equipment_uid,
            checklist_type=current_template.checklist_type
        ).prefetch_related('fields__choices').order_by('-created_at')

        serializer = self.get_serializer(history_queryset, many=True)

        return Response(serializer.data)


class ChecklistResultViewSet(viewsets.ModelViewSet):
    """
    Управление результатами заполнения чек-листов (История и Сохранение).

    - POST/PUT/PATCH: принимает плоский словарь ответов
    и выполняет динамическую валидацию типов данных.
    - GET: возвращает историю заполненных анкет.
    """

    queryset = ChecklistResult.objects.select_related(
        'template').prefetch_related('answers__field')

    filter_backends = [DjangoFilterBackend]
    filterset_class = ChecklistResultFilter

    def get_serializer_class(self):
        """
        Динамический выбор сериализатора в зависимости от HTTP-метода.

        Returns:
            ChecklistResultCreateSerializer: Для записи.
            ChecklistResultListSerializer: Для чтения.
        """

        if self.action in ['create', 'update', 'partial_update']:
            return ChecklistResultCreateSerializer
        return ChecklistResultListSerializer
