from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.checklists.models import ChecklistAnswer, ChecklistResult, \
    FieldChoice, Template, TemplateField


class FieldChoiceSerializer(serializers.ModelSerializer):
    """
    DTO для вариантов ответов.
    Используется исключительно для полей типа 'CHOICE' (выпадающий список)
    """

    class Meta:
        model = FieldChoice
        fields = ['value', 'order']


class TemplateFieldSerializer(serializers.ModelSerializer):
    """
    DTO для поля шаблона анкеты.
    Описывает конкретный вопрос, его тип и возможные варианты ответа (если применимо).
    """

    choices = FieldChoiceSerializer(many=True, required=False)
    field_type_display = serializers.CharField(source='get_field_type_display',
                                               read_only=True)

    class Meta:
        model = TemplateField
        fields = [
            'id',
            'name',
            'field_type',
            'field_type_display',
            'order',
            'choices',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        """
        Бизнес-валидация: гарантирует что варианты ответов (choices)
        сохраняются только для поля типа CHOICE. Для остальных типов очищает массив.
        """

        field_type = attrs.get('field_type')
        choices = attrs.get('choices', [])

        if field_type == TemplateField.FieldTypes.CHOICE:
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
    Записываемый вложенный сериализатор для шаблона.
    Преобразует глубокий JSON от клиента в нормализованную реляционную структуру БД.
    """

    fields = TemplateFieldSerializer(many=True)
    checklist_type_display = serializers.CharField(source='get_checklist_type_display',
                                                   read_only=True)

    has_results = serializers.SerializerMethodField()

    class Meta:
        fields = [
            'id',
            'equipment_uid',
            'checklist_type_display',
            'checklist_type',
            'created_at',
            'updated_at',
            'is_deprecated',
            'has_results',
            'fields',
        ]
        model = Template
        read_only_fields = ['id', 'created_at', 'updated_at', 'has_results']

    def get_has_results(self, obj):
        return obj.results.exists()

    @transaction.atomic
    def create(self, validated_data):
        """
        Атомарно сохраняет заголовок шаблон, его поля и варианты выбора.
        """

        fields_data = validated_data.pop('fields', [])
        equipment_uid = validated_data.get('equipment_uid')
        checklist_type = validated_data.get('checklist_type')

        Template.objects.filter(
            equipment_uid=equipment_uid,
            checklist_type=checklist_type,
            is_deprecated=False
        ).update(is_deprecated=True)

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

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Атомарно изменяет шаблон, его поля и варианты выбора.

        Если по изменяемому шаблону существует заполненный чек-лист,
        выкидывает ошибку ValidationError.
        """
        if instance.results.exists():
            raise ValidationError(
                "Невозможно изменить шаблон, так как по нему уже есть заполненные анкеты. "
                "Создайте новый шаблон."
            )

        fields_data = validated_data.pop('fields', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if fields_data:
            instance.fields.all().delete()
            for field_data in fields_data:
                choices_data = field_data.pop('choices', [])
                field = TemplateField.objects.create(template=instance,
                                                     **field_data)

                if choices_data:
                    choice_objects = [FieldChoice(field=field, **c) for c in
                                      choices_data]
                    FieldChoice.objects.bulk_create(choice_objects)

        return instance


    def validate_fields(self, value):
        """
        Проверяет, что порядковые номера полей не дублируются.
        """

        orders = [field.get('order') for field in value if
                  field.get('order') is not None]

        if len(orders) != len(set(orders)):
            raise serializers.ValidationError(
                "Порядковые номера полей (order) должны быть уникальными.")
        return value


class ChecklistResultCreateSerializer(serializers.Serializer):
    """
    Сериализатор для принятия и динамической валидации заполненной анкеты.
    Проверяет наличие ответов на все поля.
    Динамически валидирует типы присланных строковых данных, приводимость к INTEGER,
    допустимость Boolean, наличие значения в списке FieldChoice.
    """

    equipment_uid = serializers.CharField(max_length=255)
    user_uid = serializers.CharField(max_length=255)
    checklist_type = serializers.CharField(max_length=50, write_only=True)

    answers = serializers.DictField(
        child=serializers.CharField(), allow_empty=False, write_only=True
    )

    def validate(self, attrs):
        """
        Ядро динамической валидации EAV-структуры.

        Алгоритм работы:
        1. Извлекает эталонный шаблон из БД (с prefetch_related для минимизации запросов).
        2. Сверяет ключи присланных ответов с ID полей шаблона, гарантируя,
           что нет пропущенных обязательных полей.
        3. Выполняет Type Casting (приведение типов) на лету: проверяет, является ли
           строка корректным числом (INTEGER), булевым значением (CHECKBOX) или
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

        errors = {}
        validated_answers = []

        for f_id, value in answers_data.items():
            if f_id not in template_fields:
                errors[f_id] = "Поле не принадлежит этому шаблону."
                continue

            field = template_fields[f_id]
            error_msg = self._validate_single_field(field, value)

            if error_msg:
                errors[f_id] = error_msg
            else:
                validated_answers.append({'field': field, 'value': value})

        if errors:
            raise ValidationError(errors)

        attrs['template'] = template
        attrs['validated_answers'] = validated_answers

        return attrs

    @staticmethod
    def _validate_single_field(self, field, value):
        """
        Вспомогательный метод: проверяет одно поле.
        Возвращает текст ошибки или None.
        """

        if (field.field_type == TemplateField.FieldType.NUMBER
                and not value.lstrip(
                '-').isdigit()):
            return f"Поле '{field.name}' должно быть целым числом."

        elif field.field_type == TemplateField.FieldType.CHOICE:
            valid_choices = [c.value for c in field.choices.all()]
            if value not in valid_choices:
                return f"Значение '{value}' недопустимо. Варианты: {valid_choices}"

        elif field.field_type == TemplateField.FieldType.CHECKBOX:
            if value.lower() not in ['true', 'false', '1', '0']:
                return f"Поле '{field.name}' должно быть логическим (true/false)."

        return None

    @transaction.atomic
    def create(self, validated_data):
        """
        Сохранение провалидированных результатов анкетирования.
        Создает заголовок результата и привязывает к нему массив ответов (ResultAnswer).
        """

        result = ChecklistResult.objects.create(
            template=validated_data['template'],
            user_uid=validated_data['user_uid'],
        )

        answers_to_create = [
            ChecklistAnswer(result=result, field=item['field'], value=item['value'])
            for item in validated_data['validated_answers']
        ]

        ChecklistAnswer.objects.bulk_create(answers_to_create)

        return result

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Атомарно изменяет заполненный чек-лист, а также его ответы.
        """

        instance.user_uid = validated_data.get('user_uid', instance.user_uid)
        instance.save()

        validated_answers = validated_data.get('validated_answers', None)
        if validated_answers:
            for item in validated_answers:
                ChecklistAnswer.objects.update_or_create(
                    result=instance,
                    field=item['field'],
                    defaults={'value': item['value']},
                )
        return instance


class ChecklistAnswerSerializer(serializers.ModelSerializer):
    """
    DTO для вывода конкретного ответа пользователя.
    Подтягивает названия и типы полей из связанной таблицы для удобства фронтенда.
    """

    field_name = serializers.CharField(source='field.name')
    field_type = serializers.CharField(source='field.field_type')

    field_type_display = serializers.CharField(source='field.get_field_type_display', read_only=True)

    class Meta:
        model = ChecklistAnswer
        fields = [
            'field_id',
            'field_name',
            'field_type',
            'field_type_display',
            'value'
        ]


class ChecklistResultListSerializer(serializers.ModelSerializer):
    """
    DTO для вывода истории заполненных чек-листов (включая вложенные ответы).
    """

    checklist_type = serializers.CharField(source='template.checklist_type')
    checklist_type_display = serializers.CharField(
        source='template.get_checklist_type_display',
        read_only=True
    )
    equipment_uid = serializers.CharField(source='template.equipment_uid', read_only=True)

    answers = ChecklistAnswerSerializer(many=True)

    class Meta:
        model = ChecklistResult
        fields = [
            'id',
            'equipment_uid',
            'user_uid',
            'checklist_type',
            'checklist_type_display',
            'created_at',
            'updated_at',
            'answers'
        ]
