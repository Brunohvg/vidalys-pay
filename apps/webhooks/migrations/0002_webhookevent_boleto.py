import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("boletos", "0003_boleto_refunded_at"),
        ("webhooks", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhookevent",
            name="boleto",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="webhook_events",
                to="boletos.boleto",
            ),
        ),
    ]
