"""Интерфейсы для строителей документов чек-листов."""

from abc import ABC, abstractmethod


class IChecklistBuilder(ABC):
    """
    Абстрактный интерфейс Строителя.

    Определить шаги, необходимые для формирования документа анкеты.
    """

    @abstractmethod
    def build_header(self) -> None:
        """Сформировать шапку документа (метаданные, даты, смены)."""

    @abstractmethod
    def build_body(self) -> None:
        """Сформировать основное тело документа (таблицы с вопросами и ответами)."""

    @abstractmethod
    def build_footer(self) -> None:
        """Сформировать подвал документа (блок подписантов и комментариев)."""

    @abstractmethod
    def get_document_bytes(self) -> bytes:
        """Завершить формирование документа и вернуть его в виде байт-строки."""
