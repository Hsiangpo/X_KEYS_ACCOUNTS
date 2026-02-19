# TECH

## 1. 目标与分层
- 数据采集面严格走 `pc`（`httpx`）。
- 登录态通过官方登录链路获取（Playwright 仅用于人工登录窗口，不参与数据采集）。
- 抓包与接口研究通过 Chrome DevTools MCP 辅助完成。

## 2. 接口结论（Chrome MCP）
- 核心接口：`GET /i/api/graphql/{queryId}/SearchTimeline`
- 当前 `queryId`（2026-02-19 抓包）：`cGK-Qeg1XJc2sZ6kgQw_Iw`
- 关键请求头：
  - `authorization: Bearer ...`
  - `x-csrf-token: <ct0>`
  - `x-client-transaction-id: <dynamic>`
  - `x-twitter-auth-type: OAuth2Session`
  - `x-twitter-active-user: yes`
  - `x-twitter-client-language: en`
  - `referer: https://x.com/search?...`

## 3. nx 链路（x-client-transaction-id）
- 仓内实现：`src/client/x_transaction.py`
- 输入依赖：
  - `home_page`：`https://x.com` HTML
  - `ondemand_script`：`ondemand.s.<hash>a.js`
- 关键提取点：
  - `twitter-site-verification` meta
  - `loading-x-anim*` 帧节点
  - `ondemand.s` 脚本中的索引片段
- 生成流程：
  - 解析索引与关键字节位
  - 组合动画 key
  - 对 `method + path + timestamp + random + animation_key` 做摘要
  - 组装并输出 base64 风格事务串

## 4. 失败与重试策略
- `401/403`：抛 `AuthenticationError`，上层触发一次重登并续跑。
- `404`：强制刷新事务上下文后重试（应对 `nx` 上下文过期）。
- `429`：优先按 `x-rate-limit-reset` 等待到窗口重置；若无该头，走保守等待。
- 配额感知调度：当响应头给出 `x-rate-limit-remaining <= X_RATE_LIMIT_PROACTIVE_THRESHOLD` 且未到 `x-rate-limit-reset`，下一次请求前主动等待，减少连续 `429`。
- 日志观测：配额日志同时输出原始 `reset` 时间戳和北京时间（`reset_bj` / `重置北京时间`）。
- `5xx`：指数退避重试。
- 连续空页：`AccountSearchCrawler(max_empty_pages=3)` 自动停止，避免无命中时长时间翻页。
- 重复游标：检测重复 `cursor` 自动停止，避免循环。
- 最终失败写入 JSONL `error` 字段，不中断整批任务。

## 5. 配额参数（环境变量）
- `X_RATE_LIMIT_PROACTIVE_THRESHOLD`：触发主动等待的剩余额度阈值（默认 `0`）。
- `X_RATE_LIMIT_RESET_BUFFER_SECONDS`：到达 `reset` 后额外缓冲秒数（默认 `2`）。
- `X_MAX_RATE_LIMIT_WAIT_SECONDS`：单次最大等待秒数上限（默认 `900`）。
- `X_RATE_LIMIT_FALLBACK_WAIT_SECONDS`：缺失 `reset` 时的保守等待上限（默认 `180`）。

## 6. 账号池
- 启动参数：`--cookies-pool-file`（可选）。
- 文件格式：每行一个 `cookies.json` 路径；支持空行和 `#` 注释。
- 调度策略：主 `--cookies-file` + pool 文件共同组成槽位，按 `(account, keyword)` 轮转使用。
- 槽位鉴权失败：仅刷新该槽位会话，不影响其他槽位。

## 7. 当前实现文件
- `src/client/x_protocol_client.py`：协议请求、重试、事务头注入。
- `src/client/x_transaction.py`：仓内 `nx` 生成器。
- `src/auth/session_manager.py`：官方登录链路 + cookie 复用。
- `src/parser/post_parser.py`：主帖/引用帖/转发原文提取。
