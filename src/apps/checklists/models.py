"""Определение моделей базы данных для системы чек-листов."""

from django.db import models

from apps.checklists.constants import (
    ChecklistTypes,
    FieldTypes,
    ShiftTypes,
    SignatureRoles,
)
from apps.checklists.managers import ChecklistResultManager, TemplateManager
from apps.checklists.querysets import ChecklistResultQuerySet, TemplateQuerySet


class Template(models.Model):
    """
    Главная модель шаблона.

    Определяет набор полей, которые необходимо заполнить
    при выполнении осмотра, приемки или сдачи оборудования.
    """

    equipment_uid = models.CharField('UID-оборудования', max_length=36, db_index=True)
    checklist_type = models.CharField(
        'Тип чек-листа', max_length=50, choices=ChecklistTypes
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    is_deprecated = models.BooleanField('Устаревший', default=False)

    objects = TemplateManager.from_queryset(TemplateQuerySet)()

    class Meta:
        verbose_name = 'Шаблон чек-листа'
        verbose_name_plural = 'Шаблоны чек-листов'

    def __str__(self):
        status = '[УСТАРЕЛ]' if self.is_deprecated else ''
        return f'{status}{self.get_checklist_type_display()}({self.equipment_uid})'


class TemplateFieldGroup(models.Model):
    """
    Модель для группировки полей в шаблоне.

    Включает в себя ссылку на шаблон, имя группы, а также
    порядок расположения в шаблоне.
    """

    template = models.ForeignKey(
        'Template', on_delete=models.CASCADE, related_name='groups'
    )
    name = models.CharField('Название группы', max_length=255)
    order = models.PositiveIntegerField('Порядок отображения группы', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Группа полей'
        verbose_name_plural = 'Группы полей'
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'order'], name='unique_group_order_per_template'
            )
        ]

    def __str__(self):
        return f'{self.name} (Шаблон {self.template_id})'


class TemplateField(models.Model):
    """
    Описание одного поля анкеты.

    Определяет тип данных, обязательность и порядок отображения.
    Для типа CHOICE список значений хранится в FieldChoice.
    """

    group = models.ForeignKey(
        TemplateFieldGroup, on_delete=models.CASCADE, related_name='fields'
    )

    name = models.CharField('Название поля', max_length=255)
    field_type = models.CharField('Тип поля', max_length=20, choices=FieldTypes)
    order = models.PositiveIntegerField('Порядок отображения', default=0)
    is_required = models.BooleanField('Обязательное поле', default=True)
    default_value = models.TextField('Значение по умолчанию', blank=True,
                                     default='')

    metadata = models.JSONField('Метаданные (Фронтенд)', default=dict, blank=True)

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['group', 'order'], name='unique_field_order_per_group'
            )
        ]
        verbose_name = 'Поле шаблона'
        verbose_name_plural = 'Поля шаблонов'

    def __str__(self):
        return f'{self.name}({self.get_field_type_display()})'


class FieldChoice(models.Model):
    """
    Допустимое значение для поля типа CHOICE.

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

    Содержит информацию о шаблоне, оборудовании, пользователе
    и результатах проверки. Поддерживает версионирование через поле origin.
    """

    template = models.ForeignKey(
        Template, on_delete=models.PROTECT, related_name='results'
    )
    user_uid = models.CharField('UID Пользователя', max_length=255, db_index=True)

    shift_number = models.CharField(
        'Номер смены', max_length=10, choices=ShiftTypes, null=True
    )
    shift_time = models.DateTimeField('Время смены', null=True)

    is_completed = models.BooleanField('Завершена', default=False)
    is_deprecated = models.BooleanField('Устаревшая версия', default=False)
    is_draft = models.BooleanField('Черновик', default=False)
    has_violations = models.BooleanField('Есть отклонения', default=False,
                                         db_index=True)

    origin = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='edits',
        verbose_name='Оригинальная анкета',
    )

    created_at = models.DateTimeField('Дата заполнения', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    general_comment = models.TextField('Общий комментарий', null=True)

    external_id = models.CharField(
        'Внешний ID', max_length=255, null=True, db_index=True
    )
    source_service = models.CharField('Система источник', max_length=100, null=True)

    objects = ChecklistResultManager.from_queryset(ChecklistResultQuerySet)()

    class Meta:
        verbose_name = 'Результат чек-листа'
        verbose_name_plural = 'Результаты чек-листов'

    def __str__(self):
        status = '[ИЗМЕНЕНА] ' if self.is_deprecated else ''
        return f'{status}Анкета {self.id} от {self.user_uid}'

    def check_and_complete(self):
        """Проверить наличие утверждающей подписи и завершить анкету."""
        if self.is_draft:
            return

        if self.signatures.filter(role=SignatureRoles.APPROVER).exists():
            self.is_completed = True
            self.save(update_fields=['is_completed'])


class ChecklistAnswer(models.Model):
    """
    Ответ пользователя на отдельное поле чек-листа.

    Связывает заполненный чек-лист с конкретным полем шаблона.
    """

    result = models.ForeignKey(
        ChecklistResult, on_delete=models.CASCADE, related_name='answers'
    )
    field = models.ForeignKey(
        TemplateField, on_delete=models.PROTECT, related_name='answers'
    )
    value = models.TextField('Текст ответа')
    comment = models.TextField('Замечание', null=True)
    is_violation = models.BooleanField('Отклонение (Негативный ответ)',
                                       default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['result', 'field'], name='unique_answer_per_result'
            )
        ]
        verbose_name = 'Ответ'
        verbose_name_plural = 'Ответы'

    def __str__(self):
        return f'{self.field.name}:{self.value}'


class ChecklistSignature(models.Model):
    """Модель электронной подписи для анкеты."""

    result = models.ForeignKey(
        ChecklistResult, on_delete=models.CASCADE, related_name='signatures'
    )
    role = models.CharField('Роль', max_length=20, choices=SignatureRoles)
    user_uid = models.CharField('UID Подписанта', max_length=255)
    signed_at = models.DateTimeField('Дата подписи', auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['result', 'role'], name='unique_role_signature_per_result'
            )
        ]
        verbose_name = 'Подпись'
        verbose_name_plural = 'Подписи'


class ChecklistAttachment(models.Model):
    """
    Медиафайлы, прикрепленные к результату чек-листа.

    Хранит фотографии дефектов или сканы документов, загруженные пользователем.
    """

    result = models.ForeignKey(
        ChecklistResult, on_delete=models.CASCADE, related_name='attachments'
    )

    file = models.FileField('Файл', upload_to='checklists/attachments/%Y/%m/')
    uploaded_at = models.DateTimeField('Дата загрузки', auto_now_add=True)

    class Meta:
        verbose_name = 'Вложение'
        verbose_name_plural = 'Вложения'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'Вложение к анкете {self.result_id} ({self.file.name})'
