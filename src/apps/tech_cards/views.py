from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.response import Response

from apps.core.constants import DocumentStatus
from apps.tech_cards.filters import TechCardFilter
from apps.tech_cards.models import TechCard
from apps.tech_cards.serializers import TechCardSerializer
from apps.tech_cards.services import TechCardService


class TechCardViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Контроллер для работы с технологическими картами.

    Обеспечивает строгое версионирование: изменение данных происходит
    только через добавление новой версии (POST), а удаление (DELETE)
    использует механизм Soft Delete с откатом версий.
    """

    serializer_class = TechCardSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_class = TechCardFilter

    search_fields = ['equipment_uid', 'article', 'equipment_seq_num']

    ordering_fields = ['created_at', 'updated_at', 'version']
    ordering = ['-created_at']

    def get_queryset(self):
        """Формирует набор данных на основе параметров запроса.

        Извлекает параметры статуса и UID оператора, передавая их
        в кастомный QuerySet для применения бизнес-логики изоляции карт.

        Returns:
            QuerySet: Оптимизированный и отфильтрованный набор карт.
        """
        status_filter = DocumentStatus.ACTIVE

        if self.request.query_params.get('is_archived') == 'true':
            status_filter = DocumentStatus.ARCHIVED

        operator_uid = self.request.query_params.get('current_operator_uid')

        return TechCard.objects.available_for(
            operator_uid=operator_uid, status_filter=status_filter
        ).order_by('-created_at')

    def destroy(self, request, *args, **kwargs) -> Response:
        """Выполняет мягкое удаление карты с откатом версии.

        Переопределяет стандартный метод удаления DRF для вызова сервисного слоя.

        Args:
            request (Request): HTTP-запрос.
            args: Позиционные аргументы.
            kwargs: Именованные аргументы.

        Returns:
            Response: Ответ со статусом 204 No Content.
        """
        instance = self.get_object()

        TechCardService.delete_template(instance)

        return Response(status=status.HTTP_204_NO_CONTENT)
