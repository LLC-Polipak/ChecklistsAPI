"""Представления для API управления шаблонами и результатами чек-листов."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import filters, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.checklists.filters import ChecklistResultFilter, TemplateFilter
from apps.checklists.models import ChecklistAttachment, ChecklistResult, Template
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

    def create(self, request, *args, **kwargs):
        """Создать новый шаблон и вернуть его данные."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template = TemplateService.create_template(serializer.validated_data)

        output_serializer = TemplateSerializer(template, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Обновить существующий шаблон (поддерживает частичное обновление)."""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        updated_template = TemplateService.update_template(
            instance, serializer.validated_data
        )

        output_serializer = TemplateSerializer(
            updated_template, context={'request': request}
        )
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """
        Обработать запрос на удаление шаблона.

        Сервис проверит бизнес-правила и попытается восстановить предыдущую версию.
        """
        instance = self.get_object()

        if instance.results.exists():
            return Response(
                {"error": "Невозможно удалить шаблон, по нему уже есть анкеты."},
                status=400,
            )

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


class ChecklistResultViewSet(viewsets.ModelViewSet):
    """
    API-контроллер для управления Заполненными анкетами (Результатами).

    Обеспечивает создание черновиков, систему электронных подписей и
    аудиторский след (Audit Trail) при редактировании анкет.
    """

    queryset = ChecklistResult.objects.select_related('template').prefetch_related(
        'answers__field__group', 'signatures', 'attachments'
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

    def create(self, request, *args, **kwargs):
        """Создать новую анкету (сохранить результаты заполнения)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = ChecklistResultService.submit_result(serializer.validated_data)

        output_serializer = ChecklistResultListSerializer(
            result, context={'request': request}
        )
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Обновить ответы анкеты с созданием новой версии в базе данных."""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        new_result = ChecklistResultService.update_result(
            instance, serializer.validated_data
        )

        output_serializer = ChecklistResultListSerializer(
            new_result, context={'request': request}
        )
        return Response(output_serializer.data, status=status.HTTP_200_OK)

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
            status.HTTP_200_OK: inline_serializer(
                name='SignSuccessResponse',
                fields={
                    'message': serializers.CharField(),
                    'is_completed': serializers.BooleanField(),
                },
            ),
            status.HTTP_400_BAD_REQUEST: inline_serializer(
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

        serializer = ChecklistSignSerializer(
            data=request.data, context={'result': result}
        )
        serializer.is_valid(raise_exception=True)

        result, created = ChecklistResultService.sign_result(
            result=result,
            role=serializer.validated_data['role'],
            user_uid=serializer.validated_data['user_uid'],
            is_closing=serializer.validated_data['is_closing'],
        )

        msg = "Анкета успешно подписана!" if created else "Подпись успешно обновлена!"
        return Response(
            {"message": msg, "is_completed": result.is_completed},
            status=status.HTTP_200_OK,
        )


class ChecklistAttachmentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Отдельный REST-эндпоинт для работы с файлами.

    Позволяет загружать файлы, скачивать/просматривать и удалять их.
    Не поддерживает PUT/PATCH (файлы нельзя "обновить", только удалить и залить новый).
    """

    queryset = ChecklistAttachment.objects.select_related('result')
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        """Определить сериализатор в зависимости от типа запроса."""
        if self.action == 'create':
            return ChecklistAttachmentUploadSerializer
        return ChecklistAttachmentSerializer

    def create(self, request, *args, **kwargs):
        """Загрузить новый прикрепленный файл к анкете."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attachment = ChecklistResultService.add_attachment(
            result_id=serializer.validated_data['result'],
            file_obj=serializer.validated_data['file'],
        )

        output_serializer = ChecklistAttachmentSerializer(
            attachment, context={'request': request}
        )
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Перехватить удаление и отдать в Сервис."""
        attachment = self.get_object()

        try:
            ChecklistResultService.delete_attachment(attachment)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ValidationError as e:
            return Response(
                {"error": str(e.detail[0])}, status=status.HTTP_400_BAD_REQUEST
            )
