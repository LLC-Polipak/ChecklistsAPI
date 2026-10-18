from django.db import models

from apps.core.models import AbstractDocument, AbstractParameter, AbstractSection
from apps.tech_cards.managers import TechCardManager


class TechCard(AbstractDocument):
    """Модель Технологической карты оборудования.

    Идентифицируется композитным ключом оборудования, артикула и порядкового номера.
    Каждая комбинация этих трех полей + версия должна быть уникальной.

    Attributes:
        equipment_uid (CharField): Уникальный идентификатор/тип Рабочего центра.
        article (CharField): Артикул производимой продукции.
        equipment_seq_num (CharField): Порядковый номер Рабочего центра (опционально, строка на случай букв).
    """

    objects = TechCardManager()

    equipment_uid = models.CharField(max_length=100, verbose_name='UID Оборудования')
    article = models.CharField(max_length=150, verbose_name='Артикул')
    equipment_seq_num = models.CharField(
        max_length=50, blank=True, default='', verbose_name='Порядковый номер'
    )

    class Meta:
        verbose_name = 'Технологическая карта'
        verbose_name_plural = 'Технологические карты'
        constraints = [
            models.UniqueConstraint(
                fields=['equipment_uid', 'article', 'equipment_seq_num', 'version'],
                name='unique_tech_card_version',
            )
        ]
        indexes = [
            models.Index(fields=['equipment_uid', 'article', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self) -> str:
        """Возвращает строковое представление Технологической карты."""
        seq = f' [{self.equipment_seq_num}]' if self.equipment_seq_num else ''
        return f'{self.equipment_uid}{seq} - {self.article} (v{self.version})'


class TechCardSection(AbstractSection):
    """Раздел внутри конкретной технологической карты.

    Поддерживает вложенность за счет опциональной связи parent.

    Attributes:
        card (ForeignKey): Ссылка на технологическую карту.
        parent (ForeignKey): Ссылка на родительский раздел (для подразделов).
        page_number (PositiveIntegerField): Номер страницы (если фронтенду нужна разбивка).
    """

    card = models.ForeignKey(
        TechCard,
        on_delete=models.CASCADE,
        related_name='sections',
        verbose_name='Технологическая карта',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subsections',
        verbose_name='Родительский раздел',
    )
    page_number = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Номер страницы'
    )

    class Meta(AbstractSection.Meta):
        verbose_name = 'Раздел тех. карты'
        verbose_name_plural = 'Разделы тех. карты'

    def __str__(self) -> str:
        """Возвращает иерархическое название раздела."""
        if self.parent:
            return f'{self.parent.name} -> {self.name}'
        return self.name


class TechCardParameter(AbstractParameter):
    """Конкретный параметр со значением внутри раздела технологической карты.

    Attributes:
        section (ForeignKey): Ссылка на раздел, к которому принадлежит параметр.
    """

    section = models.ForeignKey(
        TechCardSection,
        on_delete=models.CASCADE,
        related_name='parameters',
        verbose_name='Раздел',
    )

    class Meta(AbstractParameter.Meta):
        verbose_name = 'Параметр тех. карты'
        verbose_name_plural = 'Параметры тех. карты'

    def __str__(self) -> str:
        """Возвращает строковое представление параметра."""
        unit_str = f' {self.unit}' if self.unit else ''
        return f'{self.name}: {self.value}{unit_str}'
