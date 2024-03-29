# models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class TelegramUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telegram_id = models.IntegerField(unique=True)

class Portfolio(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

class UserCoin(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE)
    coin_id = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    purchase_price = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    quantity = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

class CoinHistory(models.Model):
    user_coin = models.ForeignKey(UserCoin, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    price = models.DecimalField(max_digits=18, decimal_places=8)
