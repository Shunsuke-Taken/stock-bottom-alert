import os
import csv
import json
import datetime as dt
from dataclasses import dataclass
from typing import Optional, List, Dict, Set

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


def jst_day_key() -> str:
    return dt.datetime.now(JST).strftime("%Y-%m-%d")


def load_zones(csv_path: str) -> List[ZoneRow]:
    rows: List[ZoneRow] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ticker = (r.get("Ticker") or "").strip().upper()
            if not ticker:
                continue
            name = (r.get("Name") or "").strip() or ticker
            zone_low = float((r.get("ZoneLow") or "").strip())
            zone_high = float((r.get("ZoneHigh") or "").strip())
            rows.append(ZoneRow(ticker=ticker, name=name, zone_low=zone_low, zone_high=zone_high))
    return rows


def fetch_last_price_yf(ticker: str) -> Optional[float]:
    """
    Fetch last-ish price via yfinance.
    - Try intraday 1m first
    - Fallback to latest daily close
    """
    try:
        t = yf.Ticker(ticker)

        hist = t.history(period="1d", interval="1m")
        if hist is not None and not hist.empty:
            v = hist["Close"].iloc[-1]
            if pd.notna(v):
                return float(v)

        hist2 = t.history(period="10d", interval="1d")
        if hist2 is not None and not hist2.empty:
            v = hist2["Close"].iloc[-1]
            if pd.notna(v):
                return float(v)
    except Exception:
        pass
    return None


def fetch_daily_closes(ticker: str, lookback_days: int = 260) -> Optional[pd.Series]:
    """
    Fetch daily close series for lookback period (calendar days).
    Returns: Series indexed by python date -> close
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{lookback_days}d", interval="1d")
        if hist is None or hist.empty:
            return None

        closes = hist["Close"].dropna()
        if closes.empty:
            return None

        closes.index = pd.to_datetime(closes.index).date
        return closes
    except Exception:
        return None


def closest_close_before(closes: pd.Series, days_ago: int) -> Optional[float]:
    """
    Find close on (today - days_ago), or nearest prior trading day.
    """
    if closes is None or closes.empty:
        return None

    target = (dt.datetime.now(JST).date() - dt.timedelta(days=days_ago))
    candidates = [d for d in closes.index if d <= target]
    if not candidates:
        return None
    d = max(candidates)

    try:
        return float(closes.loc[d])
    except Exception:
        return None


def pct_change(current: Optional[float], past: Optional[float]) -> Optional[float]:
    if current is None or past is None:
        return None
    try:
        past = float(past)
        current = float(current)
        if past == 0:
            return None
        return (current / past - 1.0) * 100.0
    except Exception:
        return None


def classify(price: Optional[float], low: float, high: float, near_pct: float) -> str:
    """
    IN_ZONE: low <= price <= high
    NEAR: outside zone but within near_pct% of boundary
    """
    if price is None:
        return "—"

    if low <= price <= high:
        return "IN_ZONE"

    if price > high and price <= high * (1.0 + near_pct / 100.0):
        return "NEAR"

    if price < low and price >= low * (1.0 - near_pct / 100.0):
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


def save_state(path: str, state: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_dashboard_url() -> str:
    explicit = os.getenv("DASHBOARD_URL")
    if explicit:
        return explicit

    repo = os.getenv("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def build_message(hits_df: pd.DataFrame, dashboard_url: str, near_pct: float) -> str:
    def fmt_price(v):
        return "—" if v is None or pd.isna(v) else f"{float(v):.2f}"

    lines = ["📉 底値アラート（新規ヒットあり）"]

    inz = hits_df[hits_df["Status"] == "IN_ZONE"]
    nr = hits_df[hits_df["Status"] == "NEAR"]

    if not inz.empty:
        lines.append("✅ ゾーン内")
        for _, r in inz.iterrows():
            lines.append(
                f"- {r['Name']}({r['Ticker']}): {fmt_price(r['LastPrice'])} / "
                f"{float(r['ZoneLow']):.2f}-{float(r['ZoneHigh']):.2f}"
            )
        lines.append("")

    if not nr.empty:
        lines.append(f"👀 接近（±{near_pct:.0f}%以内）")
        for _, r in nr.iterrows():
            lines.append(
                f"- {r['Name']}({r['Ticker']}): {fmt_price(r['LastPrice'])} / "
                f"{float(r['ZoneLow']):.2f}-{float(r['ZoneHigh']):.2f}"
            )
        lines.append("")

    if dashboard_url:
        cache_bust = dt.datetime.now(JST).strftime("%Y%m%d%H%M")
        lines.append(f"一覧: {dashboard_url}?v={cache_bust}")

    return "\n".join(lines).strip()


def main():
    zones_csv = os.getenv("ZONES_CSV", "zones.csv")
    out_html = os.getenv("DASHBOARD_OUT", "docs/index.html")
    state_path = os.getenv("STATE_PATH", ".state/state.json")

    near_pct = float(os.getenv("NEAR_PCT") or "5")

    state = load_state(state_path)
    today = jst_day_key()

    zones = load_zones(zones_csv)
    if not zones:
        print("No tickers in zones.csv")
        return

    records = []
    for z in zones:
        price = fetch_last_price_yf(z.ticker)

        closes = fetch_daily_closes(z.ticker, lookback_days=260)
        c7 = closest_close_before(closes, 7) if closes is not None else None
        c30 = closest_close_before(closes, 30) if closes is not None else None
        c90 = closest_close_before(closes, 90) if closes is not None else None

        chg7 = pct_change(price, c7)
        chg30 = pct_change(price, c30)
        chg90 = pct_change(price, c90)

        status = classify(price, z.zone_low, z.zone_high, near_pct)

        records.append(
            {
                "Ticker": z.ticker,
                "Name": z.name,
                "ZoneLow": z.zone_low,
                "ZoneHigh": z.zone_high,
                "LastPrice": price,
                "Status": status,
                # raw closes (optional but nice to have)
                "Close7": c7,
                "Close30": c30,
                "Close90": c90,
                # percent changes (dashboard uses these)
                "Chg7Pct": chg7,
                "Chg30Pct": chg30,
                "Chg90Pct": chg90,
            }
        )

    df = pd.DataFrame(records)

    # Always render dashboard
    render(df, out_html)

    hits = df[df["Status"].isin(["IN_ZONE", "NEAR"])].copy()
    if hits.empty:
        print("No hits today. No message sent.")
        return

    if state.get("last_sent_day") == today:
        print("Already sent today. Skip.")
        return

    last_hits: Set[str] = {h.get("Ticker") for h in state.get("last_sent_hits", []) if h.get("Ticker")}
    current_hits: Set[str] = set(hits["Ticker"].tolist())
    if current_hits and current_hits == last_hits:
        print("Same hits as last time. Skip.")
        return

    dashboard_url = build_dashboard_url()
    msg = build_message(hits, dashboard_url, near_pct)
    push_message(msg)

    state["last_sent_day"] = today
    state["last_sent_hits"] = hits[["Ticker", "Status"]].to_dict(orient="records")
    save_state(state_path, state)

    print("Sent alert and updated state.")


if __name__ == "__main__":
    main()

