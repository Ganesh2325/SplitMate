from django.test import TestCase

from apps.common.factories import make_user
from apps.reports.exports import csv_safe


class ExportTests(TestCase):
    def test_formula_cells_are_quoted(self):
        self.assertEqual(csv_safe("=1+1"), "'=1+1")
        self.assertEqual(csv_safe("+cmd"), "'+cmd")
        self.assertEqual(csv_safe("Dinner"), "Dinner")

    def test_export_requires_login_and_stays_authorized(self):
        guest = self.client.get("/reports/export/csv/")
        self.assertEqual(guest.status_code, 302)
        user = make_user("ganesh")
        self.client.force_login(user)
        response = self.client.get("/reports/export/csv/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Description", response.content)
        self.assertEqual(self.client.get("/reports/export/exe/").status_code, 404)
