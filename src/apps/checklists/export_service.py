from io import BytesIO

import openpyxl
from openpyxl.styles import Font, PatternFill

from apps.checklists.models import ChecklistResult


class ChecklistExcelExporter:
    """Сервис для экспорта заполненной анкеты в Excel."""

    @classmethod
    def export(cls, result: ChecklistResult) -> bytes:
        """Создает Excel-файл из заполненной анкеты чек-листа."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f'Анкета {result.id}'

        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill('solid', fgColor='4F46E5')
        bold_font = Font(bold=True)

        ws.append(['Анкета №', str(result.id)])
        ws.append(['Оборудование', cls._format_empty(result.template.equipment_uid)])
        ws.append([
            'Тип чек-листа',
            cls._format_empty(result.template.get_checklist_type_display()),
        ])
        ws.append(['Пользователь', cls._format_empty(result.user_uid)])

        shift_num = cls._format_empty(result.get_shift_number_display())
        shift_t = cls._format_empty(result.shift_time)
        ws.append(['Смена', f'{shift_num} / {shift_t}'])

        ws.append(['Статус', 'ЗАВЕРШЕНА' if result.is_completed else 'В ПРОЦЕССЕ'])

        if result.is_draft:
            ws.append(['Тип документа', 'ЧЕРНОВИК'])

        ws.append(['Дата создания', result.created_at.strftime('%d.%m.%Y %H:%M')])
        ws.append([])

        for row in range(1, ws.max_row + 1):
            ws.cell(row=row, column=1).font = bold_font

        headers = ['Группа', 'Вопрос', 'Ответ', 'Комментарий']
        ws.append(headers)

        for col_num in range(1, 5):
            cell = ws.cell(row=ws.max_row, column=col_num)
            cell.font = header_font
            cell.fill = header_fill

        answers = result.answers.select_related('field__group').order_by(
            'field__group__order', 'field__order'
        )

        for ans in answers:
            group_name = ans.field.group.name if ans.field.group else 'Без группы'

            if ans.field.field_type == 'CHECKBOX':
                val_display = 'Да' if str(ans.value).lower() == 'true' else 'Нет'
            else:
                val_display = cls._format_empty(ans.value)

            comment_display = cls._format_empty(ans.comment)

            ws.append([group_name, ans.field.name, val_display, comment_display])

        ws.append([])
        ws.append(['ПОДПИСИ ОТВЕТСТВЕННЫХ ЛИЦ:'])
        ws.cell(row=ws.max_row, column=1).font = bold_font

        ws.append(['Роль', 'UID Сотрудника', 'Дата и время подписи'])
        for col_num in range(1, 4):
            ws.cell(row=ws.max_row, column=col_num).font = Font(
                bold=True, color='4F46E5'
            )

        signatures = result.signatures.all()
        if not signatures:
            ws.append(['-', '-', '-'])
        else:
            for sig in signatures:
                ws.append([
                    cls._format_empty(sig.get_role_display()),
                    cls._format_empty(sig.user_uid),
                    sig.signed_at.strftime('%d.%m.%Y %H:%M'),
                ])

        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 35

        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)
        return stream.getvalue()

    @staticmethod
    def _format_empty(value):
        """Вспомогательная функция: заменяет пустые значения и None на прочерк."""
        if value is None or str(value).strip() == '':
            return '-'
        return str(value)
