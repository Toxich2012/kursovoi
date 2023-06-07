from django.shortcuts import render

# Create your views here.
from apscheduler.schedulers.background import BackgroundScheduler
from .utils import update_prices
from rest_framework import viewsets
from .models import UserCoin, Portfolio
from .serializers import UserCoinSerializer, PortfolioSerializer
from django.shortcuts import render, redirect
from .forms import UpdatePortfolioForm
from django.contrib.auth.decorators import login_required


def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_prices, 'interval', minutes=1)
    scheduler.start()


@login_required
def update_portfolio(request):
    if request.method == 'POST':
        form = UpdatePortfolioForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            if form.cleaned_data.get('manual_price'):
                instance.manual_price = form.cleaned_data.get('manual_price')
            instance.save()
            return redirect('portfolio')
    else:
        form = UpdatePortfolioForm()

    return render(request, 'update_portfolio.html', {'form': form})


class UserCoinViewSet(viewsets.ModelViewSet):
    queryset = UserCoin.objects.all()
    serializer_class = UserCoinSerializer


class PortfolioViewSet(viewsets.ModelViewSet):
    queryset = Portfolio.objects.all()
    serializer_class = PortfolioSerializer
