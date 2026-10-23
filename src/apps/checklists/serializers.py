import datetime

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.checklists.constants import ChecklistTypes, FieldTypes, ShiftTypes
from apps.checklists.models import (
    ChecklistAnswer,
    ChecklistAttachment,
    ChecklistResult,
    ChecklistSignature,
    FieldChoice,
    Template,
    TemplateField,
    TemplateFieldGroup,
    TemplateFieldQCMetadata,
    TemplateQCMetadata,
)


class FieldChoiceSerializer(serializers.ModelSerializer):
    """Сериализовать варианты ответов.

    Используется исключительно для полей типа 'CHOICE' (выпадающий список).
    """

    class Meta:
        model = FieldChoice
        fields = ['value', 'order', 'is_violation']


class TemplateFieldQCMetadataSerializer(serializers.ModelSerializer):
    """Сериализатор методологии контроля качества для отдельного поля."""

    class Meta:
        model = TemplateFieldQCMetadata
        fields = ['norm_description', 'defect_description', 'control_method']


class TemplateFieldSerializer(serializers.ModelSerializer):
    """Сериализовать поле шаблона анкеты.

    Описывает конкретный вопрос, его тип и возможные варианты ответа.
    """

    choices = FieldChoiceSerializer(many=True, required=False)
    field_type_display = serializers.CharField(
        source='get_field_type_display', read_only=True
    )

    qc_metadata = TemplateFieldQCMetadataSerializer(required=False, allow_null=True)

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
            'qc_metadata',
            'choices',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        """Проверить бизнес-логику поля.

        Гарантировать, что варианты ответов сохраняются только для поля типа CHOICE.
        Для остальных типов массив очищается. Также проверяет корректность
        значения по умолчанию.
        """
        field_type = attrs.get('field_type')
        choices = attrs.get('choices', [])
        default_value = attrs.get('default_value', '').strip()

        if field_type == FieldTypes.CHOICE and not choices:
            raise serializers.ValidationError(
                {
                    'choices': "Для типа 'Выбор из списка' передайте хотя бы один вариант."
                }
            )
        if field_type != FieldTypes.CHOICE:
            attrs['choices'] = []

        if field_type == FieldTypes.AUTO_DATE:
            default_value = ''

        if default_value:
            method_name = f'_validate_default_{field_type.lower()}'
            validator_method = getattr(self, method_name, None)

            if validator_method:
                error_msg = validator_method(default_value, choices=choices)
                if error_msg:
                    raise serializers.ValidationError({'default_value': error_msg})

        attrs['default_value'] = default_value
        return attrs

    def _validate_default_integer(self, default_value, **kwargs):
        """Проверить значение по умолчанию для типа INTEGER."""
        if not default_value.lstrip('-').isdigit():
            return 'Значение по умолчанию должно быть целым числом.'
        return None

    def _validate_default_choice(self, default_value, choices, **kwargs):
        """Проверить значение по умолчанию для типа CHOICE."""
        valid_choices = [c.get('value') for c in choices]
        if default_value not in valid_choices:
            return f"Значение '{default_value}' недопустимо. Варианты: {valid_choices}"
        return None

    def _validate_default_checkbox(self, default_value, **kwargs):
        """Проверить значение по умолчанию для типа CHECKBOX."""
        return self._validate_boolean(default_value)

    def _validate_default_radio(self, default_value, **kwargs):
        """Проверить значение по умолчанию для типа RADIO."""
        return self._validate_boolean(default_value)

    def _validate_default_date(self, default_value, **kwargs):
        """Проверить значение по умолчанию для типа DATE."""
        try:
            datetime.date.fromisoformat(default_value)
        except ValueError:
            return 'Дата по умолчанию должна быть в формате ГГГГ-ММ-ДД.'
        return None

    def _validate_boolean(self, default_value):
        """Выполнить валидацию булевых значений."""
        if default_value.lower() not in ['true', 'false', '1', '0']:
            return "Для чекбокса значение по умолчанию должно быть 'true' или 'false'."
        return None


class AnswerItemSerializer(serializers.Serializer):
    """Представить ответ с комментарием во входящих данных."""

    field_id = serializers.IntegerField(help_text='ID поля шаблона')
    value = serializers.CharField(allow_blank=True)
    comment = serializers.CharField(allow_blank=True, required=False, default='')


class AnswerGroupSerializer(serializers.Serializer):
    """Представить ответ с полями, входящими в эту группу."""

    group_id = serializers.IntegerField(help_text='ID группы полей из шаблона')
    answers = AnswerItemSerializer(many=True, allow_empty=True)


