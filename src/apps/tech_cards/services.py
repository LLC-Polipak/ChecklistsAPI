from django.db import transaction
from django.db.models import Max

from apps.core.constants import DocumentStatus
from apps.tech_cards.models import TechCard, TechCardParameter, TechCardSection


class TechCardService:
    """Сервис для управления бизнес-логикой технологических карт.

    Обеспечивает создание новых ревизий (версий) документов,
    их глубокое копирование и безопасное переключение статусов.
    """

    @classmethod
    @transaction.atomic
    def create_template(cls, validated_data: dict) -> TechCard:
        """Создает новый актуальный шаблон карты и архивирует предыдущий.

        Извлекает данные для карты, разделов и параметров из словаря
        validated_data, сохраняет их в БД с учетом иерархии (вложенности).

        Args:
            validated_data (dict): Валидированные данные из сериализатора.

        Returns:
            TechCard: Созданный инстанс новой актуальной карты.
        """
        equipment_uid = validated_data.get('equipment_uid')
        article = validated_data.get('article')
        equipment_seq_num = validated_data.get('equipment_seq_num', '')

        card_type = validated_data.get('card_type', 'base')
        author_uid = validated_data.get('author_uid', '')

        TechCard.objects.filter(
            equipment_uid=equipment_uid,
            article=article,
            equipment_seq_num=equipment_seq_num,
            card_type=card_type,
            author_uid=author_uid,
            status=DocumentStatus.ACTIVE,
        ).update(status='archived')

        max_version = (
            TechCard.objects.filter(
                equipment_uid=equipment_uid,
                article=article,
                equipment_seq_num=equipment_seq_num,
                card_type=card_type,
                author_uid=author_uid,
            ).aggregate(max_v=Max('version'))['max_v']
            or 0
        )

        next_version = max_version + 1

        sections_data = validated_data.pop('sections', [])

        new_card = TechCard.objects.create(
            **validated_data, version=next_version, status=DocumentStatus.ACTIVE
        )

        cls._create_sections(new_card, None, sections_data)
        return new_card

    @classmethod
    def _create_sections(
        cls, card: TechCard, parent_section, sections_data: list
    ) -> None:
        """Рекурсивно создает разделы, подразделы и их параметры."""
        for section_data in sections_data:
            parameters_data = section_data.pop('parameters', [])
            subsections_data = section_data.pop('subsections', [])

            section = TechCardSection.objects.create(
                card=card, parent=parent_section, **section_data
            )

            params_to_create = [
                TechCardParameter(section=section, **param_data)
                for param_data in parameters_data
            ]
            if params_to_create:
                TechCardParameter.objects.bulk_create(params_to_create)

            if subsections_data:
                cls._create_sections(card, section, subsections_data)

    @classmethod
    @transaction.atomic
    def delete_template(cls, card: TechCard) -> None:
        """Помечает карту как удаленную и восстанавливает из архива предыдущую версию.

        Args:
            card (TechCard): Карта, подлежащая удалению (Soft Delete).
        """
        was_active = card.status == DocumentStatus.ACTIVE
        card.status = DocumentStatus.DELETED
        card.save(update_fields=['status'])

        if was_active:
            previous_card = (
                TechCard.objects.filter(
                    equipment_uid=card.equipment_uid,
                    article=card.article,
                    equipment_seq_num=card.equipment_seq_num,
                    card_type=card.card_type,
                    author_uid=card.author_uid,
                    status=DocumentStatus.ARCHIVED,
                )
                .order_by('-version')
                .first()
            )

            if previous_card:
                previous_card.status = DocumentStatus.ACTIVE
                previous_card.save(update_fields=['status'])
