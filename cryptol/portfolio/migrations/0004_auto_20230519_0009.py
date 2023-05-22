# Generated by Django 3.2.5 on 2023-05-18 17:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0003_auto_20230518_1954'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='usercoin',
            name='amount',
        ),
        migrations.AddField(
            model_name='usercoin',
            name='quantity',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=18),
        ),
        migrations.AlterField(
            model_name='usercoin',
            name='coin_id',
            field=models.CharField(max_length=50),
        ),
        migrations.CreateModel(
            name='CoinHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('price', models.DecimalField(decimal_places=8, max_digits=18)),
                ('user_coin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='portfolio.usercoin')),
            ],
        ),
    ]
