"""Builds docs/index.html (the results page) from state.json, trades.csv and skips.csv."""
import csv, html, json, os, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import paper

OUT = os.path.join(paper.HERE, "docs", "index.html")
TZ = ZoneInfo("America/Toronto")
e = html.escape


def rows(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def pct(x, plus=True):
    return f"{x:+.2f}%" if plus else f"{x:.2f}%"


def cls(x):
    return "up" if x > 0 else "down" if x < 0 else ""


def when(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(TZ).strftime("%b %d, %I:%M %p").replace(" 0", " ")


def curve(points, w=720, h=180):
    if len(points) < 2:
        return "<p class='muted'>The line appears after the first closed trade.</p>"
    lo, hi = min(points), max(points)
    lo, hi = min(lo, 100.0), max(hi, 100.0)
    pad = (hi - lo) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    y = lambda v: 8 + (hi - v) / (hi - lo) * (h - 16)
    x = lambda i: 8 + i / (len(points) - 1) * (w - 16)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(points))
    return (f"<svg viewBox='0 0 {w} {h}' class='curve' role='img' aria-label='Account value after each closed trade'>"
            f"<line x1='8' x2='{w - 8}' y1='{y(100):.1f}' y2='{y(100):.1f}' class='base'/>"
            f"<polyline points='{pts}' class='line' fill='none'/></svg>"
            f"<p class='muted'>Account value after each closed trade. The dashed line is where it started (100).</p>")


def table(head, body, empty):
    if not body:
        return f"<p class='muted'>{e(empty)}</p>"
    th = "".join(f"<th>{e(c)}</th>" for c in head)
    tr = "".join("<tr>" + "".join(f"<td{(' class=%s' % c) if c else ''}>{v}</td>" for v, c in r) + "</tr>" for r in body)
    return f"<div class='scroll'><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>"


def build():
    st = paper.load_state()
    trades, skips = rows(paper.TRADES), rows(paper.SKIPS)
    br = paper.Paper(st)
    acct = br.marked_equity()
    ret = acct - st["start_equity"]
    day_start = st.get("day_start_equity") or acct
    today = (acct / day_start - 1) * 100 if day_start else 0

    n = len(trades)
    pnl = [float(t["pnl_pct"]) for t in trades]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    rs = [float(t["r_multiple"]) for t in trades]

    def group(key):
        out = {}
        for t in trades:
            g = out.setdefault(t[key], [0, 0, 0.0])
            g[0] += 1
            g[1] += 1 if float(t["pnl_pct"]) > 0 else 0
            g[2] += float(t["pnl_pct"])
        return out

    def group_table(key, label):
        g = group(key)
        body = [[(e(k), ""), (str(v[0]), ""), (f"{100 * v[1] / v[0]:.0f}%", ""), (pct(v[2]), cls(v[2]))]
                for k, v in sorted(g.items())]
        return table([label, "Trades", "Winners", "Total result"], body, "No closed trades yet.")

    open_rows = []
    for sym, p in br.positions():
        last = st["symbols"][sym].get("last_close") or p["entry_price"]
        d = 1 if p["side"] == "long" else -1
        move = d * (last / p["entry_price"] - 1) * 100
        unreal = d * (last - p["entry_price"]) * p["qty"]
        size = 100 * p["qty"] * p["entry_price"] / st["equity"]
        open_rows.append([(e(sym.replace("USDT", "")), "b"), (p["side"], ""), (when(p["entry_time"]), ""),
                          (f"{p['entry_price']:.6g}", ""), (f"{last:.6g}", ""), (f"{p['stop']:.6g}", ""),
                          (f"{size:.0f}%", ""), (pct(unreal), cls(unreal))])
    closed_rows = []
    for t in reversed(trades[-200:]):
        v = float(t["pnl_pct"])
        closed_rows.append([(e(t["symbol"].replace("USDT", "")), "b"), (t["side"], ""), (e(t["entry_time"]), ""),
                            (e(t["exit_time"]), ""), (e(t["reason"]), ""),
                            (t["r_multiple"] + "R", cls(v)), (pct(v), cls(v))])
    skip_n = len(skips)
    skip_why = {}
    for s in skips:
        skip_why[s["reason"]] = skip_why.get(s["reason"], 0) + 1
    skip_body = [[(e(k), ""), (str(v), "")] for k, v in sorted(skip_why.items(), key=lambda kv: -kv[1])]

    status = "Stopped for today (6% daily loss limit hit)" if st.get("halted") else "Trading"
    last_run = when(st["last_run"]) if st.get("last_run") else "not yet"
    started = when(st["started"]) if st.get("started") else "not yet"
    equity_pts = [st["start_equity"]] + [float(t["equity_after"]) for t in trades]
    win_rate = f"{100 * len(wins) / n:.0f}%" if n else "none yet"
    avg_r = f"{sum(rs) / n:+.2f}R" if n else "none yet"
    best = pct(max(pnl)) if n else "none yet"
    worst = pct(min(pnl)) if n else "none yet"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper Trading Bot</title>
<style>
:root{{--bg:#fafaf7;--card:#fff;--ink:#1b1d1f;--muted:#6b7075;--line:#e4e4de;--up:#12805c;--down:#c03a2b;--accent:#2f5bd8}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#111315;--card:#1a1d20;--ink:#ecece8;--muted:#9aa0a6;--line:#2c3034;--up:#3ec597;--down:#ef7a6b;--accent:#8aa7ff}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:900px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:1.5rem;margin:0 0 4px}}h2{{font-size:1.05rem;margin:32px 0 8px}}
.muted{{color:var(--muted);font-size:.9rem;margin:6px 0}}
.banner{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:14px 0;font-size:.92rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}}
.card span{{display:block;color:var(--muted);font-size:.8rem}}.card b{{font-size:1.4rem}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.b{{font-weight:700}}
.scroll{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}}
table{{border-collapse:collapse;width:100%;font-size:.88rem}}th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}
th{{color:var(--muted);font-weight:600;font-size:.78rem}}tr:last-child td{{border-bottom:0}}
.curve{{width:100%;height:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}}
.curve .line{{stroke:var(--accent);stroke-width:2}}.curve .base{{stroke:var(--muted);stroke-dasharray:5 4;stroke-width:1}}
details{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin-top:10px}}summary{{cursor:pointer;font-weight:600}}
li{{margin:4px 0}}
</style></head><body><main>
<h1>Paper Trading Bot</h1>
<p class="muted">DEMA 200 + Supertrend (12, 3) + Fibonacci Bollinger Bands, 15 minute candles, 10 big coins, 24 hours a day.</p>
<div class="banner"><b>Pretend money.</b> Nothing here is a real trade and nothing here is financial advice. The account is shown in percent and starts at 100.
Results come from real prices, but the bot enters at each candle's closing price, so real life would be a little worse.</div>

