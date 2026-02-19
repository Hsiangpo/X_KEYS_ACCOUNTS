# INTERFACE

## SearchTimeline
- Method: `GET`
- Path: `/i/api/graphql/{queryId}/SearchTimeline`
- Auth:
  - `authorization` (Bearer)
  - `auth_token` cookie
  - `ct0` cookie + `x-csrf-token`
  - `x-client-transaction-id` (dynamic nx)
- Query params:
  - `variables`: JSON string
  - `features`: JSON string

## variables
- `rawQuery`: 例如 `(from:OpenAI) codex since:2026-02-19 until:2026-02-20`
- `count`: 分页数量
- `cursor`: 翻页游标（可选）
- `querySource`: `typed_query`
- `product`: `Latest`
- `withGrokTranslatedBio`: `false`

## 输出字段（JSONL）
- `account`
- `keyword`
- `post_time`
- `text`
- `post_url`
- `views`
- `likes`
- `reposts`
- `replies`
- `quoted_text`（引用帖文本或转发原文）
- `error`

## 错误语义
- `error=""`：本行是正常命中数据。
- `error!= ""`：本行为错误记录（请求失败或解析失败），其余字段留空。
