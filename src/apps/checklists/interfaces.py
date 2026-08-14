from typing import Protocol

from django.db.models import QuerySet

from apps.checklists.models import ChecklistResult, ChecklistSignature, Template


class ITemplateRepository(Protocol):
    """
    Абстрактный шлюз (интерфейс) для доступа к данным Шаблонов.
    Скрывает детали реализации БД от бизнес-логики.
    """

    def get_active_template(
        self, equipment_uid: str, checklist_type: str
    ) -> Template | None:
        """Возвращает актуальную (не устаревшую) версию шаблона для оборудования."""
        ...

    def deprecate_templates(self, equipment_uid: str, checklist_type: str) -> None:
        """Помечает все активные шаблоны данного оборудования как устаревшие."""
        ...

    def save_template_hierarchy(
        self, template_data: dict, groups_data: list
    ) -> Template:
        """Сохраняет всю иерархию: Шаблон -> Группы -> Поля -> Варианты выбора."""
        ...

    def get_unique_equipments(self) -> list[str]:
        """Возвращает список уникальных UID оборудования для подсказок на фронтенде."""
        ...

    def get_template_history(self, equipment_uid: str, checklist_type: str) -> QuerySet:
        """Возвращает историю всех версий конкретного шаблона."""
        ...

    def delete_template(self, template: Template) -> None:
        """Удаляет шаблон из БД."""
        ...

    def restore_latest_deprecated_template(
        self, equipment_uid: str, checklist_type: str
    ) -> None:
        """Находит самую свежую устаревшую версию шаблона и делает ее активной."""
        ...


class IResultRepository(Protocol):
    """Абстрактный шлюз (интерфейс) для доступа к данным Анкет (Результатов)."""

    def get_result_by_id(self, result_id: int) -> ChecklistResult:
        """Ищет анкету по первичному ключу."""
        ...

    def save_result_with_answers(
        self, result_data: dict, answers_data: list
    ) -> ChecklistResult:
        """Сохраняет заголовок анкеты и массово сохраняет ответы пользователя."""
        ...

    def deprecate_result(self, result: ChecklistResult) -> None:
        """Помечает анкету как устаревшую при ее редактировании."""
        ...

    def upsert_signature(
        self, result: ChecklistResult, role: str, user_uid: str
    ) -> tuple[ChecklistSignature, bool]:
        """
        Создает новую подпись или обновляет существующую.
        Возвращает кортеж: (объект_подписи, был_ли_создан_новый).
        """
        ...

    def get_result_history(self, origin_id: int) -> QuerySet:
        """Возвращает оригинальную анкету и все её измененные версии."""
        ...

    def delete_result(self, result: ChecklistResult) -> None:
        """Удаляет анкету из БД."""
        ...

    def restore_latest_deprecated_result(self, origin_id: int) -> None:
        """
        Находит самую свежую устаревшую версию в цепочке истории
        и делает ее активной.
        """
        ...
