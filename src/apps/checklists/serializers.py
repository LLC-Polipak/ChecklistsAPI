import datetime

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup,
)


class FieldChoiceSerializer(serializers.ModelSerializer):
    """
    DTO для вариантов ответов.
    Используется исключительно для полей типа 'CHOICE' (выпадающий список).
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
    field_type_display = serializers.CharField(
        source='get_field_type_display', read_only=True
    )

    class Meta:
        model = TemplateField
        fields = [
            'id',
            'name',
            'field_type',
            'field_type_display',
            'is_required',
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
                raise serializers.ValidationError({
                    'choices': 'Для типа "Выбор из списка" необходимо передать хотя бы один вариант ответа.'
                })
        elif choices:
            attrs['choices'] = []

        return attrs


class AnswerItemSerializer(serializers.Serializer):
    """Вспомогательный DTO для ответов с комментарием."""
    value = serializers.CharField(allow_blank=True)
    comment = serializers.CharField(allow_blank=True, required=False, default='')


class TemplateFieldGroupSerializer(serializers.ModelSerializer):
    """Вспомогательный DTO для представления группы полей шаблона."""
    fields = TemplateFieldSerializer(many=True)

    class Meta:
        model = TemplateFieldGroup
        fields = ['id', 'name', 'order', 'fields']
        read_only_fields = ['id']


class TemplateSerializer(serializers.ModelSerializer):
    """
    Записываемый вложенный сериализатор для шаблона.
    Преобразует глубокий JSON от клиента в нормализованную реляционную структуру БД.
    """
    groups = TemplateFieldGroupSerializer(many=True)
    checklist_type_display = serializers.CharField(
        source='get_checklist_type_display', read_only=True
    )

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
            'groups',
        ]
        model = Template
        read_only_fields = ['id', 'created_at', 'updated_at', 'has_results']

    def get_has_results(self, obj):
        """Проверяет существует ли на данный шаблон заполненная анкета."""
        return obj.results.exists()

    def validate_groups(self, value):
        """Проверяем уникальность порядка групп и полей внутри них."""
        group_orders = [g.get('order') for g in value if g.get('order') is not None]
        if len(group_orders) != len(set(group_orders)):
            raise serializers.ValidationError(
                'Порядковые номера групп должны быть уникальными.'
            )

        for group in value:
            fields = group.get('fields', [])
            field_orders = [
                f.get('order') for f in fields if f.get('order') is not None
            ]
            if len(field_orders) != len(set(field_orders)):
                raise serializers.ValidationError(
                    f"В группе '{group.get('name')}' дублируются номера полей."
                )
        return value

    @transaction.atomic
    def create(self, validated_data):
        """Атомарно сохраняет заголовок шаблон, его поля и варианты выбора."""
        groups_data = validated_data.pop('groups', [])
        equipment_uid = validated_data.get('equipment_uid')
        checklist_type = validated_data.get('checklist_type')

        Template.objects.filter(
            equipment_uid=equipment_uid,
            checklist_type=checklist_type,
            is_deprecated=False,
        ).update(is_deprecated=True)

        template = Template.objects.create(**validated_data)

        self._create_group_field_data(template, groups_data)

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
                'Невозможно изменить шаблон, так как по нему уже есть заполненные анкеты. '
                'Создайте новый шаблон.'
            )

        if (
            'equipment_uid' in validated_data
            and validated_data['equipment_uid'] != instance.equipment_uid
        ):
            raise ValidationError({
                'equipment_uid': 'Нельзя изменить UID оборудования у существующего шаблона.'
            })

        if (
            'checklist_type' in validated_data
            and validated_data['checklist_type'] != instance.checklist_type
        ):
            raise ValidationError({
                'checklist_type': 'Нельзя изменить тип чек-листа у существующего шаблона.'
            })

        groups_data = validated_data.pop('groups', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if groups_data is not None:
            instance.groups.all().delete()

            self._create_group_field_data(instance, groups_data)

        return instance

    @staticmethod
    def _create_group_field_data(instance, groups_data):
        """Вспомогательный метод для атомарной записи группы полей."""
        for group_data in groups_data:
            fields_data = group_data.pop('fields', [])
            group = TemplateFieldGroup.objects.create(template=instance, **group_data)

            for field_data in fields_data:
                choices_data = field_data.pop('choices', [])
                field = TemplateField.objects.create(group=group, **field_data)

                if choices_data:
                    FieldChoice.objects.bulk_create([
                        FieldChoice(field=field, **c) for c in choices_data
                    ])

    def validate_fields(self, value):
        """Проверяет, что порядковые номера полей не дублируются."""
        orders = [
            field.get('order') for field in value if field.get('order') is not None
        ]

        if len(orders) != len(set(orders)):
            raise serializers.ValidationError(
                'Порядковые номера полей (order) должны быть уникальными.'
            )
        return value


class ChecklistResultCreateSerializer(serializers.Serializer):
    """
    Сериализатор для принятия и динамической валидации заполненной анкеты.
    Проверяет наличие ответов на все поля.
    Динамически валидирует типы присланных строковых данных, приводимость к INTEGER,
    допустимость Boolean, наличие значения в списке FieldChoice.
    """
    equipment_uid = serializers.CharField(
        max_length=255, write_only=True, required=False
    )
    checklist_type = serializers.CharField(max_length=50, write_only=True)

    user_uid = serializers.CharField(max_length=36)

    shift_number = serializers.ChoiceField(
        choices=ChecklistResult.ShiftType, required=False
    )
    shift_time = serializers.DateTimeField(required=False, allow_null=True)

    answers = serializers.DictField(child=AnswerItemSerializer(), allow_empty=True)

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
        answers_data = attrs.get('answers', {})

        if self.instance:
            template = self.instance.template
        else:
            template = (
                Template.objects.prefetch_related('groups__fields__choices')
                .filter(
                    equipment_uid=attrs.get('equipment_uid'),
                    checklist_type=attrs.get('checklist_type'),
                    is_deprecated=False,
                )
                .first()
            )

            if not template:
                raise ValidationError(
                    'Активный шаблон для данного оборудования не найден.'
                )

        template_fields = {}

        for group in template.groups.all():
            for f in group.fields.all():
                template_fields[str(f.id)] = f

        required_fields = {str(f.id) for f in template_fields.values() if f.is_required}

        missing = required_fields - set(answers_data.keys())

        if missing:
            raise ValidationError(
                f'Пропущены обязательные поля (ID): {", ".join(missing)}'
            )

        errors = {}
        validated_answers = []

        for f_id, answer_obj in answers_data.items():
            if f_id not in template_fields:
                errors[f_id] = 'Поле не принадлежит этому шаблону.'
                continue

            field = template_fields[f_id]
            value = answer_obj['value']
            comment = answer_obj.get('comment', '')

            if not field.is_required and value == '':
                validated_answers.append({
                    'field': field,
                    'value': '',
                    'comment': comment,
                })
                continue

            if field.is_required and value == '':
                errors[f_id] = 'Обязательное поле не может быть пустым.'
                continue

            error_msg = self._validate_single_field(field, value)
            if error_msg:
                errors[f_id] = error_msg
            else:
                validated_answers.append({
                    'field': field,
                    'value': value,
                    'comment': comment,
                })

        if errors:
            raise ValidationError(errors)

        attrs['template'] = template
        attrs['validated_answers'] = validated_answers

        return attrs

    @staticmethod
    def _validate_single_field(field, value):
        """
        Вспомогательный метод для валидации: проверяет одно поле.
        Возвращает текст ошибки или None.
        """
        if (
            field.field_type == TemplateField.FieldTypes.INTEGER
            and not value.lstrip('-').isdigit()
        ):
            return f"Поле '{field.name}' должно быть целым числом."
        if field.field_type == TemplateField.FieldTypes.CHOICE:
            valid_choices = [c.value for c in field.choices.all()]
            if value not in valid_choices:
                return f"Значение '{value}' недопустимо. Варианты: {valid_choices}"
        elif field.field_type == TemplateField.FieldTypes.CHECKBOX:
            if value.lower() not in {'true', 'false', '1', '0'}:
                return f"Поле '{field.name}' должно быть логическим (true/false)."
        elif field.field_type == TemplateField.FieldTypes.DATE:
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                return f"Поле '{field.name}' должно быть корректной датой в формате ГГГГ-ММ-ДД."

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
            shift_number=validated_data.get('shift_number', ''),
            shift_time=validated_data.get('shift_time', ''),
        )

        self._create_checklist_answers(result, validated_data)

        ChecklistSignature.objects.create(
            result=result,
            role=ChecklistSignature.Role.AUTHOR,
            user_uid=result.user_uid,
        )

        return result

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Атомарно создает обновленный экземпляр заполненного чек-листа,
        помечая старый как устаревший.
        """
        if instance.is_completed:
            raise ValidationError(
                "Невозможно изменить анкету: "
                "она уже утверждена и закрыта для редактирования."
            )

        instance.is_deprecated = True
        instance.save(update_fields=['is_deprecated'])

        new_result = ChecklistResult.objects.create(
            template=instance.template,
            user_uid=validated_data.get('user_uid', instance.user_uid),
            shift_number=validated_data.get('shift_number', instance.shift_number),
            shift_time=validated_data.get('shift_time', instance.shift_time),
            origin=instance.origin or instance,
        )

        self._create_checklist_answers(new_result, validated_data)

        for old_sig in instance.signatures.all():
            ChecklistSignature.objects.create(
                result=new_result,
                role=old_sig.role,
                user_uid=old_sig.user_uid,
                signed_at=old_sig.signed_at,
            )

        return new_result

    @staticmethod
    def _create_checklist_answers(result, validated_data):
        """Вспомогательный метод для записи ответов анкеты."""
        answers = [
            ChecklistAnswer(
                result=result,
                field=item['field'],
                value=item['value'],
                comment=item['comment'],
            )
            for item in validated_data['validated_answers']
        ]

        ChecklistAnswer.objects.bulk_create(answers)

    def to_representation(self, instance):
        """Переопределяем выдачи ответа после успешного POST/PUT запроса."""
        return ChecklistResultListSerializer(instance, context=self.context).data


