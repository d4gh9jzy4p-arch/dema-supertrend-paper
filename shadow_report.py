"""Builds docs/v2/index.html, the results page for the v2 shadow account (see shadow.py),
and adds a link to it on the main page. Run after report.py."""
import csv, os
import paper, report

H = paper.HERE
paper.STATE = os.path.join(H, "state_v2.json")
paper.TRADES = os.path.join(H, "trades_v2.csv")
paper.SKIPS = os.path.join(H, "skips_v2.csv")
OUT2 = os.path.join(H, "docs", "v2", "index.html")
MAIN = os.path.join(H, "docs", "index.html")
ORIG_TRADES = os.path.join(H, "trades.csv")


def side_by_side(started_ms):
    def stats(path):
        rows = report.rows(path)
        if started_ms:
            rows = [r for r in rows if report.csv_ms(r["entry_time"]) >= started_ms]
        n = len(rows)
        rs = [float(r["r_multiple"]) for r in rows]
        tot = sum(float(r["pnl_pct"]) for r in rows)
        wins = sum(1 for r in rows if float(r["pnl_pct"]) > 0)
        return n, (sum(rs) / n if n else 0.0), tot, wins
    a, b = stats(ORIG_TRADES), stats(paper.TRADES)
    row = lambda name, s: (f"<tr><td><b>{name}</b></td><td>{s[0]}</td><td>{(str(round(100 * s[3] / s[0])) + '%') if s[0] else '-'}</td>"
                           f"<td>{s[1]:+.2f}R</td><td>{s[2]:+.2f}%</td></tr>")
    return ("<h2>Side by side since this page started</h2><div class='scroll'><table>"
            "<tr><th>Account</th><th>Closed trades</th><th>Winners</th><th>Average per trade</th><th>Total result</th></tr>"
            + row("Original rules", a) + row("v2 rules", b) + "</table></div>"
            "<p class='muted'>Only trades opened after the v2 account started are counted for the original rules, so the comparison is fair. "
            "A few trades prove nothing. Judge it after 50 or more trades each.</p>")


def main():
    report.OUT = OUT2
    report.CHARTS = os.path.join(H, "chart_data_v2.json")
    report.build()
    st = paper.load_state()
    page = open(OUT2).read()
    page = page.replace("<title>Paper Trading Bot</title>", "<title>Paper Trading Bot: v2 shadow</title>")
    page = page.replace("<h1>Paper Trading Bot</h1>", "<h1>Paper Trading Bot: v2 shadow account</h1>", 1)
    page = page.replace('<div class="banner"><b>Pretend money.</b>',
                        '<div class="banner"><b>This is the v2 test account.</b> It trades the same coins at the same time as the '
                        '<a href="../">original account</a>, but with three changes: no tip 1 entry, no tip 2 band exit, and setups '
                        'with a stop closer than 2% to the price are ignored.<br><br><b>Pretend money.</b>', 1)
    page = page.replace("<li><b>Tip 1:</b> if Supertrend already points the right way and the price then crosses the DEMA line, enter then.</li>",
                        "<li><b>Tip 1: OFF</b> in this account.</li>")
    page = page.replace("Tip 2 (exit at the outer Fibonacci Bollinger Band) was used until Nov 5, 2026 and is now OFF: it closed trades right after they opened.", "Tip 2 (the band exit) is OFF in this account.")
    page = page.replace(" Tip 2 (band exit) has been off since Nov 5, 2026; earlier trades that closed at the band are still listed.", "")
    page = page.replace("<li>Fee assumed:", "<li>A setup is ignored if the stop is closer than 2% to the price (fees eat small stops).</li><li>Fee assumed:", 1)
    page = page.replace("<h2>Account over time</h2>", side_by_side(st.get("started")) + "<h2>Account over time</h2>", 1)
    open(OUT2, "w").write(page)

    main_page = open(MAIN).read()
    if "v2/" not in main_page:
        link = ('<div class="banner">Testing a second set of rules on the side: <a href="v2/">see the v2 test account</a>. '
                'This page is still the original rules.</div>')
        main_page = main_page.replace('<div class="banner"><b>Pretend money.</b>', link + '<div class="banner"><b>Pretend money.</b>', 1)
        open(MAIN, "w").write(main_page)


if __name__ == "__main__":
    main()
