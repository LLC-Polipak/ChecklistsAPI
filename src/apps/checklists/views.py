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
from apps.checklists.repositories import (
    DjangoResultRepository,
    DjangoTemplateRepository,
)
from apps.checklists.serializers import (
    ChecklistResultCreateSerializer,
    ChecklistResultListSerializer,
    ChecklistSignSerializer,
    TemplateSerializer,
)
from apps.checklists.services import ChecklistResultService, TemplateService


class TemplateViewSet(viewsets.ModelViewSet):
    """
    Управление шаблонами чек-листов (CRUD).
    Обеспечивает создание, чтение, обновление и удаление структуры шаблонов.
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

    def perform_create(self, serializer):
        """
        Переопределение стандартного процесса сохранения DRF.
        Вместо вызова serializer.save(), мы делегируем бизнес-логику в слой Сервисов (TemplateService).
        Сервис сам позаботится о версионировании (устаревании прошлых шаблонов) и
        атомарном сохранении всей иерархии (Группы -> Поля -> Варианты).
        """
        service = TemplateService(DjangoTemplateRepository())
        serializer.instance = service.create_template(serializer.validated_data)

    def perform_update(self, serializer):
        """
        Переопределение стандартного процесса обновления DRF.
        Делегирует обновление в Сервис, который проверяет бизнес-правила
        (например, запрет редактирования используемых шаблонов) и полностью
        перезаписывает структуру групп и полей.
        """
        service = TemplateService(DjangoTemplateRepository())
        serializer.instance = service.update_template(
            serializer.instance, serializer.validated_data
        )

    def destroy(self, request, *args, **kwargs):
        """
        Отвечает за удаление шаблона.

        Returns:
            HTTP 204: Удаление шаблон прошло успешно.
            HTTP 400: Если на шаблон есть заполненный анкета.
            HTTP 404: Шаблон с таким параметром не найден.
        """
        instance = self.get_object()
        service = TemplateService(DjangoTemplateRepository())

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
        Возвращает историю изменений для данного шаблона.
        (Находит все устаревшие и текущую версию для этого оборудования и типа).
        """
        current_template = self.get_object()

        repo = DjangoTemplateRepository()
        history_queryset = repo.get_template_history(
            equipment_uid=current_template.equipment_uid,
            checklist_type=current_template.checklist_type,
        )

        serializer = self.get_serializer(history_queryset, many=True)

        return Response(serializer.data)

    def get_queryset(self):
        """
        При запросе всего списка шаблонов возвращает только актуальные.
        По-прямому ID возвращает всю историю для данного шаблона.
        """
        qs = super().get_queryset()
        if self.action == 'list':
            return qs.filter(is_deprecated=False)

        return qs

    @action(detail=False, methods=['get'])
    def equipments(self, request):
        """
        Возвращает список уникальных UID оборудования из активных шаблонов.
        Идеально для подсказок (autocomplete) на фронтенде.
        """
        repo = DjangoTemplateRepository()
        return Response(repo.get_unique_equipments())


class ChecklistResultViewSet(viewsets.ModelViewSet):
    """
    Управление результатами заполнения чек-листов (История и Сохранение).

    - POST/PUT/PATCH: принимает плоский словарь ответов
    и выполняет динамическую валидацию типов данных.
    - GET: возвращает историю заполненных анкет.
    - GET /history/ : возвращает полную историю всех изменений анкеты.
    - POST /sign/ : подписывает анкету пользователем с определенной ролью.
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
        """
        При запросе полного списка анкет возвращает только актуальные,
        отсекая устаревшие версии.
        По запросе по-конкретному ID возвращает всю историю для данной анкеты.
        """
        qs = super().get_queryset()

        if self.action == 'list':
            return qs.filter(is_deprecated=False)

        return qs

    def get_serializer_class(self):
        """
        Динамический выбор сериализатора в зависимости от HTTP-метода.

        Returns:
            ChecklistResultCreateSerializer: Для записи.
            ChecklistResultListSerializer: Для чтения.
        """
        if self.action in {'create', 'update', 'partial_update'}:
            return ChecklistResultCreateSerializer
        return ChecklistResultListSerializer

    def perform_create(self, serializer):
        """
        Переопределение сохранения новой анкеты.
        Передает провалидированные данные в ChecklistResultService, который
        сохраняет ответы и автоматически ставит подпись составителя (AUTHOR).
        """
        service = ChecklistResultService(DjangoResultRepository())
        serializer.instance = service.submit_result(serializer.validated_data)

    def perform_update(self, serializer):
        """
        Переопределение обновления заполненной анкеты.
        Сервис отвечает за Аудиторский след (Audit Trail): вместо изменения текущей записи,
        он помечает ее как устаревшую и создает новую версию с переносом всех старых подписей.
        """
        service = ChecklistResultService(DjangoResultRepository())
        serializer.instance = service.update_result(
            serializer.instance, serializer.validated_data
        )

    def destroy(self, request, *args, **kwargs):
        """
        Отвечает за удаление анкеты чек-листа.

        Returns:
            HTTP 204: Удаление анкеты прошло успешно.
            HTTP 404: Анкета с таким параметром не найдена.
        """
        instance = self.get_object()
        service = ChecklistResultService(DjangoResultRepository())

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
        Возвращает историю изменений конкретной анкеты.
        Включает оригинал и все его исправления, отсортированные от новых к старым.
        """
        current_result = self.get_object()
        origin_id = current_result.origin_id or current_result.id

        repo = DjangoResultRepository()
        history_queryset = repo.get_result_history(origin_id=origin_id)

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
        Эндпоинт для подписания анкеты.
        Ожидает JSON: {"role": "OPERATOR_OUT", "user_uid": "USER-99"}.
        """
        serializer = ChecklistSignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = ChecklistResultService(DjangoResultRepository())

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
        Эндопинт для генерации файла Excel из заполненной анкеты чек-листа.
        Возвращает готовый Excel-файл.
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
