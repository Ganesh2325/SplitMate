import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.constants import ADJUSTMENT_METHODS, CURRENCY_CHOICES, SPLIT_METHODS


class Expense(models.Model):
    class Method(models.TextChoices):
        EQUAL = "equal", "Equal"
        EXACT = "exact", "Exact amounts"
        PERCENT = "percent", "Percentage"
        SHARES = "shares", "Shares"
        ITEMIZED = "itemized", "Itemized"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        VOID = "void", "Voided"

    group = models.ForeignKey(
        "groups.Group", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expenses_created"
    )
    category = models.ForeignKey(
        "categories.ExpenseCategory", on_delete=models.PROTECT, related_name="expenses"
    )
    description = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="INR")
    expense_date = models.DateField()
    split_method = models.CharField(max_length=16, choices=SPLIT_METHODS, default=Method.EQUAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tip_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    adjustment_method = models.CharField(
        max_length=16, choices=ADJUSTMENT_METHODS, default="proportional"
    )
    client_token = models.UUIDField(default=uuid.uuid4)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses_voided",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_amount_positive"),
            models.UniqueConstraint(
                fields=["created_by", "client_token"], name="unique_expense_client_token"
            ),
        ]
        indexes = [
            models.Index(fields=["group", "expense_date"]),
            models.Index(fields=["created_by", "expense_date"]),
            models.Index(fields=["status", "currency"]),
            models.Index(fields=["expense_date"]),
        ]

    def __str__(self):
        return self.description


class ExpensePayer(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="payers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments_made"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "user"], name="unique_expense_payer"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payer_amount_positive"),
        ]


class ExpenseShare(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shares_owed"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    percentage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    weight = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "user"], name="unique_expense_share"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="share_amount_non_negative"),
        ]


class ExpenseItem(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    position = models.PositiveIntegerField(default=0)


class ExpenseItemShare(models.Model):
    item = models.ForeignKey(ExpenseItem, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="item_shares"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "user"], name="unique_item_share"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="item_share_non_negative"),
        ]


class ExpenseRevision(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="revisions")
    number = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expense_revisions"
    )
    reason = models.CharField(max_length=255, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "number"], name="unique_expense_revision"),
        ]
        ordering = ["number"]


class ExpenseComment(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expense_comments"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="comments_hidden",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["expense", "created_at"])]


class ExpenseAttachment(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="receipts/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=80)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploads"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        stored = self.file
        super().delete(*args, **kwargs)
        if stored:
            stored.delete(save=False)


class ExpenseTag(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags"
    )
    name = models.CharField(max_length=30)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_user_tag"),
        ]

    def __str__(self):
        return self.name


class ExpenseTagAssignment(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="tag_assignments")
    tag = models.ForeignKey(ExpenseTag, on_delete=models.PROTECT, related_name="assignments")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "tag"], name="unique_expense_tag"),
        ]


class SavedSplitPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="split_preferences"
    )
    name = models.CharField(max_length=80)
    group = models.ForeignKey(
        "groups.Group", null=True, blank=True, on_delete=models.CASCADE, related_name="split_preferences"
    )
    split_method = models.CharField(max_length=16, choices=SPLIT_METHODS)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="INR")
    category = models.ForeignKey(
        "categories.ExpenseCategory", null=True, blank=True, on_delete=models.SET_NULL
    )
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ExpenseTemplate(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="expense_templates"
    )
    name = models.CharField(max_length=80)
    group = models.ForeignKey(
        "groups.Group", null=True, blank=True, on_delete=models.CASCADE, related_name="expense_templates"
    )
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
