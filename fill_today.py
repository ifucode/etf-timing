#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为缺口 ETF 补齐「当日」K 线：若现有 K 线最新日 < 今日(交易日)，用实时行情
（东方财富实时为主，腾讯实时兜底）合成当日最后一根（open/high/low/close 取自实时价，
与同花顺盘中 close=实时价 一致），重算 A 系斜率动量并入 data.json / index.html。

用法:
  python fill_today.py ALL        # 对池中全部 ETF 合成当日（工作流盘中批使用）
  python fill_today.py 520830     # 仅补指定代码（小众标的兜底）
"""
import json, sys, time, datetime, os
import fetch_data as F

args = sys.argv[1:]
POOL = F.load_pool()
if args and args[0].upper() == 'ALL':
    codes = [c for c, *_ in POOL]
    print(f"[fill_today] 模式=ALL，处理 {len(codes)} 只")
else:
    codes = args or ['520830']
    print(f"[fill_today] 模式=指定 {codes}")

# 显式使用北京时间（UTC+8），不依赖运行环境本地时区，避免 CI(UTC) 跨日取到昨天
today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
name_of = {c: n for c, n, _ in POOL}

with open('data.json', encoding='utf-8') as f:
    data = json.load(f)
trade_dates = data['tradeDates']
week_dates = data['weekDates']
rows = data['rows']
by_code = {r['code']: r for r in rows}

# 若「今天」比现有最新列还新（盘中历史 K 线尚未含当日），把今天追加为最后一列，
# 否则合成出的当日 bar 不会被写入 moms（前端仍空白）。
if trade_dates and today > trade_dates[-1]:
    trade_dates.append(today)
    print(f"[fill_today] 追加当日列 {today} -> 共 {len(trade_dates)} 列")
# 列数维持 COLS 上限（最旧一列自然滑出）
if len(trade_dates) > F.COLS:
    trade_dates = trade_dates[-F.COLS:]


def realtime_with_retry(code, tries=3):
    last = None
    # 主源：东方财富实时
    for i in range(tries):
        try:
            return F.get_realtime_em(code)
        except Exception as e:
            last = e
            time.sleep(0.4 * (i + 1))
    # 兜底：腾讯实时（腾讯实时在盘中即含当日，且对多数 ETF 覆盖良好）
    for i in range(tries):
        try:
            return F.get_realtime_tx(code)
        except Exception as e:
            last = e
            time.sleep(0.4 * (i + 1))
    # 实时接口均受限时，回退本地实时缓存快照（盘中有效，收盘后重跑会被新值覆盖）
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'realtime_cache.json')
    try:
        cache = json.load(open(cache_path, encoding='utf-8'))
        if code in cache:
            print(f"  (实时接口不可用，使用本地缓存快照: {cache[code].get('captured','?')})")
            return cache[code]
    except Exception:
        pass
    raise last


filled = 0
for idx, code in enumerate(codes):
    row = by_code.get(code)
    if row is None:
        print(f"  ! {code} 不在 data.json，跳过")
        continue
    if idx > 0:
        time.sleep(0.12)   # 节流，避免触发上游限流
    try:
        dates, o, h, l, c = F.get_kline(code)
    except Exception as e:
        print(f"  ! {code} 日线失败: {e}")
        continue
    if today > dates[-1]:
        # 用实时价合成当日 bar（东财实时 -> 腾讯实时 -> 本地缓存）
        try:
            rt = realtime_with_retry(code)
            if rt.get('close') and rt['close'] > 0:
                o = o + [rt['open']]; h = h + [rt['high']]
                l = l + [rt['low']]; c = c + [rt['close']]
                dates = dates + [today]
                filled += 1
                print(f"  {code} {name_of.get(code,code)} 用实时合成 {today}: "
                      f"O{rt['open']:.3f} H{rt['high']:.3f} L{rt['low']:.3f} C{rt['close']:.3f}")
            else:
                print(f"  ! {code} 实时价无效，当日不补")
        except Exception as e:
            print(f"  ! {code} 实时合成失败(当日不补): {e}")
    else:
        print(f"  {code} {name_of.get(code,code)} 日线已含 {dates[-1]}，无需补当日")

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

    # 周线：由(扩展后的)日线本地聚合，保证最新周列也含当日
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

    row.update({'moms': moms, 'a2x': a2x, 'latest': latest, 'latestA2x': latest_a2x,
                'weekMoms': week_moms, 'weekLatest': week_latest})
    print(f"    最新日动量 latest={latest}, a2x={latest_a2x}; 周 latest={week_latest}")

print(f"[fill_today] 共为 {filled} 只合成当日列 {today}")

order = {c: i for i, (c, *_ ) in enumerate(POOL)}
rows.sort(key=lambda r: order.get(r['code'], 999))
data['rows'] = rows
data['tradeDates'] = trade_dates
data['asOf'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"data.json 更新后 {len(rows)} 只")

with open('template.html', encoding='utf-8') as f:
    html = f.read()
pool_json = json.dumps([{'code': c, 'name': n, 'cat': ct} for c, n, ct in POOL], ensure_ascii=False)
data_json = json.dumps(data, ensure_ascii=False)
html = html.replace('/*__POOL__*/[]', '/*__POOL__*/' + pool_json)
html = html.replace('/*__DATA__*/ null', '/*__DATA__*/ ' + data_json)
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("index.html 已重生")
