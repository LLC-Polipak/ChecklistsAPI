from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChecklistsResult, Template
from .serializers import (
    ChecklistResultCreateSerializer,
    ChecklistResultListSerializer,
    TemplateSerializer,
)


class TemplateCreateAPIView(generics.CreateAPIView):
    """
    REST эндпоинт для создания структуры (шаблона) чек-листаю
    Принимает конфигурацию полей и вариантов ответа.
    Используется администраторами или инженерами для настройки проверок оборудования.
    """

    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]


class GenerateChecklistAPIView(APIView):
    """
    REST эндпоинтов для выдачи пустого бланка чек-листа фронтенду.
    Возвращает схему полей, которую необходимо отрисовать пользователю.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary='Получить существующий шаблон чек-листа',
        parameters=[
            OpenApiParameter(name='equipment_uid', required=True, type=str),
            OpenApiParameter(name='checklist_type', required=True, type=str),
            OpenApiParameter(name='user_uid', required=True, type=str),
        ],
        responses=TemplateSerializer,
    )
    def get(self, request):
        """
        Извлекает обязательные query-параметры (equipment_uid, checklist_type).
        Возвращает HTTP 404, если шаблон не сконструирован,
        или HTTP 200 с полной JSON-схемой полей для построения UI на фронтенде.
        """

        equipment_uid = request.query_params.get('equipment_uid')
        checklist_type = request.query_params.get('checklist_type')
        user_uid = request.query_params.get('user_uid')

        if not all([equipment_uid, checklist_type, user_uid]):
            return Response(
                {
                    'error': 'Передайте параметры equipment_uid, checklist_type, user_uid'
                },
                status=400,
            )

        template = get_object_or_404(
            Template, equipment_uid=equipment_uid, checklist_type=checklist_type
        )

        serializer = TemplateSerializer(template)
        return Response(serializer.data)


class ChecklistResultAPIView(APIView):
    """
    Универсальный REST эндпоинт для работы с результатами чек-листов.
    Предоставляет методы получения истории (GET) и сохранения новых анкет (POST).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary='Получить историю заполненных чек-листов',
        parameters=[
            OpenApiParameter(
                name='equipment_uid',
                description='Фильтр по оборудованию',
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name='user_uid',
                description='Фильтр по пользователю',
                required=False,
                type=str,
            ),
        ],
        responses=ChecklistResultListSerializer(many=True),
    )
    def get(self, request):
        """
        Возвращает список результатов с поддержкой фильтрации по UID.
        """

        queryset = ChecklistsResult.objects.select_related('template').prefetch_related(
            'answers__field'
        )

        equipment_uid = request.query_params.get('equipment_uid')
        user_uid = request.query_params.get('user_uid')

        if equipment_uid:
            queryset = queryset.filter(equipment_uid=equipment_uid)
        if user_uid:
            queryset = queryset.filter(user_uid=user_uid)

        serializer = ChecklistResultListSerializer(queryset, many=True)

        return Response(serializer.data)

    @extend_schema(
        summary='Сохранить заполненный чек-лист',
        request=ChecklistResultCreateSerializer,
        responses={201: None},
    )
    def post(self, request):
        """
        Принимает плоский словарь ответов, прогоняет через динамическую валидацию
        и сохраняет результаты в динамическую EAV-структуру БД.
        """

        serializer = ChecklistResultCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = serializer.save()

        return Response(
            {'message': 'Анкета успешно сохранена', 'result_id': result.id},
            status=status.HTTP_201_CREATED,
        )
