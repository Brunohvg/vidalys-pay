from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("boletos", "0003_boleto_refunded_at"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="boleto",
            index=models.Index(
                fields=["-created_at"],
                name="boleto_created_desc_idx",
            ),
        ),
    ]
