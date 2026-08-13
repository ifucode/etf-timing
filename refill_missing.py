#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""仅补回 data.json 中缺失的 ETF（因上游限流/不支持漏掉），并入已有快照。
保留其余行的原值，避免重抓全部 46 只导致其余数据变动。"""
import json, csv
import fetch_data as F

MISSING = ['520830', '161903']   # 沙特ETF华泰柏瑞 / 万家行业优选LOF

# 1. 读池（拿名称/分类，保持顺序）
pool = F.load_pool()
name_of = {c: n for c, n, _ in pool}
cat_of = {c: ct for c, n, ct in pool}

# 2. 读现有 data.json
with open('data.json', encoding='utf-8') as f:
    data = json.load(f)
trade_dates = data['tradeDates']
week_dates = data['weekDates']
rows = data['rows']
existing = {r['code'] for r in rows}

# 3. 补缺失行
for code in MISSING:
    if code in existing:
        print(f"  - {code} 已存在，跳过")
        continue
    try:
        dates, o, h, l, c = F.get_kline(code)          # 东财/腾讯兜底
    except Exception as e:
        print(f"  ! {code} 日线失败: {e}")
        continue
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

    # 周线（东财/腾讯需直连；同花顺不支持则本地由日线聚周线）
    try:
        dw, ow, hw, lw, cw = F.get_kline(code, 'week')
    except Exception:
        dw, ow, hw, lw, cw = F.day_to_week(dates, o, h, l, c)
    _, _, a1x_w, _ = F.wh_slopes(ow, hw, lw, cw)
    week_a1x = {dw[i]: a1x_w[i] for i in range(len(dw))}
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

    rows.append({
        'code': code, 'name': name_of.get(code, code), 'cat': cat_of.get(code, ''),
        'moms': moms, 'a2x': a2x, 'latest': latest, 'latestA2x': latest_a2x,
        'live': None, 'liveA2x': None,
        'weekMoms': week_moms, 'weekLatest': week_latest,
    })
    print(f"  + {code} {name_of.get(code,code)} 已补 (latest={latest}, weekLatest={week_latest})")

# 4. 按池顺序排序
order = {c: i for i, (c, *_ ) in enumerate(pool)}
rows.sort(key=lambda r: order.get(r['code'], 999))

data['rows'] = rows
data['asOf'] = F.time.strftime('%Y-%m-%d %H:%M:%S', F.time.localtime())

with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"data.json 现 {len(rows)} 只 -> 应 {len(pool)} 只")

# 5. 重新生成 index.html（使用完整 POOL 顺序，与数据一致）
with open('template.html', encoding='utf-8') as f:
    html = f.read()
pool_json = json.dumps([{'code': c, 'name': n, 'cat': ct} for c, n, ct in pool], ensure_ascii=False)
data_json = json.dumps(data, ensure_ascii=False)
html = html.replace('/*__POOL__*/[]', '/*__POOL__*/' + pool_json)
html = html.replace('/*__DATA__*/ null', '/*__DATA__*/ ' + data_json)
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("index.html 已重生（内联快照）")
