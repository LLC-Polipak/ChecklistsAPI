import datetime
from io import BytesIO

import openpyxl
from openpyxl.styles import Font, PatternFill

from apps.checklists.models import ChecklistResult


class ChecklistExcelExporter:
    """
    Сервис для генерации печатных форм анкет в формате Microsoft Excel (.xlsx).

    Следует принципу единой ответственности (SRP): инкапсулирует логику работы
    с библиотекой openpyxl, стилизацию ячеек и компоновку данных. Не взаимодействует
    с HTTP-запросами (этим занимаются Контроллеры).
    """

    @classmethod
    def export(cls, result: ChecklistResult) -> bytes:
        """
        Формирует Excel-документ на основе заполненной анкеты чек-листа.

        Алгоритм работы:
        1. Формирует "шапку" с метаданными (Оборудование, Смена, Пользователь, Статус).
        2. Отрисовывает таблицу ответов, группируя их согласно иерархии шаблона.
        3. Заменяет пустые значения и комментарии на визуальные прочерки ('-').
        4. Выводит блок истории подписаний (роль, UID, время).

        Args:
            result (ChecklistResult): Объект заполненной анкеты из базы данных.

        Returns:
            bytes: Готовый файл в виде бинарной последовательности (сохраненный в оперативной памяти),
                   готовый к отправке клиенту через HttpResponse.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f'Анкета {result.id}'

        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill('solid', fgColor='4F46E5')
        bold_font = Font(bold=True)
        warning_font = Font(bold=True, color='FF0000')

        ws.append(['Анкета №', result.id])
        ws.append(['Оборудование', result.template.equipment_uid])
        ws.append(
            [
                'Тип чек-листа',
                cls._format_empty(result.template.get_checklist_type_display()),
            ]
        )
        ws.append(['Пользователь', result.user_uid])

        shift_num = cls._format_empty(result.get_shift_number_display())
        shift_t = cls._format_empty(result.shift_time)
        ws.append(['Смена', f'{shift_num} / {shift_t}'])

        ws.append(['Общий комментарий', cls._format_empty(result.general_comment)])

        status_text = (
            'ЗАВЕРШЕНА'
            if result.is_completed
            else ('ЧЕРНОВИК' if result.is_draft else 'В ПРОЦЕССЕ')
        )
        ws.append(['Состояние анкеты', status_text])

        version_status = (
            'УСТАРЕЛА (Есть более новая версия)'
            if result.is_deprecated
            else 'Актуальная'
        )
        ws.append(['Статус версии', version_status])

        ws.append(['Дата заполнения', result.created_at.strftime('%d.%m.%Y %H:%M')])

        export_time = datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        ws.append(['Сформировано', export_time])

        ws.append([])

        for row in range(1, 11):
            ws.cell(row=row, column=1).font = bold_font

        if result.is_deprecated:
            ws.cell(row=8, column=2).font = warning_font

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
                ws.append(
                    [
                        cls._format_empty(sig.get_role_display()),
                        cls._format_empty(sig.user_uid),
                        sig.signed_at.strftime('%d.%m.%Y %H:%M'),
                    ]
                )

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
