from django.db import models


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

    def drafts(self) -> 'TechCardQuerySet':
        """Фильтрует только черновые версии карт.

        Returns:
            TechCardQuerySet: Отфильтрованный набор данных.
        """
        return self.filter(status='draft')

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
