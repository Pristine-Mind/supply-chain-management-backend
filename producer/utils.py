from datetime import date, datetime
from django.utils.timezone import localtime, is_naive, make_aware
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter


def export_queryset_to_excel(queryset, field_names, headers=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data Export"

    if headers:
        ws.append(headers)
    else:
        ws.append([field.replace("_", " ").title() for field in field_names])

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for obj in queryset:
        row = []
        for field in field_names:
            value = getattr(obj, field)
            if callable(value):
                value = value()
            elif hasattr(value, "all"):
                value = ", ".join([str(item) for item in value.all()])
            elif isinstance(value, datetime):
                # Handle timezone for datetime objects
                if is_naive(value):
                    value = make_aware(value)
                value = localtime(value).strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, date):
                # Handle date objects (without time)
                value = value.strftime("%Y-%m-%d")
            row.append(value)
        ws.append(row)

    for col_num, column_cells in enumerate(ws.columns, 1):
        length = max(len(str(cell.value) or "") for cell in column_cells)
        ws.column_dimensions[get_column_letter(col_num)].width = length + 5

    return wb
