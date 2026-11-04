"""Second paper account, the "v2 shadow". It trades the same coins and the same candles as bot.py,
but with the three rule changes the backtest liked:

    1. tip 1 off (no entry on the price crossing the DEMA line)
    2. tip 2 off (no exit on the Fibonacci band)
    3. a setup is ignored if its stop is closer than 2% to the price

It has its own account, trades and skips (state_v2.json, trades_v2.csv, skips_v2.csv), so it can
never change the original account. Pretend money only. The original rules stay in bot.py.

    python3 shadow.py --once
"""
import os, sys
import paper, strategy, bot

STOP_GAP = 0.02

paper.STATE = os.path.join(paper.HERE, "state_v2.json")
paper.TRADES = os.path.join(paper.HERE, "trades_v2.csv")
paper.SKIPS = os.path.join(paper.HERE, "skips_v2.csv")
paper.MIN_STOP_GAP = STOP_GAP
bot.USE_TIP = False

_signals = strategy.signals


def signals_v2(candles, use_dema_cross_tip=False):
    out = _signals(candles, use_dema_cross_tip=False)
    for row, c in zip(out, candles):
        row["bu"] = None            # no Fibonacci band exit
        row["bl"] = None
        if row["entry"] and abs(c[4] - row["line"]) / c[4] < STOP_GAP:
            row["entry"] = None     # stop too close: not a setup, ignored without a log line
    return out


strategy.signals = signals_v2

if __name__ == "__main__":
    bot.main()