class TemplateFieldGroupSerializer(serializers.ModelSerializer):
    """Представить группу полей шаблона."""

    fields = TemplateFieldSerializer(many=True)

    class Meta:
        model = TemplateFieldGroup
        fields = ['id', 'name', 'order', 'page_break', 'fields']
        read_only_fields = ['id']

    def validate_fields(self, value):
        """Проверить уникальность порядковых номеров полей внутри группы.

        Вызывается автоматически при валидации поля 'fields'.
        """
        orders = [f.get('order') for f in value if f.get('order') is not None]
        if len(orders) != len(set(orders)):
            raise serializers.ValidationError(
                'Порядковые номера полей в пределах одной группы '
                'должны быть уникальными.'
            )
        return value


class TemplateQCMetadataSerializer(serializers.ModelSerializer):
    """Сериализатор метаданных шаблона контроля качества (ПКК).

    Отвечает за валидацию и представление привязки шаблона к конкретному
    материалу, а также за указание необходимого количества образцов для проверки.
    Используется как вложенное поле в сериализаторе шаблона.
    """

    class Meta:
        model = TemplateQCMetadata
        fields = ['material_uid', 'number_of_samples']


class TemplateSerializer(serializers.ModelSerializer):
    """Сериализовать шаблон в нормализованную реляционную структуру БД.

    Поддерживает вложенную запись групп и полей.
    """

    groups = TemplateFieldGroupSerializer(many=True, required=False)
    fields = TemplateFieldSerializer(many=True, required=False, write_only=True)

    checklist_type_display = serializers.CharField(
        source='get_checklist_type_display', read_only=True
    )

    qc_metadata = TemplateQCMetadataSerializer(required=False, allow_null=True)

    has_results = serializers.SerializerMethodField()

    class Meta:
        model = Template
        fields = [
            'id',
            'name',
            'equipment_uid',
            'checklist_type',
            'checklist_type_display',
            'is_draft',
            'is_deprecated',
            'has_results',
            'created_at',
            'updated_at',
            'groups',
            'fields',
            'qc_metadata',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'has_results',
            'is_deprecated',
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_has_results(self, obj):
        """Проверить существование заполненной анкеты на данный шаблон."""
        return obj.results.exists()

    def to_representation(self, instance):
        """Очищаем выдачу: вытаскиваем поля из скрытой группы __DEFAULT__ в корень JSON."""
        data = super().to_representation(instance)
        groups = data.get('groups', [])

        default_group = next((g for g in groups if g['name'] == '__DEFAULT__'), None)

        if default_group:
            data['fields'] = default_group['fields']
            data['groups'] = [g for g in groups if g['name'] != '__DEFAULT__']
        else:
            data['fields'] = []

        return data

    def validate(self, attrs):
        """Выполнить бизнес-валидацию перед сохранением.

        Защищает используемые шаблоны от изменений и предотвращает
        смену идентичности (UID и Типа).
        """
        if self.instance:
            if (
                'equipment_uid' in attrs
                and attrs['equipment_uid'] != self.instance.equipment_uid
            ):
                raise serializers.ValidationError(
                    {
                        'equipment_uid': 'Нельзя изменить UID оборудования у существующего шаблона.'
                    }
                )
            if (
                'checklist_type' in attrs
                and attrs['checklist_type'] != self.instance.checklist_type
            ):
                raise serializers.ValidationError(
                    {
                        'checklist_type': 'Нельзя изменить тип чек-листа у существующего шаблона.'
                    }
                )
            if 'qc_metadata' in attrs and attrs['qc_metadata'] is not None:
                new_material = attrs['qc_metadata'].get('material_uid')
                if (
                    hasattr(self.instance, 'qc_metadata')
                    and new_material != self.instance.qc_metadata.material_uid
                ):
                    raise serializers.ValidationError(
                        {
                            'qc_metadata': 'Нельзя изменить материал у существующего шаблона ПКК.'
                        }
                    )

        checklist_type = attrs.get(
            'checklist_type', self.instance.checklist_type if self.instance else None
        )
        qc_metadata = attrs.get('qc_metadata')

        if checklist_type == ChecklistTypes.QUALITY_CONTROL:
            if not qc_metadata or not qc_metadata.get('material_uid'):
                raise serializers.ValidationError(
                    {
                        'qc_metadata': 'Для шаблона Листа контроля качества (ПКК) обязательно указание material_uid.'
                    }
                )
        else:
            attrs['qc_metadata'] = None
        return attrs

    def validate_groups(self, value):
        """Проверить уникальность порядковых номеров групп в шаблоне.

        Вызывается автоматически при валидации поля 'groups'.
        """
        group_orders = [g.get('order') for g in value if g.get('order') is not None]
        if len(group_orders) != len(set(group_orders)):
            raise serializers.ValidationError(
                'Порядковые номера групп в шаблоне должны быть уникальными.'
            )
        return value


class ChecklistResultCreateSerializer(serializers.Serializer):
    """Принять и провалидировать заполненную анкету.

    Выполняет проверку типов данных (Type Casting) и контроль обязательных полей.
    """

    equipment_uid = serializers.CharField(
        max_length=255, write_only=True, required=False
    )
    checklist_type = serializers.CharField(
        max_length=50, write_only=True, required=False
    )
    material_uid = serializers.CharField(
        max_length=255, write_only=True, required=False, allow_null=True
    )

    user_uid = serializers.CharField(max_length=36)

    shift_number = serializers.ChoiceField(choices=ShiftTypes, required=False)
    shift_time = serializers.DateTimeField(required=False, allow_null=True)

    is_draft = serializers.BooleanField(default=False)
    is_completed = serializers.BooleanField(
        required=False, allow_null=True, default=None
    )

    groups = AnswerGroupSerializer(many=True, allow_empty=True, required=False)
    answers = AnswerItemSerializer(many=True, allow_empty=True, required=False)

    general_comment = serializers.CharField(
        allow_blank=True, required=False, default=''
    )
    external_id = serializers.CharField(max_length=255, required=False, allow_null=True)
    source_service = serializers.CharField(
        max_length=100, required=False, allow_null=True
    )

    def validate(self, attrs):
        """Выполнить главную оркестрацию динамической валидации EAV-структуры.

        Метод выступает фасадным оркестратором. Детализация вынесена в приватные методы
        для снижения цикломатической сложности и соблюдения SRP.
        """
        # 1. Приведение флагов черновика к единому стандарту
        self._normalize_status_flags(attrs)

        # 2. Получение эталонного шаблона
        template = self._get_active_template(attrs)

        # 3. Интеграция рутовых ответов (без группы) в системную группу
        self._inject_root_answers(template, attrs)

        # 4. Проверка метаданных контроля качества
        self._validate_qc_metadata(template, attrs)

        # 5. Картирование полей шаблона
        template_fields = self._map_template_fields(template)

        # 6. Проверка структуры присланных ответов (принадлежность полей и групп)
        groups_data = attrs.get('groups', [])
        answers_data = self._extract_and_validate_answers_structure(
            groups_data, template_fields
        )

        # 7. Детальная проверка значений EAV
        is_draft = attrs.get('is_draft', False)
        self._check_missing_required_fields(template_fields, answers_data, is_draft)

        validated_answers = self._process_and_validate_answers(
            template_fields, answers_data, is_draft
        )

        attrs.pop('groups', None)
        attrs.pop('answers', None)
        attrs.pop('equipment_uid', None)
        attrs.pop('checklist_type', None)
        attrs.pop('material_uid', None)

        attrs['template'] = template
        attrs['validated_answers'] = validated_answers
        return attrs

    def _normalize_status_flags(self, attrs: dict) -> None:
        """Определяет и устанавливает корректные статусы для черновика и чистовика."""
        if attrs.get('is_draft', False):
            attrs['is_completed'] = False
        elif attrs.get('is_completed') is None:
            attrs['is_completed'] = True

    def _inject_root_answers(self, template: Template, attrs: dict) -> None:
        """Интегрирует плоские ответы в системную скрытую группу __DEFAULT__."""
        root_answers = attrs.get('answers', [])
        if not root_answers:
            return

        default_group = template.groups.filter(name='__DEFAULT__').first()
        if not default_group:
            raise ValidationError({'answers': 'В данном шаблоне нет полей без группы.'})

        groups_data = attrs.setdefault('groups', [])
        groups_data.append({'group_id': default_group.id, 'answers': root_answers})

    def _validate_qc_metadata(self, template: Template, attrs: dict) -> None:
        """Проверяет корректность метаданных для листов контроля качества (ПКК)."""
        if template.checklist_type == ChecklistTypes.QUALITY_CONTROL:
            if not attrs.get('material_uid'):
                raise ValidationError(
                    {
                        'material_uid': 'Для листов контроля качества (ПКК) обязательно нужно указать material_uid в корне запроса.'
                    }
                )
        else:
            # Сбрасываем метаданные для обычных чек-листов
            attrs['qc_metadata'] = None

    def _map_template_fields(self, template: Template) -> dict:
        """Создает плоский словарь всех полей шаблона для быстрого доступа по ID."""
        template_fields = {}
        for group in template.groups.all():
            for field in group.fields.all():
                template_fields[str(field.id)] = field
        return template_fields

    def _extract_and_validate_answers_structure(
        self, groups_data: list, template_fields: dict
    ) -> dict:
        """Извлекает ответы и проверяет их структурную принадлежность к шаблону и группам.

        Args:
            groups_data (list): Список групп с ответами из запроса.
            template_fields (dict): Плоский словарь полей эталонного шаблона.

        Returns:
            dict: Словарь извлеченных ответов в формате {field_id: answer_obj}.

        Raises:
            ValidationError: Если найдены поля, не принадлежащие шаблону или группе.
        """
        answers_data = {}
        errors = {}

        for group_item in groups_data:
            g_id = group_item.get('group_id')

            for ans_obj in group_item.get('answers', []):
                f_id = str(ans_obj.get('field_id'))

                if f_id not in template_fields:
                    errors[f_id] = 'Поле не принадлежит этому шаблону.'
                    continue

                field = template_fields[f_id]
                if field.group_id != g_id:
                    errors[f_id] = (
                        f"Поле '{field.name}' принадлежит группе ID {field.group_id}, "
                        f'а передано в группе ID {g_id}.'
                    )
                    continue

                answers_data[f_id] = ans_obj

        if errors:
            raise ValidationError(errors)

        return answers_data

    def _get_active_template(self, attrs):
        """Извлечь активный шаблон из базы данных.

        Raises:
            ValidationError: Если шаблон для указанного оборудования не найден.
        """
        if self.instance:
            template = self.instance.template
        else:
            template = Template.objects.get_active(
                attrs.get('equipment_uid'),
                attrs.get('checklist_type'),
                attrs.get('material_uid'),
            )
            if not template:
                raise ValidationError(
                    'Активный шаблон для данного оборудования и материала не найден.'
                )

        return template

    def _process_and_validate_answers(self, template_fields, answers_data, is_draft):
        """Проверить каждый ответ пользователя через индивидуальный валидатор типов.

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
                    {'field': field, 'value': value, 'comment': comment}
                )
                continue

            if field.is_required and value == '' and not is_draft:
                errors[f_id] = 'Обязательное поле не может быть пустым.'
                continue

            if value == '':
                validated_answers.append(
                    {'field': field, 'value': value, 'comment': comment}
                )
                continue

            error_msg = self._validate_single_field(field, value)
            if error_msg:
                errors[f_id] = error_msg
            else:
                validated_answers.append(
                    {'field': field, 'value': value, 'comment': comment}
                )

        if errors:
            raise ValidationError(errors)

        return validated_answers

    def _validate_single_field(self, field, value):
        """Выполнить проверку значения для конкретного типа поля.

        Убеждается, что строку можно безопасно конвертировать в целевой тип.
        """
        method_name = f'_validate_{field.field_type.lower()}'
        validator_method = getattr(self, method_name, None)

        if validator_method:
            return validator_method(field, value)

        return None

    def _validate_integer(self, field, value):
        """Проверить поле с типом INTEGER."""
        if not value.lstrip('-').isdigit():
            return f"Поле '{field.name}' должно быть целым числом."
        return None

    def _validate_choice(self, field, value):
        """Проверить поле с типом CHOICE."""
        valid_choices = [c.value for c in field.choices.all()]
        if value not in valid_choices:
            return f"Значение '{value}' недопустимо. Варианты: {valid_choices}"
        return None

    def _validate_checkbox(self, field, value):
        """Проверить поле с типом CHECKBOX."""
        return self._validate_boolean(field, value)

    def _validate_radio(self, field, value):
        """Проверить поле с типом RADIO."""
        return self._validate_boolean(field, value)

    def _validate_date(self, field, value):
        """Проверить поле с типом DATE."""
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return f"Поле '{field.name}' должно быть корректной датой в формате ГГГГ-ММ-ДД."
        return None

    def _validate_boolean(self, field, value):
        """Выполнить проверку булевых значений."""
        if value.lower() not in ['true', 'false', '1', '0']:
            return f"Поле '{field.name}' должно быть логическим (true/false)."
        return None

    @staticmethod
    def _check_missing_required_fields(template_fields, answers_data, is_draft):
        """Проверить наличие всех обязательных полей в чистовике."""
        if is_draft:
            return

        required_fields = {str(f.id) for f in template_fields.values() if f.is_required}
        missing = required_fields - set(answers_data.keys())
        if missing:
            raise ValidationError(
                f'Пропущены обязательные поля (ID): {", ".join(missing)}'
            )


class ChecklistAnswerSerializer(serializers.ModelSerializer):
    """Представить ответ пользователя с метаданными поля."""

    field_name = serializers.CharField(source='field.name')
    field_type = serializers.CharField(source='field.field_type')

    field_type_display = serializers.CharField(
        source='field.get_field_type_display', read_only=True
    )

    metadata = serializers.JSONField(source='field.metadata', read_only=True)

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
            'is_violation',
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
        fields = ['result', 'file']


class OutputGroupItemSerializer(serializers.Serializer):
    """Сформировать вспомогательную схему исключительно для Swagger.

    Отвечает за отрисовку правильной структуры ответа для групп.
    """

    group_id = serializers.IntegerField()
    group_name = serializers.CharField()
    page_break = serializers.BooleanField()
    answers = ChecklistAnswerSerializer(many=True)


class ChecklistSignSerializer(serializers.Serializer):
    """Валидировать запрос на постановку подписи в анкету."""

    role = serializers.CharField(max_length=50, help_text='Название роли подписанта.')
    user_uid = serializers.CharField(
        max_length=255, help_text='UID пользователя, ставящего подпись.'
    )

    is_closing = serializers.BooleanField(
        default=False,
        help_text='Если true, анкета будет переведена в статус Завершена (заблокирована для изменений).',
    )

    def validate(self, attrs):
        """Проверить возможность подписания анкеты в текущем статусе.

        Запрещает подпись черновиков, устаревших или закрытых анкет.
        """
        result = self.context.get('result')
        is_closing = attrs.get('is_closing')

        if result:
            if result.is_draft:
                raise ValidationError(
                    'Нельзя подписать черновик. Сначала сохраните анкету как чистовик.'
                )
            if result.is_deprecated:
                raise ValidationError('Нельзя подписать устаревшую анкету.')
            if result.is_completed and is_closing:
                raise ValidationError(
                    'Анкета уже закрыта. Можно только добавлять ознакомительные подписи без флага закрытия.'
                )

        return attrs


class ChecklistSignatureSerializer(serializers.ModelSerializer):
    """Представить электронную подпись анкеты."""

    class Meta:
        model = ChecklistSignature
        fields = ['role', 'user_uid', 'signed_at']


class ChecklistResultListSerializer(serializers.ModelSerializer):
    """Представить историю и детальную информацию заполненных анкет."""

    template_name = serializers.CharField(source='template.name', read_only=True)
    checklist_type = serializers.CharField(
        source='template.checklist_type', read_only=True
    )
    checklist_type_display = serializers.CharField(
        source='template.get_checklist_type_display', read_only=True
    )
    equipment_uid = serializers.CharField(
        source='template.equipment_uid', read_only=True
    )
    material_uid = serializers.CharField(
        source='template.qc_metadata.material_uid', read_only=True
    )

    signatures = ChecklistSignatureSerializer(many=True, read_only=True)

    groups = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    attachments = ChecklistAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ChecklistResult
        fields = [
            'id',
            'template_name',
            'equipment_uid',
            'user_uid',
            'external_id',
            'source_service',
            'checklist_type',
            'checklist_type_display',
            'material_uid',
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
            'answers',
            'groups',
            'attachments',
        ]

    @extend_schema_field(OutputGroupItemSerializer(many=True))
    def get_groups(self, obj):
        """Сгруппировать плоский список ответов по их группам из шаблона."""
        groups_map = {}
        for ans in obj.answers.all():
            group = ans.field.group
            if group.name == '__DEFAULT__':
                continue
            if group.id not in groups_map:
                groups_map[group.id] = {
                    'group_id': group.id,
                    'group_name': group.name,
                    'order': group.order,
                    'page_break': group.page_break,
                    'answers': [],
                }
            groups_map[group.id]['answers'].append(ChecklistAnswerSerializer(ans).data)

        sorted_groups = sorted(groups_map.values(), key=lambda x: x['order'])

        for g in sorted_groups:
            g.pop('order', None)

        return sorted_groups

    @extend_schema_field(ChecklistAnswerSerializer(many=True))
    def get_answers(self, obj):
        """Возвращает ответы, принадлежащие скрытой группе __DEFAULT__."""
        default_answers = [
            ans for ans in obj.answers.all() if ans.field.group.name == '__DEFAULT__'
        ]

        serializer = ChecklistAnswerSerializer(default_answers, many=True)
        return serializer.data


class TemplateCloneSerializer(serializers.Serializer):
    """Сериализатор для валидации запроса на клонирование шаблона."""

    equipment_uid = serializers.CharField(
        max_length=255,
        help_text='UID нового оборудования, для которого создается копия',
    )