class ChecklistAnswerSerializer(serializers.ModelSerializer):
    """
    DTO для вывода конкретного ответа пользователя.
    Подтягивает названия и типы полей из связанной таблицы для удобства фронтенда.
    """
    field_name = serializers.CharField(source='field.name')
    field_type = serializers.CharField(source='field.field_type')

    field_type_display = serializers.CharField(
        source='field.get_field_type_display', read_only=True
    )

    class Meta:
        model = ChecklistAnswer
        fields = [
            'field_id',
            'field_name',
            'field_type',
            'field_type_display',
            'value',
            'comment',
        ]


class ChecklistResultListSerializer(serializers.ModelSerializer):
    """
    DTO для вывода истории заполненных чек-листов (включая вложенные ответы).
    """
    checklist_type = serializers.CharField(
        source='template.checklist_type', read_only=True
    )
    checklist_type_display = serializers.CharField(
        source='template.get_checklist_type_display', read_only=True
    )
    equipment_uid = serializers.CharField(
        source='template.equipment_uid', read_only=True
    )

    answers = ChecklistAnswerSerializer(many=True)

    class Meta:
        model = ChecklistResult
        fields = [
            'id',
            'equipment_uid',
            'user_uid',
            'checklist_type',
            'checklist_type_display',
            'shift_number',
            'shift_time',
            'is_completed',
            'is_deprecated',
            'created_at',
            'updated_at',
            'signatures',
            'answers',
        ]


class ChecklistSignatureSerializer(serializers.ModelSerializer):
    """
    DTO для представления подписей анкет чек-листа.
    """
    role_display = serializers.CharField(source='get_role_display',
                                         read_only=True)

    class Meta:
        model = ChecklistSignature
        fields = ['role', 'role_display', 'user_uid', 'signed_at']


class ChecklistSignSerializer(serializers.Serializer):
    """
    DTO для валидации запроса на подписание анкеты.
    """
    role = serializers.ChoiceField(
        choices=ChecklistSignature.Role,
        help_text="Роль подписанта (например, APPROVER)"
    )
    user_uid = serializers.CharField(
        max_length=255,
        help_text="UID пользователя, ставящего подпись"
    )