import os
import yfinance as yf
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import time
from datetime import datetime
import pytz
import threading
import warnings
warnings.filterwarnings('ignore')

TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    print("⚠️ ОШИБКА: Токен не найден!")
    exit()

EKB_TZ = pytz.timezone('Asia/Yekaterinburg')
bot = telebot.TeleBot(TOKEN)

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
user_pair = {}
user_timeframe = {}
last_signals = {}
auto_enabled = False

def get_signal(pair, timeframe):
    try:
        period_map = {"5m": "2d", "15m": "3d", "1h": "5d", "4h": "10d", "1d": "30d"}
        ticker = pair + "=X"
        df = yf.download(ticker, period=period_map[timeframe], interval=timeframe, progress=False)
        if df is None or len(df) < 20:
            return None
        close = df['Close'].values.flatten()
        if len(close) < 20:
            return None
        price = float(close[-1])
        ma10 = float(np.mean(close[-10:]))
        ma30 = float(np.mean(close[-30:])) if len(close) >= 30 else ma10
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = np.mean(gain[-14:]) if len(gain) >= 14 else np.mean(gain) if len(gain) > 0 else 0
        avg_loss = np.mean(loss[-14:]) if len(loss) >= 14 else np.mean(loss) if len(loss) > 0 else 0.001
        if avg_loss == 0 or np.isnan(avg_loss):
            rsi = 50.0
        else:
            rsi = float(100 - (100 / (1 + max(avg_gain, 0.001)/avg_loss)))
            if np.isnan(rsi) or rsi > 100:
                rsi = 50.0
        if rsi < 30 and price > ma10:
            signal = "📈 ВВЕРХ"
            conf = 75 + (30 - rsi) * 0.5
            emoji = "🟢"
        elif rsi > 70 and price < ma10:
            signal = "📉 ВНИЗ"
            conf = 75 + (rsi - 70) * 0.5
            emoji = "🔴"
        elif price > ma10 and price > ma30:
            signal = "📈 ВВЕРХ (тренд)"
            conf = 60
            emoji = "🟡"
        elif price < ma10 and price < ma30:
            signal = "📉 ВНИЗ (тренд)"
            conf = 60
            emoji = "🟡"
        else:
            signal = "⏸ НЕЙТРАЛЬНО"
            conf = 50
            emoji = "⚪"
        return {
            'pair': pair,
            'price': round(price, 4),
            'signal': signal,
            'conf': round(min(conf, 95), 1),
            'rsi': round(rsi, 1),
            'emoji': emoji,
            'timeframe': timeframe
        }
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

def auto_analyze():
    global auto_enabled
    print("🔄 Авто-анализ запущен!")
    while auto_enabled:
        try:
            now = datetime.now(EKB_TZ)
            for pair in PAIRS:
                for tf in TIMEFRAMES[:3]:
                    result = get_signal(pair, tf)
                    if result and result['conf'] >= 85:
                        key = f"{pair}_{tf}_{result['signal']}"
                        if key not in last_signals or last_signals[key] < time.time() - 3600:
                            msg = (f"🔔 *СИЛЬНЫЙ СИГНАЛ!*\n\n"
                                   f"{result['emoji']} *{result['pair']}*\n"
                                   f"🎯 Сигнал: {result['signal']}\n"
                                   f"📊 Уверенность: *{result['conf']}%* 🔥\n"
                                   f"💰 Цена: {result['price']}\n"
                                   f"📉 RSI: {result['rsi']}\n"
                                   f"⏱ Таймфрейм: {tf}\n"
                                   f"🕐 Время: {now.strftime('%H:%M')} (Екб)")
                            bot.send_message(5207522480, msg, parse_mode="Markdown")
                            last_signals[key] = time.time()
            time.sleep(300)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(60)

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Получить сигнал", callback_data="signal"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
        InlineKeyboardButton("🔔 Авто-сигналы", callback_data="autosignal")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    user_pair[chat_id] = "EURUSD"
    user_timeframe[chat_id] = "5m"
    bot.send_message(chat_id, "🚀 Привет! Я твой ИИ-аналитик!", parse_mode="Markdown", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global auto_enabled
    chat_id = call.message.chat.id
    if call.data == "autosignal":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Включить", callback_data="auto_on"),
            InlineKeyboardButton("❌ Выключить", callback_data="auto_off"),
            InlineKeyboardButton("🔙 Назад", callback_data="main")
        )
        bot.edit_message_text("🔔 Авто-сигналы", chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    elif call.data == "auto_on":
        auto_enabled = True
        threading.Thread(target=auto_analyze, daemon=True).start()
        bot.answer_callback_query(call.id, "✅ Включено!")
    elif call.data == "auto_off":
        auto_enabled = False
        bot.answer_callback_query(call.id, "❌ Выключено!")
    elif call.data == "signal":
        result = get_signal(user_pair.get(chat_id, "EURUSD"), user_timeframe.get(chat_id, "5m"))
        if result:
            bot.edit_message_text(f"{result['emoji']} *{result['pair']}*\n💰 {result['price']}\n🎯 {result['signal']}\n📊 {result['conf']}%", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    elif call.data == "main":
        bot.edit_message_text("🚀 Главное меню", chat_id=chat_id, message_id=call.message.message_id, reply_markup=main_menu())

print("🤖 Бот запущен!")
while True:
    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"Ошибка: {e}")
        time.sleep(10)
