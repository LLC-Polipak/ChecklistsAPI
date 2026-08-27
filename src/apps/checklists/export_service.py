"""Сервис для экспорта данных чек-листов во внешние форматы (Excel)."""
import os
from io import BytesIO

import openpyxl
from openpyxl.styles import Font, Border, Side
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from django.conf import settings

from apps.checklists.models import ChecklistResult


class ChecklistExcelExporter:
    """
    Сервис для генерации печатных форм анкет в формате Microsoft Excel (.xlsx).

    Следует принципу единой ответственности (SRP): инкапсулирует логику работы
    с библиотекой openpyxl, стилизацию ячеек и компоновку данных.
    """

    def __init__(self, result: ChecklistResult):
        self.result = result
        self.wb = openpyxl.Workbook()
        self.ws = self.wb.active
        self.ws.title = "Журнал смены"

        self.current_row = 2

        self.font_bold = Font(bold=True, size=11)
        self.font_normal = Font(size=11)
        self.font_violation = Font(bold=True,
                                   color="FF0000")
        self.font_equipment = Font(bold=True, size=12, color="0000FF")
        self.thin_bottom = Border(bottom=Side(style='thin', color="000000"))

    @classmethod
    def export(cls, result: ChecklistResult) -> bytes:
        """
        Главная точка входа. Создает экземпляр экспортера и запускает сборку файла.

        :param result: Объект заполненной анкеты (ChecklistResult)
        :return: Байты готового Excel-файла (xlsx)
        """
        exporter = cls(result)
        return exporter._generate_document()

    def _generate_document(self) -> bytes:
        """
        Оркестратор сборки. Вызывает методы генерации блоков строго по очереди.
        """
        self._apply_sheet_settings()
        self._build_header()
        self._build_body()
        self._build_footer()
        self._set_column_widths()

        stream = BytesIO()
        self.wb.save(stream)
        stream.seek(0)
        return stream.getvalue()

    def _apply_sheet_settings(self) -> None:
        """
        Применяет визуальные настройки к листу (например, убирает серую сетку).
        """
        self.ws.sheet_view.showGridLines = False

    def _build_header(self) -> None:
        """
        Генерирует шапку документа с метаданными (Дата, Смена, Время).
        """
        date_str = self.result.created_at.strftime("%d.%m.%Y")
        shift_str = self.result.get_shift_number_display() or "___"
        time_str = self.result.shift_time.strftime(
            "%H:%M") if self.result.shift_time else "___"

        self.ws.cell(row=self.current_row, column=1,
                     value=f"Дата  {date_str}").font = self.font_bold
        self.ws.cell(row=self.current_row, column=3,
                     value=f"Смена  {shift_str}").font = self.font_bold
        self.ws.cell(row=self.current_row, column=7,
                     value=f"Время смены  {time_str}").font = self.font_bold

        self.current_row += 2

    def _build_body(self) -> None:
        """
        Генерирует основное тело анкеты: выводит название оборудования,
        группирует вопросы и записывает ответы пользователя с комментариями.
        """
        self.ws.cell(row=self.current_row, column=1,
                     value="Техническое состояние оборудования").font = self.font_bold
        self.ws.cell(row=self.current_row, column=5,
                     value=self.result.template.equipment_uid).font = self.font_equipment
        self.current_row += 1

        answers = self.result.answers.select_related('field__group').order_by(
            'field__group__order', 'field__order'
        )

        current_group = None

        for ans in answers:
            group_name = ans.field.group.name if ans.field.group else "Дополнительно"

            if current_group != group_name:
                current_group = group_name
                if self.current_row > 5:
                    self.current_row += 1
                    self.ws.cell(row=self.current_row, column=1,
                                 value=group_name).font = self.font_bold
                    self.current_row += 1

            self._write_answer_row(ans)

    def _write_answer_row(self, answer) -> None:
        """
        Вспомогательный метод для записи одной строки с ответом и комментарием.

        :param answer: Объект ChecklistAnswer
        """
        val_display = answer.value
        if answer.field.field_type == 'CHECKBOX':
            val_display = "Да" if str(
                answer.value).lower() == 'true' else "Нет"
        if not str(val_display).strip():
            val_display = "—"

        self.ws.cell(row=self.current_row, column=1,
                     value=answer.field.name).font = self.font_normal

        cell_val = self.ws.cell(row=self.current_row, column=4,
                                value=val_display)
        cell_val.font = self.font_violation if answer.is_violation else self.font_bold

        self.ws.cell(row=self.current_row, column=6,
                     value="Замечания").font = self.font_normal

        comment_val = answer.comment if str(answer.comment).strip() else ""
        cell_comment = self.ws.cell(row=self.current_row, column=7,
                                    value=comment_val)
        cell_comment.font = self.font_normal
        cell_comment.border = self.thin_bottom

        self.current_row += 1

    def _build_footer(self) -> None:
        """
        Генерирует подвал документа: общий комментарий к смене и подписи ответственных лиц.
        """
        self.current_row += 2

        sigs = {sig.role: sig for sig in self.result.signatures.all()}

        operator_out = sigs.get('AUTHOR')
        operator_in = sigs.get('READER')
        master = sigs.get('APPROVER')

        self.ws.cell(row=self.current_row, column=1,
                     value="Смену сдал").font = self.font_bold
        self.ws.cell(row=self.current_row, column=3,
                     value=operator_out.user_uid if operator_out else "").border = self.thin_bottom
        self.ws.cell(row=self.current_row, column=6,
                     value="Замечания").font = self.font_normal
        self.ws.cell(row=self.current_row, column=7,
                     value=self.result.general_comment or "").border = self.thin_bottom
        self.current_row += 1

        self.ws.cell(row=self.current_row, column=1,
                     value="Смену принял").font = self.font_bold
        self.ws.cell(row=self.current_row, column=3,
                     value=operator_in.user_uid if operator_in else "").border = self.thin_bottom
        self.current_row += 1

        self.ws.cell(row=self.current_row, column=1,
                     value="Мастер смены").font = self.font_bold
        self.ws.cell(row=self.current_row, column=3,
                     value=master.user_uid if master else "").border = self.thin_bottom

    def _set_column_widths(self) -> None:
        """
        Настраивает ширину колонок для идеального отображения на листе A4.
        """
        self.ws.column_dimensions['A'].width = 50  # Названия узлов
        self.ws.column_dimensions['B'].width = 2  # Отступ
        self.ws.column_dimensions['C'].width = 25  # Подписи
        self.ws.column_dimensions['D'].width = 18  # Значение ответа
        self.ws.column_dimensions['E'].width = 2  # Отступ
        self.ws.column_dimensions['F'].width = 12  # Слово "Замечания"
        self.ws.column_dimensions['G'].width = 45  # Текст замечаний


