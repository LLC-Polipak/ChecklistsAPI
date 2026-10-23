from rest_framework import serializers

from apps.core.constants import DocumentStatus
from apps.tech_cards.constants import MAX_DEPTH, MAX_SECTIONS, CardType
from apps.tech_cards.models import TechCard, TechCardParameter, TechCardSection
from apps.tech_cards.services import TechCardService


class TechCardParameterSerializer(serializers.ModelSerializer):
    """Сериализатор для параметров технологической карты.

    Преобразует модель параметра в JSON и обратно.
    """

    class Meta:
        model = TechCardParameter
        fields = ['id', 'name', 'value', 'unit', 'order']


class TechCardSectionSerializer(serializers.ModelSerializer):
    """Сериализатор для разделов технологической карты.

    Поддерживает рекурсивную отдачу подразделов и параметров.
    Включает в себя только параметры, привязанные непосредственно к этому разделу.
    """

    parameters = TechCardParameterSerializer(many=True, required=False)

    class Meta:
        model = TechCardSection
        fields = ['id', 'name', 'order', 'page_number', 'parameters']
        read_only_fields = ['id']

    def get_fields(self) -> dict:
        """Переопределение метода для поддержки рекурсивной вложенности.

        Returns:
            dict: Словарь полей сериализатора с добавленным полем subsections.
        """
        fields = super().get_fields()
        fields['subsections'] = TechCardSectionSerializer(many=True, required=False)
        return fields


class TechCardSerializer(serializers.ModelSerializer):
    """Сериализатор для технологической карты.

    Отдает корневые элементы карты (информацию об оборудовании) и
    дерево разделов, начиная с верхнего уровня.
    """

    sections = TechCardSectionSerializer(many=True, required=False)
    status_verbose = serializers.CharField(source='get_status_display', read_only=True)

    based_on_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = TechCard
        fields = [
            'id',
            'equipment_uid',
            'article',
            'equipment_seq_num',
            'version',
            'status',
            'status_verbose',
            'card_type',
            'author_uid',
            'created_at',
            'updated_at',
            'sections',
            'based_on_id',
        ]
        read_only_fields = ['id', 'version', 'status', 'created_at', 'updated_at']
        validators = []

    def validate(self, attrs):
        """Выполняет бизнес-валидацию, включая защиту веток (форков)."""
        based_on_id = attrs.pop('based_on_id', None)
        card_type = attrs.get('card_type', CardType.BASE)
        author_uid = attrs.get('author_uid', '')
        equipment_uid = attrs.get('equipment_uid')
        article = attrs.get('article')
        equipment_seq_num = attrs.get('equipment_seq_num', '')

        if based_on_id:
            try:
                parent_card = TechCard.objects.get(id=based_on_id)

                if (
                    card_type == CardType.PERSONAL
                    and parent_card.card_type == CardType.PERSONAL
                    and parent_card.author_uid != author_uid
                ):
                    raise serializers.ValidationError(
                        {
                            'non_field_errors': 'Нельзя создать свою версию на основе персональной карты другого оператора. Вносите изменения только в базовый эталон или в свою собственную карту.'
                        }
                    )

                if (
                    card_type == CardType.BASE
                    and parent_card.card_type == CardType.PERSONAL
                ):
                    raise serializers.ValidationError(
                        {
                            'non_field_errors': 'Руководитель не может сохранить базовую (эталонную) карту на основе персональной карты оператора.'
                        }
                    )
            except TechCard.DoesNotExist:
                pass

        if card_type == CardType.PERSONAL:
            base_exists = TechCard.objects.filter(
                equipment_uid=equipment_uid,
                article=article,
                equipment_seq_num=equipment_seq_num,
                card_type=CardType.BASE,
                status=DocumentStatus.ACTIVE,
            ).exists()

            if not base_exists:
                raise serializers.ValidationError(
                    {
                        'non_field_errors': 'Невозможно сохранить персональные настройки: для данного оборудования и артикула отсутствует базовый эталон.'
                    }
                )

        return attrs

    def validate_sections(self, sections_data: list) -> list:
        """Валидирует иерархию дерева разделов перед сохранением.

        Предотвращает атаки типа "JSON-бомба" (атака на исчерпание памяти и CPU)
        путем ограничения максимальной глубины рекурсивной вложенности подразделов
        и общего количества узлов (разделов) в рамках одной технологической карты.

        Args:
            sections_data (list): Список словарей с данными корневых разделов
                и их вложенных элементов.

        Returns:
            list: Исходный список разделов, если валидация успешно пройдена.

        Raises:
            ValidationError:
                - Если глубина вложенности превышает порог MAX_DEPTH.
                - Если суммарное количество разделов превышает порог MAX_SECTIONS.
        """
        total_sections = 0

        def _walk_tree(sections: list, current_depth: int):
            nonlocal total_sections
            if current_depth > MAX_DEPTH:
                raise serializers.ValidationError(
                    f'Превышена максимальная глубина вложенности разделов (максимум {MAX_DEPTH}).'
                )

            for section in sections:
                total_sections += 1
                if total_sections > MAX_SECTIONS:
                    raise serializers.ValidationError(
                        f'Превышено максимальное количество разделов в карте (максимум {MAX_SECTIONS}).'
                    )

                subsections = section.get('subsections', [])
                if subsections:
                    _walk_tree(subsections, current_depth + 1)

        _walk_tree(sections_data, current_depth=1)
        return sections_data

    def create(self, validated_data: dict) -> TechCard:
        """Перехватывает создание и делегирует логику сервисному слою.

        Args:
            validated_data (dict): Валидированные данные из запроса.

        Returns:
            TechCard: Созданная технологическая карта.
        """
        return TechCardService.create_template(validated_data)
