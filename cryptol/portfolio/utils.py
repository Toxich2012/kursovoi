from pycoingecko import CoinGeckoAPI
import requests
from .models import UserCoin

def update_prices():
    cg = CoinGeckoAPI()
    coins = cg.get_coins_markets(vs_currency='usd')

    for coin in coins:
        try:
            user_coin = UserCoin.objects.get(coin_id=coin['id'])
            user_coin.price_usd = coin['current_price']
            user_coin.save()
        except UserCoin.DoesNotExist:
            continue

def get_coins_by_name(name):
    response = requests.get('https://api.coingecko.com/api/v3/coins/list')
    if response.status_code == 200:
        coins = response.json()
        return [coin for coin in coins if name.lower() in coin['id'] or name.lower() in coin['symbol']]
    return []