<div class="grid">
<div class="card"><span>Account value (start 100)</span><b class="{cls(ret)}">{acct:.2f}</b></div>
<div class="card"><span>Total result</span><b class="{cls(ret)}">{pct(ret)}</b></div>
<div class="card"><span>Today</span><b class="{cls(today)}">{pct(today)}</b></div>
<div class="card"><span>Status</span><b style="font-size:1rem">{e(status)}</b></div>
</div>
<p class="muted">Started {e(started)} Toronto time. Last check {e(last_run)}. Updates about every 15 minutes.</p>

<h2>Account over time</h2>
{curve(equity_pts)}

<h2>Open trades right now</h2>
{table(["Coin", "Side", "Opened", "Entry", "Now", "Stop", "Size", "Result so far"], open_rows, "No open trades. The bot is waiting for a setup that matches every rule.")}
<p class="muted">Size is how much of the account the trade holds. Result so far is in percent of the account and does not include fees yet.</p>

<h2>The numbers</h2>
<div class="grid">
<div class="card"><span>Closed trades</span><b>{n}</b></div>
<div class="card"><span>Winners</span><b>{win_rate}</b></div>
<div class="card"><span>Average result per trade</span><b>{avg_r}</b></div>
<div class="card"><span>Best / worst trade</span><b style="font-size:1rem">{best} / {worst}</b></div>
<div class="card"><span>Daily loss limit hit</span><b>{st.get("halt_count", 0)} times</b></div>
<div class="card"><span>Valid setups skipped</span><b>{skip_n}</b></div>
</div>
<p class="muted">1R means one full stop-loss worth of money (1.5% of the account). A +3R trade made three times what it risked.</p>

<h2>Long trades against short trades</h2>
{group_table("side", "Side")}
<p class="muted">Regular Canadian crypto accounts can only buy, not short. The long line is what you could have done with a normal account.</p>

<h2>How trades ended</h2>
{group_table("reason", "Exit reason")}

<h2>Closed trades (newest first)</h2>
{table(["Coin", "Side", "Opened", "Closed", "Why it closed", "Result in R", "Result"], closed_rows, "No closed trades yet.")}
<p class="muted">Result includes the 0.25% fee on the buy and the sell.</p>

<h2>Valid setups the bot could not take</h2>
{table(["Reason", "Times"], skip_body, "None so far.")}

<details><summary>The rules the bot follows</summary>
<ul>
<li>Looks at every coin after every 15 minute candle closes, all day and night.</li>
<li><b>Buy:</b> the Supertrend turns to a buy signal while the price is above the DEMA 200 line. Wait for the candle to close, then enter.</li>
<li><b>Short:</b> the exact opposite: Supertrend turns to sell while the price is below the DEMA.</li>
<li><b>Tip 1:</b> if Supertrend already points the right way and the price then crosses the DEMA line, enter then.</li>
<li><b>Stop loss:</b> at the Supertrend line. The trade is sized so a stop hit loses 1.5% of the account, fees included.</li>
<li><b>Exit:</b> no profit target. Leave when Supertrend flips, or at once if the price touches the outer Fibonacci Bollinger Band (tip 2).</li>
<li>At most 6% of the account is at risk across all open trades together. A full-size trade risks 1.5%, so about 4 at once. A setup that would push the total past 6% is skipped.</li>
<li>Paper borrowing is allowed (up to 10 times the account) so every valid setup can be taken. A real spot account could not borrow, so real results would be smaller.</li>
<li>Down 6% in one day (Toronto time): everything closes and the bot rests until the next day.</li>
<li>Coins: BTC, ETH, SOL, XRP, DOGE, ADA, LTC, LINK, AVAX, DOT. A coin is skipped if it traded under 5 million USDT in the last 24 hours.</li>
<li>Fee assumed: 0.25% on every buy and every sell.</li>
</ul></details>
</main></body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(page)
    return OUT


if __name__ == "__main__":
    print("wrote", build())
