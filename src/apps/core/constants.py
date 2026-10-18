from django.db import models


class DocumentStatus(models.TextChoices):
    """Перечисление статусов жизненного цикла документа."""

    DRAFT = 'draft', 'Черновик'
    ACTIVE = 'active', 'Активный'
    ARCHIVED = 'archived', 'В архиве'
    DELETED = 'deleted', 'Удален'
