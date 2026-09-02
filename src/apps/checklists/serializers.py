"""Сериализаторы для преобразования данных шаблонов и результатов чек-листов."""

import datetime

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.checklists.constants import FieldTypes, ShiftTypes, SignatureRoles
from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistAttachment,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup,
)
from apps.checklists.services import ChecklistResultService, TemplateService


class FieldChoiceSerializer(serializers.ModelSerializer):
    """
    Сериализовать варианты ответов.

    Используется исключительно для полей типа 'CHOICE' (выпадающий список).
    """

    class Meta:
        model = FieldChoice
        fields = ['value', 'order']


class TemplateFieldSerializer(serializers.ModelSerializer):
    """
    Сериализовать поле шаблона анкеты.

    Описывает конкретный вопрос, его тип и возможные варианты ответа.
    """

    choices = FieldChoiceSerializer(many=True, required=False)
    field_type_display = serializers.CharField(
        source='get_field_type_display', read_only=True
    )

    metadata = serializers.DictField(required=False, default=dict)

    class Meta:
        model = TemplateField
        fields = [
            'id',
            'name',
            'field_type',
            'field_type_display',
            'is_required',
            'order',
            'default_value',
            'metadata',
            'choices',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        """
        Проверить бизнес-логику поля.

        Гарантировать, что варианты ответов сохраняются только для поля типа CHOICE.
        Для остальных типов массив очищается. Также проверяет корректность
        значения по умолчанию.
        """
        field_type = attrs.get('field_type')
        choices = attrs.get('choices', [])
        default_value = attrs.get('default_value', '').strip()

        if field_type == FieldTypes.CHOICE and not choices:
            raise serializers.ValidationError({
                                                  "choices": "Для типа 'Выбор из списка' передайте хотя бы один вариант."})
        if field_type != FieldTypes.CHOICE:
            attrs['choices'] = []

        if field_type == FieldTypes.AUTO_DATE:
            default_value = ''

        if default_value:
            method_name = f"_validate_default_{field_type.lower()}"
            validator_method = getattr(self, method_name, None)

            if validator_method:
                error_msg = validator_method(default_value, choices=choices)
                if error_msg:
                    raise serializers.ValidationError(
                        {"default_value": error_msg})

        attrs['default_value'] = default_value
        return attrs

    def _validate_default_integer(self, default_value, **kwargs):
        """Вспомогательный метод для валидации значения по умолчанию для типа INTEGER."""
        if not default_value.lstrip('-').isdigit():
            return "Значение по умолчанию должно быть целым числом."
        return None

    def _validate_default_choice(self, default_value, choices, **kwargs):
        """Вспомогательный метод для валидации значения по умолчанию для типа CHOICE."""
        valid_choices = [c.get('value') for c in choices]
        if default_value not in valid_choices:
            return f"Значение '{default_value}' недопустимо. Варианты: {valid_choices}"
        return None

    def _validate_default_checkbox(self, default_value, **kwargs):
        """Вспомогательный метод для валидации значения по умолчанию для типа CHECKBOX."""
        return self._validate_boolean(default_value)

    def _validate_default_radio(self, default_value, **kwargs):
        """Вспомогательный метод для валидации значения по умолчанию для типа RADIO."""
        return self._validate_boolean(default_value)

    def _validate_default_date(self, default_value, **kwargs):
        """Вспомогательный метод для валидации значения по умолчанию для типа DATE."""
        try:
            import datetime
            datetime.date.fromisoformat(default_value)
        except ValueError:
            return "Дата по умолчанию должна быть в формате ГГГГ-ММ-ДД."

    def _validate_boolean(self, default_value):
        """Вспомошательный метод для валидации булевых значений."""
        if default_value.lower() not in ['true', 'false', '1', '0']:
            return "Для чекбокса значение по умолчанию должно быть 'true' или 'false'."
        return None


class AnswerItemSerializer(serializers.Serializer):
    """Представить ответ с комментарием во входящих данных."""

    field_id = serializers.IntegerField(help_text="ID поля шаблона")
    value = serializers.CharField(allow_blank=True)
    comment = serializers.CharField(allow_blank=True, required=False, default='')


class AnswerGroupSerializer(serializers.Serializer):
    """Представить ответ с полями, входящие в эту группу."""

    group_id = serializers.IntegerField(help_text="ID группы полей из шаблона")
    answers = AnswerItemSerializer(many=True, allow_empty=True)


class TemplateFieldGroupSerializer(serializers.ModelSerializer):
    """Представить группу полей шаблона."""

    fields = TemplateFieldSerializer(many=True)

    class Meta:
        model = TemplateFieldGroup
        fields = ['id', 'name', 'order', 'fields']
        read_only_fields = ['id']

    def validate_fields(self, value):
        """
        Проверить уникальность порядковых номеров полей внутри группы.

        Вызывается автоматически при валидации поля 'fields'.
        """
        orders = [
            f.get('order') for f in value if f.get('order') is not None
        ]
        if len(orders) != len(set(orders)):
            raise serializers.ValidationError(
                'Порядковые номера полей в пределах одной группы '
                'должны быть уникальными.'
            )
        return value


class TemplateSerializer(serializers.ModelSerializer):
    """
    Сериализовать шаблон в нормализованную реляционную структуру БД.

    Поддерживает вложенную запись групп и полей.
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

    @extend_schema_field(serializers.BooleanField())
    def get_has_results(self, obj):
        """Проверить существование заполненной анкеты на данный шаблон."""
        return obj.results.exists()

    def validate(self, attrs):
        """
        Выполнить бизнес-валидацию перед сохранением.

        Защищает используемые шаблоны от изменений и предотвращает
        смену идентичности (UID и Типа).
        """
        if self.instance and self.instance.results.exists():
            raise serializers.ValidationError(
                "Невозможно изменить шаблон, по нему уже есть анкеты."
            )

        if self.instance:
            if 'equipment_uid' in attrs and attrs[
                'equipment_uid'] != self.instance.equipment_uid:
                raise serializers.ValidationError({
                    "equipment_uid": "Нельзя изменить UID оборудования "
                                     "у существующего шаблона."
                })
            if 'checklist_type' in attrs and attrs[
                'checklist_type'] != self.instance.checklist_type:
                raise serializers.ValidationError({
                    "checklist_type": "Нельзя изменить тип чек-листа "
                                      "у существующего шаблона."
                })

        return attrs

    def create(self, validated_data):
        """
        Передать провалидированные данные в Сервисный слой для создания.

        Сервис атомарно сохранит иерархию и выполнит версионирование.
        """
        return TemplateService.create_template(validated_data)

    def update(self, instance, validated_data):
        """Передать данные в Сервисный слой для полного обновления (перезаписи)."""
        return TemplateService.update_template(instance, validated_data)

    def validate_groups(self, value):
        """
        Проверить уникальность порядковых номеров групп в шаблоне.

        Вызывается автоматически при валидации поля 'groups'.
        """
        group_orders = [
            g.get('order') for g in value if g.get('order') is not None
        ]
        if len(group_orders) != len(set(group_orders)):
            raise serializers.ValidationError(
                'Порядковые номера групп в шаблоне должны быть уникальными.'
            )
        return value


class ChecklistResultCreateSerializer(serializers.Serializer):
    """
    Обеспечить прием и динамическую валидацию заполненной анкеты.

    Выполняет проверку типов данных (Type Casting) и контроль обязательных полей.
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
    groups = AnswerGroupSerializer(many=True, allow_empty=True)
    general_comment = serializers.CharField(
        allow_blank=True, required=False, default=''
    )
    external_id = serializers.CharField(max_length=255, required=False, allow_null=True)
    source_service = serializers.CharField(
        max_length=100, required=False, allow_null=True
    )

    def validate(self, attrs):
        """
        Выполнить главную оркестрацию динамической валидации EAV-структуры.

        Шаги:
        1. Получить эталонный шаблон.
        2. Проверить отсутствие пропущенных обязательных полей.
        3. Запустить проверку типов данных для каждого ответа.
        """
        groups_data = attrs.get('groups', [])
        is_draft = attrs.get('is_draft', False)

        template = self._get_active_template(attrs)

        template_fields = {}
        for group in template.groups.all():
            for f in group.fields.all():
                template_fields[str(f.id)] = f

        answers_data = {}
        errors = {}

        for group_item in groups_data:
            g_id = group_item['group_id']

            for ans_obj in group_item['answers']:
                f_id = str(ans_obj['field_id'])

                if f_id not in template_fields:
                    errors[f_id] = "Поле не принадлежит этому шаблону."
                    continue

                field = template_fields[f_id]
                if field.group_id != g_id:
                    errors[
                        f_id] = f"Поле '{field.name}' принадлежит группе ID {field.group_id}, а передано в группе ID {g_id}."
                    continue

                answers_data[f_id] = ans_obj

        if errors:
            raise ValidationError(errors)

        self._check_missing_required_fields(template_fields, answers_data, is_draft)
        validated_answers = self._process_and_validate_answers(
            template_fields, answers_data, is_draft
        )

        attrs.pop('groups', None)
        attrs.pop('equipment_uid', None)
        attrs.pop('checklist_type', None)

        attrs['template'] = template
        attrs['validated_answers'] = validated_answers
        return attrs

    def create(self, validated_data):
        """
        Делегировать сохранение новой анкеты слою Сервисов.

        Сервис проставит подпись автора автоматически.
        """
        return ChecklistResultService.submit_result(validated_data)

    def update(self, instance, validated_data):
        """
        Делегировать обновление анкеты слою Сервисов.

        Реализует Аудиторский след через создание новой версии.
        """
        return ChecklistResultService.update_result(instance, validated_data)

    def to_representation(self, instance):
        """Вернуть расширенный JSON после успешного POST/PUT запроса."""
        return ChecklistResultListSerializer(instance, context=self.context).data

    def _get_active_template(self, attrs):
        """
        Извлечь активный шаблон из базы данных.

        Raises:
            ValidationError: Если шаблон для указанного оборудования не найден.
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
        Проверить каждый ответ пользователя через индивидуальный валидатор типов.

        Returns:
            Список подготовленных словарей с объектами полей и значениями.
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

    def _validate_single_field(self, field, value):
        """
        Выполнить проверку значения для конкретного типа поля.

        Убеждается, что строку можно безопасно конвертировать в целевой тип.
        """
        method_name = f"_validate_{field.field_type.lower()}"
        validator_method = getattr(self, method_name, None)

        if validator_method:
            return validator_method(field, value)

        return None

    def _validate_integer(self, field, value):
        """Метод для валидации поля с типом INTEGER."""
        if not value.lstrip('-').isdigit():
            return f"Поле '{field.name}' должно быть целым числом."
        return None

    def _validate_choice(self, field, value):
        """Метод для валидации поля с типом CHOICE."""
        valid_choices = [c.value for c in field.choices.all()]
        if value not in valid_choices:
            return f"Значение '{value}' недопустимо. Варианты: {valid_choices}"
        return None

    def _validate_checkbox(self, field, value):
        """Метод для валидации поля с типом CHECKBOX."""
        return self._validate_boolean(field, value)

    def _validate_radio(self, field, value):
        """Метод для валидации поля с типом RADIO."""
        return self._validate_boolean(field, value)

    def _validate_date(self, field, value):
        """Метод для валидации поля с типом DATE."""
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return f"Поле '{field.name}' должно быть корректной датой в формате ГГГГ-ММ-ДД."

    def _validate_boolean(self, field, value):
        """Вспомогательный метод для валидации булевых значений."""
        if value.lower() not in ['true', 'false', '1', '0']:
            return f"Поле '{field.name}' должно быть логическим (true/false)."
        return None

    @staticmethod
    def _check_missing_required_fields(template_fields, answers_data,
                                       is_draft):
        """Проверить наличие всех обязательных полей в чистовике."""
        if is_draft:
            return

        required_fields = {str(f.id) for f in template_fields.values() if
                           f.is_required}
        missing = required_fields - set(answers_data.keys())
        if missing:
            raise ValidationError(
                f'Пропущены обязательные поля (ID): {", ".join(missing)}'
            )


class AnswerMetadataSerializer(serializers.Serializer):
    """Сериализатор для возможного представления данных, хранящихся в метадате."""

    bool_true_label = serializers.CharField(allow_null=True)
    bool_false_label = serializers.CharField(allow_null=True)
    comment_label = serializers.CharField(allow_null=True)


class ChecklistAnswerSerializer(serializers.ModelSerializer):
    """Представить ответ пользователя с метаданными поля."""

    field_name = serializers.CharField(source='field.name')
    field_type = serializers.CharField(source='field.field_type')

    field_type_display = serializers.CharField(
        source='field.get_field_type_display', read_only=True
    )

    metadata = AnswerMetadataSerializer(source='field.metadata', read_only=True)

    class Meta:
        model = ChecklistAnswer
        fields = [
            'field_id',
            'field_name',
            'field_type',
            'field_type_display',
            'metadata',
            'value',
            'comment',
            'is_violation'
        ]


class ChecklistAttachmentSerializer(serializers.ModelSerializer):
    """Представить информацию о прикрепленном файле."""

    class Meta:
        model = ChecklistAttachment
        fields = ['id', 'file', 'uploaded_at']


class ChecklistAttachmentUploadSerializer(serializers.ModelSerializer):
    """Валидировать входящий файл при его загрузке."""

    class Meta:
        model = ChecklistAttachment
        fields = ['file']


class OutputGroupItemSerializer(serializers.Serializer):
    """
    Вспомогательный сериализатор исключительно для Swagger.

    Отвечает за отрисовку правильной схемы ответа для групп.
    """

    group_id = serializers.IntegerField()
    group_name = serializers.CharField()
    answers = ChecklistAnswerSerializer(many=True)


class ChecklistSignSerializer(serializers.Serializer):
    """Валидировать запрос на постановку подписи в анкету."""

    role = serializers.ChoiceField(
        choices=SignatureRoles,
        help_text='Роль подписанта (например, APPROVER).',
    )
    user_uid = serializers.CharField(
        max_length=255, help_text='UID пользователя, ставящего подпись.'
    )

    def validate(self, attrs):
        """
        Проверить возможность подписания анкеты в текущем статусе.

        Запрещает подпись черновиков, устаревших или закрытых анкет.
        """
        result = self.context.get('result')
        role = attrs.get('role')

        if result:
            if result.is_draft:
                raise ValidationError(
                    "Нельзя подписать черновик. Сначала сохраните анкету как чистовик."
                )
            if result.is_deprecated:
                raise ValidationError("Нельзя подписать устаревшую анкету.")
            if result.is_completed and role != SignatureRoles.READER:
                raise ValidationError(
                    "Анкета закрыта. Разрешены только подписи Читателя."
                )

        return attrs


class ChecklistResultListSerializer(serializers.ModelSerializer):
    """Представить историю и детальную информацию заполненных анкет."""

    checklist_type = serializers.CharField(
        source='template.checklist_type', read_only=True
    )
    checklist_type_display = serializers.CharField(
        source='template.get_checklist_type_display', read_only=True
    )
    equipment_uid = serializers.CharField(
        source='template.equipment_uid', read_only=True
    )

    signatures = ChecklistSignSerializer(many=True, read_only=True)

    groups = serializers.SerializerMethodField()
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
            'has_violations',
            'general_comment',
            'created_at',
            'updated_at',
            'signatures',
            'groups',
            'attachments',
        ]

    @extend_schema_field(OutputGroupItemSerializer(many=True))
    def get_groups(self, obj):
        """Группирует плоский список ответов по их группам из шаблона."""
        groups_map = {}
        for ans in obj.answers.all():
            group = ans.field.group
            if group.id not in groups_map:
                groups_map[group.id] = {
                    "group_id": group.id,
                    "group_name": group.name,
                    "order": group.order,
                    "answers": []
                }
            groups_map[group.id]["answers"].append(
                ChecklistAnswerSerializer(ans).data)

        sorted_groups = sorted(groups_map.values(), key=lambda x: x['order'])

        for g in sorted_groups:
            g.pop('order', None)

        return sorted_groups


class ChecklistSignatureSerializer(serializers.ModelSerializer):
    """Представить электронную подпись анкеты."""

    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = ChecklistSignature
        fields = ['role', 'role_display', 'user_uid', 'signed_at']
