from django.db import migrations, models


def blank_provider_ids_to_null(apps, schema_editor):
    payment_link = apps.get_model("payment_links", "PaymentLink")
    payment_link.objects.filter(provider_link_id="").update(provider_link_id=None)


class Migration(migrations.Migration):
    dependencies = [("payment_links", "0001_initial")]

    operations = [
        migrations.RunPython(blank_provider_ids_to_null, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="paymentlink",
            name="provider_link_id",
            field=models.CharField(blank=True, default=None, max_length=100, null=True, unique=True),
        ),
    ]
