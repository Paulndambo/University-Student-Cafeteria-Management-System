# Generated by Django 4.1.7 on 2023-11-24 06:10

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0004_alter_salesreport_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesreport",
            name="item",
            field=models.CharField(max_length=255, null=True),
        ),
    ]