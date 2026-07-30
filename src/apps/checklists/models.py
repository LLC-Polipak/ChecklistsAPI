from django.db import models


class Template(models.Model):
    """
    Главная модель шаблона

    Определяет набор полей, которые необходимо заполнить
    при выполнении осмотра, приемки или сдачи оборудования.
    """

    class ChecklistType(models.TextChoices):
        INSPECTION = 'INSPECTION', 'Осмотр'
        ACCEPTANCE = 'ACCEPTANCE', 'Приемка'
        HANDOVER = 'HANDOVER', 'Сдача'

    equipment_uid = models.CharField('UID-оборудования', max_length=255, db_index=True)
    checklist_type = models.CharField(
        'Тип чек-листа', max_length=50, choices=ChecklistType.choices
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        unique_together = ('equipment_uid', 'checklist_type')
        verbose_name = 'Шаблон чек-листа'
        verbose_name_plural = 'Шаблоны чек-листов'

    def __str__(self):
        return f'{self.get_checklist_type_display()}({self.equipment_uid})'


class TemplateField(models.Model):
    """
    Описывает одно поле анкеты, его тип и порядок отображения.
    Для полей с типом ``CHOICE`` список допустимых значений
    хранится в модели ``FieldChoice``.
    """

    class FieldType(models.TextChoices):
        STRING = 'STRING', 'Строка'
        INTEGER = 'INTEGER', 'Целое число'
        CHOICE = 'CHOICE', 'Выбор из списка'
        CHECKBOX = 'CHECKBOX', 'Чекбокс'
        AUTO = 'AUTO', 'Автозаполняемое значение'

    template = models.ForeignKey(
        Template, on_delete=models.CASCADE, related_name='fields'
    )
    name = models.CharField('Название поля', max_length=255)
    field_type = models.CharField('Тип поля', max_length=20, choices=FieldType.choices)
    order = models.PositiveIntegerField('Порядок отображения', default=0)

    class Meta:
        ordering = ['order', 'id']
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

    def __str__(self):
        return self.value


class ChecklistsResult(models.Model):
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
    equipment_uid = models.CharField('UID Оборудования', max_length=255, db_index=True)
    user_uid = models.CharField('UID Пользователя', max_length=255, db_index=True)
    created_at = models.DateTimeField('Дата заполнения', auto_now_add=True)

    class Meta:
        verbose_name = 'Результат чек-листа'
        verbose_name_plural = 'Результаты чек-листов'

    def __str__(self):
        return f'Отчет {self.template.checklist_type} от {self.user_uid}'


class ChecklistAnswer(models.Model):
    """
    Ответ пользователя на отдельное поле чек-листа.

    Связывает заполненный чек-лист с полем шаблона
    и хранит введенное пользователем значение.
    """

    result = models.ForeignKey(
        ChecklistsResult, on_delete=models.CASCADE, related_name='answers'
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
