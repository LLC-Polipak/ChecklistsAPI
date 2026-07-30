from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Template
from .serializers import TemplateSerializer


class TemplateCreateAPIView(generics.CreateAPIView):
    """
    Эндпоинт для создания нового шаблона чек-листа
    """

    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]


class GenerateChecklistAPIView(APIView):
    """
    Эндпоинт генерации структуры анкеты для фронтенда.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='equipment_uid', required=True, type=str),
            OpenApiParameter(name='checklist_type', required=True, type=str),
            OpenApiParameter(name='user_uid', required=True, type=str),
        ],
        responses=TemplateSerializer,
    )
    def get(self, request):
        """
        Обработка GET-запроса на получение структуры чек-листа.

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
