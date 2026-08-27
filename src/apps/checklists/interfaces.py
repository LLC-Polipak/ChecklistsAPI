from abc import ABC, abstractmethod


class IChecklistBuilder(ABC):
    """
    Абстрактный интерфейс Строителя.
    Определяет шаги, необходимые для формирования документа анкеты.
    """
    @abstractmethod
    def build_header(self) -> None:
        """Формирует шапку документа (метаданные, даты, смены)."""
        pass

    @abstractmethod
    def build_body(self) -> None:
        """Формирует основное тело документа (таблицы с вопросами и ответами)."""
        pass

    @abstractmethod
    def build_footer(self) -> None:
        """Формирует подвал документа (блок подписантов и комментариев)."""
        pass

    @abstractmethod
    def get_document_bytes(self) -> bytes:
        """Завершает формирование документа и возвращает его в виде байт-строки."""
        pass
