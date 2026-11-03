"""Builds docs/index.html (the results page) from state.json, trades.csv and skips.csv.

Times are shown in Toronto time with AM/PM (EST in winter, EDT in summer).
Each closed trade gets a small 15 minute chart. The candles are fetched once from Binance's free
public feed and cached in chart_data.json, so the bot itself does not need to change.
"""
import csv, html, json, os, time, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import paper

OUT = os.path.join(paper.HERE, "docs", "index.html")
CHARTS = os.path.join(paper.HERE, "chart_data.json")
TZ = ZoneInfo("America/Toronto")
KL = "https://data-api.binance.vision/api/v3/klines?symbol={}&interval=15m&limit=1000&startTime={}&endTime={}"
M = 900_000          # one 15 minute candle in milliseconds
MAX_CHARTS = 40      # pictures kept for the latest trades
e = html.escape

CSS = """
:root{--bg:#fafaf7;--card:#fff;--ink:#1b1d1f;--muted:#6b7075;--line:#e4e4de;--up:#12805c;--down:#c03a2b;--accent:#2f5bd8}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111315;--card:#1a1d20;--ink:#ecece8;--muted:#9aa0a6;--line:#2c3034;--up:#3ec597;--down:#ef7a6b;--accent:#8aa7ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:900px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.05rem;margin:32px 0 8px}
.muted{color:var(--muted);font-size:.9rem;margin:6px 0}
.banner{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:14px 0;font-size:.92rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.card span{display:block;color:var(--muted);font-size:.8rem}.card b{font-size:1.4rem}
.up{color:var(--up)}.down{color:var(--down)}.b{font-weight:700}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:.78rem}tr:last-child td{border-bottom:0}
.curve{width:100%;height:auto;display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;touch-action:pan-y;cursor:crosshair}
.curve .line{stroke:var(--accent);stroke-width:2}.curve .base{stroke:var(--muted);stroke-dasharray:5 4;stroke-width:1}
.curve .cross{stroke:var(--ink);stroke-width:1;opacity:.55}.curve .dot{fill:var(--accent);stroke:var(--card);stroke-width:2}
.tip{min-height:2.6em;font-size:.92rem;margin:8px 0 0}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin-top:10px}summary{cursor:pointer;font-weight:600}
li{margin:4px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:12px;margin-top:12px}
.tc{border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--bg)}
.th{font-size:.95rem}.ts{color:var(--muted);font-size:.78rem;margin:2px 0 6px}
.mini{width:100%;height:auto;display:block}
.mini .cu{fill:var(--up);stroke:var(--up)}.mini .cd{fill:var(--down);stroke:var(--down)}
.mini .sl{stroke:var(--down);stroke-dasharray:4 3;stroke-width:1.3}.mini .ent{stroke:var(--accent);stroke-dasharray:2 3;stroke-width:1}
.mini .shade{fill:var(--accent);opacity:.08}.mini text{fill:var(--ink);font-size:9px}.mini .tl{fill:var(--down)}.mini .ta{fill:var(--accent)}
.mini .mk{fill:var(--accent);stroke:var(--card);stroke-width:1.5}.mini .xk{fill:var(--ink);stroke:var(--card);stroke-width:1.5}
.cap{color:var(--muted);font-size:.74rem;margin:4px 0 0}
"""

SCRIPT = """
(function(){
  var box=document.getElementById('eqbox'); if(!box) return;
  var svg=box.querySelector('svg'), cross=svg.querySelector('.cross'), dot=svg.querySelector('.dot'), tip=box.querySelector('.tip');
  var pts=JSON.parse(box.getAttribute('data-pts')), W=parseFloat(box.getAttribute('data-w'));
  function show(ev){
    var r=svg.getBoundingClientRect(), cx=(ev.clientX-r.left)/r.width*W, best=0, bd=1e9;
    for(var i=0;i<pts.length;i++){var d=Math.abs(pts[i][0]-cx); if(d<bd){bd=d;best=i;}}
    var p=pts[best];
    cross.setAttribute('x1',p[0]); cross.setAttribute('x2',p[0]); cross.style.display='';
    dot.setAttribute('cx',p[0]); dot.setAttribute('cy',p[1]); dot.style.display='';
    tip.textContent=p[2];
  }
  svg.addEventListener('pointermove',show); svg.addEventListener('pointerdown',show);
  svg.addEventListener('pointerleave',function(ev){ if(ev.pointerType==='mouse'){cross.style.display='none';dot.style.display='none';tip.textContent=tip.getAttribute('data-hint');} });
})();
"""


