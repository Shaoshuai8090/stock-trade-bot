# A股股票选股策略交易信号推送系统

这是一个本地可运行的 MVP，用于在 A 股收盘后生成“次日观察池”，并通过 Telegram 推送候选股票或无信号心跳。

## 快速运行

```bash
python3 -m trade_signal_tool.cli scan --demo
python3 -m trade_signal_tool.cli scan --demo --json
python3 -m trade_signal_tool.cli scan --input data/sample_candidates.csv --json
```

## 真实行情数据

真实行情现在默认走 `astock` 聚合 provider：先用低风险全市场源构建候选池，再用腾讯财经批量刷新候选股实时字段，最后保留 AkShare/Eastmoney/Sina 作为兜底。先安装依赖：

```bash
pip install -r requirements.txt
```

盘中扫描：

```bash
python3 -m trade_signal_tool.cli scan --provider astock --json
python3 -m trade_signal_tool.cli scan --provider astock --telegram
```

仍可显式使用旧 AkShare provider：

```bash
python3 -m trade_signal_tool.cli scan --provider akshare --json
```

参数：

- `--max-candidates`: 实时行情粗筛后最多补充多少只股票，默认 80
- `--enrich-limit`: 拉日线和分钟线做深度计算的数量，默认 20

数据源优先级：

- 腾讯财经 `qt.gtimg.cn`: 对候选池批量刷新实时价、涨跌幅、成交量、换手率、流通市值，并在推送里标记 `数据源: tencent`
- AkShare 新浪全市场行情: 聚合 provider 优先用它枚举全市场，避免高频依赖东财
- AkShare 日线/分钟线: 计算 MA5/10/20/60、近期成交量、压力位、分时均线上方占比
- AkShare/东方财富概念板块: 拉取热门概念板块和成分股，为候选股填充 `theme`、`theme_rank`、`has_hot_theme`
- Eastmoney/Sina 原始接口: 作为兜底源；Eastmoney 只在低风险源不可用时使用

如果所有实时行情接口都被当前网络断开，CLI 会输出一行 `error: failed to fetch realtime A-share market data from AkShare/Eastmoney/Sina`。这通常是行情接口在当前网络、代理或 TLS 环境下拒绝连接；可以稍后重试，或在有稳定外网的服务器上运行。

macOS 系统 Python 常见 `LibreSSL` 环境，项目依赖里固定了 `urllib3<2` 来避免 urllib3 v2 的兼容性警告。

## Telegram 推送

Telegram 配置默认复用相邻 `spot-trade-bot` 项目的 `.env`：

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

发送到 Telegram：

```bash
python3 -m trade_signal_tool.cli scan --input data/sample_candidates.csv --telegram
```

如果配置文件不在默认位置，可以显式指定：

```bash
python3 -m trade_signal_tool.cli scan --demo --telegram --telegram-env /path/to/spot-trade-bot/.env
```

## 收盘后自动推送

收盘推送命令：

```bash
.venv/bin/python -m trade_signal_tool.cli close-push --telegram
```

行为：

- 默认 15:05 后才执行扫描
- 优先用 AkShare 交易日历判断是否为 A 股交易日
- 交易日历失败时，退回到周一至周五判断
- 筛出信号后推送到 Telegram
- 当天没有符合策略的股票时也会发送“今日无符合策略的股票，服务正常运行”的心跳通知

LaunchAgent 模板在：

```bash
data/com.trade-signal-tool.plist
```

安装或更新本机定时任务：

```bash
cp data/com.trade-signal-tool.plist ~/Library/LaunchAgents/com.trade-signal-tool.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.trade-signal-tool.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.trade-signal-tool.plist
```

## 收盘候选池 V2 策略

收盘任务使用 `AfterCloseStrategy`，不再使用原来的盘中追强硬筛。

硬过滤：

- 剔除 ST、停牌、上市不足 60 天的股票
- 剔除 `68` 开头科创板股票，避免推送账户不可交易标的
- 当日涨幅超过 8% 的股票不进入候选池，避免收盘后追涨停或接近涨停票
- 价格不能同时远离 MA5 超过 5%、远离 MA10 超过 8%，避免推送买点不友好的强势票
- 流通市值必须在 50 亿-400 亿
- 收盘价必须站上 MA20
- 换手率按市值动态分层：
  - 50-100 亿：6%-18%
  - 100-200 亿：4%-14%
  - 200-400 亿：3%-10%

不再硬剔除：

- 量比低于 1：改为量价评分项
- 上方压力位过近：改为风险扣分
- MA20 低于 MA60：改为趋势扣分，不直接删除
- 分时均线上方占比不足：不再作为收盘后硬条件

## 评分

总分 100 分：

- 市场/相对强度：15
- 题材强度：25，真实行情通过 AkShare/东方财富概念板块填充热门题材排名；接口不可用时按中性题材评分
- 资金流扩展项：主力净流入加分、净流出扣分；未接入时中性
- 趋势结构：20
- 量价配合：20
- 风险位置：10
- 流动性/市值：10

默认 70 分以上进入观察候选，80 分以上为重点候选。

推送语义：

- `strong`：重点候选
- `watch`：观察候选
- 无候选：仍推送“今日无符合策略的股票，服务正常运行”

## CSV 字段

列表字段使用 `|` 分隔：

- `same_time_volumes_5d`: 过去 5 个交易日同一时刻累计成交量
- `recent_daily_volumes`: 最近几个交易日成交量

布尔字段支持 `true/false`、`1/0`、`yes/no`、`是`。
