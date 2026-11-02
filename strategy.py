"""DEMA 200 + Supertrend (12, 3) + Fibonacci Bollinger Bands, exactly as described in the video.

Pure functions: no network, no money. A candle is [open_time_ms, open, high, low, close, volume].
Only CLOSED candles may be passed in, because the rules say to wait for the signal candle to close.
"""

DEMA_LEN = 200
ATR_LEN = 12
ATR_MULT = 3.0
FBB_LEN = 200
FBB_MULT = 3.0   # the indicator's standard settings; the video gives no numbers
# The video says to untick every Fibonacci level except the ones marked 1, so only the outer band is used.


def ema(values, n):
    k = 2.0 / (n + 1)
    out = []
    prev = None
    for v in values:
        prev = v if prev is None else prev + k * (v - prev)
        out.append(prev)
    return out


def dema(closes, n=DEMA_LEN):
    e1 = ema(closes, n)
    e2 = ema(e1, n)
    return [2 * a - b for a, b in zip(e1, e2)]


def supertrend(candles, atr_len=ATR_LEN, mult=ATR_MULT):
    """Returns (trend, line). trend is +1 (buy signal) or -1 (sell signal), None while warming up.
    Same method as TradingView's built-in: Wilder-smoothed ATR on hl2, bands only tighten."""
    n = len(candles)
    trend = [None] * n
    line = [None] * n
    tr = []
    for i, cd in enumerate(candles):
        h, l = cd[2], cd[3]
        if i == 0:
            tr.append(h - l)
        else:
            pc = candles[i - 1][4]
            tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = [None] * n
    up_f = dn_f = None
    t = 1
    for i in range(n):
        if i < atr_len - 1:
            continue
        if i == atr_len - 1:
            atr[i] = sum(tr[:atr_len]) / atr_len
        else:
            atr[i] = (atr[i - 1] * (atr_len - 1) + tr[i]) / atr_len
        h, l, c = candles[i][2], candles[i][3], candles[i][4]
        hl2 = (h + l) / 2
        up = hl2 - mult * atr[i]
        dn = hl2 + mult * atr[i]
        if up_f is None:
            up_f, dn_f, t = up, dn, 1
        else:
            pc = candles[i - 1][4]
            pu, pd = up_f, dn_f
            up_f = max(up, pu) if pc > pu else up
            dn_f = min(dn, pd) if pc < pd else dn
            if t == -1 and c > pd:
                t = 1
            elif t == 1 and c < pu:
                t = -1
        trend[i] = t
        line[i] = up_f if t == 1 else dn_f
    return trend, line


def fib_bands(candles, n=FBB_LEN, mult=FBB_MULT):
    """Outer (level 1) Fibonacci Bollinger Bands: volume weighted average of hlc3 +/- mult * stdev."""
    m = len(candles)
    upper = [None] * m
    lower = [None] * m
    src = [(c[2] + c[3] + c[4]) / 3.0 for c in candles]
    vol = [c[5] if len(c) > 5 else 1.0 for c in candles]
    for i in range(n - 1, m):
        w = src[i - n + 1:i + 1]
        v = vol[i - n + 1:i + 1]
        sv = sum(v)
        if sv <= 0:
            continue
        basis = sum(a * b for a, b in zip(w, v)) / sv
        mean = sum(w) / n
        sd = (sum((a - mean) ** 2 for a in w) / n) ** 0.5
        upper[i] = basis + mult * sd
        lower[i] = basis - mult * sd
    return upper, lower


def signals(candles, use_dema_cross_tip=True):
    """For every candle return a dict with the indicator values and an 'entry' of
    'long', 'short' or None. Entry is judged at the candle CLOSE.

    Main rule: Supertrend FLIPS to buy while close is above the DEMA -> long.
               Supertrend flips to sell while close is below the DEMA -> short.
    Tip 1:     Supertrend already says buy, and close crosses UP through the DEMA -> long.
               Mirror for shorts.
    Tip 2 (the Fibonacci band exit) is applied by the bot while a trade is open."""
    closes = [c[4] for c in candles]
    d = dema(closes)
    trend, line = supertrend(candles)
    bu, bl = fib_bands(candles)
    out = []
    for i in range(len(candles)):
        row = {"t": candles[i][0], "close": closes[i], "dema": d[i],
               "trend": trend[i], "line": line[i], "bu": bu[i], "bl": bl[i],
               "entry": None, "flip": None}
        if i > 0 and trend[i] is not None and trend[i - 1] is not None:
            if trend[i] != trend[i - 1]:
                row["flip"] = "up" if trend[i] == 1 else "down"
            if i >= DEMA_LEN:
                above, below = closes[i] > d[i], closes[i] < d[i]
                crossed_up = closes[i - 1] <= d[i - 1] and above
                crossed_dn = closes[i - 1] >= d[i - 1] and below
                if trend[i] == 1 and above and (row["flip"] == "up" or (use_dema_cross_tip and crossed_up)):
                    row["entry"] = "long"
                elif trend[i] == -1 and below and (row["flip"] == "down" or (use_dema_cross_tip and crossed_dn)):
                    row["entry"] = "short"
        out.append(row)
    return out