class ChecklistPDFExporter:
    """
    Сервис для экспорта анкеты в PDF-формат.
    Генерирует документ по структуре, аналогичной Excel (печатный бланк).
    """

    def __init__(self, result: ChecklistResult):
        self.result = result
        self.elements = []

        font_path = os.path.join(settings.BASE_DIR + '/fonts/', 'arial.ttf')
        try:
            pdfmetrics.registerFont(TTFont('Arial', font_path))
            self.font_name = 'Arial'
        except Exception:
            print(
                f"[WARNING] Файл шрифта {font_path} не найден! Русский текст может не отображаться.")
            self.font_name = 'Helvetica'

    @classmethod
    def export(cls, result: ChecklistResult) -> bytes:
        """Главная точка входа. Оркестратор сборки PDF."""
        exporter = cls(result)
        return exporter._generate_document()

    def _generate_document(self) -> bytes:
        self._build_header()
        self._build_body()
        self._build_footer()

        stream = BytesIO()
        doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=30,
                                leftMargin=30, topMargin=40, bottomMargin=30)
        doc.build(self.elements)

        return stream.getvalue()

    def _build_header(self) -> None:
        """Генерирует шапку (Дата, Смена, Время)."""
        date_str = self.result.created_at.strftime("%d.%m.%Y")
        shift_str = self.result.get_shift_number_display() or "___"
        time_str = self.result.shift_time.strftime(
            "%H:%M") if self.result.shift_time else "___"

        data = [
            [f"Дата:  {date_str}", "", f"Смена:  {shift_str}", "",
             f"Время смены:  {time_str}"]
        ]

        t = Table(data, colWidths=[120, 30, 120, 30, 150])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('FONTBOLD', (0, 0), (-1, -1), 1),
        ]))

        self.elements.append(t)
        self.elements.append(Spacer(1, 25))

    def _build_body(self) -> None:
        """Генерирует основное тело (Оборудование и Вопросы)."""
        data = []
        styles = [
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        data.append(["Техническое состояние оборудования", "", "", "",
                     self.result.template.equipment_uid, "", ""])
        styles.append(('TEXTCOLOR', (4, 0), (4, 0), colors.blue))
        styles.append(('FONTSIZE', (0, 0), (-1, 0), 11))

        row_idx = 1
        answers = self.result.answers.select_related('field__group').order_by(
            'field__group__order', 'field__order'
        )
        current_group = None

        for ans in answers:
            group_name = ans.field.group.name if ans.field.group else "Дополнительно"

            if current_group != group_name:
                current_group = group_name
                data.append([group_name, "", "", "", "", "", ""])
                row_idx += 1

            val_display = ans.value
            if ans.field.field_type == 'CHECKBOX':
                val_display = "Да" if str(
                    ans.value).lower() == 'true' else "Нет"
            if not str(val_display).strip():
                val_display = "—"

            comment_val = ans.comment if str(ans.comment).strip() else ""

            data.append([
                ans.field.name, "", "", val_display, "", "Замечания",
                comment_val
            ])

            if ans.is_violation:
                styles.append(
                    ('TEXTCOLOR', (3, row_idx), (3, row_idx), colors.red))

            styles.append(
                ('LINEBELOW', (6, row_idx), (6, row_idx), 0.5, colors.black))
            row_idx += 1

        t = Table(data, colWidths=[200, 10, 10, 80, 10, 70, 150])
        t.setStyle(TableStyle(styles))
        self.elements.append(t)
        self.elements.append(Spacer(1, 30))

    def _build_footer(self) -> None:
        """Генерирует блок с подписями."""
        data = []
        styles = [
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
        ]

        sigs = {sig.role: sig for sig in self.result.signatures.all()}
        operator_out = sigs.get('AUTHOR')
        operator_in = sigs.get('READER')
        master = sigs.get('APPROVER')

        data.append(
            ["Смену сдал", operator_out.user_uid if operator_out else "", "",
             "Замечания", self.result.general_comment or ""])
        styles.append(('LINEBELOW', (1, 0), (1, 0), 0.5,
                       colors.black))
        styles.append(('LINEBELOW', (4, 0), (4, 0), 0.5,
                       colors.black))

        data.append(
            ["Смену принял", operator_in.user_uid if operator_in else "", "",
             "", ""])
        styles.append(('LINEBELOW', (1, 1), (1, 1), 0.5, colors.black))

        data.append(
            ["Мастер смены", master.user_uid if master else "", "", "", ""])
        styles.append(('LINEBELOW', (1, 2), (1, 2), 0.5, colors.black))

        t = Table(data, colWidths=[100, 150, 20, 80, 150])
        t.setStyle(TableStyle(styles))
        self.elements.append(t)
