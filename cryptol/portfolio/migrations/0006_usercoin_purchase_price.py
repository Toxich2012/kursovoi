# Generated by Django 3.2.5 on 2023-05-20 17:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0005_auto_20230519_0157'),
    ]

    operations = [
        migrations.AddField(
            model_name='usercoin',
            name='purchase_price',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=18),
        ),
    ]