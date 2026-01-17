import os
import csv
import json
import datetime as dt
from dataclasses import dataclass
from typing import Optional, List, Dict

import pandas as pd
import yfinance as yf

from line_push import push_message
from render_dashboard import render


JST = dt.timezone(dt.timedelta(hours=9))


@dataclass
class ZoneRow:
    ticker: str
    name: str
    zone_low: float
    zone_high: float


def jst_today_key() -> str:
    return dt.datetime.now(JST).strftime("%Y-%m-%d")


def load_zones(csv_path: str) -> List[ZoneRow]:
    rows: List[ZoneRow] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ticker = (r.get("Ticker") or "").strip().upper()
            name = (r.get("Name") or "").strip() or ticker
            zone_low = float((r.get("ZoneLow") or "").strip())
            zone_high = float((r.get("ZoneHigh") or "").strip())
            rows.append(ZoneRow(ticker, name, zone_low, zone_high))
    return rows


def fetch_last_price_yf(ticker: str) -> Optional[float]:
    """
    Fetch last close-ish price using yfinance.
    Uses short intraday window if possible; falls back to 1d daily.
    """
    try:
        t = yf.Ticker(ticker)

        # Try intraday first
        hist = t.history(period="1d", interval="1m")
        if hist is not None and not hist.empty:
            v = hist["Close"].iloc[-1]
            if pd.notna(v):
                return float(v)

        # Fallback: daily
        hist2 = t.history(period="5d", interval="1d")
        if hist2 is not None and not hist2.empty:
            v = hist2["Close"].iloc[-1]
            if pd.notna(v):
                return float(v)

    except Exception:
        pass
    return None


def classify(price: Optional[float], low: float, high: float, near_pct: float) -> str:
    if price is None:
        return "—"
    if low <= price <= high:
        return "IN_ZONE"

    # "NEAR" means close to the zone boundary (outside but within near_pct%)
    # If price is above high: near if within high*(1+near_pct/100)
    # If price is below low: near if within low*(1-near_pct/100)
    if price > high:
        if price <= high * (1.0 + near_pct / 100.0):
            return "NEAR"
    else:  # price < low
        if price >= low * (1.0 - near_pct / 100.0):
            return "NEAR"

    return "—"


def load_state(path: str) -> Dict:
    if not os.path.exists(path):
        return {"last_sent_day": None, "last_sent_hits": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_sent_day": None, "last_sent_hits": []}


def save_state(path: str, state: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_message(hits_df: pd.DataFrame, dashboard_url: str) -> str:
    # Make a compact message for LINE
    lines = ["📉 底値アラート（該当あり）"]
    for _, r in hits_df.iterrows():
        price = r["LastPrice"]
        price_disp = "—" if price is None or pd.isna(price) else f"{float(price):.2f}"
        lines.append(f"- {r['Name']}({r['Ticker']}): {price_disp} / {float(r['ZoneLow']):.2f}-{float(r['ZoneHigh']):.2f} [{r['Status']}]")
    lines.append("")
    lines.append(f"一覧: {dashboard_url}")
    return "\n".join(lines)


def main():
    # Inputs
    zones_csv = os.getenv("ZONES_CSV", "zones.csv")
    out_html = os.getenv("DASHBOARD_OUT", "docs/index.html")

    # Pages URL (you can set this in repo variables if you want)
    github_owner = os.getenv("GITHUB_OWNER", "Shunsuke-Taken")
    github_repo = os.getenv("GITHUB_REPO", "stock-bottom-alert")
    dashboard_url = os.getenv(
        "DASHBOARD_URL",
        f"https://{github_owner.lower()}.github.io/{github_repo}/"
    )

    # Near threshold percent (empty-safe)
    near_pct = float(os.getenv("NEAR_PCT") or "5")

    # State (for 1/day max)
    state_path = os.getenv("STATE_PATH", ".state/state.json")
    state = load_state(state_path)
    today = jst_today_key()

    zones = load_zones(zones_csv)

    # Fetch prices & evaluate
    records = []
    for z in zones:
        price = fetch_last_price_yf(z.ticker)
        status = classify(price, z.zone_low, z.zone_high, near_pct)
        records.append(
            {
                "Ticker": z.ticker,
                "Name": z.name,
                "ZoneLow": z.zone_low,
                "ZoneHigh": z.zone_high,
                "LastPrice": price,
                "Status": status,
            }
        )

    df = pd.DataFrame(records)

    # Render dashboard every run
    render(df, out_html)

    # Decide hits
    hits = df[df["Status"].isin(["IN_ZONE", "NEAR"])].copy()

    if hits.empty:
        print("No hits today. No message sent.")
        return

    # 1/day cap: if already sent today, skip
    if state.get("last_sent_day") == today:
        print("Already sent today. Skip.")
        return

    # Send LINE
    msg = build_message(hits, dashboard_url)
    push_message(msg)

    # Update state
    state["last_sent_day"] = today
    state["last_sent_hits"] = hits[["Ticker", "Status"]].to_dict(orient="records")
    save_state(state_path, state)

    print("Sent alert and updated state.")


if __name__ == "__main__":
    main()
