# X 协议爬虫使用说明

## 1. 项目简介
本项目用于在 X（原 Twitter）上按“账号 + 关键词 + 时间范围”抓取帖子，并输出为 `JSONL` 文件。

抓取方式为纯协议请求（`httpx`），不依赖页面采集。

## 2. 功能范围
- 按账号、关键词检索帖子
- 按发帖时间过滤（开始和结束日期都包含）
- 输出字段包括：
  - `account`
  - `keyword`
  - `post_time`
  - `text`
  - `post_url`
  - `views`
  - `likes`
  - `reposts`
  - `replies`
  - `quoted_text`
  - `error`
- 运行日志落盘，便于排障

## 3. 环境要求
- Python 3.10 及以上
- 操作系统：Windows / Linux / macOS
- 网络可访问 `x.com`

## 4. 安装步骤（从零开始）
以下命令以 Windows PowerShell 为例。

### 4.1 进入项目目录
```powershell
cd D:\Develop\masterpiece\Spider\Website\x
```

### 4.2 创建虚拟环境
```powershell
python -m venv .venv
```

### 4.3 激活虚拟环境
```powershell
.\.venv\Scripts\Activate.ps1
```

### 4.4 安装依赖
```powershell
pip install -r requirements.txt
```

### 4.5 首次安装 Playwright 浏览器内核（建议执行一次）
```powershell
python -m playwright install chromium
```

## 5. 输入文件准备
### 5.1 账号文件：`docs/Accounts.txt`
每行一个账号主页链接，例如：
```text
https://x.com/NBCOlympics
https://x.com/OpenAI
```

### 5.2 关键词文件：`docs/Keys.txt`
每行一个关键词规则，支持以下规则：
- 行内多词：AND（必须全部命中）
- 行间多行：OR（命中任一行即可）
- 行内分隔符支持：空格、英文逗号 `,`、中文逗号 `，`、加号 `+`

示例：
```text
China Climate
China,Energy
codex+OpenAI
```

## 6. 启动命令
```powershell
python run.py <start_date> <end_date>
```

示例：
```powershell
python run.py 2021_9_1 2026_2_19
```

日期格式固定为：`YYYY_M_D`  
时间边界说明：开始日期和结束日期都包含当天。

## 7. 首次登录说明
首次运行或会话失效时，程序会自动打开 X 官方登录页：
1. 在打开的浏览器中完成登录
2. 程序自动捕获并保存 Cookie
3. 后续运行优先复用本地 Cookie

默认 Cookie 文件路径：
`state/cookies.json`

## 8. 输出结果位置
每次运行会创建独立目录：
`output/<run_id>/`

包含两个文件：
- 数据文件：`output/<run_id>/data.jsonl`
- 运行日志：`output/<run_id>/crawl.log`

## 9. JSONL 字段说明
每行一条 JSON 记录，常见示例：
```json
{
  "account": "OpenAI",
  "keyword": "codex",
  "post_time": "2026-02-19T12:34:56+00:00",
  "text": "...",
  "post_url": "https://x.com/OpenAI/status/1234567890",
  "views": "12345",
  "likes": "100",
  "reposts": "20",
  "replies": "5",
  "quoted_text": "",
  "error": ""
}
```

字段含义（逐项）：
- `account`：账号标识（即账号 handle，例如 `OpenAI`）
- `keyword`：命中时使用的关键词规则（来自 `docs/Keys.txt` 的原规则行）
- `post_time`：帖子发布时间（UTC 时间，ISO 8601 格式）
- `text`：帖子正文文本
- `post_url`：帖子完整链接
- `views`：浏览量（字符串；接口无值时可能为空）
- `likes`：点赞数（字符串）
- `reposts`：转发数（字符串）
- `replies`：评论数（字符串）
- `quoted_text`：被引用/被转发原文文本（无对应内容时为空字符串）
- `error`：错误信息字段（为空表示正常数据，非空表示该条为错误记录）

## 10. 常见问题
### 10.1 出现 429 限流
程序会根据响应头自动等待并重试，属于正常保护机制。  
建议不要并发开过多进程同时抓取。

### 10.2 `quoted_text` 为空
不一定是程序问题。很多帖子本身没有引用/转发对象，或接口返回中无对应字段，此时为空是正常结果。

### 10.3 登录后仍提示鉴权失败
可删除本地 Cookie 后重试：
```powershell
Remove-Item state\cookies.json -Force
python run.py 2025_1_1 2025_1_2
```

## 11. 可选参数
```powershell
python run.py <start_date> <end_date> `
  --accounts-file docs/Accounts.txt `
  --keys-file docs/Keys.txt `
  --cookies-file state/cookies.json
```

## 12. 交付前自检命令（建议）
```powershell
python -m pytest -q
powershell -File scripts/run_ci_gate.ps1 -MaxFileLines 1000 -MaxFuncLines 200 -MaxFilesPerDir 10
```
