from django.db import models
from django.db.models import Q

from apps.core.constants import DocumentStatus
from apps.tech_cards.constants import CardType


class TechCardQuerySet(models.QuerySet):
    """Кастомный QuerySet для модели TechCard.

    Инкапсулирует логику фильтрации по статусам и оптимизацию запросов.
    """

    def active(self) -> 'TechCardQuerySet':
        """Фильтрует только активные технологические карты.

        Returns:
            TechCardQuerySet: Отфильтрованный набор данных.
        """
        return self.filter(status='active')

    def archived(self) -> 'TechCardQuerySet':
        """Фильтрует только устаревшие (архивные) технологические карты.

        Returns:
            TechCardQuerySet: Набор данных со статусом 'archived'.
        """
        return self.filter(status='archived')

    def deleted(self) -> 'TechCardQuerySet':
        """Фильтрует только удаленные (Soft Delete) технологические карты.

        Returns:
            TechCardQuerySet: Набор данных со статусом 'deleted'.
        """
        return self.filter(status='deleted')

    def with_full_hierarchy(self) -> 'TechCardQuerySet':
        """Оптимизирует запрос, подтягивая связанные разделы и их параметры.

        Используется для предотвращения проблемы N+1 при отдаче
        карты через API или рендеринге сложных страниц.

        Returns:
            TechCardQuerySet: Оптимизированный набор данных.
        """
        return self.prefetch_related(
            'sections',
            'sections__parameters',
            'sections__subsections',
            'sections__subsections__parameters',
        )

    def available_for(
        self,
        operator_uid: str = None,
        status_filter: DocumentStatus = DocumentStatus.ACTIVE,
    ) -> 'TechCardQuerySet':
        """Формирует выдачу карт, доступных конкретному оператору.

        Бизнес-логика:
        - Всегда отдаются Базовые (эталонные) карты от руководителя.
        - Если передан operator_uid, в выборку добавляются Персональные карты
          этого оператора.
        - Чужие персональные карты полностью исключаются из выборки.

        Args:
            operator_uid (str, optional): Уникальный идентификатор оператора.
                Если None, вернутся только базовые карты.
            status_filter (DocumentStatus, optional): Статус карт для выборки (по умолчанию DocumentStatus.ACTIVE).

        Returns:
            TechCardQuerySet: Отфильтрованный набор доступных карт.
        """
        qs = self.with_full_hierarchy().filter(status=status_filter)

        if operator_uid:
            return qs.filter(
                Q(card_type=CardType.BASE)
                | Q(card_type=CardType.PERSONAL, author_uid=operator_uid)
            )

        return qs.filter(card_type=CardType.BASE)
