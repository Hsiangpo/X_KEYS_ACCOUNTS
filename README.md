# X 协议爬虫使用说明

## 项目目标
按“账号 + 关键词 + 时间范围”抓取 X 帖子，输出结构化数据，支持批量运行与日志留存，便于业务分析和交付归档。

## 交付结果
- 输入：`docs/Accounts.txt`、`docs/Keys.txt`
- 输出：
  - `output/<run_id>/data.jsonl`（数据结果）
  - `output/<run_id>/crawl.log`（完整运行日志）

## 快速启动（Windows PowerShell）
### 1) 进入目录
```powershell
cd D:\Develop\masterpiece\Spider\Website\x
```

### 2) 创建并激活虚拟环境
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3) 安装依赖
```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

### 4) 运行抓取
```powershell
python run.py <start_date> <end_date>
```

示例：
```powershell
python run.py 2021_9_1 2026_2_19
```

日期格式固定为 `YYYY_M_D`，开始和结束日期都包含当天。

## 输入文件说明
### 账号文件：`docs/Accounts.txt`
每行一个账号主页链接，例如：
```text
https://x.com/NBCOlympics
https://x.com/OpenAI
```

### 关键词文件：`docs/Keys.txt`
每行一个关键词规则，规则如下：
- 行内多词：AND（必须全部命中）
- 行间多行：OR（命中任一行即可）
- 行内分隔符支持：空格、`,`、`，`、`+`

示例：
```text
China Climate
China,Energy
codex+OpenAI
```

## 首次登录说明
首次运行或会话失效时，程序会自动打开 X 官方登录页。
登录成功后会自动保存 Cookie 到：
`state/cookies.json`

## 输出字段中文释义
- `account`：账号标识（账号 handle）
- `keyword`：命中时使用的关键词规则
- `post_time`：帖子发布时间（UTC，ISO 8601）
- `text`：帖子正文
- `post_url`：帖子链接
- `views`：浏览量（字符串，可能为空）
- `likes`：点赞数（字符串）
- `reposts`：转发数（字符串）
- `replies`：评论数（字符串）
- `quoted_text`：被引用/被转发原文文本（无对应内容时为空）
- `error`：错误信息（为空表示正常记录）

## 常见情况
- `quoted_text` 为空：通常表示该帖子不是引用/转发结构，或接口未返回对应对象，属于正常情况。
- 出现 `429`：程序会自动等待并重试，建议不要同时开启过多抓取进程。

## 可选参数
```powershell
python run.py <start_date> <end_date> `
  --accounts-file docs/Accounts.txt `
  --keys-file docs/Keys.txt `
  --cookies-file state/cookies.json
```

## 交付前自检（建议）
```powershell
python -m pytest -q
powershell -File scripts/run_ci_gate.ps1 -MaxFileLines 1000 -MaxFuncLines 200 -MaxFilesPerDir 10
```
