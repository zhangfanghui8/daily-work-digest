# daily-work-digest

**帮你自动汇总每天做了什么，并用 AI 助手一键生成日报、周报。**

写日报时经常想不起当天开了什么会、改了哪些代码、还处理了哪些杂事？这个项目会从你常用的工作来源里**自动采集线索**，整理成一份摘要，再交给 **AI 助手**（Cursor、Claude Code、Windsurf 等）按 `SKILL.md` 帮你写成正式的日报或周报。

---

## 能帮你做什么

| 场景 | 说明 |
|------|------|
| **写日报** | 汇总当天的代码提交、会议、手动补记等，生成结构化日报 |
| **写周报** | 把本周各天的记录合并，生成周报 |
| **减少遗漏** | 会议、协作类工作往往没有代码痕迹，可通过日程和手动补记补上 |
| **本地私密** | 数据保存在本机 `data/` 目录，不上传云端 |

---

## 目前支持的数据来源

| 来源 | 是否需要配置 |
|------|----------------|
| **Git 提交** | 需在 `config.yaml` 填写本地仓库路径 |
| **手动补记** | 可选，在 `data/manual/` 写 Markdown 即可 |
| **企业微信日程** | 可选，需配置 CalDAV 账号（见下方文档） |
| 钉钉 / 飞书日程 | 规划中 |
| 聊天记录、文档等 | 规划中 |

---

## 怎么用（三步）

### 1. 安装

需要 **Python 3.10+** 和 **Git**。

```bash
cd daily-work-digest
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy config.example.yaml config.yaml   # macOS/Linux: cp config.example.yaml config.yaml
```

编辑 `config.yaml`，至少配置你要扫描的 **Git 仓库路径**（填业务项目路径，不要填本工具目录）。

### 2. 采集今天的工作记录

```bash
python scripts/collect_all.py --date today
```

执行成功后，当天的工作线索会写入本地 `data/` 目录。

### 3. 用 AI 助手生成日报

打开本项目，让**能读项目文件、能执行终端命令**的 AI 助手按根目录 `SKILL.md` 的说明成文。不同工具唤起方式略有不同：

| 工具 | 示例说法 |
|------|----------|
| **Cursor** | `@SKILL.md 生成今天的工作日报` |
| **Claude Code** | `按 SKILL.md 生成今天的工作日报`（或 `@SKILL.md`） |
| **Windsurf 等** | `读取 SKILL.md，根据今天的 digest 写日报` |

也可以直接用自然语言，例如：**「生成今天的工作日报」**、**「根据本周记录帮我写周报」**——助手应读取 `SKILL.md` 与 `data/digest/`，**不会编造**未采集到的工作内容。

---

## 可选配置

- **手动补记**：在 `data/manual/` 按日期写 Markdown，记录会议、沟通等。格式见 [手动补记示例](docs/手动补记示例.md)。
- **企业微信日程**：在手机企微「日程 → 同步至其他日历」获取账号密码，写入 `config.yaml`。详见 [企微日程采集指南](docs/企微日程采集-用户指南.md)。
- **定时采集**：可用 Windows 任务计划程序每天固定时间运行 `collect_all.py`，详见 [快速开始](docs/快速开始.md)。

---

## 常见问题

| 问题 | 处理 |
|------|------|
| 采集结果为空 | 当天可能没有 Git 提交；可用手动补记或检查 `git.repos` 路径 |
| 企微日程报 403 | 重新获取同步密码，或查看 [企微指南](docs/企微日程采集-用户指南.md) |
| 找不到 config.yaml | 从 `config.example.yaml` 复制一份 |

更多安装与排错说明见 **[快速开始](docs/快速开始.md)**。架构与实现细节见 **[技术文档](docs/技术文档.md)**。

---

## 文档

| 文档 | 说明 |
|------|------|
| [快速开始](docs/快速开始.md) | 安装、配置、周报、定时任务 |
| [手动补记示例](docs/手动补记示例.md) | 无 Git 痕迹的工作如何补记 |
| [企微日程采集](docs/企微日程采集-用户指南.md) | CalDAV 配置与 403 排查 |
| [技术文档](docs/技术文档.md) | 架构、数据模型、路线图（开发者） |

> **发布前提醒**：`config.yaml` 含个人路径与密钥，已在 `.gitignore` 中，请勿 `git add` 提交。
