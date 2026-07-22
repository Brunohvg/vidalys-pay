from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_add_recipient_type_and_event_type")]

    operations = [
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.TextField()),
                ("auth", models.TextField()),
                ("user_agent", models.CharField(blank=True, default="", max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("failure_count", models.PositiveSmallIntegerField(default=0)),
                ("last_delivery_key", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("seller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_subscriptions", to="sellers.seller")),
            ],
            options={"verbose_name": "Assinatura Push", "verbose_name_plural": "Assinaturas Push", "ordering": ["-updated_at"]},
        ),
    ]
