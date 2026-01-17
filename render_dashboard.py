import os
import datetime as dt
import pandas as pd

def render(df: pd.DataFrame, out_path: str):
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")

    rows = []
    for _, r in df.iterrows():
        status = r["Status"]
        cls = "ok" if status == "IN_ZONE" else ("near" if status == "NEAR" else "")
        ticker = r["Ticker"]

        chart_url = (
            f"https://finance.yahoo.com/chart/{ticker}"
            f"?range=6mo&interval=1d&indicators=quote&includeAdjustedClose=true"
        )

        rows.append(f"""
<tr class="{cls}">
  <td>
    <details>
      <summary><strong>{r['Name']}</strong> ({ticker})</summary>
      <div style="margin-top:10px">
        <iframe
          src="{chart_url}"
          width="100%"
          height="420"
          style="border:0"
          loading="lazy">
        </iframe>
      </div>
    </details>
  </td>
  <td>{r['LastPrice']:.2f}</td>
  <td>{r['ZoneLow']:.2f} – {r['ZoneHigh']:.2f}</td>
  <td>{status}</td>
</tr>
""")

    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>底値目安ダッシュボード</title>
<style>
body {{ font-family:-apple-system,BlinkMacSystemFont,sans-serif; margin:20px; }}
h1 {{ font-size:20px; }}
table {{ border-collapse:collapse; width:100%; }}
th, td {{ padding:10px; border-bottom:1px solid #eee; vertical-align:top; }}
tr.ok {{ background:#f0fff4; }}
tr.near {{ background:#fffaf0; }}
summary {{ cursor:pointer; }}
small {{ color:#666; }}
</style>
</head>
<body>
<h1>底値目安ダッシュボード</h1>
<p>最終更新: {now}</p>

<table>
<thead>
<tr>
  <th>銘柄（クリックでチャート表示）</th>
  <th>現在値</th>
  <th>目安ゾーン</th>
  <th>状態</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>

<p><small>IN_ZONE=底値目安内 / NEAR=上限付近（接近）</small></p>
</body>
</html>
"""

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
