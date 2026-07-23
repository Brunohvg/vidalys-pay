from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("boletos", "0002_alter_company_cnpj"),
    ]

    operations = [
        migrations.AddField(
            model_name="boleto",
            name="refunded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
