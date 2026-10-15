"""Константы и перечисления (Enums) для бизнес-логики чек-листов."""

from django.db import models


class ChecklistTypes(models.TextChoices):
    """Бизнес-типы шаблонов чек-листов.

    Определяют жизненный цикл и назначение бланка:
    - INSPECTION: Регулярный плановый осмотр оборудования.
    - ACCEPTANCE: Приемка оборудования перед началом работы.
    - HANDOVER: Сдача оборудования после завершения смены или этапа работ.
    - TECH_CARD: Технологическая карта (контроль качества).
    """

    INSPECTION = 'INSPECTION', 'Осмотр'
    ACCEPTANCE = 'ACCEPTANCE', 'Приемка'
    HANDOVER = 'HANDOVER', 'Сдача'
    TECH_CARD = 'TECH_CARD', 'Технологическая карта'


class FieldTypes(models.TextChoices):
    """Типы данных для динамической генерации полей (EAV-модель).

    Используются фронтендом для отрисовки инпутов и бэкендом для строгой
    валидации входящих значений.
    """

    STRING = 'STRING', 'Строка'
    INTEGER = 'INTEGER', 'Целое число'
    CHOICE = 'CHOICE', 'Выбор из списка'
    CHECKBOX = 'CHECKBOX', 'Чекбокс'
    RADIO = 'RADIO', 'Радио-кнопки (Да/Нет)'
    DATE = 'DATE', 'Дата'
    AUTO_DATE = 'AUTO_DATE', 'Автоматическая дата'


class ShiftTypes(models.TextChoices):
    """Временные смены на производстве.

    Помогают фильтровать и группировать результаты проверок по сменам.
    """

    DAY = 'DAY', 'Дневная'
    NIGHT = 'NIGHT', 'Ночная'
