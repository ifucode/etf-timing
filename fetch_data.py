#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取腾讯财经数据 -> 计算 文华多空 A系斜率动量矩阵 -> 生成离线自包含 index.html (+ data.json)
用法: python fetch_data.py
依赖: 仅标准库 (urllib / json)

动量逻辑（来自 文华多空_主图.txt）：
  A0  = (L + H + C*2) / 4                { 典型价格，给收盘更高权重 }
  A1  = EMA(A0, 14)                       { 短期成本线 }
  A2  = EMA(A0, 25)                       { 中期成本线 }
  A1X = (A1 - REF(A1,1)) / REF(A1,1) * 100  { A1 日变化率%，短期趋势斜率 }
  A2X = (A2 - REF(A2,1)) / REF(A2,1) * 100  { A2 日变化率%，中期趋势斜率 }

矩阵主动量 = A1X（文华主图的核心决策驱动：A1X>=0 看多/持股，A1X<0 转空）；
A2X 作为副参考（A1X<0 且 A2X<0 时 逃顶/空仓），存入 a2x 字段供副图/ tooltip 使用。
"""
import json, math, time, os, urllib.request, urllib.parse, re, csv, datetime

# ---- ETF 标的池（来自 ETF-pool.csv：代码,名称,分类,组内序号）----
def load_pool(path='ETF-pool.csv'):
    """读取 ETF-pool.csv，返回 [(code, name, cat), ...]，保持文件原顺序。"""
    pool = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            code = (row.get('代码') or '').strip()
            name = (row.get('名称') or '').strip()
            cat  = (row.get('分类') or '').strip()
            if code:
                pool.append((code, name, cat))
    return pool

EMA_SHORT = 14      # A1 周期
EMA_MID = 25        # A2 周期
COLS = 30           # 矩阵展示最近交易日列数
WCOLS = 4            # 右侧周线展示最近周数
KLINE_DAYS = 160    # 抓取日线长度（足够 EMA 预热）
WKLINE_WEEKS = 160  # 抓取周线长度（足够 EMA 预热）

def to_tencent(code):
    return ('sh' if code[:2] in ('51','58','56','60','68','90','11','13') else 'sz') + code

def iso_week_key(datestr):
    """返回日期所属自然周键（年-W周，周一为一周起点），用于把“本周至今”这根
    不同 ETF 截止日不同的周线合并成同一列。"""
    y, m, dd = int(datestr[:4]), int(datestr[5:7]), int(datestr[8:10])
    wk = datetime.date(y, m, dd).isocalendar().week
    return f"{y}-W{wk:02d}"

def fetch(url, retries=3, headers=None):
    last = None
    h = {'User-Agent':'Mozilla/5.0'}
    if headers:
        h.update(headers)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read().decode('utf-8','ignore')
            return raw
        except Exception as e:
            last = e
            time.sleep(0.4 * (i+1))
    raise last

# ---- 同花顺金融数据 API（fuyao.aicubes.cn，主数据源；需 API Key）----
def get_fuyao_key():
    """API Key 优先级：环境变量 FUYAO_API_KEY > 本地 fuyao_key.txt（已被 .gitignore 排除）。
    未配置时返回 None，上层会回退到东方财富/腾讯。绝不硬编码 Key 到本文件。"""
    v = os.environ.get('FUYAO_API_KEY')
    if v and v.strip():
        return v.strip()
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fuyao_key.txt')
    if os.path.exists(p):
        try:
            return open(p, 'r', encoding='utf-8').read().strip()
        except Exception:
            return None
    return None

def to_thscode(code):
    """ETF 6 位代码 -> 同花顺 thscode（沪市 .SH / 深市 .SZ）。"""
    return code + ('.SH' if code[:2] in ('51','58','56','60','68','90','11','13') else '.SZ')

def day_to_week(dates, o, h, l, c):
    """日线序列 -> 周线序列：按 ISO 自然周（周一为起点）聚合，
    周开=组首日开，周高=max，周低=min，周收=组末日收，周日期=组末日。"""
    groups = {}
    for i, d in enumerate(dates):
        y, mo, da = int(d[:4]), int(d[5:7]), int(d[8:10])
        wk = datetime.date(y, mo, da).isocalendar().week
        groups.setdefault(f"{y}-W{wk:02d}", []).append(i)
    wdates, wo, wh, wl, wc = [], [], [], [], []
    for mk in sorted(groups):
        idxs = groups[mk]
        wdates.append(dates[idxs[-1]])
        wo.append(o[idxs[0]])
        wh.append(max(h[i] for i in idxs))
        wl.append(min(l[i] for i in idxs))
        wc.append(c[idxs[-1]])
    return wdates, wo, wh, wl, wc

def get_kline_ths(code, ktype='day'):
    """同花顺 ETF 历史日线（/api/fund/market/historical，仅 ETF，adjust=null 不复权）。
    该接口只给日线，ktype='week' 时由日线本地聚合为周线。"""
    key = get_fuyao_key()
    if not key:
        raise RuntimeError('no fuyao key')
    thscode = to_thscode(code)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 730 * 86400 * 1000   # 约 2 年，足够 EMA 预热
    url = (f"https://fuyao.aicubes.cn/api/fund/market/historical"
           f"?thscode={thscode}&interval=1d&start={start_ms}&end={end_ms}&adjust=null")
    obj = json.loads(fetch(url, headers={'X-api-key': key}))
    if obj.get('code') != 0:
        raise ValueError(f"ths historical err {thscode}: {obj.get('message')}")
    bars = obj.get('data', {}).get('item') or []
    if not bars:
        raise ValueError('empty ths bars for ' + thscode)
    dates, opens, closes, highs, lows = [], [], [], [], []
    for b in bars:
        dt = datetime.datetime.fromtimestamp(b['date_ms'] / 1000)
        dates.append(dt.strftime('%Y-%m-%d'))
        opens.append(float(b['open_price'])); closes.append(float(b['close_price']))
        highs.append(float(b['high_price'])); lows.append(float(b['low_price']))
    if ktype == 'week':
        return day_to_week(dates, opens, highs, lows, closes)
    return dates, opens, highs, lows, closes

def get_quotes_ths(codes):
    """同花顺场内基金行情快照（/api/fund/market/snapshot），返回与 get_quotes 兼容的结构。"""
    key = get_fuyao_key()
    if not key:
        raise RuntimeError('no fuyao key')
    out = {}
    for code in codes:
        thscode = to_thscode(code)
        url = f"https://fuyao.aicubes.cn/api/fund/market/snapshot?thscode={thscode}"
        try:
            obj = json.loads(fetch(url, headers={'X-api-key': key}))
            it = obj.get('data', {}).get('item') or []
            if it:
                b = it[0]
                out[to_tencent(code)] = {
                    'name': '', 'price': float(b.get('last_price') or 0),
                    'prevClose': float(b.get('prev_price') or 0), 'time': ''
                }
        except Exception:
            pass
        time.sleep(0.12)   # 客户端节流，避免触发上游限流
    return out

def get_kline_em(code, ktype='day'):
    """东方财富 K 线（沙箱/本地均可直连，作为主源）。返回 (dates, opens, highs, lows, closes)。"""
    full = to_tencent(code)
    market = '1' if full.startswith('sh') else '0'
    klt = '102' if ktype == 'week' else '101'   # 101=日, 102=周
    n = WKLINE_WEEKS if ktype == 'week' else KLINE_DAYS
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56"
           f"&klt={klt}&fqt=1&secid={market}.{code}&end=20500101&lmt={n}")
    obj = json.loads(fetch(url))
    data = obj.get('data') or {}
    kl = data.get('klines')
    if not kl:
        raise ValueError('empty em klines for ' + full)
    dates, opens, closes, highs, lows = [], [], [], [], []
    for row in kl:
        f = row.split(',')
        dates.append(f[0]); opens.append(float(f[1])); closes.append(float(f[2]))
        highs.append(float(f[3])); lows.append(float(f[4]))
    return dates, opens, highs, lows, closes

def get_kline_tx(code, ktype='day'):
    """腾讯 K 线（本地直连，作为兜底）。"""
    full = to_tencent(code)
    n = WKLINE_WEEKS if ktype == 'week' else KLINE_DAYS
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full},{ktype},,,{n},qfq"
    obj = json.loads(fetch(url))
    data = obj.get('data')
    node = data.get(full) if isinstance(data, dict) else (data[0].get(full) if data else None)
    if not node:
        raise ValueError('node missing for ' + full)
    rows = (node.get('qfqday') or node.get('day') or node.get('qfqweek')
            or node.get('week') or node.get('bfqday'))
    if not rows:
        raise ValueError('empty rows for ' + full)
    # 行格式: [date, open, close, high, low, volume, ...]
    dates  = [r[0] for r in rows]
    opens  = [float(r[1]) for r in rows]
    closes = [float(r[2]) for r in rows]
    highs  = [float(r[3]) for r in rows]
    lows   = [float(r[4]) for r in rows]
    return dates, opens, highs, lows, closes

def get_kline_sina(code, ktype='day'):
    """新浪财经 K 线（备用兜底，覆盖多数 ETF；部分小众标的返回 null 则上层回退）。
    新浪只给日线，ktype='week' 时由日线本地聚合成周线。"""
    pre = 'sh' if code[:2] in ('51','58','56','60','68','90','11','13') else 'sz'
    sym = pre + code
    n = WKLINE_WEEKS if ktype == 'week' else KLINE_DAYS
    url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={n}")
    raw = fetch(url, headers={'Referer': 'https://finance.sina.com.cn'})
    try:
        arr = json.loads(raw)
    except Exception:
        arr = None
    if not arr:
        raise ValueError('empty sina klines for ' + sym)
    dates  = [x['day'] for x in arr]
    opens  = [float(x['open']) for x in arr]
    highs  = [float(x['high']) for x in arr]
    lows   = [float(x['low']) for x in arr]
    closes = [float(x['close']) for x in arr]
    if ktype == 'week':
        return day_to_week(dates, opens, highs, lows, closes)
    return dates, opens, highs, lows, closes

def get_realtime_em(code):
    """东方财富实时行情（push2 stock/get）——用于「当日 K 线盘中尚未发布」时，
    用实时价合成当日最后一根：open/high/low/close/prevClose（已 ÷1000 还原为真实价格）。
    对同花顺/腾讯/Sina 都不收录的小众标的（如 520830 沙特ETF）是唯一可用实时源。"""
    market = '1' if code[:2] in ('51','58','56','60','68','90','11','13') else '0'
    url = (f"https://push2.eastmoney.com/api/qt/stock/get?secid={market}.{code}"
           f"&fields=f43,f44,f45,f46,f57,f58,f60")
    obj = json.loads(fetch(url))
    d = (obj or {}).get('data') or {}
    if not d or d.get('f43') is None:
        raise ValueError('empty em realtime for ' + code)
    return {
        'open':      d['f46'] / 1000.0,
        'high':      d['f44'] / 1000.0,
        'low':       d['f45'] / 1000.0,
        'close':     d['f43'] / 1000.0,
        'prevClose': d['f60'] / 1000.0,
        'name':      d.get('f58', ''),
    }

def get_kline(code, ktype='day'):
    """优先同花顺（主源），失败回退东方财富，再回退腾讯，最后回退新浪。"""
    last = None
    for fn in (get_kline_ths, get_kline_em, get_kline_tx, get_kline_sina):
        for attempt in range(2):
            try:
                return fn(code, ktype)
            except Exception as e:
                last = e
                time.sleep(0.3 * (attempt + 1))
    raise last

# ============ 文华多空 A 系斜率计算 ============
def ema_series(vals, n):
    """递归 EMA（与文华一致：首值取首元素，之后 EMA = 前值 + k*(现值-前值)）。"""
    k = 2.0 / (n + 1)
    out = []
    prev = vals[0]
    for i, v in enumerate(vals):
        prev = v if i == 0 else prev + k * (v - prev)
        out.append(prev)
    return out

def wh_a0(o, h, l, c):
    """A0 = (L + H + C*2) / 4"""
    return [(l[i] + h[i] + c[i] * 2.0) / 4.0 for i in range(len(c))]

def wh_slopes(o, h, l, c):
    """返回完整序列的 EMA 数组与斜率：A1/A2（EMA）、A1X/A2X（斜率%）。"""
    a0 = wh_a0(o, h, l, c)
    a1 = ema_series(a0, EMA_SHORT)
    a2 = ema_series(a0, EMA_MID)
    n = len(a0)
    a1x = [0.0] * n
    a2x = [0.0] * n
    for i in range(1, n):
        a1x[i] = (a1[i] - a1[i-1]) / a1[i-1] * 100.0
        a2x[i] = (a2[i] - a2[i-1]) / a2[i-1] * 100.0
    return a1, a2, a1x, a2x

def wh_live_slope(a1_prev, a2_prev, a0_last_new):
    """用实时价替换最新一根 A0 后，仅重算最后一根 A1X / A2X（EMA 仅末端受影响）。"""
    k1 = 2.0 / (EMA_SHORT + 1)
    k2 = 2.0 / (EMA_MID + 1)
    a1_last = a1_prev + k1 * (a0_last_new - a1_prev)
    a2_last = a2_prev + k2 * (a0_last_new - a2_prev)
    a1x_last = (a1_last - a1_prev) / a1_prev * 100.0
    a2x_last = (a2_last - a2_prev) / a2_prev * 100.0
    return a1x_last, a2x_last

def get_quotes(codes):
    # 主源：同花顺场内基金快照（需 Key）；无 Key 或失败则回退腾讯行情
    try:
        q = get_quotes_ths(codes)
        if q:
            return q
    except Exception:
        pass
    fulls = [to_tencent(c) for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(fulls)
    raw = fetch(url)
    # GBK 解码
    try:
        txt = raw.encode('latin1').decode('gbk')
    except Exception:
        txt = raw
    out = {}
    for m in re.finditer(r'v_(\w+)="([^"]*)"', txt):
        f = m.group(2).split('~')
        try:
            out[m.group(1)] = {
                'name': f[1],
                'price': float(f[3]) if f[3] else 0.0,
                'prevClose': float(f[4]) if f[4] else 0.0,
                'time': f[30] if len(f) > 30 else '',
            }
        except (ValueError, IndexError):
            pass
    return out

def main():
    POOL = load_pool()
    print(f"从 ETF-pool.csv 载入 {len(POOL)} 只 ETF")
    kl = {}
    for i, (code, name, cat) in enumerate(POOL):
        try:
            kl[code] = get_kline(code)
        except Exception as e:
            print(f"  ! {code} {name} 日线失败: {e}")
        if (i+1) % 10 == 0:
            print(f"  ... {i+1}/{len(POOL)}")
        time.sleep(0.05)

    # 交易日列：取各只并集里最近的 COLS 个（任一只有的最新日都保留，缺者显示 ·，避免单只缺日拖累全体）
    ok = [c for c in POOL if c[0] in kl]
    all_dates = set()
    for c in ok:
        all_dates.update(kl[c[0]][0])
    trade_dates = sorted(all_dates)[-COLS:]
    print(f"交易日列 = {len(trade_dates)} 个，最新 {trade_dates[-1]}")

    # 实时快照
    print("抓取实时行情...")
    quotes = get_quotes([c[0] for c in ok])

    # 周线（用于右侧近 4 周 A1X 列）
    print("抓取周线...")
    kl_week = {}
    for i, (code, name, cat) in enumerate(POOL):
        try:
            kl_week[code] = get_kline(code, 'week')
        except Exception as e:
            print(f"  ! {code} {name} 周线失败: {e}")
        if (i+1) % 10 == 0:
            print(f"  ... {i+1}/{len(POOL)}")
        time.sleep(0.05)
    okw = [c for c in ok if c[0] in kl_week]
    # 以自然周(ISO 周)为单位对齐：避免“本周至今”这根被不同 ETF 拆成不同日期列
    week_iso_rep = {}          # iso 周键 -> 代表日期(全局该周内最大日期)
    week_a1x = {}              # code -> (dates, a1x_w)
    for code in [c[0] for c in okw]:
        dw, ow, hw, lw, cw = kl_week[code]
        _, _, a1x_w, _ = wh_slopes(ow, hw, lw, cw)
        week_a1x[code] = (dw, a1x_w)
        for d in dw:
            k = iso_week_key(d)
            if d > week_iso_rep.get(k, ''):
                week_iso_rep[k] = d
    week_dates = sorted(week_iso_rep.values())[-WCOLS:]
    week_iso_of_date = {rep: iso_week_key(rep) for rep in week_dates}
    print(f"周线列(自然周) = {len(week_dates)} 个: {week_dates}")

    rows = []
    for code, name, cat in ok:
        dates, o, h, l, c = kl[code]
        a1_full, a2_full, a1x_full, a2x_full = wh_slopes(o, h, l, c)
        idx_of = {d: i for i, d in enumerate(dates)}
        moms = {}
        a2x = {}
        for d in trade_dates:
            p = idx_of.get(d)
            if p is None or p < 1:   # A1X 需要上一根做差分
                continue
            moms[d] = round(a1x_full[p], 4)
            a2x[d] = round(a2x_full[p], 4)
        latest = moms.get(trade_dates[-1])
        latest_a2x = a2x.get(trade_dates[-1])
        # 实时动量：用实时价替换窗口最后一日收盘，重算末端 A1X / A2X
        live = None
        live_a2x = None
        q = quotes.get(to_tencent(code))
        last_d = trade_dates[-1]
        p = idx_of.get(last_d)
        if q and q['price'] > 0 and p is not None and p >= 1:
            a0_last_new = (l[p] + h[p] + q['price'] * 2.0) / 4.0
            live, live_a2x = wh_live_slope(a1_full[p-1], a2_full[p-1], a0_last_new)
            live = round(live, 4)
            live_a2x = round(live_a2x, 4)
        # 周线 A1X（近 WCOLS 个自然周），按 ISO 周对齐聚合，键为该周代表日期
        week_moms = {}
        if code in week_a1x:
            dw, a1x_w = week_a1x[code]
            idxw = {d: i for i, d in enumerate(dw)}
            for rep in week_dates:
                ik = week_iso_of_date[rep]
                cand = [d for d in dw if iso_week_key(d) == ik]
                if not cand:
                    continue
                dlast = max(cand)
                pw = idxw.get(dlast)
                if pw is None or pw < 1:
                    continue
                week_moms[rep] = round(a1x_w[pw], 4)
        week_latest = week_moms.get(week_dates[-1]) if week_dates else None
        rows.append({
            'code': code, 'name': name, 'cat': cat, 'moms': moms, 'a2x': a2x,
            'latest': latest, 'latestA2x': latest_a2x,
            'live': live, 'liveA2x': live_a2x,
            'weekMoms': week_moms, 'weekLatest': week_latest,
        })

    as_of = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    data = {'asOf': as_of, 'tradeDates': trade_dates, 'weekDates': week_dates, 'rows': rows}

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"已写 data.json（{len(rows)} 只）")

    # 生成自包含 index.html
    with open('template.html', 'r', encoding='utf-8') as f:
        html = f.read()
    pool_json = json.dumps([{'code': c, 'name': n, 'cat': ct} for c, n, ct in POOL], ensure_ascii=False)
    data_json = json.dumps(data, ensure_ascii=False)
    html = html.replace('/*__POOL__*/[]', '/*__POOL__*/' + pool_json)
    html = html.replace('/*__DATA__*/ null', '/*__DATA__*/ ' + data_json)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"已生成 index.html（内联快照 asOf={as_of}）")

if __name__ == '__main__':
    main()
