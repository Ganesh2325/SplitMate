from django.db.models.signals import post_migrate
from django.dispatch import receiver

from apps.categories.defaults import DEFAULT_CATEGORIES


@receiver(post_migrate)
def seed_categories(sender, **kwargs):
    if sender.name != "apps.categories":
        return
    from apps.categories.models import ExpenseCategory

    for slug, name, icon in DEFAULT_CATEGORIES:
        ExpenseCategory.objects.get_or_create(
            slug=slug,
            is_system=True,
            defaults={"name": name, "icon": icon},
        )
