from django.views.generic import TemplateView
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ChecklistResult, Template
from .serializers import (
    ChecklistResultCreateSerializer,
    ChecklistResultListSerializer,
    TemplateSerializer,
)


class TemplateViewSet(viewsets.ModelViewSet):
    """
    Управление шаблонами чек-листов (CRUD).

    Обеспечивает создание, чтение, обновление и удаление структуры шаблонов.
    """

    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Получить список шаблонов (или один по фильтрам)',
        parameters=[
            OpenApiParameter(
                name='equipment_uid',
                description='Фильтр по оборудованию',
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name='checklist_type',
                description='Фильтр по типу чек-листа',
                required=False,
                type=str,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """
        Извлекает шаблон из БД по параметрам и отдает его структуру.

        Returns:
            HTTP 200: JSON со структурой полей и вариантами выбора.
            HTTP 400: Если отсутствуют обязательные query-параметры.
            HTTP 404: Если шаблон с такими параметрами не найден.
        """
        queryset = self.get_queryset()

        equipment_uid = request.query_params.get('equipment_uid')
        checklist_type = request.query_params.get('checklist_type')

        if equipment_uid:
            queryset = queryset.filter(equipment_uid=equipment_uid)
        if checklist_type:
            queryset = queryset.filter(checklist_type=checklist_type)

        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


class ChecklistResultViewSet(viewsets.ModelViewSet):
    """
    Управление результатами заполнения чек-листов (История и Сохранение).

    - POST/PUT/PATCH: принимает плоский словарь ответов
    и выполняет динамическую валидацию типов данных.
    - GET: возвращает историю заполненных анкет.
    """

    queryset = ChecklistResult.objects.select_related('template').prefetch_related(
        'answers__field'
    )
    permission_classes = [AllowAny]

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

    @extend_schema(
        parameters=[
            OpenApiParameter(name='equipment_uid', required=False, type=str),
            OpenApiParameter(name='user_uid', required=False, type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        Получение списка сохраненных анкет с возможностью фильтрации.

        Поддерживает Query-параметры `equipment_uid` и `user_uid` для поиска
        истории проверок конкретного оборудования или конкретным инспектором.
        """

        queryset = self.get_queryset()
        equipment_uid = request.query_params.get('equipment_uid')
        user_uid = request.query_params.get('user_uid')

        if equipment_uid:
            queryset = queryset.filter(equipment_uid=equipment_uid)
        if user_uid:
            queryset = queryset.filter(user_uid=user_uid)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
