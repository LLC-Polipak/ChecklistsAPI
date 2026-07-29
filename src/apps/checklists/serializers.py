from rest_framework import serializers

from .models import FieldChoice, Template, TemplateField


class FieldChoiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор вариантов ответов для выпадающего списка.
    Используется исключительно для полей типа 'Choice.'
    """

    class Meta:
        model = FieldChoice
        fields = ['value', 'order']


class TemplateFieldSerializer(serializers.ModelSerializer):
    """
    Сериализатор структуры отдельного поля чек-листа.
    Обрабатывает вложенные варианты ответов и гарантирует целостность данных.
    """

    choices = FieldChoiceSerializer(many=True, required=False)

    class Meta:
        model = TemplateField
        fields = ['name', 'field_type', 'order', 'choices']

    def validate(self, attrs):
        """
        Валидация поля перед сохранением

        Правила:
        1. Если тип поля 'Choice' -> массив choices обязателен.
        2. Для любых других типов -> массив choices принудительно очищается,
            чтобы избежать мусорных данных в БД.
        """

        field_type = attrs.get('field_type')
        choices = attrs.get('choices', [])

        if field_type == TemplateField.FieldType.CHOICE:
            if not choices:
                raise serializers.ValidationError(
                    {
                        'choices': 'Для типа "Выбор из списка" необходимо передать хотя бы один вариант ответа.'
                    }
                )
            else:
                if choices:
                    attrs['choices'] = []

        return attrs


class TemplateSerializer(serializers.ModelSerializer):
    """
    Главный сериализатор для создания шаблонов чек-листов.
    Принимает комплексный JSON (Шаблон -> Поля -> Варианты выбора)
        и маршрутизирует данные по таблицам.
    """

    fields = TemplateFieldSerializer(many=True)

    class Meta:
        model = Template
        fields = ['id', 'equipment_uid', 'checklist_type', 'created_at', 'fields']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        """
        Переопределенный метод создания со строгой транзакционностью.
        Если произойдет сбой при сохранении любого поля или варианта выбора,
        создание самого шаблона будет отменено.
        """

        fields_data = validated_data.pop('fields', [])

        template = Template.objects.create(**validated_data)

        for field_data in fields_data:
            choices_data = field_data.pop('choices', [])

            field = Template.objects.create(template=template, **field_data)

            if choices_data:
                choice_objects = [
                    FieldChoice(field=field, **choice_info)
                    for choice_info in choices_data
                ]
                FieldChoice.objects.bulk_create(choice_objects)

        return template
