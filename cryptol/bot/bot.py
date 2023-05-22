# Imports: Python Standard Library
import os
import decimal
import requests
import aiohttp
import asyncio
# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cryptol.settings')
import django
django.setup()
# Imports: Third Party
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from asgiref.sync import sync_to_async

from django.contrib.auth.models import User
from portfolio.models import UserCoin, Portfolio, TelegramUser, CoinHistory

API_TOKEN = ''
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

class Form(StatesGroup):
    coin_id = State()
    price = State()
    quantity = State()

class SellForm(StatesGroup):
    coin_id = State()
    quantity = State()

def get_user_coins(portfolio):
    return list(UserCoin.objects.filter(portfolio=portfolio))

@sync_to_async
def async_get_user_coins(portfolio):
    return get_user_coins(portfolio)

@sync_to_async
def get_or_create_user(user_id):
    user, created = User.objects.get_or_create(username=user_id)
    TelegramUser.objects.get_or_create(user=user, telegram_id=user_id)
    return user, created

def coin_exists(coin_id):
    response = requests.get(f'https://api.coingecko.com/api/v3/coins/{coin_id}')
    return response.status_code == 200

async def get_current_price(coin_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd") as response:
            print(f"Response status: {response.status}")  # Debug line
            print(f"Response content: {await response.text()}")  # Debug line
            data = await response.json()
            if coin_id in data:
                return data[coin_id]['usd']
            else:
                raise ValueError(f"Бот не смог найти такую монету: {coin_id}")

@sync_to_async
def create_or_update_user_coin(portfolio, coin_id, new_price, new_quantity):
    try:
        user_coin = UserCoin.objects.get(portfolio=portfolio, coin_id=coin_id)
        old_total_price = user_coin.price * user_coin.quantity
        new_total_price = new_price * new_quantity
        user_coin.quantity += new_quantity
        user_coin.price = round((old_total_price + new_total_price) / user_coin.quantity, 2)
        user_coin.save()
    except UserCoin.DoesNotExist:
        user_coin = UserCoin.objects.create(
            portfolio=portfolio,
            coin_id=coin_id,
            price=new_price,
            quantity=new_quantity
        )
    return user_coin

@sync_to_async
def save_price_history(user_coin, price):
    CoinHistory.objects.create(user_coin=user_coin, price=price)

@sync_to_async
def get_user(telegram_id):
    try:
        return TelegramUser.objects.get(telegram_id=telegram_id).user
    except TelegramUser.DoesNotExist:
        return None

@sync_to_async
def get_or_create_portfolio(user):
    return Portfolio.objects.get_or_create(user=user)

@sync_to_async
def get_portfolio_data(user):
    portfolio = Portfolio.objects.get(user=user)
    user_coins = UserCoin.objects.filter(portfolio=portfolio)
    data = []
    for coin in user_coins:
        coin_data = {
            "coin_id": coin.coin_id,
            "quantity": coin.quantity,
            "price": coin.price
        }
        data.append(coin_data)
    return data

@sync_to_async
def delete_all_user_coins(portfolio):
    UserCoin.objects.filter(portfolio=portfolio).delete()

@dp.callback_query_handler(lambda c: c.data == 'add')
async def process_callback_add(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Пожалуйста используйте команду /add чтобы добавить монету в портфель.')

from asgiref.sync import sync_to_async
async def update_coin_prices_async():
    while True:
        try:
            coins = await sync_to_async(UserCoin.objects.all)()
            for coin in coins:
                coin_id = await sync_to_async(getattr)(coin, 'coin_id')
                new_price = await get_current_price(coin_id)
                await sync_to_async(setattr)(coin, 'price', new_price)  # обновляем текущую цену
                await sync_to_async(coin.save)()
        except Exception as e:
            print(f"Cannot update coin prices due to error: {e}")
        else:
            print("Prices updated")
        await asyncio.sleep(20)  # ждем 20 секунд

loop = asyncio.get_event_loop()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    user, created = await get_or_create_user(user_id)

    if created:
        await bot.send_message(user_id, "Добро пожаловать! Вы зарегистрированы.")
    else:
        await bot.send_message(user_id, "Добро пожаловать обратно!")

@dp.message_handler(commands=['add'])
async def cmd_add(message: types.Message, state: FSMContext):
    try:
        coin_id = message.text.split(" ")[1]
    except IndexError:
        await bot.send_message(message.chat.id, "Пожалуйста, укажите название монеты. Например, `/add bitcoin`.")
        return

    if not coin_exists(coin_id):
        await bot.send_message(message.chat.id, f"Произошла ошибка: Монета с таким именем {coin_id} не найдена. Пожалуйста, убедитесь, что вы ввели имя монеты правильно.")
        return

    price = await get_current_price(coin_id)

    await state.update_data(coin_id=coin_id, price=price)  # save coin_id and price to state
    await Form.quantity.set()
    await bot.send_message(message.chat.id, f"Сколько монет вы хотите добавить?")

@dp.message_handler(commands=['sell'])
async def cmd_sell(message: types.Message, state: FSMContext):
    try:
        coin_id = message.text.split(" ")[1]
    except IndexError:
        await bot.send_message(message.chat.id, "Пожалуйста, укажите название монеты. Например, `/sell bitcoin`.")
        return

    await state.update_data(coin_id=coin_id)  # save coin_id to state
    await SellForm.quantity.set()
    await bot.send_message(message.chat.id, f"Сколько монет вы хотите продать?")

@dp.message_handler(state=SellForm.quantity)
async def process_sell_quantity(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        coin_id = data['coin_id']
        quantity_to_sell = message.text

        try:
            quantity_to_sell = Decimal(quantity_to_sell)
        except decimal.InvalidOperation:
            await bot.send_message(message.chat.id, f"Неправильный ввод. Введите действительное число.")
            return

        user = await get_user(message.from_user.id)
        portfolio, _ = await get_or_create_portfolio(user)
        user_coins = await async_get_user_coins(portfolio)

        for user_coin in user_coins:
            if await sync_to_async(getattr)(user_coin, 'coin_id') == coin_id:
                user_coin_quantity = await sync_to_async(getattr)(user_coin, 'quantity')
                user_coin_quantity = Decimal(user_coin_quantity)
                if user_coin_quantity < quantity_to_sell:
                    await bot.send_message(message.chat.id, "У вас недостаточно монет для продажи.")
                else:
                    await sync_to_async(setattr)(user_coin, 'quantity', str(user_coin_quantity - quantity_to_sell))
                    await sync_to_async(user_coin.save)()
                    await bot.send_message(message.chat.id, f"Вы продали {quantity_to_sell} монет {coin_id}")
                break
        else:
            await bot.send_message(message.chat.id, "У вас нет такой монеты в вашем портфеле.")

    await state.finish()

@dp.message_handler(state=Form.coin_id)
async def process_coin_id(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['coin_id'] = message.text
        data['price'] = await get_current_price(message.text)
    await Form.next()

@dp.message_handler(state=Form.quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        new_quantity = Decimal(message.text)
        telegram_user = await sync_to_async(TelegramUser.objects.get)(telegram_id=message.from_user.id)

        user = await sync_to_async(getattr)(telegram_user, 'user')

        portfolio, created = await sync_to_async(Portfolio.objects.get_or_create)(user=user)

        new_price = data['price']  # remove await here
        user_coin = await create_or_update_user_coin(
            portfolio=portfolio,
            coin_id=data['coin_id'],
            new_price=new_price,
            new_quantity=new_quantity
        )
        await sync_to_async(CoinHistory.objects.create)(user_coin=user_coin, price=new_price)  # and here
        await bot.send_message(
            message.chat.id,
            f"Монета {data['coin_id']} добавлена по цене {new_price} в количестве {new_quantity}"
        )
    await state.finish()

from decimal import Decimal, ROUND_DOWN

@dp.message_handler(commands=['portfolio'])
async def cmd_portfolio(message: types.Message):
    telegram_id = message.from_user.id
    user = await get_user(telegram_id)
    portfolio, _ = await get_or_create_portfolio(user)
    user_coins = await async_get_user_coins(portfolio)
    total_portfolio_value = Decimal(0)
    total_portfolio_cost = Decimal(0)

    reply = "📊 *Ваш портфель:*\n\n"
    for user_coin in user_coins:
        coin_id = await sync_to_async(getattr)(user_coin, 'coin_id')
        quantity = await sync_to_async(getattr)(user_coin, 'quantity')
        if quantity is None:
            await bot.send_message(message.chat.id, f"У монеты {coin_id} не определено количество.")
            continue
        quantity = Decimal(quantity).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        current_price = Decimal(await get_current_price(coin_id)).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        total_coin_value = (quantity * current_price).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        average_price = Decimal(await sync_to_async(getattr)(user_coin, 'price')).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        total_coin_cost = (average_price * quantity).quantize(Decimal('0.00'), rounding=ROUND_DOWN)

        # Calculate change in price
        price_change = (current_price - average_price).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        price_change_percent = ((price_change / average_price) * 100 if average_price != 0 else 0).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        price_change_usd = (price_change * quantity).quantize(Decimal('0.00'), rounding=ROUND_DOWN)

        total_portfolio_value += total_coin_value
        total_portfolio_cost += total_coin_cost
        reply += f"🪙 *Монета*: `{coin_id}`\n" \
                 f"💰 *Количество*: `{quantity}`\n" \
                 f"📉 *Средняя цена покупки*: `${average_price}`\n" \
                 f"📈 *Текущая стоимость*: `${current_price}`\n" \
                 f"💸 *Общая стоимость*: `${total_coin_value}`\n" \
                 f"🔀 *Изменение цены*: `{price_change_percent}%` (`${price_change_usd}`)\n\n"

    total_portfolio_change_percent = (((total_portfolio_value - total_portfolio_cost) / total_portfolio_cost) * 100 if total_portfolio_cost != 0 else 0).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
    total_portfolio_change_usd = (total_portfolio_value - total_portfolio_cost).quantize(Decimal('0.00'), rounding=ROUND_DOWN)

    reply += f"\n💼 *Общая стоимость портфеля*: `${total_portfolio_value}`"
    reply += f"\n⚖️ *Изменение общей стоимости портфеля*: `{total_portfolio_change_percent}%` (`${total_portfolio_change_usd}`)"

    await bot.send_message(message.chat.id, reply, parse_mode='Markdown')

@dp.message_handler(commands=['clear'])
async def cmd_clear(message: types.Message):
    telegram_id = message.from_user.id
    user = await get_user(telegram_id)
    portfolio, _ = await get_or_create_portfolio(user)
    await delete_all_user_coins(portfolio)
    await bot.send_message(message.chat.id, "Все монеты в вашем портфеле были удалены.")

async def on_startup(dp):
    asyncio.create_task(update_coin_prices_async())

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, on_startup=on_startup)
