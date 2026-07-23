from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("boletos", "0004_boleto_created_desc_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="boleto",
            name="status",
            field=models.CharField(
                choices=[
                    ("CREATING", "Processando"),
                    ("CREATION_UNKNOWN", "Confirmação pendente"),
                    ("CREATION_ERROR", "Erro na emissão"),
                    ("PENDING", "Aguardando pagamento"),
                    ("CANCELING", "Cancelamento pendente"),
                    ("PAID", "Pago"),
                    ("FAILED", "Falhou"),
                    ("EXPIRED", "Vencido"),
                    ("CANCELED", "Cancelado"),
                    ("PARTIALLY_CANCELED", "Parcialmente cancelado"),
                    ("REFUNDED", "Estornado"),
                ],
                db_index=True,
                default="CREATING",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="boleto",
            name="reissued_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="reissues",
                to="boletos.boleto",
            ),
        ),
        migrations.AddField(
            model_name="boleto",
            name="cancellation_idempotency_key",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="boleto",
            name="cancellation_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="boleto",
            name="cancellation_response",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
