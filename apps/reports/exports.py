import csv
from io import BytesIO, StringIO

from django.http import HttpResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from apps.reports.models import DataExportJob


def csv_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def export_rows(user, rows, export_format, filters):
    headers = ["Date", "Description", "Group", "Category", "Currency", "Amount", "Status"]
    DataExportJob.objects.create(
        user=user,
        export_format=export_format,
        status=DataExportJob.Status.COMPLETED,
        filters=filters,
        row_count=len(rows),
    )
    if export_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Expenses"
        sheet.append(headers)
        for row in rows:
            sheet.append([csv_safe(cell) if isinstance(cell, str) else cell for cell in row])
        buffer = BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="splitmate-expenses.xlsx"'
        return response
    if export_format == "pdf":
        from reportlab.lib.styles import getSampleStyleSheet

        buffer = BytesIO()
        styles = getSampleStyleSheet()
        data = [headers] + [[csv_safe(cell) for cell in row] for row in rows]
        document = SimpleDocTemplate(buffer, pagesize=A4)
        document.build([Paragraph("SplitMate expenses", styles["Title"]), Spacer(1, 12), Table(data)])
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="splitmate-expenses.pdf"'
        return response
    handle = StringIO()
    writer = csv.writer(handle)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([csv_safe(cell) for cell in row])
    response = HttpResponse(handle.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="splitmate-expenses.csv"'
    response.content = b"\xef\xbb\xbf" + handle.getvalue().encode("utf-8")
    return response