def rows(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def pct(x, plus=True):
    return f"{x:+.2f}%" if plus else f"{x:.2f}%"


def cls(x):
    return "up" if x > 0 else "down" if x < 0 else ""


def et(dt):
    """Toronto time with AM/PM and the zone name, e.g. Nov 2, 12:30 PM EST."""
    d = dt.astimezone(TZ)
    return f"{d:%b} {d.day}, {d.hour % 12 or 12}:{d:%M} {'AM' if d.hour < 12 else 'PM'} {d:%Z}"


def when(ms):
    return et(datetime.fromtimestamp(ms / 1000, timezone.utc))


def csv_ms(s):
    """trades.csv stores times like 2026-11-02 17:30Z (UTC). Returns milliseconds."""
    return int(datetime.strptime(s, "%Y-%m-%d %H:%MZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


def when_csv(s):
    return when(csv_ms(s))


def curve(points, labels, w=720, h=180):
    if len(points) < 2:
        return "<p class='muted'>The line appears after the first closed trade.</p>"
    lo, hi = min(points), max(points)
    lo, hi = min(lo, 100.0), max(hi, 100.0)
    pad = (hi - lo) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    y = lambda v: 8 + (hi - v) / (hi - lo) * (h - 16)
    x = lambda i: 8 + i / (len(points) - 1) * (w - 16)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(points))
    data = json.dumps([[round(x(i), 1), round(y(v), 1), labels[i]] for i, v in enumerate(points)])
    hint = "Move your mouse or slide your finger along the line to see the account at that point."
    return (f"<div id='eqbox' data-w='{w}' data-pts='{e(data, quote=True)}'>"
            f"<svg viewBox='0 0 {w} {h}' class='curve' role='img' aria-label='Account value after each closed trade'>"
            f"<line x1='8' x2='{w - 8}' y1='{y(100):.1f}' y2='{y(100):.1f}' class='base'/>"
            f"<polyline points='{pts}' class='line' fill='none'/>"
            f"<line class='cross' x1='0' x2='0' y1='0' y2='{h}' style='display:none'/>"
            f"<circle class='dot' r='5' cx='0' cy='0' style='display:none'/></svg>"
            f"<p class='tip' data-hint='{e(hint, quote=True)}'>{e(hint)}</p></div>"
            f"<p class='muted'>Account value after each closed trade. The dashed line is where it started (100).</p>")


def table(head, body, empty):
    if not body:
        return f"<p class='muted'>{e(empty)}</p>"
    th = "".join(f"<th>{e(c)}</th>" for c in head)
    tr = "".join("<tr>" + "".join(f"<td{(' class=%s' % c) if c else ''}>{v}</td>" for v, c in r) + "</tr>" for r in body)
    return f"<div class='scroll'><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>"


# ---------- little 15 minute pictures of each trade ----------

def fetch_klines(sym, start_ms, end_ms):
    rows_ = json.load(urllib.request.urlopen(KL.format(sym, start_ms, end_ms), timeout=20))
    return [[r[0], round(float(r[1]), 8), round(float(r[2]), 8), round(float(r[3]), 8), round(float(r[4]), 8)] for r in rows_]


def chart_key(t):
    return f"{t['symbol']}|{t['entry_time']}|{t['exit_time']}"


def load_charts(trades):
    """Return {key: candles} for the latest MAX_CHARTS trades, fetching any that are missing."""
    cache = {}
    if os.path.exists(CHARTS):
        try:
            cache = json.load(open(CHARTS))
        except ValueError:
            cache = {}
    keep = {}
    for t in trades[-MAX_CHARTS:]:
        k = chart_key(t)
        if k in cache:
            keep[k] = cache[k]
            continue
        try:
            a, b = csv_ms(t["entry_time"]), csv_ms(t["exit_time"])
            start = a - 16 * M
            end = min(b + 4 * M, start + 220 * M)
            keep[k] = fetch_klines(t["symbol"], start, end)
            time.sleep(0.2)
        except Exception as ex:
            print("chart fetch failed for", k, ex)
    if keep != cache:
        json.dump(keep, open(CHARTS, "w"), separators=(",", ":"))
    return keep


def mini_chart(t, candles, w=360, h=190):
    if len(candles) < 3:
        return "<p class='muted'>Chart not available yet.</p>"
    ep, xp, sl = float(t["entry_price"]), float(t["exit_price"]), float(t["stop"])
    a, b = csv_ms(t["entry_time"]), csv_ms(t["exit_time"])
    lo = min(min(c[3] for c in candles), sl, ep, xp)
    hi = max(max(c[2] for c in candles), sl, ep, xp)
    pad = (hi - lo) * 0.08 or 1e-9
    lo, hi = lo - pad, hi + pad
    left, right, top, bot = 6, 64, 8, h - 8
    n = len(candles)
    step = (w - left - right) / n
    bw = max(1.2, step * 0.6)
    y = lambda p: top + (hi - p) / (hi - lo) * (bot - top)
    cx = lambda i: left + i * step + step / 2
    ia = next((i for i, c in enumerate(candles) if c[0] >= a), 0)
    ib = next((i for i, c in enumerate(candles) if c[0] >= b), n - 1)
    s = f"<svg viewBox='0 0 {w} {h}' class='mini' role='img' aria-label='15 minute chart of the trade'>"
    s += f"<rect class='shade' x='{cx(ia):.1f}' y='{top}' width='{max(2, cx(ib) - cx(ia)):.1f}' height='{bot - top}'/>"
    for i, (_, o, hh, ll, c) in enumerate(candles):
        k = "cu" if c >= o else "cd"
        s += f"<line class='{k}' x1='{cx(i):.1f}' x2='{cx(i):.1f}' y1='{y(hh):.1f}' y2='{y(ll):.1f}' stroke-width='1'/>"
        s += f"<rect class='{k}' x='{cx(i) - bw / 2:.1f}' y='{y(max(o, c)):.1f}' width='{bw:.1f}' height='{max(1.2, abs(y(o) - y(c))):.1f}'/>"
    xr = w - right + 3
    s += f"<line class='sl' x1='{left}' x2='{w - right}' y1='{y(sl):.1f}' y2='{y(sl):.1f}'/>"
    s += f"<line class='ent' x1='{left}' x2='{w - right}' y1='{y(ep):.1f}' y2='{y(ep):.1f}'/>"
    s += f"<circle class='mk' cx='{cx(ia):.1f}' cy='{y(ep):.1f}' r='4.5'/>"
    s += f"<rect class='xk' x='{cx(ib) - 4:.1f}' y='{y(xp) - 4:.1f}' width='8' height='8' transform='rotate(45 {cx(ib):.1f} {y(xp):.1f})'/>"
    # price labels on the right, nudged apart so they never sit on top of each other
    labels = sorted([[y(sl), "tl", f"SL {sl:.6g}"], [y(ep), "ta", f"In {ep:.6g}"], [y(xp), "", f"Out {xp:.6g}"]])
    for i in range(1, 3):
        if labels[i][0] - labels[i - 1][0] < 11:
            labels[i][0] = labels[i - 1][0] + 11
    for ly, k, txt in labels:
        s += f"<text class='{k}' x='{xr}' y='{ly + 3:.1f}'>{txt}</text>"
    return s + "</svg>"


def trade_cards(trades, charts):
    out = []
    for t in reversed(trades[-MAX_CHARTS:]):
        v = float(t["pnl_pct"])
        why = e(t["reason"])
        svg = mini_chart(t, charts.get(chart_key(t), []))
        out.append(
            f"<div class='tc'><div class='th'><b>{e(t['symbol'].replace('USDT', ''))}</b> {e(t['side'])} "
            f"<span class='{cls(v)}'>{pct(v)} ({t['r_multiple']}R)</span></div>"
            f"<div class='ts'>In {e(when_csv(t['entry_time']))}. Out {e(when_csv(t['exit_time']))}. Ended by: {why}.</div>"
            f"{svg}<p class='cap'>Circle = entry. Diamond = exit. Red dashed = stop loss (SL). Blue band = how long the trade was open. "
            f"No take profit price: the bot stays in until the exit.</p></div>")
    return "".join(out)


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
        unreal = d * (last - p["entry_price"]) * p["qty"]
        size = 100 * p["qty"] * p["entry_price"] / st["equity"]
        open_rows.append([(e(sym.replace("USDT", "")), "b"), (p["side"], ""), (e(when(p["entry_time"])), ""),
                          (f"{p['entry_price']:.6g}", ""), (f"{last:.6g}", ""), (f"{p['stop']:.6g}", ""),
                          (f"{size:.0f}%", ""), (pct(unreal), cls(unreal))])
    closed_rows = []
    for t in reversed(trades[-200:]):
        v = float(t["pnl_pct"])
        closed_rows.append([(e(t["symbol"].replace("USDT", "")), "b"), (t["side"], ""), (e(when_csv(t["entry_time"])), ""),
                            (e(when_csv(t["exit_time"])), ""), (e(t["reason"]), ""),
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
    labels = [f"Start: account {st['start_equity']:.2f}"] + [
        f"After trade {i}: {t['symbol'].replace('USDT', '')} {t['side']} closed {when_csv(t['exit_time'])}, "
        f"{pct(float(t['pnl_pct']))}. Account {float(t['equity_after']):.2f}"
        for i, t in enumerate(trades, 1)]
    win_rate = f"{100 * len(wins) / n:.0f}%" if n else "none yet"
    avg_r = f"{sum(rs) / n:+.2f}R" if n else "none yet"
    best = pct(max(pnl)) if n else "none yet"
    worst = pct(min(pnl)) if n else "none yet"

    charts = load_charts(trades) if n else {}
    shown = min(n, MAX_CHARTS)
    folder = (f"<details><summary>Trade pictures: 15 minute charts of the latest {shown} trades</summary>"
              f"<div class='cards'>{trade_cards(trades, charts)}</div></details>") if n else ""

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper Trading Bot</title>
<style>{CSS}</style></head><body><main>
<h1>Paper Trading Bot</h1>
<p class="muted">DEMA 200 + Supertrend (12, 3) + Fibonacci Bollinger Bands, 15 minute candles, 10 big coins, 24 hours a day.</p>
<div class="banner"><b>Pretend money.</b> Nothing here is a real trade and nothing here is financial advice. The account is shown in percent and starts at 100.
Results come from real prices, but the bot enters at each candle's closing price, so real life would be a little worse. All times are Toronto time (EST or EDT).</div>

<div class="grid">
<div class="card"><span>Account value (start 100)</span><b class="{cls(ret)}">{acct:.2f}</b></div>
<div class="card"><span>Total result</span><b class="{cls(ret)}">{pct(ret)}</b></div>
<div class="card"><span>Today</span><b class="{cls(today)}">{pct(today)}</b></div>
<div class="card"><span>Status</span><b style="font-size:1rem">{e(status)}</b></div>
</div>
<p class="muted">Started {e(started)}. Last check {e(last_run)}. Updates about every 15 minutes.</p>

<h2>Account over time</h2>
{curve(equity_pts, labels)}
{folder}

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
</main><script>{SCRIPT}</script></body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(page)
    return OUT


if __name__ == "__main__":
    print("wrote", build())
