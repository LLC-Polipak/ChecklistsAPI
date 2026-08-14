from io import BytesIO

import openpyxl
from openpyxl.styles import Font, PatternFill

from apps.checklists.models import ChecklistResult


class ChecklistExcelExporter:
    """Сервис для экспорта заполненной анкеты в Excel."""

    @staticmethod
    def export(result: ChecklistResult) -> bytes:
        """Создает Excel-файл из заполненной анкеты чек-листа."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f'Анкета {result.id}'

        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill('solid', fgColor='4F46E5')  # Цвет Индиго
        bold_font = Font(bold=True)

        ws.append(['Анкета №', result.id])
        ws.append(['Оборудование', result.template.equipment_uid])
        ws.append(['Тип чек-листа', result.template.get_checklist_type_display()])
        ws.append(['Пользователь', result.user_uid])

        shift_info = (
            f'{result.get_shift_number_display() or "-"} / {result.shift_time or "-"}'
        )
        ws.append(['Смена', shift_info])
        ws.append(['Статус', 'ЗАВЕРШЕНА' if result.is_completed else 'В ПРОЦЕССЕ'])
        ws.append(['Дата создания', result.created_at.strftime('%d.%m.%Y %H:%M')])
        ws.append([])

        for row in range(1, 8):
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
                val_display = ans.value

            ws.append([group_name, ans.field.name, val_display, ans.comment])

        ws.append([])
        ws.append(['ПОДПИСИ ОТВЕТСТВЕННЫХ ЛИЦ:'])
        ws.cell(row=ws.max_row, column=1).font = bold_font

        ws.append(['Роль', 'UID Сотрудника', 'Дата и время подписи'])
        for col_num in range(1, 4):
            ws.cell(row=ws.max_row, column=col_num).font = Font(
                bold=True, color='4F46E5'
            )

        for sig in result.signatures.all():
            ws.append([
                sig.get_role_display(),
                sig.user_uid,
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
