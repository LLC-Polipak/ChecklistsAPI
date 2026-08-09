from django.db import models


class Template(models.Model):
    """
    Главная модель шаблона

    Определяет набор полей, которые необходимо заполнить
    при выполнении осмотра, приемки или сдачи оборудования.
    """

    class ChecklistTypes(models.TextChoices):
        """
        Возможные типы чек-листов
        """

        INSPECTION = 'INSPECTION', 'Осмотр'
        ACCEPTANCE = 'ACCEPTANCE', 'Приемка'
        HANDOVER = 'HANDOVER', 'Сдача'

    equipment_uid = models.CharField('UID-оборудования', max_length=36, db_index=True)
    checklist_type = models.CharField(
        'Тип чек-листа', max_length=50, choices=ChecklistTypes.choices
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    is_deprecated = models.BooleanField('Устаревший', default=False)

    class Meta:
        verbose_name = 'Шаблон чек-листа'
        verbose_name_plural = 'Шаблоны чек-листов'

    def __str__(self):
        status = "[УСТАРЕЛ]" if self.is_deprecated else ""
        return f'{status}{self.get_checklist_type_display()}({self.equipment_uid})'


class TemplateField(models.Model):
    """
    Описывает одно поле анкеты, его тип и порядок отображения.
    Для полей с типом ``CHOICE`` список допустимых значений
    хранится в модели ``FieldChoice``.
    """

    class FieldTypes(models.TextChoices):
        """
        Возможные типы полей, которые могут быть представлены в шаблоне
        """

        STRING = 'STRING', 'Строка'
        INTEGER = 'INTEGER', 'Целое число'
        CHOICE = 'CHOICE', 'Выбор из списка'
        CHECKBOX = 'CHECKBOX', 'Чекбокс'
        AUTO = 'AUTO', 'Автозаполняемое значение'

    template = models.ForeignKey(
        Template, on_delete=models.CASCADE, related_name='fields'
    )
    name = models.CharField('Название поля', max_length=255)
    field_type = models.CharField('Тип поля', max_length=20, choices=FieldTypes.choices)
    order = models.PositiveIntegerField('Порядок отображения', default=0)
    is_required = models.BooleanField('Обязательное поле', default=True)

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['template', 'order'],
                                    name='unique_field_order_per_template')
        ]
        verbose_name = 'Поле шаблона'
        verbose_name_plural = 'Поля шаблонов'


    def __str__(self):
        return f'{self.name}({self.get_field_type_display()})'


class FieldChoice(models.Model):
    """
    Допустимое значение для поля типа ``CHOICE``.

    Используется для формирования списка вариантов,
    доступных пользователю при заполнении чек-листа.
    """

    field = models.ForeignKey(
        TemplateField, on_delete=models.CASCADE, related_name='choices'
    )
    value = models.CharField('Значение варианта', max_length=255)
    order = models.PositiveIntegerField('Порядок вывода', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Вариант выбора'
        verbose_name_plural = 'Варианты выбора'

    def __str__(self):
        return self.value


class ChecklistResult(models.Model):
    """
    Заполненный экземпляр чек-листа.

    Содержит информацию о шаблоне, оборудовании,
    пользователе и времени заполнения.
    Ответы на отдельные поля хранятся
    в связанных объектах ``ChecklistAnswer``.
    """

    template = models.ForeignKey(
        Template, on_delete=models.PROTECT, related_name='results'
    )
    user_uid = models.CharField('UID Пользователя', max_length=255, db_index=True)

    is_deprecated = models.BooleanField('Устаревшая версия', default=False)

    origin = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='edits',
        verbose_name='Оригинальная анкета'
    )

    created_at = models.DateTimeField('Дата заполнения', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Результат чек-листа'
        verbose_name_plural = 'Результаты чек-листов'

    def __str__(self):
        status = "[ИЗМЕНЕНА] " if self.is_deprecated else ""
        return f"{status}Анкета {self.id} от {self.user_uid}"


class ChecklistAnswer(models.Model):
    """
    Ответ пользователя на отдельное поле чек-листа.

    Связывает заполненный чек-лист с полем шаблона
    и хранит введенное пользователем значение.
    """

    result = models.ForeignKey(
        ChecklistResult, on_delete=models.CASCADE, related_name='answers'
    )
    field = models.ForeignKey(
        TemplateField, on_delete=models.PROTECT, related_name='answers'
    )
    value = models.TextField('Текст ответа')

    class Meta:
        unique_together = ('result', 'field')
        verbose_name = 'Ответ'
        verbose_name_plural = 'Ответы'

    def __str__(self):
        return f'{self.field.name}:{self.value}'
