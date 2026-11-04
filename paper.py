"""Paper account: pretend money, real prices. Nothing here can touch a real account.

There is deliberately NO live broker and NO API key anywhere in this project.
The account is measured in percent: it starts at 100.
"""
import csv, json, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
TRADES = os.path.join(HERE, "trades.csv")
SKIPS = os.path.join(HERE, "skips.csv")
LOG = os.path.join(HERE, "bot.log")

# ---- the rules the owner chose ----
START_EQUITY = 100.0
RISK_PER_TRADE = 0.02      # a stop hit loses 2% of the account (fees included). Was 1.5% until 4 Nov 2026.
MAX_TOTAL_RISK = 0.10      # all open trades together can risk at most 10%. Was 6% until 4 Nov 2026.
DAILY_LOSS_LIMIT = 0.06    # down 6% in a day: close everything, stop until the next day
FEE = 0.0025               # 0.25% of the trade's value on every buy and every sell
MAX_NOTIONAL = 10.0        # paper borrowing allowed: holdings can reach 10x the account. A real spot account could not.
MIN_STOP_GAP = 0.001       # skip setups whose stop is closer than 0.1% to the price

FIELDS = ["symbol", "side", "entry_time", "entry_price", "exit_time", "exit_price",
          "size_pct_of_account", "stop", "reason", "pnl_pct", "r_multiple", "equity_after"]


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def new_state():
    return {"equity": START_EQUITY, "start_equity": START_EQUITY, "symbols": {},
            "day": None, "day_start_equity": None, "halted": False, "halt_count": 0,
            "last_run": None, "started": None}


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return new_state()


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def fmt_t(ms):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000)) + "Z"


def _append(path, fields, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


class Paper:
    def __init__(self, state):
        self.st = state

    def positions(self):
        return [(s, v["position"]) for s, v in self.st["symbols"].items() if v.get("position")]

    def marked_equity(self):
        eq = self.st["equity"]
        for sym, p in self.positions():
            last = self.st["symbols"][sym].get("last_close") or p["entry_price"]
            d = 1 if p["side"] == "long" else -1
            eq += d * (last - p["entry_price"]) * p["qty"]
        return eq

    def skip(self, sym, side, t, why):
        _append(SKIPS, ["time", "symbol", "side", "reason"],
                {"time": fmt_t(t), "symbol": sym, "side": side, "reason": why})
        self.st["skip_count"] = self.st.get("skip_count", 0) + 1
        log(f"{sym} skip {side}: {why}")

    def open(self, sym, side, t, price, stop):
        dist = abs(price - stop)
        wrong_side = (side == "long" and stop >= price) or (side == "short" and stop <= price)
        if wrong_side or dist / price < MIN_STOP_GAP:
            return self.skip(sym, side, t, "stop too close to price")
        eq = self.st["equity"]
        # size so that hitting the stop, fees included, loses exactly RISK_PER_TRADE of the account
        loss_per_unit = dist + FEE * (price + stop)
        risk_money = eq * RISK_PER_TRADE
        open_risk = sum(p["risk"] for _, p in self.positions())
        if open_risk + risk_money > eq * MAX_TOTAL_RISK + 1e-9:
            return self.skip(sym, side, t, f"total risk cap ({MAX_TOTAL_RISK * 100:g}%) reached")
        qty = risk_money / loss_per_unit
        used = sum(p["qty"] * p["entry_price"] for _, p in self.positions())
        room = eq * MAX_NOTIONAL - used
        if room < eq * 0.01:
            return self.skip(sym, side, t, "no room left in the account")
        if qty * price > room:
            qty = room / price      # smaller trade, so a stop hit costs less than 1.5%
        pos = {"side": side, "entry_time": t, "entry_price": price, "stop": stop,
               "qty": qty, "risk": qty * loss_per_unit}
        self.st["symbols"][sym]["position"] = pos
        log(f"{sym} OPEN {side} at {price:.6g} stop {stop:.6g} size {100 * qty * price / eq:.0f}% of account")

    def close(self, sym, t, price, reason):
        pos = self.st["symbols"][sym]["position"]
        d = 1 if pos["side"] == "long" else -1
        gross = d * (price - pos["entry_price"]) * pos["qty"]
        fees = FEE * pos["qty"] * (pos["entry_price"] + price)
        pnl = gross - fees
        eq_before = self.st["equity"]
        self.st["equity"] += pnl
        row = {"symbol": sym, "side": pos["side"], "entry_time": fmt_t(pos["entry_time"]),
               "entry_price": round(pos["entry_price"], 8), "exit_time": fmt_t(t),
               "exit_price": round(price, 8),
               "size_pct_of_account": round(100 * pos["qty"] * pos["entry_price"] / eq_before, 1),
               "stop": round(pos["stop"], 8), "reason": reason,
               "pnl_pct": round(pnl, 4), "r_multiple": round(pnl / pos["risk"], 2) if pos["risk"] else 0,
               "equity_after": round(self.st["equity"], 4)}
        _append(TRADES, FIELDS, row)
        self.st["symbols"][sym]["position"] = None
        log(f"{sym} CLOSE {pos['side']} at {price:.6g} ({reason}) {pnl:+.2f}% account now {self.st['equity']:.2f}")
