from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.categories.models import ExpenseCategory
from apps.common.factories import make_user
from apps.expenses.models import Expense
from apps.friends.services import accept_friend_request, send_friend_request
from apps.groups.models import GroupMembership
from apps.groups.services import create_group


class AccessAndExpenseTests(TestCase):
    def test_outsider_cannot_open_a_group(self):
        owner = make_user("ganesh")
        stranger = make_user("arjun")
        group = create_group(actor=owner, name="Weekend Trip", group_type="trip", currency="INR")
        self.client.force_login(stranger)
        response = self.client.get(f"/groups/{group.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_friend_expense_receipt_and_viewer_block(self):
        ganesh = make_user("ganesh")
        rahul = make_user("rahul")
        request = send_friend_request(ganesh, rahul)
        accept_friend_request(rahul, request)
        category = ExpenseCategory.objects.get(slug="food-and-dining")
        self.client.force_login(ganesh)
        saved = self.client.post(
            "/expenses/add/",
            {
                "description": "Dinner",
                "amount": "300.00",
                "expense_date": date.today().isoformat(),
                "currency": "INR",
                "split_method": "equal",
                "participant": [str(ganesh.id), str(rahul.id)],
                "payer": [str(ganesh.id)],
                "payer_amount_%s" % ganesh.id: "300.00",
                "category": str(category.id),
                "notes": "",
                "tags": "",
            },
        )
        expense = Expense.objects.get()
        self.assertRedirects(saved, f"/expenses/{expense.pk}/")
        self.client.force_login(rahul)
        self.assertEqual(self.client.get(f"/expenses/{expense.pk}/").status_code, 200)
        stranger = make_user("arjun")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(f"/expenses/{expense.pk}/").status_code, 404)

        group = create_group(actor=ganesh, name="Flat", group_type="home", currency="INR")
        membership = GroupMembership.objects.get(group=group, user=ganesh)
        membership.role = GroupMembership.Role.VIEWER
        membership.save(update_fields=["role"])
        self.client.force_login(ganesh)
        blocked = self.client.post(
            "/expenses/add/",
            {
                "description": "Rent",
                "amount": "1000.00",
                "expense_date": date.today().isoformat(),
                "group": str(group.id),
                "split_method": "equal",
                "participant": [str(ganesh.id)],
                "payer": [str(ganesh.id)],
                "category": str(category.id),
            },
        )
        self.assertContains(blocked, "cannot add expenses")

        self.client.force_login(rahul)
        buffer = BytesIO()
        Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
        upload = SimpleUploadedFile("bill.png", buffer.getvalue(), content_type="image/png")
        uploaded = self.client.post(f"/expenses/{expense.pk}/receipts/", {"receipt": upload})
        self.assertRedirects(uploaded, f"/expenses/{expense.pk}/")
        self.assertEqual(expense.attachments.count(), 1)
        attachment = expense.attachments.get()
        download = self.client.get(f"/expenses/receipts/{attachment.pk}/")
        self.assertEqual(download.status_code, 200)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(f"/expenses/receipts/{attachment.pk}/").status_code, 404)
