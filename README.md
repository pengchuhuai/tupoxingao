# A股历史新高与首次MA10回踩跟踪

已部署增量扫描程序（**尚未运行成功，也尚未验证全市场覆盖**）。

## 首次运行
1. 仓库 Settings → Secrets and variables → Actions → New repository secret，创建 `TUSHARE_TOKEN`。
2. Actions → A-share historical-high tracker → Run workflow。
3. 检查 Actions 日志及 `data/status.json`；缺少 token 或 Tushare 权限/额度会失败。
4. GitHub Actions 工作日北京时间约16:25运行（cron可能延迟），每次默认扫描25只，优先从未处理股票。

## 输出
- `data/history/*.csv.gz`：股票上市以来的日K历史（Tushare daily + adj_factor）。
- `data/breakouts.json`：盘中 high 严格突破此前全历史 high 的事件，区分 raw 未复权与 hfq 后复权；按代码、日期、口径去重。
- `data/watchlist.json`：突破后 MA10 首次触及、缩量及跳空低开筛选；仅观察，不是买入指令。
- `data/status.json`：当日完成数、总数、错误和覆盖状态。

## 注意事项
- 依赖 Tushare Pro token、接口权限与额度；未配置时不能获取真实行情。
- 当前为 MVP，历史数据完整性仅做基础检查，不能保证交易日缺口、停牌、历史修订等全部得到独立核验。
- 当前 MA10 用未复权收盘价计算，后复权突破事件的回踩判断也使用未复权 MA10；后续需要统一价格口径。
- 回填每只股票需多次请求，长上市历史可能遇到频率限制；每日仅25只，首次全市场回填需要较长时间。
- 观察名单暂包含历史突破事件，规模可能较大；需要增加只跟踪近期有效突破、失效条件和板块风控。
- GitHub Actions 定时执行和自动提交需要仓库 Actions 启用、工作流写权限。公开仓库中的策略和历史数据对外可见。
- 未接入实时盘中数据、板块资金、微信推送、券商自动交易；不要把当前结果当作已验证交易信号。
