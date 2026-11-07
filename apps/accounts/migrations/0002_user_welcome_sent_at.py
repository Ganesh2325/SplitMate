from django.db import migrations, models
from django.utils import timezone


def mark_existing_users_welcomed(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(welcome_sent_at__isnull=True).update(welcome_sent_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="welcome_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_users_welcomed, migrations.RunPython.noop),
    ]
