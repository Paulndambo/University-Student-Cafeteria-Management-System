# Generated by Django 4.1.7 on 2023-10-18 06:58

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0003_walletrechargelog"),
    ]

    operations = [
        migrations.AlterField(
            model_name="walletrechargelog",
            name="amount_recharged",
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
    ]