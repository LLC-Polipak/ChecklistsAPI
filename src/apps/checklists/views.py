from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.checklists.export_service import ChecklistExcelExporter
from apps.checklists.filters import ChecklistResultFilter, TemplateFilter
from apps.checklists.models import ChecklistResult, Template
from apps.checklists.serializers import (
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
    (сохранение иерархии Группы -> Поля, версионирование и удаление)
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
        Динамическая фильтрация QuerySet в зависимости от типа запроса.
        - При получении списка (action == 'list') скрывает устаревшие шаблоны.
        - При прямом обращении по ID (detail, history, update) предоставляет доступ ко всей базе.
        """
        qs = super().get_queryset()
        if self.action == 'list':
            return qs.filter(is_deprecated=False)

        return qs

    def perform_create(self, serializer):
        """
        Перехватывает создание шаблона для интеграции с Сервисом.
        Сервис атомарно сохранит иерархию и отправит старые шаблоны в архив.
        """
        service = TemplateService()
        serializer.instance = service.create_template(serializer.validated_data)

    def perform_update(self, serializer):
        """
        Перехватывает обновление шаблона.
        Сервис проверит возможность редактирования (отсутствие привязанных анкет)
        и выполнит полную перезапись полей и групп.
        """
        service = TemplateService()
        serializer.instance = service.update_template(
            serializer.instance, serializer.validated_data
        )

    def destroy(self, request, *args, **kwargs):
        """
        Обрабатывает запрос на удаление шаблона.
        Сервис проверит бизнес-правила и попытается "воскресить" предыдущую версию
        шаблона (откат/rollback), если текущая удаляется.
        """
        instance = self.get_object()
        service = TemplateService()

        try:
            service.delete_template(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ValidationError as e:
            return Response(
                {'error': str(e.detail[0])}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Эндпоинт: GET /api/v1/templates/{id}/history/
        Возвращает хронологическую историю изменений (все версии) шаблона
        для данного оборудования и типа чек-листа.
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
        Эндпоинт: GET /api/v1/templates/equipments/
        Возвращает плоский массив уникальных UID оборудования.
        Используется фронтендом для реализации автодополнения (Autocomplete/Datalist).
        """
        return Response(Template.objects.get_unique_equipments())


class ChecklistResultViewSet(viewsets.ModelViewSet):
    """
    API-контроллер для управления Заполненными анкетами (Результатами).

    Поддерживает динамическую EAV-структуру (Entity-Attribute-Value).
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
        """Скрывает исторические (устаревшие) версии анкет из общего списка выдачи."""
        qs = super().get_queryset()

        if self.action == 'list':
            return qs.filter(is_deprecated=False)

        return qs

    def get_serializer_class(self):
        """
        Разделяет потоки данных:
        - Запись (POST/PUT): Использует строгий валидатор.
        - Чтение (GET): Использует DTO с полной разверткой связей и названий (display_name).
        """
        if self.action in {'create', 'update', 'partial_update'}:
            return ChecklistResultCreateSerializer
        return ChecklistResultListSerializer

    def perform_create(self, serializer):
        """
        Делегирует сохранение ответов Сервису.
        Сервис дополнительно проставит автоматическую подпись Составителя (AUTHOR).
        """
        service = ChecklistResultService()
        serializer.instance = service.submit_result(serializer.validated_data)

    def perform_update(self, serializer):
        """
        Делегирует обновление Сервису.
        Вместо деструктивной перезаписи, Сервис реализует Аудиторский след (Audit Trail),
        помещая старую анкету в архив и создавая новую версию с переносом подписей.
        """
        service = ChecklistResultService()
        serializer.instance = service.update_result(
            serializer.instance, serializer.validated_data
        )

    def destroy(self, request, *args, **kwargs):
        """Удаляет актуальную версию анкеты и "воскрешает" предыдущую, если она существует."""
        instance = self.get_object()
        service = ChecklistResultService()
        try:
            service.delete_result(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ValidationError as e:
            return Response(
                {'error': str(e.detail[0])}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Эндпоинт: GET /api/v1/results/{id}/history/
        Возвращает всю цепочку исправлений (версий) данной анкеты от новых к старым.
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
        Эндпоинт: POST /api/v1/results/{id}/sign/
        Обрабатывает добавление подписей. Бизнес-логика защиты от подписания черновиков
        или устаревших анкет инкапсулирована в ChecklistResultService.
        """
        serializer = ChecklistSignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = ChecklistResultService()
        result, created = service.sign_result(
            result_id=pk,
            role=serializer.validated_data['role'],
            user_uid=serializer.validated_data['user_uid'],
        )

        msg = 'Анкета успешно подписана!' if created else 'Подпись успешно обновлена!'
        return Response(
            {'message': msg, 'is_completed': result.is_completed},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary='Экспорт анкеты в Excel',
        description='Генерирует Excel-файл со всеми ответами, комментариями и подписями.',
        responses={200: OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=['get'])
    def export_excel(self, request, pk=None):
        """
        Эндпоинт: GET /api/v1/results/{id}/export_excel/
        Генерирует и отдает файл Excel для скачивания (без сохранения его на диск сервера).
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
