# forms.py
from django import forms
from .models import UserCoin


class UpdatePortfolioForm(forms.ModelForm):
    class Meta:
        model = UserCoin
        fields = ['coin_id', 'quantity', 'purchase_price']
        manual_price = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
