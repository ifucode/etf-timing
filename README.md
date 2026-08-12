# ETF择时 · 文华多空斜率矩阵

基于**文华多空主图**逻辑的 ETF 多空择时看板。每个交易日（及周线）计算文华 A 系斜率 `A1X`，用颜色矩阵直观展示 46 只 ETF 的多空状态，可一键部署到 GitHub Pages 并每日自动更新。

## 计算逻辑（文华 A 系斜率）

```
A0 = (L + H + C×2) / 4          # 典型价（收盘加权）
A1 = EMA(A0, 14)                # 短期均线
A2 = EMA(A0, 25)                # 中期均线
A1X = (A1 − REF(A1,1)) / REF(A1,1) × 100   # 主动量：短期趋势斜率%
A2X = (A2 − REF(A2,1)) / REF(A2,1) × 100   # 副参考：中期斜率%
```

- 日线展示最近 30 个交易日；右侧另加 4 个周线 A1X（近 4 周），颜色逻辑与日线一致。
- 数据源：腾讯财经（`web.ifzq.gtimg.cn` 日线 / 周线 + `qt.gtimg.cn` 实时行情）。

## 颜色 / 信号

| 颜色 | 含义 | 条件 |
|---|---|---|
| 橙底 + 红框 | **看多（持股）** | `A1X ≥ 0` |
| 蓝底 | **空仓** | `A1X < 0`（逃顶 `A2X<0` / 纯空头 `A2X≥0` 统一为蓝） |

tooltip 会标注「信号:看多 / 信号:逃顶」。

## 本地运行

依赖 Python 标准库（`json / math / time / urllib / re / csv`），无需 `pip install`。

```bash
python fetch_data.py      # 抓取行情 → 生成 data.json + index.html
```

`index.html` 是自包含静态文件（数据已内联），浏览器直接打开即可，离线也能看快照。

## 部署到 GitHub Pages（自动更新）

看板已配置好 `.github/workflows/deploy.yml`，首次推送后会：

1. 每个交易日 **15:30 北京时间** 自动重算行情并重新部署（无需手动）；
2. 也支持网页/API 手动触发（`workflow_dispatch`）。

### 上线步骤（需你的 GitHub 凭证）

> 沙箱环境无 GitHub CLI，以下在你本机终端执行一次即可。

**方式 A：用 GitHub CLI（推荐）**

```bash
# 1) 安装并登录（浏览器授权，不暴露 token）
winget install --id GitHub.cli
gh auth login

# 2) 在仓库根目录，创建公开仓库并首次推送
gh repo create etf-timing --public --source=. --push

# 3) 仓库 Settings → Pages → Build and deployment → Source 选 “GitHub Actions”
```

**方式 B：手动**

```bash
# GitHub 网页新建仓库 etf-timing（公开）后：
git remote add origin https://github.com/<你的用户名>/etf-timing.git
git push -u origin main
# 再到 Settings → Pages → Source 选 “GitHub Actions”
```

完成后，访问 `https://<你的用户名>.github.io/etf-timing/` 即可看到看板，之后数据每日自动刷新。

## 文件结构

| 文件 | 作用 |
|---|---|
| `fetch_data.py` | 抓取行情、计算 A1X/A2X、生成 `data.json` 与 `index.html` |
| `template.html` | 看板模板（渲染逻辑、配色、信号规则），`fetch_data.py` 注入数据后生成 `index.html` |
| `gen_pool.py` | 从 `ETF-pool.csv` 读取标的池 |
| `ETF-pool.csv` | ETF 标的池（代码/名称/分类/组内序号） |
| `文华多空_主图.txt` | 原始计算逻辑参考 |
| `data.json` | 生成的快照数据（46 ETF × 30 日 + 4 周） |
| `index.html` | 最终看板（自包含，可直接部署） |
