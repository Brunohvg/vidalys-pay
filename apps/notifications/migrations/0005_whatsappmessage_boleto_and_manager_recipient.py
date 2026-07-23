import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("boletos", "0003_boleto_refunded_at"),
        ("notifications", "0004_alter_notificationoutbox_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappmessage",
            name="boleto",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_messages",
                to="boletos.boleto",
            ),
        ),
        migrations.AlterField(
            model_name="whatsappmessage",
            name="recipient_type",
            field=models.CharField(
                choices=[
                    ("seller", "Vendedor"),
                    ("customer", "Cliente"),
                    ("manager", "Gestor"),
                ],
                default="seller",
                max_length=20,
            ),
        ),
    ]
