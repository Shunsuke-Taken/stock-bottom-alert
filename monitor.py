import os
import json
import datetime as dt
import pandas as pd
import yfinance as yf

from line_push import line_push
from render_dashboard import render

ZONES_CSV = os.getenv("ZONES_CSV", "zones.csv")
STATE_PATH = os.getenv("STATE_PATH", ".state/state.json")
NEAR_PCT = float(os.getenv("NEAR_PCT", "5"))

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_sent": None}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

def sent_today(state):
    return state.get("last_sent") == dt.date.today().isoformat()

def mark_sent_today(state):
    state["last_sent"] = dt.date.today().isoformat()
    return state

def classify(price, low, high):
    if price is None:
        return "—"
    if low <= price <= high:
        return "IN_ZONE"
    if price > high and (price / high - 1.0) * 100.0 <= NEAR_PCT:
        return "NEAR"
    return "—"

def fetch_last_prices(tickers):
    df = yf.download(
        tickers=tickers,
        period="7d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    last = {}
    for t in tickers:
        try:
            last[t] = float(df[t]["Close"].dropna().iloc[-1])
        except Exception:
            last[t] = None
    return last

def build_message(hits: pd.DataFrame, pages_url: str) -> str:
    lines = []

    inz = hits[hits["Status"] == "IN_ZONE"]
    nr = hits[hits["Status"] == "NEAR"]

    if not inz.empty:
        lines.append("✅【底値目安ゾーン突入】")
        for _, r in inz.iterrows():
            lines.append(f"- {r['Name']}({r['Ticker']}): {r['LastPrice']:.2f} 目安 {r['ZoneLow']}-{r['ZoneHigh']}")
        lines.append("")

    if not nr.empty:
        lines.append(f"👀【ゾーン接近（上限+{NEAR_PCT:.0f}%以内）】")
        for _, r in nr.iterrows():
            lines.append(f"- {r['Name']}({r['Ticker']}): {r['LastPrice']:.2f} 目安 {r['ZoneLow']}-{r['ZoneHigh']}")
        lines.append("")

    lines.append(f"🔗 一覧（全銘柄＋チャート）: {pages_url}")
    lines.append("※今日はこの1回だけ通知（該当時のみ）")
    return "\n".join(lines).strip()

def main():
    state = load_state()
    if sent_today(state):
        print("Already sent today. Skip.")
        return

    zones = pd.read_csv(ZONES_CSV)
    zones["Ticker"] = zones["Ticker"].astype(str).str.upper()

    tickers = zones["Ticker"].dropna().unique().tolist()
    if not tickers:
        print("No tickers in zones.csv")
        return

    prices = fetch_last_prices(tickers)

    zones["LastPrice"] = zones["Ticker"].map(prices)
    zones["Status"] = zones.apply(
        lambda r: classify(r["LastPrice"], float(r["ZoneLow"]), float(r["ZoneHigh"])),
        axis=1,
    )

    # Pages用HTMLを常に更新（全銘柄）
    render(
        zones[["Ticker", "Name", "ZoneLow", "ZoneHigh", "LastPrice", "Status"]],
        "docs/index.html",
    )

    hits = zones[zones["Status"].isin(["IN_ZONE", "NEAR"])].copy()
    if hits.empty:
        print("No hits today. No message sent.")
        return

    repo = os.getenv("GITHUB_REPOSITORY", "")
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        pages_url = f"https://{owner}.github.io/{name}/"
    else:
        pages_url = "(Pages URL not available)"

    msg = build_message(hits, pages_url)
    line_push(msg)

    save_state(mark_sent_today(state))
    print("Sent alert and updated state.")

if __name__ == "__main__":
    main()
