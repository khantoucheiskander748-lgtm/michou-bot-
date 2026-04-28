import asyncio
import random
import time
from datetime import datetime, timedelta
from pyquotex.stable_api import Quotex
from telethon import TelegramClient
from flask import Flask, jsonify
import threading

EMAIL = "wagife9306@mugstock.com"
PASSWORD = "latchi23@@"

API_ID = 33567199
API_HASH = "3fdd30ef25043c39d8cc897d6251b8f1"
CHANNEL = "@latchidz0"

ASSETS = ["NZDCHF_otc", "USDINR_otc", "USDBDT_otc", "USDARS_otc", "USDPKR_otc"]
BASE_AMOUNT = 1.0

# متغيرات لتخزين آخر إشارة ونتيجة
last_signal = None
last_result = None

# =========================
# SMART ANALYSIS STRATEGY
# =========================
async def decide_direction(client, asset):
    call_score = 0
    put_score = 0
    try:
        candles = await client.get_candles(asset, int(time.time()), 5, 60)
        if candles:
            ups = sum(1 for c in candles if c["close"] > c["open"])
            downs = sum(1 for c in candles if c["close"] < c["open"])
            if ups >= 3: call_score += 3
            if downs >= 3: put_score += 3
            last_close = candles[-1]["close"]
        else:
            last_close = 0

        # RSI
        rsi = await client.calculate_indicator(asset, "RSI", {"period":14}, history_size=3600, timeframe=60)
        if rsi and "current" in rsi and rsi["current"]:
            if float(rsi["current"]) < 35: call_score += 2
            elif float(rsi["current"]) > 65: put_score += 2

        # EMA
        ema = await client.calculate_indicator(asset, "EMA", {"period":20}, history_size=3600, timeframe=60)
        if ema and "current" in ema and ema["current"]:
            if last_close > float(ema["current"]): call_score += 2
            elif last_close < float(ema["current"]): put_score += 2

        # SMA
        sma = await client.calculate_indicator(asset, "SMA", {"period":20}, history_size=3600, timeframe=60)
        if sma and "current" in sma and sma["current"]:
            if last_close > float(sma["current"]): call_score += 1
            elif last_close < float(sma["current"]): put_score += 1

        # MACD
        macd = await client.calculate_indicator(asset, "MACD", {}, history_size=3600, timeframe=60)
        if macd and "macd" in macd and macd["macd"]:
            if macd["macd"][-1] > macd["signal"][-1]: call_score += 2
            else: put_score += 2

        # Bollinger
        boll = await client.calculate_indicator(asset, "BOLLINGER", {"period":20,"std":2}, history_size=3600, timeframe=60)
        if boll and "middle" in boll:
            if last_close < boll["lower"][-1]: call_score += 2
            elif last_close > boll["upper"][-1]: put_score += 2

        # Stochastic
        stoch = await client.calculate_indicator(asset, "STOCHASTIC", {"k_period":14,"d_period":3}, history_size=3600, timeframe=60)
        if stoch and "current" in stoch and stoch["current"]:
            if stoch["current"] < 20: call_score += 1
            elif stoch["current"] > 80: put_score += 1

        # ATR
        atr = await client.calculate_indicator(asset, "ATR", {"period":14}, history_size=3600, timeframe=60)
        if atr and "current" in atr and atr["current"]:
            if float(atr["current"]) > 0.5:
                call_score += 1; put_score += 1

        # ADX
        adx = await client.calculate_indicator(asset, "ADX", {"period":14}, history_size=3600, timeframe=60)
        if adx and "adx" in adx and adx["adx"]:
            if adx["adx"][-1] > 25:
                if call_score > put_score: call_score += 1
                elif put_score > call_score: put_score += 1

        # Ichimoku
        ichi = await client.calculate_indicator(asset, "ICHIMOKU", {"tenkan_period":9,"kijun_period":26,"senkou_b_period":52}, history_size=3600, timeframe=60)
        if ichi and "tenkan" in ichi and ichi["tenkan"]:
            if last_close > ichi["tenkan"][-1]: call_score += 1
            elif last_close < ichi["tenkan"][-1]: put_score += 1

        if call_score > put_score: return "call"
        elif put_score > call_score: return "put"
        else: return random.choice(["call","put"])

    except Exception as e:
        print("DECIDE ERROR:", e)
        return random.choice(["call","put"])


# =========================
# EXECUTE + RESULT ENGINE
# =========================
async def trade_once(client, asset, amount, direction, duration, target_time):
    global last_signal, last_result
    now = datetime.now()
    wait_seconds = (target_time - now).total_seconds() - 2.0
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    try:
        print(f"🟡 محاولة شراء: {asset} | {direction}")
        success, order_info = await client.buy(amount, asset, direction, duration)
    except Exception as e:
        print("BUY ERROR:", e)
        return None, None, None, "none"

    if not success or "id" not in order_info:
        print("❌ فشل فتح الصفقة")
        return None, None, None, "none"

    order_id = order_info["id"]
    last_signal = f"{asset.upper()} | {direction.upper()}"

    await asyncio.sleep(duration + 10)

    try:
        profit, status = await client.check_win(order_id)
        print(f"📊 النتيجة: {status} | Profit: {profit}")
        last_result = status
    except Exception as e:
        print("RESULT ERROR:", e)
        status = "none"
        last_result = status

    return order_id, asset, direction, status


# =========================
# MAIN BOT
# =========================
async def main():
    client = Quotex(email=EMAIL, password=PASSWORD, lang="en")
    client.set_account_mode("PRACTICE")

    connected, reason = await client.connect()
    if not connected:
        print("❌ فشل الاتصال:", reason)
        return

    await client.change_account("PRACTICE")

    tg = TelegramClient("session_pc", API_ID, API_HASH)
    await tg.start()

    while True:
        try:
            asset = random.choice(ASSETS)
            direction = await decide_direction(client, asset)

            now = datetime.now()
            next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            target_time = next_minute.replace(second=0)

            await tg.send_message(CHANNEL, f"📊 صفقة جديدة: {asset.upper()} | {direction.upper()} | {target_time.strftime('%H:%M')}")

            order_id, asset_used, dir_used, result = await trade_once(
                client, asset, BASE_AMOUNT, direction, 60, target_time
            )

            if result == "win":
                await tg.send_message(CHANNEL, f"🟢 ربح ✅ | {asset_used.upper()} | {dir_used.upper()}")
            elif result == "loss":
                await tg.send_message(CHANNEL, f"🔴 خسارة ❌ | {asset_used.upper()} | {dir_used.upper()}")
            else:
                await tg.send_message(CHANNEL, f"⚠️ النتيجة غير معروفة | {asset_used.upper()}")

            await asyncio.sleep(10)

        except Exception as e:
            print("MAIN LOOP ERROR:", e)
            await asyncio.sleep(5)


# =========================
# FLASK API
# =========================
app = Flask(__name__)

@app.route("/status")
def status():
    return jsonify({
        "bot": "running",
        "last_signal": last_signal,
        "last_result": last_result
    })

def run_flask():
    app.run(host="0.0.0.0", port=8000)

# تشغيل البوت و Flask مع بعض
if __name__ == "__main__":
    # نشغل البوت في Thread منفصل
    threading.Thread(target=lambda: asyncio.run(main()), daemon=True).start()
    # نشغل Flask API
    run_flask()