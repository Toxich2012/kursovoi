from django.shortcuts import render

# Create your views here.
from apscheduler.schedulers.background import BackgroundScheduler
from .utils import update_prices

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_prices, 'interval', minutes=1)
    scheduler.start()
