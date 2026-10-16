from rest_framework import serializers

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
            'created_at',
            'updated_at',
            'sections',
        ]
        read_only_fields = ['id', 'version', 'status', 'created_at', 'updated_at']
        validators = []

    def create(self, validated_data: dict) -> TechCard:
        """Перехватывает создание и делегирует логику сервисному слою.

        Args:
            validated_data (dict): Валидированные данные из запроса.

        Returns:
            TechCard: Созданная технологическая карта.
        """
        return TechCardService.create_template(validated_data)
