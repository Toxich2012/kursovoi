# Generated by Django 3.2.5 on 2023-06-07 15:30

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('portfolio', '0008_auto_20230607_1152'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramuser',
            name='minute_threshold',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='telegramuser',
            name='percent',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
    ]