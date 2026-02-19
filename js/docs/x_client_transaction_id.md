# x-client-transaction-id

## 1. 参数定位
- 目标头：`x-client-transaction-id`
- 作用：`SearchTimeline` 等 GraphQL 接口的 `nx` 校验字段之一
- 结论：该值需要动态生成，随机串不可替代

## 2. 依赖输入
- `home_page` (`https://x.com`)
  - `meta[name="twitter-site-verification"]`
  - `loading-x-anim*` 帧节点
- `ondemand` 脚本
  - `ondemand.s.<hash>a.js`
  - 脚本内索引片段（用于关键字节定位）
- 请求上下文
  - `method`
  - `path`
  - `unix_delta_seconds`
  - `random_byte`

## 3. 生成链路
1. 从 `home_page` 提取 `twitter-site-verification`，做 base64 解码。
2. 从 `ondemand` 脚本提取索引，确定 row/index 选择。
3. 从 `loading-x-anim*` 帧计算动画 key。
4. 拼接 `method + path + timestamp + random_keyword + animation_key` 做 `sha256`。
5. 组合 `key_bytes + time_bytes + digest[:16] + random_number`，再按随机字节异或。
6. base64（去掉 `=`）输出事务串。

## 4. 仓内实现
- 生产实现：`src/client/x_transaction.py`
- 协议接入：`src/client/x_protocol_client.py`
- 研究辅助：
  - `js/analysis/x_client_transaction_id_analysis.js`
  - `js/dist/x_client_transaction_id.js`

## 5. Chrome MCP 对照要点
- 抓包确认 `SearchTimeline` 请求头必须包含 `x-client-transaction-id`。
- 同会话下该值按请求动态变化（非固定常量）。
- 缺失或无效事务串时常出现 `404`（接口路径存在但请求校验失败）。
