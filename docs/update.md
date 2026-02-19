## v0.3.1 (2026-02-19)

### 新增
- 新增账号池：支持 `--cookies-pool-file`，按 `(account, keyword)` 任务轮转会话槽位。
- 新增 `tests/test_run_cookie_pool.py`，覆盖账号池路径解析与去重规则。

### 变更
- 限流策略回归为“低剩余额度主动等待到 reset”，移除高水位平滑节流逻辑。

## v0.3.0 (2026-02-19)

### 新增
- 新增“配额感知调度器”：记录 `x-rate-limit-remaining` / `x-rate-limit-reset`，低配额时主动等待。
- 新增 `tests/test_x_protocol_client.py` 配额调度相关测试用例（状态更新、主动等待、阈值跳过）。

### 变更
- 关键词规则增强：`docs/Keys.txt` 行内分隔符新增 `+`（与空格、`,`、`，` 等价）。
- 文档更新：`README.md`、`docs/PRD.md`、`docs/TECH.md` 同步配额策略与关键词规则。

### 修复
- 修复 `XProtocolClient` 中配额方法调用已接入但方法未实现的风险，补齐实现并回归通过。

## v0.2.0 (2026-02-19)

### 新增
- 新增仓内 `nx` 生成器：`src/client/x_transaction.py`。
- 新增 `tests/test_x_transaction.py`，覆盖 `ondemand` 提取与事务串生成稳定性。
- 新增 `js/analysis`、`js/dist`、`js/docs` 的 `x-client-transaction-id` 资料文件。

### 变更
- `src/client/x_protocol_client.py` 改为仅依赖仓内事务链路，不再依赖第三方事务库。
- 文档更新：`docs/TECH.md`、`docs/INTERFACE.md` 对齐 Chrome MCP 抓包结论。

### 修复
- 404 场景下的事务上下文刷新逻辑继续保留，确保 `nx` 失效后可重建重试。
- retweet 原文提取路径补齐后维持在 `quoted_text` 输出。
- 修复空结果翻页过长问题：新增重复 cursor 终止和连续空页上限。

### 依赖
- 删除：`xclienttransaction`
- 增加：`beautifulsoup4`
