# Chinese Super League Prediction

中超联赛数据更新与建模相关脚本。

## 环境

```bash
conda env create -f environment.yml
conda activate csl-workflows
```

## 本地配置

复制本地环境模板：

```bash
cp .env.local.example .env.local
```

然后在 `.env.local` 中填写：

- `RAPIDAPI_KEY`
- `THE_ODDS_API_KEY`

说明：

- `./scripts/csl.sh` 会自动加载 `.env.local`
- 日常使用不再需要手动 `export PYTHONPATH=src`
- 也不需要每次手动 `export THE_ODDS_API_KEY=...`

## 日常入口

统一入口：

```bash
./scripts/csl.sh
```

可直接使用的子命令：

```bash
./scripts/csl.sh update
./scripts/csl.sh model
./scripts/csl.sh dashboard
./scripts/csl.sh odds
./scripts/csl.sh publish
./scripts/csl.sh all
```

推荐日常命令：

- 完整流程：`./scripts/csl.sh all`
- 只更新数据：`./scripts/csl.sh update`
- 只重建发布站点：`./scripts/csl.sh publish`

## 当前可用功能

目前项目内已具备以下 6 项功能，对应代码入口如下：

1. 抓取比赛结果和 xG  
   - 比赛结果 / 未来赛程：`python -m csl.fixtures.chn_fixture_v5`
   - xG 抓取：`python -m csl.xg.xg_pipeline`
   - xG 合并回主表：`python -m csl.xg.chn_merge`
   - 计算 `HExpG+` / `AExpG+`：`python -m csl.xg.compute_expg`
2. 跑模型预测比赛结果概率（`1x2` + 让分盘）
   - 入口：`python DC_CHN.py`
   - 模型实现：`src/csl/models/dc.py`
   - 当前导出列包含：
     - `Home Win Probability`
     - `Draw Probability`
     - `Away Win Probability`
     - `Home -1 Handicap`
     - `Home -2 Handicap`
     - `Away -1 Handicap`
     - `Away -2 Handicap`
3. 导出常规 CSV
   - `data/output_data/CHN_team_stats.csv`
   - `data/output_data/CHN_team_stats_match_simulations.csv`
4. 导出 dashboard 展示用 CSV / JSON
   - CSV：`python -m csl.dashboard.export_dashboard_csv`
   - JSON：`python -m csl.dashboard.export_dashboard_json`
5. 抓取 Pinnacle 让分盘口 CSV
   - 入口：`python -m csl.odds.fetch_pinnacle_spreads`
   - 数据源：The Odds API
   - 输出：`data/raw_data/CHN_pinnacle_spreads.csv`
6. 导出未来赛程 vs 模型 vs Pinnacle 盘口对比表
   - 入口：`python -m csl.odds.export_upcoming_market_comparison`
   - 输出：
     - `data/output_data/CHN_upcoming_market_comparison.csv`
     - `data/dashboard/csv/upcoming_market_comparison.csv`

## 完整流程说明

执行：

```bash
./scripts/csl.sh all
```

`all` 的顺序：

1. 数据更新
2. 模型运行
3. 抓 Pinnacle 赔率
4. 导出 market comparison
5. 导出 dashboard CSV / JSON
6. 构建 Netlify `site/`

如果你只想看菜单，不带参数直接运行：

```bash
./scripts/csl.sh
```

## 模型与导出命令

### 1. 只更新数据

```bash
./scripts/csl.sh update
```

说明：

- 对应底层脚本：`./scripts/run_csl_update.sh`
- 自动完成环境激活、`.env.local` 加载和 `PYTHONPATH` 设置

### 2. 生成模型输出 CSV

```bash
./scripts/csl.sh model
```

输出：

- `data/output_data/CHN_team_stats.csv`
- `data/output_data/CHN_team_stats_match_simulations.csv`

### 3. 生成 dashboard CSV / JSON

```bash
./scripts/csl.sh dashboard
```

输出：

- `data/dashboard/csv/dashboard_meta.csv`
- `data/dashboard/csv/upcoming_fixtures.csv`
- `data/dashboard/json/dashboard_meta.json`
- `data/dashboard/json/upcoming_fixtures.json`
- `data/dashboard/json/match_predictions.json`
- `data/dashboard/json/team_strength_rankings.json`

### 4. 生成 Netlify 静态站点

执行：

```bash
./scripts/csl.sh publish
```

输出：

- `site/index.html`
- `site/app.js`
- `site/styles.css`
- `site/assets/`
- `site/data/*.json`

说明：

- `publish` 会先重建 dashboard CSV / JSON
- 然后再调用 `./scripts/build_dashboard_site.sh` 生成 `site/`
- 如果你只需要底层打包脚本，仍然可以直接运行 `./scripts/build_dashboard_site.sh`

### 5. 抓取 Pinnacle spreads CSV 并导出 market comparison

执行：

```bash
./scripts/csl.sh odds
```

- `data/raw_data/CHN_pinnacle_spreads.csv`
- `data/output_data/CHN_upcoming_market_comparison.csv`
- `data/dashboard/csv/upcoming_market_comparison.csv`

### 6. 重建发布产物

执行：

```bash
./scripts/csl.sh publish
```

说明：

- 不重新抓数据
- 不重新跑模型
- 会重建 dashboard CSV / JSON 和 `site/`

## 数据目录（当前布局）

| 路径 | 说明 |
|------|------|
| `data/raw_data/` | 主联赛 CSV、xG、赛程导出、自动备份 `backups/` |
| `data/output_data/` | 队名映射、Dixon–Coles 球队统计与模拟输出等 |
| `data/dashboard/csv/` | dashboard 直接读取的 CSV 数据 |
| `data/dashboard/json/` | dashboard 页面读取的 JSON 数据 |

后续整理会按目标结构逐步迁移到 `data/raw/`、`data/processed/`（或 `output/`）等，见仓库内讨论与后续提交。

## 当前检查结果

本次对 6 项功能做了代码核对，其中：

- 已本地跑通：
  - `python DC_CHN.py`
  - `python -m csl.dashboard.export_dashboard_csv`
  - `python -m csl.dashboard.export_dashboard_json`
  - `python -m csl.odds.export_upcoming_market_comparison`
- 已做代码级核对，但未在本次会话中执行实时抓取：
  - `python -m csl.fixtures.chn_fixture_v5`
  - `python -m csl.xg.xg_pipeline`
  - `python -m csl.xg.chn_merge`
  - `python -m csl.xg.compute_expg`
  - `python -m csl.odds.fetch_pinnacle_spreads`

原因：

- 抓取链路依赖 TheSportsDB、SofaScore / RapidAPI、The Odds API 外部接口
- 本地建模与导出链路不依赖外部接口，因此本次可以直接验证

## 其他脚本

- 根目录 `DC_CHN.py`：`src/csl/models/dc.py` 的轻量入口封装，负责生成模型输出 CSV  
- `backtest/`：历史回测与实验（运行前请在该目录下确认路径与依赖）
