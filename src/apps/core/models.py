from django.db import models

from apps.core.constants import DocumentStatus


class TimeStampedModel(models.Model):
    """Абстрактная базовая модель для отслеживания времени создания и обновления.

    Attributes:
        created_at (DateTimeField): Дата и время создания записи (автоматически).
        updated_at (DateTimeField): Дата и время последнего обновления записи (автоматически).
    """

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        abstract = True


class AbstractDocument(TimeStampedModel):
    """Абстрактная модель версионируемого документа.

    Является основой для любого справочника или карты в системе.

    Attributes:
        version (PositiveIntegerField): Номер версии документа. Начинается с 1.
        status (CharField): Текущий статус документа (Draft, Active, Archived).
    """

    version = models.PositiveIntegerField(default=1, verbose_name='Версия')
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus,
        default=DocumentStatus.DRAFT,
        verbose_name='Статус',
    )

    class Meta:
        abstract = True


class AbstractSection(TimeStampedModel):
    """Абстрактная модель раздела (категории) внутри документа.

    Attributes:
        name (CharField): Название раздела.
        order (PositiveIntegerField): Порядковый номер для сортировки при выводе.
    """

    name = models.CharField(max_length=255, verbose_name='Название раздела')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')

    class Meta:
        abstract = True
        ordering = ['order', 'id']


class AbstractParameter(TimeStampedModel):
    """Абстрактная модель параметра документа.

    Attributes:
        name (CharField): Название параметра.
        value (CharField): Значение параметра строкой (например, '10,0±2,0').
        unit (CharField): Единица измерения.
        order (PositiveIntegerField): Порядок вывода параметра внутри раздела.
    """

    name = models.CharField(max_length=255, verbose_name='Название параметра')
    value = models.CharField(max_length=500, verbose_name='Значение')
    unit = models.CharField(
        max_length=50, blank=True, default='', verbose_name='Ед. измерения'
    )
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')

    class Meta:
        abstract = True
        ordering = ['order', 'id']
