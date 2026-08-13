#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单独刷新指定 ETF 的日/周线并重算动量，并入现有 data.json（保留其余行）。
用法: python update_2rows.py 159941 520830
"""
import json, csv, sys, time
import fetch_data as F

codes = sys.argv[1:] or ['159941', '520830']

pool = F.load_pool()
name_of = {c: n for c, n, _ in pool}
cat_of = {c: ct for c, n, ct in pool}

with open('data.json', encoding='utf-8') as f:
    data = json.load(f)
trade_dates = data['tradeDates']
week_dates = data['weekDates']
rows = data['rows']
by_code = {r['code']: r for r in rows}

for code in codes:
    try:
        dates, o, h, l, c = F.get_kline(code)
    except Exception as e:
        print(f"  ! {code} 日线失败: {e}")
        continue
    print(f"  {code} {name_of.get(code,code)} 日线末5: {dates[-5:]} 含08-13? {'2026-08-13' in dates}")
    a1_full, a2_full, a1x_full, a2x_full = F.wh_slopes(o, h, l, c)
    idx_of = {d: i for i, d in enumerate(dates)}
    moms, a2x = {}, {}
    for d in trade_dates:
        p = idx_of.get(d)
        if p is None or p < 1:
            continue
        moms[d] = round(a1x_full[p], 4)
        a2x[d] = round(a2x_full[p], 4)
    latest = moms.get(trade_dates[-1])
    latest_a2x = a2x.get(trade_dates[-1])

    # 周线
    try:
        dw, ow, hw, lw, cw = F.get_kline(code, 'week')
    except Exception:
        dw, ow, hw, lw, cw = F.day_to_week(dates, o, h, l, c)
    _, _, a1x_w, _ = F.wh_slopes(ow, hw, lw, cw)
    week_iso_of_date = {d: F.iso_week_key(d) for d in dw}
    week_moms = {}
    for rep in week_dates:
        ik = F.iso_week_key(rep)
        cand = [d for d in dw if week_iso_of_date.get(d) == ik]
        if not cand:
            continue
        dlast = max(cand)
        pw = dw.index(dlast)
        if pw < 1:
            continue
        week_moms[rep] = round(a1x_w[pw], 4)
    week_latest = week_moms.get(week_dates[-1]) if week_dates else None

    row = by_code.get(code)
    if row is None:
        # 全新行
        rows.append({
            'code': code, 'name': name_of.get(code, code), 'cat': cat_of.get(code, ''),
            'moms': moms, 'a2x': a2x, 'latest': latest, 'latestA2x': latest_a2x,
            'live': None, 'liveA2x': None, 'weekMoms': week_moms, 'weekLatest': week_latest,
        })
    else:
        row.update({'moms': moms, 'a2x': a2x, 'latest': latest, 'latestA2x': latest_a2x,
                    'weekMoms': week_moms, 'weekLatest': week_latest})
    print(f"    最新日动量 latest={latest}, a2x={latest_a2x}; 周 latest={week_latest}")

order = {c: i for i, (c, *_ ) in enumerate(pool)}
rows.sort(key=lambda r: order.get(r['code'], 999))
data['rows'] = rows
data['asOf'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"data.json 更新后 {len(rows)} 只")

with open('template.html', encoding='utf-8') as f:
    html = f.read()
pool_json = json.dumps([{'code': c, 'name': n, 'cat': ct} for c, n, ct in pool], ensure_ascii=False)
data_json = json.dumps(data, ensure_ascii=False)
html = html.replace('/*__POOL__*/[]', '/*__POOL__*/' + pool_json)
html = html.replace('/*__DATA__*/ null', '/*__DATA__*/ ' + data_json)
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("index.html 已重生")
