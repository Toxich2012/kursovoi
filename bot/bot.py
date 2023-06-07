# Imports: Python Standard Library
import os
import decimal
import requests
import asyncio
import traceback
import sys

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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from django.contrib.auth.models import User
from portfolio.models import UserCoin, Portfolio, TelegramUser, CoinPriceHistory

API_TOKEN = ''
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

yes_no_keyboard = InlineKeyboardMarkup(row_width=2).add(
    InlineKeyboardButton("Да", callback_data="yes"),
    InlineKeyboardButton("Нет", callback_data="no")
)


class Form(StatesGroup):
    coin_id = State()
    price = State()
    quantity = State()
    custom_price_choice = State()
    threshold = State()


class TelegramUserPercent(StatesGroup):
    percent = State()


class SellForm(StatesGroup):
    coin_id = State()
    quantity = State()


@sync_to_async
def save_price_history(user_coin, price):
    CoinPriceHistory.objects.create(user_coin=user_coin, price=price)


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


import aiohttp


async def get_current_price(coin_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd") as response:
            data = await response.json()
            return data[coin_id]['usd']



@sync_to_async
def create_or_update_user_coin(portfolio, coin_id, new_price, new_quantity):
    try:
        user_coin = UserCoin.objects.get(portfolio=portfolio, coin_id=coin_id)
        old_total_price = user_coin.price * user_coin.quantity
        new_total_price = Decimal(new_price) * new_quantity
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
    CoinPriceHistory.objects.create(user_coin=user_coin, price=price)


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
    await bot.send_message(callback_query.from_user.id,
                           'Пожалуйста используйте команду /add чтобы добавить монету в портфель.')


from asgiref.sync import sync_to_async


async def update_coin_prices_async():
    while True:
        try:
            coins = await sync_to_async(UserCoin.objects.all)()
            for coin in coins:
                coin_id = await sync_to_async(getattr)(coin, 'coin_id')
                new_price = await sync_to_async(get_current_price)(coin_id)
                await sync_to_async(setattr)(coin, 'price', new_price)  # обновляем текущую цену
                await sync_to_async(coin.save)()

                # Сохраняем историю цен для монеты
                await save_price_history(coin, new_price)

        except Exception as e:
            print(f"Cannot update coin prices due to error: {e}")
        else:
            print("Prices updated")
        await asyncio.sleep(20)  # ждем 20 секунд


loop = asyncio.get_event_loop()


@dp.message_handler(state=Form.custom_price_choice)
async def process_custom_price_choice(message: types.Message, state: FSMContext):
    custom_price_choice = message.text.lower()
    if custom_price_choice in ['yes', 'да']:
        await Form.price.set()
        await bot.send_message(message.chat.id, f"Пожалуйста, введите вашу цену для монеты.")
    elif custom_price_choice in ['no', 'нет']:
        async with state.proxy() as data:
            data['price'] = await get_current_price(data['coin_id'])
        await Form.quantity.set()
        await bot.send_message(message.chat.id, f"Сколько монет вы хотите добавить?")
    else:
        await bot.send_message(message.chat.id, f"Пожалуйста, ответьте 'да' или 'нет'.")


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    user, created = await get_or_create_user(user_id)

    if created:
        await bot.send_message(user_id, "Добро пожаловать! Вы зарегистрированы.")
    else:
        await bot.send_message(user_id, "Добро пожаловать обратно!")


@dp.message_handler(commands=['vperc'])
async def cmd_view_thresholds(message: types.Message, state: FSMContext):
    user = await sync_to_async(TelegramUser.objects.get, thread_sensitive=True)(telegram_id=message.from_user.id)

    minute_threshold = await sync_to_async(getattr)(user, 'minute_threshold')
    five_minutes_threshold = await sync_to_async(getattr)(user, 'five_minutes_threshold')
    fifteen_minutes_threshold = await sync_to_async(getattr)(user, 'fifteen_minutes_threshold')
    thirty_minutes_threshold = await sync_to_async(getattr)(user, 'thirty_minutes_threshold')
    hour_threshold = await sync_to_async(getattr)(user, 'hour_threshold')
    percent = await sync_to_async(getattr)(user, 'percent')

    minute_answer = f"1 минута: {minute_threshold}%\n"
    if minute_threshold is None or minute_threshold == 0:
        minute_answer = f"1 минута: интервал не задан\n"

    five_minutes_answer = f"5 минут: {five_minutes_threshold}%\n"
    if five_minutes_threshold is None or five_minutes_threshold == 0:
        five_minutes_answer = f"5 минут: интервал не задан\n"

    fifteen_minutes_answer = f"15 минут: {fifteen_minutes_threshold}%\n"
    if fifteen_minutes_threshold is None or fifteen_minutes_threshold == 0:
        fifteen_minutes_answer = f"15 минут: интервал не задан\n"

    thirty_minutes_answer = f"30 минут: {thirty_minutes_threshold}%\n"
    if thirty_minutes_threshold is None or thirty_minutes_threshold == 0:
        thirty_minutes_answer = f"30 минут: интервал не задан\n"

    hour_answer = f"1 час: {hour_threshold}%\n"
    if hour_threshold is None or hour_threshold == 0:
        hour_answer = f"1 час: интервал не задан\n"

    response = (
        f"Пороги изменения цены:\n"
        f"{minute_answer}"
        f"{five_minutes_answer}"
        f"{fifteen_minutes_answer}"
        f"{thirty_minutes_answer}"
        f"{hour_answer}"
    )

    await bot.send_message(message.chat.id, response)


@dp.message_handler(commands=['add'])
async def cmd_add(message: types.Message, state: FSMContext):
    try:
        coin_id = message.text.split(" ")[1]
    except IndexError:
        await bot.send_message(message.chat.id, "Пожалуйста, укажите название монеты. Например, `/add bitcoin`.")
        return

    if not coin_exists(coin_id):
        await bot.send_message(message.chat.id,
                               f"Произошла ошибка: Монета с таким именем {coin_id} не найдена. Пожалуйста, убедитесь, что вы ввели имя монеты правильно.")
        return

    await state.update_data(coin_id=coin_id)
    await Form.custom_price_choice.set()
    await bot.send_message(message.chat.id, f"Хотите ли вы установить свою собственную цену для этой монеты?",
                           reply_markup=yes_no_keyboard)


@dp.callback_query_handler(lambda c: c.data == 'yes', state=Form.custom_price_choice)
async def process_callback_yes(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await Form.price.set()
    await bot.send_message(callback_query.from_user.id, f"Пожалуйста, введите вашу цену для монеты.")


@dp.callback_query_handler(lambda c: c.data == 'no', state=Form.custom_price_choice)
async def process_callback_no(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    async with state.proxy() as data:
        data['price'] = await get_current_price(data['coin_id'])
    await Form.quantity.set()
    await bot.send_message(callback_query.from_user.id, f"Сколько монет вы хотите добавить?")


@dp.message_handler(state=Form.price)
async def process_price(message: types.Message, state: FSMContext):
    try:
        price = Decimal(message.text)
        await state.update_data(price=price)
        await Form.quantity.set()
        await bot.send_message(message.chat.id, f"Сколько монет вы хотите добавить?")
    except decimal.InvalidOperation:
        await bot.send_message(message.chat.id, "Введите корректное число.")


@dp.message_handler(commands=['sell'])
async def cmd_sell(message: types.Message, state: FSMContext):
    try:
        coin_id = message.text.split(" ")[1]
    except IndexError:
        await bot.send_message(message.chat.id, "Пожалуйста, укажите название монеты. Например, `/sell bitcoin`.")
        return

    await state.update_data(coin_id=coin_id)
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
    print("\n\n\n god2222 \n\n\n")
    try:
        if 'threshold' in (await state.get_data()).keys():
            # Пользователь выбрал период порога, пропускаем ввод идентификатора монеты
            await Form.next()
        else:
            async with state.proxy() as data:
                data['coin_id'] = message.text
                try:
                    data['price'] = await get_current_price(message.text)
                except AttributeError:
                    print("\n\n\n god \n\n\n")
            await Form.next()
    except aiohttp.ClientError:
        await bot.send_message(message.chat.id,
                               "Ошибка при получении цены монеты. Пожалуйста, попробуйте еще раз позже.")


@dp.message_handler(state=TelegramUserPercent.percent)
async def process_percent(message: types.Message, state: FSMContext):

    try:
        if not message.text.isnumeric():
            await bot.send_message(message.chat.id, "процент должен быть числом.")
            await state.finish()
            return
        if int(message.text) <= 0:
            await bot.send_message(message.chat.id, "процент должен быть больше нуля.")
            await state.finish()
            return
        threshold_interval = 'percent'
        data = await (state.get_data())
        print(data)
        if data.get('minute_threshold'):
            threshold_interval = 'minute_threshold'
        if data.get('five_minutes_threshold'):
            threshold_interval = 'five_minutes_threshold'
        if data.get('fifteen_minutes_threshold'):
            threshold_interval = 'fifteen_minutes_threshold'
        if data.get('thirty_minutes_threshold'):
            threshold_interval = 'thirty_minutes_threshold'
        if data.get('hour_threshold'):
            threshold_interval = 'hour_threshold'

        user = await sync_to_async(TelegramUser.objects.get, thread_sensitive=True)(telegram_id=message.from_user.id)
        await sync_to_async(setattr)(user, threshold_interval, message.text)
        await sync_to_async(user.save)()
        await bot.send_message(message.chat.id, "процент установлен.")

    except aiohttp.ClientError:
        await bot.send_message(message.chat.id, "процент не установлен.")

    await state.finish()


@dp.message_handler(state=Form.quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        new_quantity = Decimal(message.text)
        telegram_user = await sync_to_async(TelegramUser.objects.get)(telegram_id=message.from_user.id)

        user = await sync_to_async(getattr)(telegram_user, 'user')

        portfolio, created = await sync_to_async(Portfolio.objects.get_or_create)(user=user)

        new_price = data['price']
        user_coin = await create_or_update_user_coin(
            portfolio=portfolio,
            coin_id=data['coin_id'],
            new_price=new_price,
            new_quantity=new_quantity
        )
        await sync_to_async(CoinPriceHistory.objects.create)(user_coin=user_coin, price=new_price)
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
        average_price = Decimal(await sync_to_async(getattr)(user_coin, 'price')).quantize(Decimal('0.00'),
                                                                                           rounding=ROUND_DOWN)
        total_coin_cost = (average_price * quantity).quantize(Decimal('0.00'), rounding=ROUND_DOWN)

        # Calculate change in price
        price_change = (current_price - average_price).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        price_change_percent = ((price_change / average_price) * 100 if average_price != 0 else 0).quantize(
            Decimal('0.00'), rounding=ROUND_DOWN)
        price_change_usd = (price_change * quantity).quantize(Decimal('0.00'), rounding=ROUND_DOWN)

        total_portfolio_value += total_coin_value
        total_portfolio_cost += total_coin_cost
        reply += f"🪙 *Монета*: `{coin_id}`\n" \
                 f"💰 *Количество*: `{quantity}`\n" \
                 f"📉 *Средняя цена покупки*: `${average_price}`\n" \
                 f"📈 *Текущая стоимость*: `${current_price}`\n" \
                 f"💸 *Общая стоимость*: `${total_coin_value}`\n" \
                 f"🔀 *Изменение цены*: `{price_change_percent}%` (`${price_change_usd}`)\n\n"

    total_portfolio_change_percent = Decimal(((total_portfolio_value - total_portfolio_cost) / total_portfolio_cost) * 100 if total_portfolio_cost != 0 else 0).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
    total_portfolio_change_usd = Decimal(total_portfolio_value - total_portfolio_cost).quantize(Decimal('0.00'), rounding=ROUND_DOWN)

    reply += f"\n💼 *Общая стоимость портфеля*: `${total_portfolio_value}`"
    reply += f"\n⚖️ *Изменение общей стоимости портфеля*: `{total_portfolio_change_percent}%` (`${total_portfolio_change_usd}`)"

    await bot.send_message(message.chat.id, reply, parse_mode='Markdown')


async def process_portfolio_change(user_coin, old_price, new_price):
    percentage_change = (new_price - old_price) / old_price * 100

    if percentage_change == 0:
        return

    user = user_coin.portfolio.user
    telegram_user = await sync_to_async(TelegramUser.objects.get)(user=user)
    minute_threshold = await sync_to_async(getattr)(telegram_user, 'minute_threshold')
    five_minutes_threshold = await sync_to_async(getattr)(telegram_user, 'five_minutes_threshold')
    fifteen_minutes_threshold = await sync_to_async(getattr)(telegram_user, 'fifteen_minutes_threshold')
    thirty_minutes_threshold = await sync_to_async(getattr)(telegram_user, 'thirty_minutes_threshold')
    hour_threshold = await sync_to_async(getattr)(telegram_user, 'hour_threshold')

    if minute_threshold and percentage_change >= minute_threshold:
        await send_price_change_notification(user, user_coin, "1 минута", percentage_change)

    if five_minutes_threshold and percentage_change >= five_minutes_threshold:
        await send_price_change_notification(user, user_coin, "5 минут", percentage_change)

    if fifteen_minutes_threshold and percentage_change >= fifteen_minutes_threshold:
        await send_price_change_notification(user, user_coin, "15 минут", percentage_change)

    if thirty_minutes_threshold and percentage_change >= thirty_minutes_threshold:
        await send_price_change_notification(user, user_coin, "30 минут", percentage_change)

    if hour_threshold and percentage_change >= hour_threshold:
        await send_price_change_notification(user, user_coin, "1 час", percentage_change)


async def send_price_change_notification(user, user_coin, time_frame, percentage_change):
    coin_id = await sync_to_async(getattr)(user_coin, 'coin_id')
    quantity = await sync_to_async(getattr)(user_coin, 'quantity')
    new_price = await sync_to_async(get_current_price)(coin_id)

    message = f"Цена монеты {coin_id} в вашем портфеле изменилась на {percentage_change}% за {time_frame}.\n" \
              f"Количество монет: {quantity}\n" \
              f"Текущая цена: {new_price}"


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


@dp.message_handler(commands=['perc'])
async def cmd_set_threshold(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("1 минута", callback_data="threshold_minute"),
        InlineKeyboardButton("5 минут", callback_data="threshold_five_minutes"),
        InlineKeyboardButton("15 минут", callback_data="threshold_fifteen_minutes"),
        InlineKeyboardButton("30 минут", callback_data="threshold_thirty_minutes"),
        InlineKeyboardButton("1 час", callback_data="threshold_hour")
    )
    await bot.send_message(message.chat.id, "Выберите промежуток времени:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith('threshold_'))
async def process_threshold_callback(callback_query: types.CallbackQuery, state: FSMContext):
    period = callback_query.data.replace('threshold_', '')
    threshold_attr = f"{period}_threshold"

    await state.update_data({threshold_attr: True})  # Установка атрибута состояния в True
    await bot.send_message(callback_query.from_user.id, f"Порог изменения цены для промежутка {period} установлен.")
    await bot.answer_callback_query(callback_query.id)
    await TelegramUserPercent.next()  # Переходим к следующему состоянию
    await bot.send_message(callback_query.from_user.id, "Введите новый процент порога для изменения цены:")


@dp.message_handler(state=Form.threshold)
async def process_threshold(message: types.Message, state: FSMContext):
    try:
        threshold = Decimal(message.text)
        await state.update_data(threshold=threshold)
        await bot.send_message(message.chat.id, f"Порог изменения цены установлен на {threshold}%.")
    except decimal.InvalidOperation:
        await bot.send_message(message.chat.id, "Введите корректное число для порога изменения цены.")

    await state.finish()


async def check_portfolio_prices_async():
    while True:
        try:
            user_coins = await sync_to_async(UserCoin.objects.all)()
            for user_coin in user_coins:
                coin_id = await sync_to_async(getattr)(user_coin, 'coin_id')
                old_price = await sync_to_async(getattr)(user_coin, 'price')
                new_price = await sync_to_async(get_current_price)(coin_id)

                if new_price != old_price:
                    await sync_to_async(setattr)(user_coin, 'price', new_price)
                    await sync_to_async(user_coin.save)()

                    # Вызываем функцию для обработки изменения цены в портфеле
                    await process_portfolio_change(user_coin, old_price, new_price)

        except Exception as e:
            print(f"Cannot check portfolio prices due to error: {e}")

        await asyncio.sleep(60)  # Проверяем цены каждую минуту


@dp.message_handler(commands=['clear'])
async def cmd_clear(message: types.Message):
    telegram_id = message.from_user.id
    user = await get_user(telegram_id)
    portfolio, _ = await get_or_create_portfolio(user)
    await delete_all_user_coins(portfolio)
    await bot.send_message(message.chat.id, "Все монеты в вашем портфеле были удалены.")


def log_exception(exc_type, exc_value, exc_traceback):
    traceback_string = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"Error occurred:\n{traceback_string}", file=sys.stderr)


sys.excepthook = log_exception


async def on_startup(dp):
    asyncio.create_task(update_coin_prices_async())
    asyncio.create_task(check_portfolio_prices_async())


if __name__ == '__main__':
    from aiogram import executor

    executor.start_polling(dp, on_startup=on_startup)
