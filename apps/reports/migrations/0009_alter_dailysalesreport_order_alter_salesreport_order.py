# Generated by Django 4.1.7 on 2023-11-24 20:35

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0012_alter_order_payment_method"),
        ("reports", "0008_generalisedreportdata"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dailysalesreport",
            name="order",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="orders.order"
            ),
        ),
        migrations.AlterField(
            model_name="salesreport",
            name="order",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="orders.order"
            ),
        ),
    ]