import os
import datetime as dt
import pandas as pd


def _is_na(v) -> bool:
    try:
        return v is None or pd.isna(v)
    except Exception:
        return v is None


def _fmt_price(v):
    if _is_na(v):
        return "—"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "—"


def _pct_class(v) -> str:
    """Return css class for pct values."""
    if _is_na(v):
        return "pct-na"
    try:
        x = float(v)
        if x > 0:
            return "pct-pos"
        if x < 0:
            return "pct-neg"
        return "pct-zero"
    except Exception:
        return "pct-na"


def _pct_disp(v) -> str:
    """Return string with arrow + signed %."""
    if _is_na(v):
        return "—"
    try:
        x = float(v)
        if x > 0:
            return f"▲ +{x:.1f}%"
        if x < 0:
            return f"▼ {x:.1f}%"
        return "• 0.0%"
    except Exception:
        return "—"


def _status_badge(status: str) -> str:
    if status == "IN_ZONE":
        return '<span class="badge badge-zone">IN_ZONE</span>'
    if status == "NEAR":
        return '<span class="badge badge-near">NEAR</span>'
    return '<span class="badge badge-none">—</span>'


def render(df: pd.DataFrame, out_path: str):
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")

    # Make sure expected columns exist (robust)
    for col in ["Ticker", "Name", "ZoneLow", "ZoneHigh", "LastPrice", "Status", "Chg7Pct", "Chg30Pct", "Chg90Pct"]:
        if col not in df.columns:
            df[col] = None

    # Sort: IN_ZONE first, then NEAR, then others; within group show largest drop (more "interesting") first
    def _status_rank(s):
        return 0 if s == "IN_ZONE" else (1 if s == "NEAR" else 2)

    df_sorted = df.copy()
    df_sorted["__rank"] = df_sorted["Status"].apply(_status_rank)

    # For within-group sort, use 30d% change as a decent default; NA -> big number so it goes last
    def _sort_key(v):
        if _is_na(v):
            return 999999.0
        try:
            return float(v)
        except Exception:
            return 999999.0

    df_sorted["__chg_key"] = df_sorted["Chg30Pct"].apply(_sort_key)
    df_sorted = df_sorted.sort_values(["__rank", "__chg_key"], ascending=[True, True]).drop(columns=["__rank", "__chg_key"])

    # Summary counts
    n_zone = int((df_sorted["Status"] == "IN_ZONE").sum())
    n_near = int((df_sorted["Status"] == "NEAR").sum())

    rows = []
    for _, r in df_sorted.iterrows():
        status = r.get("Status", "—")
        ticker = str(r.get("Ticker", "")).upper().strip()
        name = str(r.get("Name", "")).strip() or ticker

        price_disp = _fmt_price(r.get("LastPrice"))

        # Zone
        zone_disp = "—"
        try:
            zl = r.get("ZoneLow")
            zh = r.get("ZoneHigh")
            if not _is_na(zl) and not _is_na(zh):
                zone_disp = f"{float(zl):.2f} – {float(zh):.2f}"
        except Exception:
            zone_disp = "—"

        # Pct displays
        chg7 = r.get("Chg7Pct")
        chg30 = r.get("Chg30Pct")
        chg90 = r.get("Chg90Pct")

        chg7_cls = _pct_class(chg7)
        chg30_cls = _pct_class(chg30)
        chg90_cls = _pct_class(chg90)

        chg7_disp = _pct_disp(chg7)
        chg30_disp = _pct_disp(chg30)
        chg90_disp = _pct_disp(chg90)

        # Links
        quote_url = f"https://finance.yahoo.com/quote/{ticker}"
        chart_url = f"https://finance.yahoo.com/chart/{ticker}?range=6mo&interval=1d"

        # Row highlight
        tr_cls = "row-zone" if status == "IN_ZONE" else ("row-near" if status == "NEAR" else "row-none")

        rows.append(f"""
<tr class="{tr_cls}">
  <td class="col-name">
    <div class="name-wrap">
      <div class="name-top">
        <span class="name">{name}</span>
        <span class="ticker">{ticker}</span>
      </div>
      <div class="name-sub">
        {_status_badge(status)}
      </div>
    </div>
  </td>

  <td class="col-price">
    <div class="mono price">{price_disp}</div>
    <div class="mono zone">{zone_disp}</div>
  </td>

  <td class="col-pct">
    <div class="pct {chg7_cls}">{chg7_disp}</div>
    <div class="pct-label">7d</div>
  </td>
  <td class="col-pct">
    <div class="pct {chg30_cls}">{chg30_disp}</div>
    <div class="pct-label">30d</div>
  </td>
  <td class="col-pct">
    <div class="pct {chg90_cls}">{chg90_disp}</div>
    <div class="pct-label">90d</div>
  </td>

  <td class="col-link">
    <a class="btn" href="{chart_url}" target="_blank" rel="noopener">チャート</a>
    <a class="btn btn-ghost" href="{quote_url}" target="_blank" rel="noopener">詳細</a>
  </td>
</tr>
""")

    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>底値目安ダッシュボード</title>
