"""Third paper account, the "2 hour test". Same coins, but on the 2 hour chart and with the rules the big
backtest liked best:

    1. 2 hour candles (the bot checks every 15 minutes, but a new 2 hour candle only closes every 2 hours)
    2. flips only: no tip 1
    3. no Fibonacci band exit
    4. a setup is ignored if its stop is closer than 1.5% to the price
    5. risk 1% of the account per trade and at most 6% open at once (the main account uses 2% and 12%)

Own files (state_2h.json, trades_2h.csv, skips_2h.csv), so it can never change the other accounts.
Pretend money only.

    python3 shadow2h.py --once
"""
import os
from datetime import datetime, timezone
import paper, strategy, bot

SPAN = 7_200_000        # one 2 hour candle in milliseconds
STOP_GAP = 0.015

paper.STATE = os.path.join(paper.HERE, "state_2h.json")
paper.TRADES = os.path.join(paper.HERE, "trades_2h.csv")
paper.SKIPS = os.path.join(paper.HERE, "skips_2h.csv")
paper.MIN_STOP_GAP = STOP_GAP
paper.RISK_PER_TRADE = 0.01
paper.MAX_TOTAL_RISK = 0.06
bot.USE_TIP = False
bot.SYMBOLS = bot.ALL_SYMBOLS
bot.USE_BAND_EXIT = False
bot.URL = bot.URL.replace("interval=15m", "interval=2h")


def day_of(t_ms):
    """Trading day = calendar date in Toronto, taken at the candle's close."""
    return datetime.fromtimestamp((t_ms + SPAN - 1) / 1000, timezone.utc).astimezone(bot.TZ).date().isoformat()


def liquid(candles, i):
    lo = max(0, i - 11)             # 12 candles of 2 hours = the last 24 hours
    return sum(c[4] * c[5] for c in candles[lo:i + 1]) >= bot.MIN_DAY_VOLUME


bot.day_of = day_of
bot.liquid = liquid
_signals = strategy.signals


def signals_2h(candles, use_dema_cross_tip=False):
    out = _signals(candles, use_dema_cross_tip=False)
    for row, c in zip(out, candles):
        row["bu"] = None
        row["bl"] = None
        if row["entry"] and abs(c[4] - row["line"]) / c[4] < STOP_GAP:
            row["entry"] = None
    return out


strategy.signals = signals_2h

if __name__ == "__main__":
    bot.main()
