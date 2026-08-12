import csv, json, re

# 从 ETF-pool.csv 取 ETF 池（代码 + 名称 + 分类）作为复现基准
pool = []
with open('ETF-pool.csv', 'r', encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        code = (row.get('代码') or '').strip()
        name = (row.get('名称') or '').strip()
        cat  = (row.get('分类') or '').strip()
        if code:
            pool.append({'code': code, 'name': name, 'cat': cat})

tpl = open('template.html', encoding='utf-8').read()
repl = '/*__POOL__*/' + json.dumps(pool, ensure_ascii=False)
out = re.sub(r'/\*__POOL__\*/\[\]', repl, tpl)
open('index.html', 'w', encoding='utf-8').write(out)
print('generated index.html with', len(pool), 'etfs')
