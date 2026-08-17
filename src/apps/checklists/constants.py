from django.db import models


class ChecklistTypes(models.TextChoices):
    """Типы чек-листов."""

    INSPECTION = 'INSPECTION', 'Осмотр'
    ACCEPTANCE = 'ACCEPTANCE', 'Приемка'
    HANDOVER = 'HANDOVER', 'Сдача'


class FieldTypes(models.TextChoices):
    """Типы полей в анкетах."""

    STRING = 'STRING', 'Строка'
    INTEGER = 'INTEGER', 'Целое число'
    CHOICE = 'CHOICE', 'Выбор из списка'
    CHECKBOX = 'CHECKBOX', 'Чекбокс'
    DATE = 'DATE', 'Дата'
    AUTO_DATE = 'AUTO_DATE', 'Автоматическая дата'


class ShiftTypes(models.TextChoices):
    """Варианты рабочих смен."""

    DAY = 'DAY', 'Дневная'
    NIGHT = 'NIGHT', 'Ночная'


class SignatureRoles(models.TextChoices):
    """Роли для электронных подписей."""

    AUTHOR = 'AUTHOR', 'Составитель'
    APPROVER = 'APPROVER', 'Утверждающий (Подписант)'
    READER = 'READER', 'Ознакомлен (Читатель)'
