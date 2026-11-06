"""Builds docs/2h/index.html, the results page for the 2 hour test account (see shadow2h.py),
and adds a link to it on the main page. Run after report.py."""
import os, re
import paper, report

H = paper.HERE
paper.STATE = os.path.join(H, "state_2h.json")
paper.TRADES = os.path.join(H, "trades_2h.csv")
paper.SKIPS = os.path.join(H, "skips_2h.csv")
paper.MIN_STOP_GAP = 0.015
paper.RISK_PER_TRADE = 0.01
paper.MAX_TOTAL_RISK = 0.06
OUT2 = os.path.join(H, "docs", "2h", "index.html")
MAIN = os.path.join(H, "docs", "index.html")
ACCOUNTS = [("Original rules (15 minute)", os.path.join(H, "trades.csv")),
            ("v2 test (15 minute)", os.path.join(H, "trades_v2.csv")),
            ("2 hour test", os.path.join(H, "trades_2h.csv"))]


def compare(started_ms):
    def stats(path):
        rows = report.rows(path)
        if started_ms:
            rows = [r for r in rows if report.csv_ms(r["entry_time"]) >= started_ms]
        n = len(rows)
        rs = [float(r["r_multiple"]) for r in rows]
        wins = sum(1 for r in rows if float(r["pnl_pct"]) > 0)
        return n, (sum(rs) / n if n else 0.0), sum(rs), wins
    body = ""
    for name, path in ACCOUNTS:
        n, a, tot, w = stats(path)
        body += (f"<tr><td><b>{name}</b></td><td>{n}</td><td>{(str(round(100 * w / n)) + '%') if n else '-'}</td>"
                 f"<td>{a:+.2f}R</td><td>{tot:+.1f}R</td></tr>")
    return ("<h2>All three accounts side by side</h2><div class='scroll'><table>"
            "<tr><th>Account</th><th>Closed trades</th><th>Winners</th><th>Average per trade</th><th>Total</th></tr>"
            + body + "</table></div>"
            "<p class='muted'>Counted from the moment this 2 hour account started. R means one stop-loss worth of money, so the accounts "
            "compare fairly even though they risk different amounts per trade. A few trades prove nothing. Judge it after 50 or more trades each, "
            "and expect the 2 hour account to trade much less often.</p>")


def main():
    report.OUT = OUT2
    report.CHARTS = os.path.join(H, "chart_data_2h.json")
    report.load_charts = lambda trades: {}          # the trade pictures are 15 minute charts, so skip them here
    report.trade_cards = lambda *a, **k: ""
    report.build()
    st = paper.load_state()
    page = open(OUT2).read()
    page = re.sub(r"<details><summary>Trade pictures.*?</details>", "", page, flags=re.S)
    page = re.sub(r"<li>History:.*?</li>", "", page, flags=re.S)
    page = page.replace("<title>Paper Trading Bot</title>", "<title>Paper Trading Bot: 2 hour test</title>")
    page = page.replace("<h1>Paper Trading Bot</h1>", "<h1>Paper Trading Bot: 2 hour test account</h1>", 1)
    page = page.replace("DEMA 200 + Supertrend (12, 3) + Fibonacci Bollinger Bands, 15 minute candles,",
                        "DEMA 200 + Supertrend (12, 3), 2 hour candles,", 1)
    page = page.replace('<div class="banner"><b>Pretend money.</b>',
                        '<div class="banner"><b>This is the 2 hour test account.</b> It trades the same coins as the '
                        '<a href="../">original account</a>, but on 2 hour candles, with no tip 1, no band exit, no setups whose stop is '
                        'closer than 1.5% to the price, and half the risk (1% per trade, 6% open at once). A big backtest liked this version best, '
                        'but the edge was small and could be luck, so this account is the live test.<br><br><b>Pretend money.</b>', 1)
    page = page.replace("after every 15 minute candle closes", "after every 2 hour candle closes")
    page = page.replace("<li><b>Tip 1:</b> if Supertrend already points the right way and the price then crosses the DEMA line, enter then.</li>",
                        "<li><b>Tip 1: OFF</b> in this account.</li>")
    page = re.sub(r"Leave when Supertrend flips\..*?</li>", "Leave when Supertrend flips. The Fibonacci band exit is OFF in this account.</li>", page, count=1, flags=re.S)
    page = page.replace("<li>Fee assumed:", "<li>A setup is ignored if the stop is closer than 1.5% to the price (fees eat small stops).</li><li>Fee assumed:", 1)
    page = page.replace("<h2>Account over time</h2>", compare(st.get("started")) + "<h2>Account over time</h2>", 1)
    page = page.replace("BTC and DOGE, 24 hours a day.", "10 big coins, 24 hours a day.")
    page = page.replace("<li>Coins: BTC and DOGE.", "<li>Coins: BTC, ETH, SOL, XRP, DOGE, ADA, LTC, LINK, AVAX, NEAR.")
    open(OUT2, "w").write(page)

    main_page = open(MAIN).read()
    if "2h/" not in main_page:
        link = ('<div class="banner">Another test on the side: <a href="2h/">the 2 hour test account</a> (slower chart, half the risk).</div>')
        main_page = main_page.replace('<div class="banner"><b>Pretend money.</b>', link + '<div class="banner"><b>Pretend money.</b>', 1)
        open(MAIN, "w").write(main_page)


if __name__ == "__main__":
    main()
