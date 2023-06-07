from rest_framework import serializers
from .models import UserCoin, Portfolio


class UserCoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCoin
        fields = '__all__'  # Или указать конкретные поля


class PortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Portfolio
        fields = '__all__'
