"""Сервис для экспорта данных чек-листов во внешние форматы (Excel)."""

import datetime
from io import BytesIO

import openpyxl
from openpyxl.styles import Font, PatternFill

from apps.checklists.models import ChecklistResult


class ChecklistExcelExporter:
    """
    Сервис для генерации печатных форм анкет в формате Microsoft Excel (.xlsx).

    Следует принципу единой ответственности (SRP): инкапсулирует логику работы
    с библиотекой openpyxl, стилизацию ячеек и компоновку данных.
    """

    @classmethod
    def export(cls, result: ChecklistResult) -> bytes:
        """Главный фасадный метод. Инициализирует класс и запускает процесс сборки."""
        exporter = cls(result)
        return exporter.generate()

    def __init__(self, result: ChecklistResult):
        self.result = result
        self.wb = openpyxl.Workbook()
        self.ws = self.wb.active
        self.ws.title = f"Анкета {self.result.id}"

        self.header_font = Font(bold=True, color="FFFFFF")
        self.header_fill = PatternFill("solid", fgColor="4F46E5")
        self.bold_font = Font(bold=True)
        self.warning_font = Font(bold=True, color="FF0000")
        self.success_font = Font(bold=True, color="008000")
        self.signature_font = Font(bold=True, color="4F46E5")

    def generate(self) -> bytes:
        """Оркестратор: поочередно вызывает все этапы сборки файла."""
        self._write_metadata()
        self._write_answers_table()
        self._write_signatures()
        self._adjust_column_widths()
        return self._get_file_bytes()

    def _write_metadata(self):
        """Пишет шапку документа с общей информацией об анкете."""
        res = self.result
        shift_info = f"{res.get_shift_number_display() or '-'} / {res.shift_time or '-'}"
        status_text = "ЗАВЕРШЕНА" if res.is_completed else (
            "ЧЕРНОВИК" if res.is_draft else "В ПРОЦЕССЕ")
        violation_text = "ЕСТЬ ОТКЛОНЕНИЯ" if res.has_violations else "Всё в норме"
        version_status = "УСТАРЕЛА (Есть более новая версия)" if res.is_deprecated else "Актуальная"
        export_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        metadata_rows = [
            ["Анкета №", res.id],
            ["Оборудование", res.template.equipment_uid],
            ["Тип чек-листа", res.template.get_checklist_type_display()],
            ["Пользователь", res.user_uid],
            ["Смена", shift_info],
            ["Общий комментарий",
             res.general_comment if res.general_comment else "-"],
            ["Состояние анкеты", status_text],
            ["Отклонения по ответам", violation_text],
            ["Статус версии", version_status],
            ["Дата заполнения", res.created_at.strftime("%d.%m.%Y %H:%M")],
            ["Сформировано", export_time],
            []
        ]

        for row_data in metadata_rows:
            self.ws.append(row_data)

        for row in range(1, len(metadata_rows)):
            self.ws.cell(row=row, column=1).font = self.bold_font

        self.ws.cell(row=8,
                     column=2).font = self.warning_font if res.has_violations else self.success_font
        if res.is_deprecated:
            self.ws.cell(row=9, column=2).font = self.warning_font

    def _write_answers_table(self):
        """Отрисовывает таблицу со всеми ответами и комментариями."""
        headers = ["Группа", "Вопрос", "Ответ", "Комментарий", "Отклонение?"]
        self.ws.append(headers)

        header_row_idx = self.ws.max_row
        for col_num in range(1, 6):
            cell = self.ws.cell(row=header_row_idx, column=col_num)
            cell.font = self.header_font
            cell.fill = self.header_fill

        answers = self.result.answers.select_related('field__group').order_by(
            'field__group__order', 'field__order'
        )

        for ans in answers:
            group_name = ans.field.group.name if ans.field.group else "Без группы"

            if ans.field.field_type == 'CHECKBOX':
                val_display = "Да" if str(
                    ans.value).lower() == 'true' else "Нет"
            else:
                val_display = ans.value if str(
                    ans.value).strip() != "" else "-"

            comment_display = ans.comment if str(
                ans.comment).strip() != "" else "-"
            violation_display = "⚠️ ДА" if ans.is_violation else "Нет"

            self.ws.append(
                [group_name, ans.field.name, val_display, comment_display,
                 violation_display])

            if ans.is_violation:
                self.ws.cell(row=self.ws.max_row,
                             column=3).font = self.warning_font
                self.ws.cell(row=self.ws.max_row,
                             column=5).font = self.warning_font

    def _write_signatures(self):
        """Отрисовывает блок с электронными подписями."""
        self.ws.append([])
        self.ws.append(["ПОДПИСИ ОТВЕТСТВЕННЫХ ЛИЦ:"])
        self.ws.cell(row=self.ws.max_row, column=1).font = self.bold_font

        self.ws.append(["Роль", "UID Сотрудника", "Дата и время подписи"])

        for col_num in range(1, 4):
            self.ws.cell(row=self.ws.max_row,
                         column=col_num).font = self.signature_font

        for sig in self.result.signatures.all():
            self.ws.append([
                sig.get_role_display(),
                sig.user_uid,
                sig.signed_at.strftime("%d.%m.%Y %H:%M")
            ])

    def _adjust_column_widths(self):
        """Задает жесткую ширину для всех колонок документа."""
        self.ws.column_dimensions['A'].width = 25
        self.ws.column_dimensions['B'].width = 40
        self.ws.column_dimensions['C'].width = 25
        self.ws.column_dimensions['D'].width = 35
        self.ws.column_dimensions['E'].width = 15

    def _get_file_bytes(self) -> bytes:
        """Сохраняет книгу Excel в оперативную память и возвращает байты."""
        stream = BytesIO()
        self.wb.save(stream)
        stream.seek(0)
        return stream.getvalue()
