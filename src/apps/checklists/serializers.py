import datetime as dt

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.checklists.constants import FieldTypes, ShiftTypes, SignatureRoles
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

        if field_type == FieldTypes.CHOICE:
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
        """Проверяет существование заполненной анкеты на данный шаблон."""
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
        choices=ShiftTypes, required=False
    )
    shift_time = serializers.DateTimeField(required=False, allow_null=True)
    is_draft = serializers.BooleanField(default=False)
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
        is_draft = attrs.get('is_draft', False)

        if self.instance:
            template = self.instance.template
        else:
            from apps.checklists.repositories import DjangoTemplateRepository

            repo = DjangoTemplateRepository()
            template = repo.get_active_template(
                attrs.get('equipment_uid'), attrs.get('checklist_type')
            )
            if not template:
                raise ValidationError(
                    'Активный шаблон для данного оборудования не найден.'
                )

        template_fields = {}

        for group in template.groups.all():
            for f in group.fields.all():
                template_fields[str(f.id)] = f

        if not is_draft:
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

            if field.is_required and value == "" and not is_draft:
                errors[f_id] = "Обязательное поле не может быть пустым."
                continue

            if value == "":
                validated_answers.append({'field': field, 'value': value, 'comment': comment})
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
            field.field_type == FieldTypes.INTEGER
            and not value.lstrip('-').isdigit()
        ):
            return f"Поле '{field.name}' должно быть целым числом."
        if field.field_type == FieldTypes.CHOICE:
            valid_choices = [c.value for c in field.choices.all()]
            if value not in valid_choices:
                return f"Значение '{value}' недопустимо. Варианты: {valid_choices}"
        elif field.field_type == FieldTypes.CHECKBOX:
            if value.lower() not in {'true', 'false', '1', '0'}:
                return f"Поле '{field.name}' должно быть логическим (true/false)."
        elif field.field_type == FieldTypes.DATE:
            try:
                dt.date.fromisoformat(value)
            except ValueError:
                return f"Поле '{field.name}' должно быть корректной датой в формате ГГГГ-ММ-ДД."

        return None

    def to_representation(self, instance):
        """Выдачи ответа после успешного POST/PUT запроса."""
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
    """DTO для вывода истории заполненных чек-листов (включая вложенные ответы)."""

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
    """DTO для представления подписей анкет чек-листа."""

    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = ChecklistSignature
        fields = ['role', 'role_display', 'user_uid', 'signed_at']


class ChecklistSignSerializer(serializers.Serializer):
    """DTO для валидации запроса на подписание анкеты."""

    role = serializers.ChoiceField(
        choices=SignatureRoles,
        help_text='Роль подписанта (например, APPROVER)',
    )
    user_uid = serializers.CharField(
        max_length=255, help_text='UID пользователя, ставящего подпись'
    )
