from django.conf import settings
from django.db import models
from django.db.models import Q


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    icon = models.CharField(max_length=40, default="bi-tag")
    is_system = models.BooleanField(default=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="custom_categories",
    )
    group = models.ForeignKey(
        "groups.Group",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(is_system=True),
                name="unique_system_category_slug",
            ),
            models.UniqueConstraint(
                fields=["owner", "slug"],
                condition=Q(owner__isnull=False),
                name="unique_user_category_slug",
            ),
            models.UniqueConstraint(
                fields=["group", "slug"],
                condition=Q(group__isnull=False),
                name="unique_group_category_slug",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_system=True, owner__isnull=True, group__isnull=True)
                    | Q(is_system=False, owner__isnull=False, group__isnull=True)
                    | Q(is_system=False, owner__isnull=True, group__isnull=False)
                ),
                name="category_scope_consistent",
            ),
        ]

    def __str__(self):
        return self.name
