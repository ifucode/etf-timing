#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""仅用本地 data.json + ETF-pool.csv 重新生成 index.html（不联网、不改数据）。"""
import json, csv, os

BASE = os.path.dirname(os.path.abspath(__file__))

def load_pool(path):
    pool = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            code = (row.get('代码') or '').strip()
            name = (row.get('名称') or '').strip()
            cat  = (row.get('分类') or '').strip()
            if code:
                pool.append((code, name, cat))
    return pool

def main():
    with open(os.path.join(BASE, 'data.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)
    pool_json = json.dumps(
        [{'code': c, 'name': n, 'cat': ct} for c, n, ct in load_pool(os.path.join(BASE, 'ETF-pool.csv'))],
        ensure_ascii=False)
    data_json = json.dumps(data, ensure_ascii=False)
    with open(os.path.join(BASE, 'template.html'), 'r', encoding='utf-8') as f:
        html = f.read()
    assert '/*__POOL__*/[]' in html, 'POOL placeholder missing'
    assert '/*__DATA__*/ null' in html, 'DATA placeholder missing'
    html = html.replace('/*__POOL__*/[]', '/*__POOL__*/' + pool_json)
    html = html.replace('/*__DATA__*/ null', '/*__DATA__*/ ' + data_json)
    with open(os.path.join(BASE, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    print('index.html regenerated, bytes =', len(html))

if __name__ == '__main__':
    main()
