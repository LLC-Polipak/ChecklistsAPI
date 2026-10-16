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
    """API для управления технологическими картами.

    Поддерживает строгую парадигму версионирования.
    Методы PUT и PATCH отключены на уровне архитектуры. Любое обновление
    данных должно происходить через POST (создание новой версии).
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
        """Возвращает базовый QuerySet с подгруженной иерархией.

        По умолчанию (если клиент не запросил явно is_archived)
        оставляем только активные шаблоны, чтобы не засорять выдачу.

        Returns:
            QuerySet: Оптимизированный набор карт.
        """
        queryset = TechCard.objects.with_full_hierarchy()

        if self.action == 'list':
            return queryset.filter(status=DocumentStatus.ACTIVE)

        return queryset

    def destroy(self, request, *args, **kwargs) -> Response:
        """Удаляет технологическую карту с применением бизнес-логики.

        Полностью переопределяет базовый метод для явного вызова сервисного
        слоя и самостоятельного формирования HTTP-ответа.

        Args:
            request (Request): HTTP-запрос.

        Returns:
            Response: Пустой ответ со статусом 204 No Content при успехе.
        """
        instance = self.get_object()

        TechCardService.delete_template(instance)

        return Response(status=status.HTTP_204_NO_CONTENT)