<style>
:root {{
  --bg: #0b1020;
  --card: rgba(255,255,255,0.06);
  --card2: rgba(255,255,255,0.04);
  --text: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.62);
  --line: rgba(255,255,255,0.12);
  --zone: rgba(34,197,94,0.22);
  --near: rgba(245,158,11,0.20);
  --none: rgba(255,255,255,0.03);

  --pos: rgba(34,197,94,0.95);
  --neg: rgba(239,68,68,0.95);
  --zero: rgba(255,255,255,0.75);
  --na: rgba(255,255,255,0.45);
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 18px;
  background: radial-gradient(1200px 600px at 20% 0%, rgba(99,102,241,0.25), transparent),
              radial-gradient(900px 500px at 90% 20%, rgba(34,197,94,0.18), transparent),
              var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}

.header {{
  max-width: 1100px;
  margin: 0 auto 14px auto;
  padding: 14px 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  backdrop-filter: blur(10px);
}}

.h-title {{
  display: flex;
  gap: 10px;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
}}

h1 {{
  font-size: 18px;
  margin: 0;
  letter-spacing: 0.2px;
}}

.meta {{
  font-size: 12px;
  color: var(--muted);
}}

.pills {{
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}}

.pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--card2);
  font-size: 12px;
  color: var(--muted);
}}

.dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}}
.dot-zone {{ background: rgba(34,197,94,0.95); }}
.dot-near {{ background: rgba(245,158,11,0.95); }}
.dot-all {{ background: rgba(99,102,241,0.9); }}

.table-wrap {{
  max-width: 1100px;
  margin: 0 auto;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--card);
  backdrop-filter: blur(10px);
}}

table {{
  width: 100%;
  border-collapse: collapse;
}}

thead th {{
  text-align: left;
  font-size: 12px;
  color: var(--muted);
  padding: 12px 12px;
  border-bottom: 1px solid var(--line);
  position: sticky;
  top: 0;
  background: rgba(11,16,32,0.92);
  backdrop-filter: blur(10px);
  z-index: 10;
}}

tbody td {{
  padding: 12px 12px;
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
}}

.row-zone {{ background: var(--zone); }}
.row-near {{ background: var(--near); }}
.row-none {{ background: var(--none); }}

.name-wrap {{ display: flex; flex-direction: column; gap: 6px; }}
.name-top {{ display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }}
.name {{ font-weight: 700; font-size: 14px; }}
.ticker {{ font-size: 12px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}

.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.price {{ font-size: 14px; font-weight: 700; }}
.zone {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}

.badge {{
  display: inline-flex;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid var(--line);
  width: fit-content;
}}
.badge-zone {{ background: rgba(34,197,94,0.18); color: rgba(34,197,94,0.95); }}
.badge-near {{ background: rgba(245,158,11,0.18); color: rgba(245,158,11,0.95); }}
.badge-none {{ background: rgba(255,255,255,0.06); color: var(--muted); }}

.pct {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  font-weight: 700;
}}
.pct-label {{
  margin-top: 4px;
  font-size: 11px;
  color: var(--muted);
}}

.pct-pos {{ color: var(--pos); }}
.pct-neg {{ color: var(--neg); }}
.pct-zero {{ color: var(--zero); }}
.pct-na {{ color: var(--na); }}

.btn {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: rgba(255,255,255,0.08);
  color: var(--text);
  text-decoration: none;
  font-size: 12px;
  margin-right: 8px;
}}
.btn:hover {{ background: rgba(255,255,255,0.12); }}
.btn-ghost {{
  background: transparent;
  color: var(--muted);
}}
.btn-ghost:hover {{ background: rgba(255,255,255,0.06); }}

.footer {{
  max-width: 1100px;
  margin: 12px auto 0 auto;
  padding: 10px 14px;
  color: var(--muted);
  font-size: 11px;
}}

@media (max-width: 820px) {{
  thead th:nth-child(3),
  thead th:nth-child(4),
  thead th:nth-child(5),
  tbody td:nth-child(3),
  tbody td:nth-child(4),
  tbody td:nth-child(5) {{
    width: 90px;
  }}
}}

@media (max-width: 640px) {{
  body {{ padding: 12px; }}
  .table-wrap {{ border-radius: 12px; }}
  thead th {{ font-size: 11px; padding: 10px; }}
  tbody td {{ padding: 10px; }}
  .btn {{ padding: 7px 9px; border-radius: 9px; }}
}}
</style>
</head>
<body>

<div class="header">
  <div class="h-title">
    <h1>底値目安ダッシュボード</h1>
    <div class="meta">最終更新: {now}</div>
  </div>

  <div class="pills">
    <div class="pill"><span class="dot dot-all"></span>対象: {len(df_sorted)} 銘柄</div>
    <div class="pill"><span class="dot dot-zone"></span>IN_ZONE: {n_zone}</div>
    <div class="pill"><span class="dot dot-near"></span>NEAR: {n_near}</div>
  </div>
</div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th style="width: 34%;">銘柄</th>
        <th style="width: 18%;">現在値 / ゾーン</th>
        <th style="width: 10%;">7日%</th>
        <th style="width: 10%;">30日%</th>
        <th style="width: 10%;">90日%</th>
        <th style="width: 18%;">リンク</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</div>

<div class="footer">
  IN_ZONE = 底値目安内 / NEAR = 境界の±NEAR_PCT%以内（ゾーン外） / 7/30/90日%は直近の取引日終値基準（休日は直前取引日に寄せます）
</div>

</body>
</html>
"""

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

