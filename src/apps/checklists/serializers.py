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
    TemplateFieldGroup, ChecklistAttachment,
)


class FieldChoiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для вариантов ответов.
    Используется исключительно для полей типа 'CHOICE' (выпадающий список).
    """

    class Meta:
        model = FieldChoice
        fields = ['value', 'order']


class TemplateFieldSerializer(serializers.ModelSerializer):
    """
    Сериализатор для поля шаблона анкеты.
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
            'metadata',
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
                raise serializers.ValidationError(
                    {
                        'choices': 'Для типа "Выбор из списка" необходимо передать хотя бы один вариант ответа.'
                    }
                )
        elif choices:
            attrs['choices'] = []

        return attrs


class AnswerItemSerializer(serializers.Serializer):
    """Вспомогательный сериализатор для ответов с комментарием."""

    value = serializers.CharField(allow_blank=True)
    comment = serializers.CharField(allow_blank=True, required=False, default='')


class TemplateFieldGroupSerializer(serializers.ModelSerializer):
    """Вспомогательный сериализатор для представления группы полей шаблона."""

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

    Особенности:
    - Проверяет наличие ответов на все ОБЯЗАТЕЛЬНЫЕ поля (если анкета не является черновиком).
    - Выполняет Type Casting (приведение типов) "на лету", гарантируя, что
      строковые ответы пользователя соответствуют требованиям БД (INTEGER, DATE, BOOLEAN).
    - Передает провалидированные данные слою Сервисов для последующего сохранения.
    """

    equipment_uid = serializers.CharField(
        max_length=255, write_only=True, required=False
    )
    checklist_type = serializers.CharField(
        max_length=50, write_only=True, required=False
    )

    user_uid = serializers.CharField(max_length=36)

    shift_number = serializers.ChoiceField(choices=ShiftTypes, required=False)
    shift_time = serializers.DateTimeField(required=False, allow_null=True)
    is_draft = serializers.BooleanField(default=False)
    answers = serializers.DictField(child=AnswerItemSerializer(), allow_empty=True)
    general_comment = serializers.CharField(
        allow_blank=True, required=False, default=''
    )
    external_id = serializers.CharField(max_length=255, required=False, allow_null=True)
    source_service = serializers.CharField(
        max_length=100, required=False, allow_null=True
    )

    def validate(self, attrs):
        """
        Главный оркестратор динамической валидации EAV-структуры.

        Шаги:
        1. Получает эталонный шаблон (из БД при создании, либо из инстанса при обновлении).
        2. Проверяет отсутствие пропущенных обязательных полей (только для чистовиков).
        3. Запускает проверку типов данных для каждого присланного ответа.

        Returns:
            Словарь с подготовленными данными (добавляет ключи 'template' и 'validated_answers').
        """
        answers_data = attrs.get('answers', {})
        is_draft = attrs.get('is_draft', False)

        template = self._get_active_template(attrs)

        template_fields = {}
        for group in template.groups.all():
            for f in group.fields.all():
                template_fields[str(f.id)] = f

        self._check_missing_required_fields(template_fields, answers_data, is_draft)
        validated_answers = self._process_and_validate_answers(
            template_fields, answers_data, is_draft
        )

        attrs['template'] = template
        attrs['validated_answers'] = validated_answers
        return attrs

    def _get_active_template(self, attrs):
        """
        Извлекает шаблон из БД с использованием кастомного Менеджера.

        Raises:
            ValidationError: Если активного шаблона для данного оборудования не существует.
        """
        if self.instance:
            return self.instance.template

        template = Template.objects.get_active(
            attrs.get('equipment_uid'), attrs.get('checklist_type')
        )
        if not template:
            raise ValidationError('Активный шаблон для данного оборудования не найден.')
        return template

    def _process_and_validate_answers(self, template_fields, answers_data, is_draft):
        """
        Прогоняет каждый ответ пользователя через индивидуальный валидатор типов.
        Игнорирует пустые ответы для необязательных полей или черновиков.

        Returns:
            Список подготовленных словарей [{'field': объект_поля, 'value': значение, 'comment': комментарий}].
        """
        errors = {}
        validated_answers = []

        for f_id, answer_obj in answers_data.items():
            if f_id not in template_fields:
                errors[f_id] = 'Поле не принадлежит этому шаблону.'
                continue

            field = template_fields[f_id]
            value = str(answer_obj.get('value', '')).strip()
            comment = str(answer_obj.get('comment', '')).strip()

            if not field.is_required and value == '':
                validated_answers.append(
                    {
                        'field': field,
                        'value': value,
                        'comment': comment,
                    }
                )
                continue

            if field.is_required and value == '' and not is_draft:
                errors[f_id] = 'Обязательное поле не может быть пустым.'
                continue

            if value == '':
                validated_answers.append(
                    {
                        'field': field,
                        'value': value,
                        'comment': comment,
                    }
                )
                continue

            error_msg = self._validate_single_field(field, value)
            if error_msg:
                errors[f_id] = error_msg
            else:
                validated_answers.append(
                    {
                        'field': field,
                        'value': value,
                        'comment': comment,
                    }
                )

        if errors:
            raise ValidationError(errors)

        return validated_answers

    @staticmethod
    def _check_missing_required_fields(template_fields, answers_data, is_draft):
        """Проверяет, все ли обязательные поля присутствуют (отключается, если is_draft=True)."""
        if is_draft:
            return

        required_fields = {str(f.id) for f in template_fields.values() if f.is_required}
        missing = required_fields - set(answers_data.keys())
        if missing:
            raise ValidationError(
                f'Пропущены обязательные поля (ID): {", ".join(missing)}'
            )

    @staticmethod
    def _validate_single_field(field, value):
        """
        Низкоуровневая проверка значения для конкретного поля шаблона.
        Убеждается, что строку можно безопасно конвертировать в целевой тип БД.

        Returns:
            Строка с текстом ошибки, либо None, если проверка пройдена.
        """
        if field.field_type == FieldTypes.INTEGER and not value.lstrip('-').isdigit():
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
        """
        Определяет формат ответа после успешного POST/PUT запроса.
        Делегирует сериализацию объекту ChecklistResultListSerializer для выдачи полной иерархии.
        """
        return ChecklistResultListSerializer(instance, context=self.context).data


class ChecklistAnswerSerializer(serializers.ModelSerializer):
    """Сериализатор для вывода конкретного ответа пользователя (содержит значение и комментарий)."""

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


class ChecklistAttachmentSerializer(serializers.ModelSerializer):
    """
    Сериализатор для ВЫДАЧИ информации о прикрепленном файле.
    Django REST Framework автоматически преобразует относительный путь файла
    в абсолютный HTTP-URL (например, http://localhost/media/...), чтобы
    фронтенд мог сразу отобразить картинку или дать ссылку на скачивание.
    """
    class Meta:
        model = ChecklistAttachment
        fields = ['id', 'file', 'uploaded_at']


class ChecklistAttachmentUploadSerializer(serializers.ModelSerializer):
    """
    Сериализатор для ВАЛИДАЦИИ входящего файла при его загрузке.
    Используется исключительно в связке с MultiPartParser для обработки form-data.
    """
    class Meta:
        model = ChecklistAttachment
        fields = ['file']


class ChecklistResultListSerializer(serializers.ModelSerializer):
    """
    Сериализатор для вывода истории заполненных чек-листов.
    Инкапсулирует в себе ответы пользователя (answers) и подписи (signatures).
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
    attachments = ChecklistAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ChecklistResult
        fields = [
            'id',
            'equipment_uid',
            'user_uid',
            'external_id',
            'source_service',
            'checklist_type',
            'checklist_type_display',
            'shift_number',
            'shift_time',
            'is_draft',
            'is_completed',
            'is_deprecated',
            'general_comment',
            'created_at',
            'updated_at',
            'signatures',
            'answers',
            'attachments'
        ]


class ChecklistSignatureSerializer(serializers.ModelSerializer):
    """Сериализатор для представления электронных подписей анкеты."""

    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = ChecklistSignature
        fields = ['role', 'role_display', 'user_uid', 'signed_at']


class ChecklistSignSerializer(serializers.Serializer):
    """
    Сериализатор для валидации запроса на подписание анкеты.
    Позволяет Swagger'у правильно отрисовать форму для эндпоинта /sign/.
    """

    role = serializers.ChoiceField(
        choices=SignatureRoles,
        help_text='Роль подписанта (например, APPROVER)',
    )
    user_uid = serializers.CharField(
        max_length=255, help_text='UID пользователя, ставящего подпись'
    )
