"""Представления для API управления шаблонами и результатами чек-листов."""

from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.checklists.export_service import ChecklistExcelExporter
from apps.checklists.filters import ChecklistResultFilter, TemplateFilter
from apps.checklists.models import ChecklistResult, Template
from apps.checklists.serializers import (
    ChecklistAttachmentSerializer,
    ChecklistAttachmentUploadSerializer,
    ChecklistResultCreateSerializer,
    ChecklistResultListSerializer,
    ChecklistSignSerializer,
    TemplateSerializer,
)
from apps.checklists.services import ChecklistResultService, TemplateService


class TemplateViewSet(viewsets.ModelViewSet):
    """
    API-контроллер для управления Шаблонами чек-листов (CRUD).

    Отвечает за маршрутизацию REST-запросов. Вся сложная бизнес-логика
    делегирована слою сервисов (TemplateService).
    """

    queryset = Template.objects.prefetch_related('groups__fields__choices')

    serializer_class = TemplateSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = TemplateFilter

    search_fields = ['equipment_uid', 'groups__fields__name']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Выполнить динамическую фильтрацию QuerySet в зависимости от типа запроса.

        - При получении списка (action == 'list') скрывает устаревшие шаблоны.
        - При прямом обращении предоставляет доступ ко всей базе.
        """
        qs = super().get_queryset()
        if self.action == 'list':
            return qs.filter(is_deprecated=False)

        return qs

    def destroy(self, request, *args, **kwargs):
        """
        Обработать запрос на удаление шаблона.

        Сервис проверит бизнес-правила и попытается восстановить предыдущую версию.
        """
        instance = self.get_object()

        if instance.results.exists():
            return Response({
                                "error": "Невозможно удалить шаблон, по нему уже есть анкеты."},
                            status=400)

        TemplateService.delete_template(instance)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Получить хронологическую историю изменений (все версии) шаблона.

        Эндпоинт: GET /api/v1/templates/{id}/history/.
        """
        current = self.get_object()
        history_queryset = Template.objects.get_history(
            current.equipment_uid, current.checklist_type
        )
        serializer = self.get_serializer(history_queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def equipments(self, request):
        """
        Получить массив уникальных UID оборудования.

        Используется фронтендом для реализации автодополнения (Autocomplete).
        """
        return Response(Template.objects.get_unique_equipments())


class ChecklistResultViewSet(viewsets.ModelViewSet):
    """
    API-контроллер для управления Заполненными анкетами (Результатами).

    Обеспечивает создание черновиков, систему электронных подписей и
    аудиторский след (Audit Trail) при редактировании анкет.
    """

    queryset = ChecklistResult.objects.select_related('template').prefetch_related(
        'answers__field'
    )

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ChecklistResultFilter

    search_fields = [
        'user_uid',
        'template__equipment_uid',
        'answers__value',
        'answers__comment',
    ]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Скрыть исторические (устаревшие) версии анкет из общего списка выдачи."""
        qs = super().get_queryset()

        if self.action == 'list':
            return qs.filter(is_deprecated=False)

        return qs

    def get_serializer_class(self):
        """
        Определить класс сериализатора в зависимости от действия.

        - Запись: использует строгий валидатор.
        - Чтение: использует DTO с полной разверткой связей.
        """
        if self.action in {'create', 'update', 'partial_update'}:
            return ChecklistResultCreateSerializer
        return ChecklistResultListSerializer

    def destroy(self, request, *args, **kwargs):
        """Удалить актуальную версию анкеты и восстановить предыдущую."""
        instance = self.get_object()
        ChecklistResultService.delete_result(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Получить всю цепочку исправлений (версий) данной анкеты.

        Эндпоинт: GET /api/v1/results/{id}/history/.
        """
        current = self.get_object()
        origin_id = current.origin_id or current.id
        history_queryset = ChecklistResult.objects.get_history(origin_id)
        serializer = self.get_serializer(history_queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary='Подписать анкету',
        description='Роль APPROVER закрывает анкету от изменений. '
        'READER может подписывать даже закрытую анкету.',
        request=ChecklistSignSerializer,
        responses={
            200: inline_serializer(
                name='SignSuccessResponse',
                fields={
                    'message': serializers.CharField(),
                    'is_completed': serializers.BooleanField(),
                },
            ),
            400: inline_serializer(
                name='SignErrorResponse', fields={'error': serializers.CharField()}
            ),
        },
    )
    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        """
        Добавить или обновить электронную подпись к анкете.

        Бизнес-логика защиты инкапсулирована в ChecklistResultService.
        """
        result = self.get_object()

        serializer = ChecklistSignSerializer(data=request.data,
                                             context={'result': result})
        serializer.is_valid(raise_exception=True)

        result, created = ChecklistResultService.sign_result(
            result=result,
            role=serializer.validated_data['role'],
            user_uid=serializer.validated_data['user_uid']
        )

        msg = "Анкета успешно подписана!" if created else "Подпись успешно обновлена!"
        return Response({"message": msg, "is_completed": result.is_completed},
                        status=200)

    @extend_schema(
        summary='Экспорт анкеты в Excel',
        description='Генерирует Excel-файл со всеми ответами, комментариями и подписями.',
        responses={200: OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=['get'])
    def export_excel(self, request, pk=None):
        """
        Сгенерировать и отдать Excel-файл для скачивания.

        Эндпоинт: GET /api/v1/results/{id}/export_excel/.
        """
        result = self.get_object()

        excel_bytes = ChecklistExcelExporter.export(result)

        response = HttpResponse(
            excel_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        safe_uid = str(result.template.equipment_uid).replace(' ', '_')
        filename = f'Checklist_Result_{result.id}_{safe_uid}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    @extend_schema(
        summary='Прикрепить файл к анкете',
        description='Загрузка фото/документов. Файл нужно передавать через form-data.',
        request=ChecklistAttachmentUploadSerializer,
        responses={201: ChecklistAttachmentSerializer},
    )
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_attachment(self, request, pk=None):
        """
        Загрузить медиафайл (фото/документ) к анкете.

        Проверяет статус анкеты в Сервисном слое перед сохранением.
        """
        serializer = ChecklistAttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attachment = ChecklistResultService.add_attachment(
            result_id=pk, file_obj=serializer.validated_data['file']
        )

        return Response(
            ChecklistAttachmentSerializer(
                attachment, context={'request': request}
            ).data,
            status=status.HTTP_201_CREATED,
        )
