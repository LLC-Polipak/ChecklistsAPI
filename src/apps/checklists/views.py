from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import inline_serializer, extend_schema
from rest_framework import status, viewsets, serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.checklists.filters import ChecklistResultFilter, TemplateFilter
from apps.checklists.models import ChecklistResult, ChecklistSignature, Template
from apps.checklists.serializers import (
    ChecklistResultCreateSerializer,
    ChecklistResultListSerializer,
    TemplateSerializer, ChecklistSignSerializer,
)


class TemplateViewSet(viewsets.ModelViewSet):
    """
    Управление шаблонами чек-листов (CRUD).

    Обеспечивает создание, чтение, обновление и удаление структуры шаблонов.
    """
    queryset = Template.objects.prefetch_related('groups__fields__choices')

    serializer_class = TemplateSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_class = TemplateFilter

    def destroy(self, request, *args, **kwargs):
        """
        Отвечает за удаление шаблона.

        Returns:
            HTTP 204: Удаление шаблон прошло успешно.
            HTTP 400: Если на шаблон есть заполненный анкета.
            HTTP 404: Шаблон с таким параметром не найден.
        """
        instance = self.get_object()

        if instance.results.exists():
            return Response(
                {
                    'error': 'Невозможно удалить шаблон, '
                    'так как по нему уже есть заполненные анкеты.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Возвращает историю изменений для данного шаблона.
        (Находит все устаревшие и текущую версию для этого оборудования и типа).
        """
        current_template = self.get_object()

        history_queryset = (
            Template.objects.filter(
                equipment_uid=current_template.equipment_uid,
                checklist_type=current_template.checklist_type,
            )
            .prefetch_related('fields__choices')
            .order_by('-created_at')
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
        uids = (self.get_queryset()
                .values_list('equipment_uid', flat=True).distinct())

        return Response(list(uids))


class ChecklistResultViewSet(viewsets.ModelViewSet):
    """
    Управление результатами заполнения чек-листов (История и Сохранение).

    - POST/PUT/PATCH: принимает плоский словарь ответов
    и выполняет динамическую валидацию типов данных.
    - GET: возвращает историю заполненных анкет.
    - GET /history/ : возвращает полную историю всех изменений анкеты.
    """
    queryset = (ChecklistResult.objects.select_related('template')
    .prefetch_related(
        'answers__field'
    ))

    filter_backends = [DjangoFilterBackend]
    filterset_class = ChecklistResultFilter

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

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Возвращает историю изменений конкретной анкеты.
        Включает оригинал и все его исправления, отсортированные от новых к старым.
        """
        current_result = self.get_object()

        origin_id = current_result.origin_id or current_result.id

        history_queryset = (
            ChecklistResult.objects.filter(Q(id=origin_id)
                                           | Q(origin_id=origin_id))
            .select_related('template')
            .prefetch_related('answers__field')
            .order_by('-created_at')
        )

        serializer = self.get_serializer(history_queryset, many=True)

        return Response(serializer.data)

    @extend_schema(
        summary="Подписать анкету",
        description="Роль APPROVER закрывает анкету от изменений. "
                    "READER может подписывать даже закрытую анкету.",
        request=ChecklistSignSerializer,
        responses={
            200: inline_serializer(
                name='SignSuccessResponse',
                fields={
                    'message': serializers.CharField(),
                    'is_completed': serializers.BooleanField()
                }
            ),
            400: inline_serializer(
                name='SignErrorResponse',
                fields={
                    'error': serializers.CharField()
                }
            )
        }
    )
    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        """
        Эндпоинт для подписания анкеты.
        Ожидает JSON: {"role": "OPERATOR_OUT", "user_uid": "USER-99"}.
        """
        result = self.get_object()

        serializer = ChecklistSignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role = serializer.validated_data['role']
        user_uid = serializer.validated_data['user_uid']

        if result.is_deprecated:
            return Response(
                {
                    "error":
                        "Нельзя подписать устаревшую анкету"
                }, status=status.HTTP_400_BAD_REQUEST
            )

        if result.is_completed and role != ChecklistSignature.Role.READER:
            return Response(
                {
                    "error": "Анкета уже закрыта. "
                             "Допускаются только подписи об ознакомлении (READER)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.utils.timezone import now

        signature, created = ChecklistSignature.objects.get_or_create(
            result=result,
            role=role,
            defaults={'user_uid': user_uid}
        )

        if not created:
            signature.user_uid = user_uid
            signature.signed_at = now()
            signature.save(update_fields=['user_uid', 'signed_at'])

        result.check_and_complete()

        status_msg = "Анкета успешно подписана!" if created \
            else "Подпись успешно обновлена!"

        return Response({
            "message": status_msg,
            "is_completed": result.is_completed
        }, status=status.HTTP_200_OK)
