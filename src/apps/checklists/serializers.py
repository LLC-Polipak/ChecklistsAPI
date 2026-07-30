from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import (
    ChecklistAnswer,
    ChecklistsResult,
    FieldChoice,
    Template,
    TemplateField,
)


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

    @transaction.atomic
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

            field = TemplateField.objects.create(template=template, **field_data)

            if choices_data:
                choice_objects = [
                    FieldChoice(field=field, **choice_info)
                    for choice_info in choices_data
                ]
                FieldChoice.objects.bulk_create(choice_objects)

        return template


class ChecklistResultCreateSerializer(serializers.Serializer):
    """
    Сериализатор для принятия и динамической валидации заполненной анкеты.
    Проверяет наличие ответов на все поля.
    Динамически валидирует типы присланных строковых данных, приводимость к NUMBER,
    допустимость Boolean, наличие значения в списке FieldChoice.
    """

    equipment_uid = serializers.CharField(max_length=255)
    user_uid = serializers.CharField(max_length=255)
    checklist_type = serializers.CharField(max_length=50)

    answers = serializers.DictField(child=serializers.CharField(), allow_empty=False)

    def validate(self, attrs):
        """
        Ядро динамической валидации EAV-структуры.

        Алгоритм работы:
        1. Извлекает эталонный шаблон из БД (с prefetch_related для минимизации запросов).
        2. Сверяет ключи присланных ответов с ID полей шаблона, гарантируя,
           что нет пропущенных обязательных полей.
        3. Выполняет Type Casting (приведение типов) на лету: проверяет, является ли
           строка корректным числом (NUMBER), булевым значением (CHECKBOX) или
           существующим вариантом (CHOICE).

        Возвращает подготовленный и безопасный список данных для метода create().
        """

        equipment_uid = attrs.get('equipment_uid')
        checklist_type = attrs.get('checklist_type')
        answers_data = attrs.get('answers')

        try:
            template = Template.objects.prefetch_related('fields__choices').get(
                equipment_uid=equipment_uid, checklist_type=checklist_type
            )
        except Template.DoesNotExist:
            raise ValidationError('Шаблон для данного оборудования и типа не найден.')

        template_fields = {str(f.id): f for f in template.fields.all()}

        missing_fields = set(template_fields.keys()) - set(answers_data.keys())

        if missing_fields:
            raise ValidationError(
                f'Пропущены обязательные поля (ID): {",".join(missing_fields)}'
            )

        validated_answers = []
        for field_id_str, value in answers_data.items():
            if field_id_str not in template_fields:
                raise ValidationError(
                    f'Поле с ID {field_id_str} не принадлежит этому шаблону.'
                )

            field = template_fields[field_id_str]

            if field.field_type == TemplateField.FieldType.INTEGER:
                if not value.lstrip('-').isdigit():
                    raise (
                        ValidationError(
                            f'Поле "{field.name}" должно быть целым числом.'
                        )
                    )

            elif field.field_type == TemplateField.FieldType.CHOICE:
                valid_choices = [c.value for c in field.choices.all()]
                if value not in valid_choices:
                    raise (
                        ValidationError(
                            {
                                field_id_str: f'Значение "{value}" недопустимо. Допустимые: {valid_choices}'
                            }
                        )
                    )

            elif field.field_type == TemplateField.FieldType.CHECKBOX:
                if value.lower() not in ['true', 'false', '1', '0']:
                    raise (
                        ValidationError(
                            {
                                field_id_str: f'Поле "{field.name}" должно быть логическим (true/false).'
                            }
                        )
                    )

        validated_answers.append({'field': field, 'value': value})

        attrs['template'] = template
        attrs['validated_answers'] = validated_answers

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        Сохранение провалидированных результатов анкетирования.
        Создает заголовок результата и привязывает к нему массив ответов (ResultAnswer).
        """

        result = ChecklistsResult.objects.create(
            template=validated_data['template'],
            equipment_uid=validated_data['equipment_uid'],
            user_uid=validated_data['user_uid'],
        )

        answers_to_create = [
            ChecklistAnswer(result=result, field=item['field'], value=item['value'])
            for item in validated_data['validated_answers']
        ]

        ChecklistAnswer.objects.bulk_create(answers_to_create)

        return result
