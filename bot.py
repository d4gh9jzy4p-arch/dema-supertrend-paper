"""Paper-trading bot: DEMA 200 + Supertrend (12, 3) + Fibonacci Bollinger Bands, 15 minute candles.

One run looks at every candle that closed since the last run, in time order, and trades them
exactly as they would have arrived live. So a late or missed run only delays the paper trades,
it never skips a candle.

    python3 bot.py --once    do one check and stop (what the GitHub schedule runs)
    python3 bot.py           keep running on this computer, checking every 15 minutes

Pretend money only. Prices come from Binance's free public data feed (no account, no key).
"""
import argparse, json, time, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import strategy, paper

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "LTCUSDT", "LINKUSDT", "AVAXUSDT", "NEARUSDT"]
URL = "https://data-api.binance.vision/api/v3/klines?symbol={}&interval=15m&limit=1000"
USE_TIP = True              # the video's blue-line cross entry tip
USE_BAND_EXIT = False       # the video's Fibonacci band exit tip. Off since 5 Nov 2026: it closed trades right after entry, even below the entry price
LONG_ONLY = False           # the owner chose long and short
MIN_DAY_VOLUME = 5_000_000  # skip a coin whose last 24h traded under this many USDT (thin coins fill badly)
TZ = ZoneInfo("America/Toronto")


def fetch_closed(sym):
    rows = json.load(urllib.request.urlopen(URL.format(sym), timeout=30))
    now = int(time.time() * 1000)
    # row[6] is the candle's close time. Keep only candles that have fully closed.
    return [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
            for r in rows if r[6] < now]


def day_of(t_ms):
    """Trading day = calendar date in Toronto, taken at the candle's close."""
    return datetime.fromtimestamp((t_ms + 900_000 - 1) / 1000, timezone.utc).astimezone(TZ).date().isoformat()


def liquid(candles, i):
    lo = max(0, i - 95)
    return sum(c[4] * c[5] for c in candles[lo:i + 1]) >= MIN_DAY_VOLUME


def handle_candle(broker, sym, candles, sigs, i):
    st = broker.st
    ss = st["symbols"][sym]
    t, o, h, l, c = candles[i][:5]
    s = sigs[i]

    d = day_of(t)
    if d != st["day"]:
        st["day"] = d
        st["day_start_equity"] = broker.marked_equity()
        if st["halted"]:
            paper.log(f"new day {d}: trading allowed again")
        st["halted"] = False

    pos = ss.get("position")
    if pos:
        long_ = pos["side"] == "long"
        # Order inside one candle is unknown, so assume the worst case for us: stop first.
        if (long_ and l <= pos["stop"]) or (not long_ and h >= pos["stop"]):
            gap = min(o, pos["stop"]) if long_ else max(o, pos["stop"])
            broker.close(sym, t, gap, "stop loss")
        elif USE_BAND_EXIT and s["bu"] is not None and long_ and h >= s["bu"]:
            broker.close(sym, t, s["bu"], "Fibonacci band")
        elif USE_BAND_EXIT and s["bl"] is not None and not long_ and l <= s["bl"]:
            broker.close(sym, t, s["bl"], "Fibonacci band")
        elif (long_ and s["trend"] == -1) or (not long_ and s["trend"] == 1):
            broker.close(sym, t, c, "Supertrend flip")

    ss["last_close"] = c
    ss["last_time"] = t

    # Daily loss limit: down 6% on the day (open trades counted) -> close everything, stop for the day.
    if not st["halted"] and st["day_start_equity"]:
        if broker.marked_equity() <= st["day_start_equity"] * (1 - paper.DAILY_LOSS_LIMIT) + 1e-9:
            for other, _ in broker.positions():
                lc = st["symbols"][other].get("last_close") or c
                broker.close(other, t, lc, "daily loss limit")
            st["halted"] = True
            st["halt_count"] = st.get("halt_count", 0) + 1
            paper.log(f"DAILY LOSS LIMIT hit on {d}: everything closed, no new trades today")

    if ss.get("position") or not s["entry"]:
        return
    side = s["entry"]
    if side == "short" and LONG_ONLY:
        return
    if st["halted"]:
        return broker.skip(sym, side, t, "daily loss limit already hit today")
    if not liquid(candles, i):
        return broker.skip(sym, side, t, "coin too thinly traded")
    broker.open(sym, side, t, c, s["line"])


def process(broker, feeds):
    """feeds: {symbol: closed candles}. Walk all new candles of all coins in time order."""
    st = broker.st
    sigs, events = {}, []
    for sym, candles in feeds.items():
        ss = st["symbols"].setdefault(sym, {"position": None, "last_time": None, "last_close": None})
        sigs[sym] = strategy.signals(candles, use_dema_cross_tip=USE_TIP)
        if ss["last_time"] is None:
            # First ever look at this coin: do not trade old history, just start watching.
            ss["last_time"] = candles[-1][0]
            ss["last_close"] = candles[-1][4]
            paper.log(f"{sym} watching from {paper.fmt_t(candles[-1][0])}")
            continue
        events += [(c[0], sym, i) for i, c in enumerate(candles) if c[0] > ss["last_time"]]
    if st["day"] is None and feeds:
        any_c = next(iter(feeds.values()))[-1]
        st["day"] = day_of(any_c[0])
        st["day_start_equity"] = broker.marked_equity()
    for _, sym, i in sorted(events):
        handle_candle(broker, sym, feeds[sym], sigs[sym], i)
    return len(events)


def cycle(st, broker):
    feeds = {}
    for sym in SYMBOLS:
        try:
            feeds[sym] = fetch_closed(sym)
        except Exception as e:
            paper.log(f"{sym} data error: {e}")
    n = process(broker, feeds)
    st["last_run"] = int(time.time() * 1000)
    if st["started"] is None:
        st["started"] = st["last_run"]
    paper.save_state(st)
    return n


def status(st, broker):
    open_n = len(broker.positions())
    paper.log(f"account {broker.marked_equity():.2f} (start 100) | open trades {open_n} | halted today: {st['halted']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    st = paper.load_state()
    broker = paper.Paper(st)
    while True:
        cycle(st, broker)
        status(st, broker)
        if a.once:
            return
        time.sleep(900 - (time.time() % 900) + 10)   # wake 10 seconds after the next 15 minute mark


if __name__ == "__main__":
    main()
