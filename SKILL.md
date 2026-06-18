---
name: daily-work-digest
description: |
  从多维度采集并汇总日常工作内容（代码提交、聊天记录、文档编辑、会议日历、手动补记等），归并为 digest 后生成日报、周报。
  Git 只是采集渠道之一，非本技能的全部范围；各渠道由独立 Adapter 脚本接入，统一写入 data/raw/ 再归并。
  当用户说「生成今天的工作日报」「汇总本周工作」「收集工作记录」「帮我写周报」「今天做了什么」「写日报」「写周报」时使用本技能。
  基于本仓库 Python 脚本已采集的真实数据成文，禁止编造未采集到的工作项。
tags: [工作日报, 周报, 工作内容, 日报生成, 多源采集, 工作记录, 内容聚合]
version: 1.0
author: 用户
---

# 每日工作摘要（daily-work-digest）

本技能通过**本仓库根目录**的多渠道采集脚本，从代码、沟通、文档、会议等维度收集工作线索，归并为 digest 后由 Agent 生成日报/周报。

**适用环境**：任何能读取本项目、执行终端命令的 AI 助手（如 **Cursor、Claude Code、Windsurf**）。`SKILL.md` 是编排说明，**不绑定某一 IDE**。用户无需会编程，用自然语言提需求即可。

## 采集渠道（数据源）

本工程采用 **Adapter 模式**：每个渠道独立采集，统一写入 `data/raw/{date}/`，再由 `merge_daily.py` 归并。

| 渠道 | 实现 | 状态 |
|------|------|------|
| 代码提交（Git） | `collectors/git.py` · `GitCollector` | ✅ 已实现 |
| 手动补记 | `collectors/manual.py` · `ManualCollector` | ✅ 已实现 |
| 企业微信日程 | `collectors/wecom_schedule.py` · CalDAV | ✅ 已实现 |
| 钉钉/飞书日程 | 复用 `collectors/calendar/caldav_client.py` | 🔜 待接入 |
| 聊天记录 | `collectors/chat.py`（规划） | 🔜 待接入 |
| 文档库 | `collectors/docs.py`（规划） | 🔜 待接入 |
| PR / Issue | `collectors/issue.py`（规划） | 🔜 待接入 |

**L1 对外入口**：`scripts/collect_all.py`（调度各 Collector，继承 `BaseCollector`）

**说明**：企微日程需在 `config.yaml` 配置 CalDAV 账号（见 `docs/企微日程采集-用户指南.md`）。成文时只使用**已采集**渠道的数据。

## 环境准备（Agent 必读）

**核心原则**：使用本技能前，若缺少运行条件（Python、依赖包、config.yaml、git.repos 配置等），Agent **须先检测 → 用白话告知缺什么、打算做什么 → 征得用户同意 → 再自行在终端处理**。不要把 `pip install`、`python scripts/...` 等命令丢给用户执行。

**典型流程：**

1. **检测**：工作目录是否为项目根（含 `scripts/collect_all.py`）、Python 3.10+ 是否可用、依赖是否已装、`config.yaml` 是否存在。
2. **说明并征得同意**（示例）：「当前还没装依赖，我可以在项目里执行安装，大约 1 分钟，是否继续？」
3. **用户同意后，Agent 自行完成**：切换目录、`pip install -r requirements.txt`、运行采集/归并命令。
4. **配置检查**：`git.repos` 必须填**用户实际提交代码的项目**（有 `.git` 的目录），不要填本工具目录（若未 git init）。
5. **仅 Agent 无法代劳时再请用户配合**：本机未装 Python、IDE 未授权终端需用户点允许。

**禁止**：跳过采集直接编造日报；未经用户同意擅自修改系统配置；将 `data/raw/` 上传到外部服务（除非用户明确要求）。

## 如何唤起本技能

本仓库根目录的 `SKILL.md` 即技能说明。Agent 被唤起后，按本文档执行采集、读 digest、成文。

| 工具 | 常见唤起方式 |
|------|----------------|
| **Cursor** | `@SKILL.md` 或 `@daily-work-digest` + 需求 |
| **Claude Code** | 在项目目录对话；说「按 SKILL.md 生成日报」或引用本文件 |
| **Windsurf 等** | 打开本项目，用自然语言描述需求，并指明遵循 `SKILL.md` |

**通用说法**（各工具均适用）：「生成今天的工作日报」「汇总本周工作」「帮我写周报」——Agent 应主动读取本文件与 `data/digest/`。

## 何时使用本技能

- 用户要写**日报**或**周报**
- 用户想汇总今天/本周做了什么（不限于写代码）
- 用户要求从多维度工作记录生成报告
- 用户说「收集工作记录」「今天做了什么」

## 数据处理分工

| 层级 | 执行者 | 做什么 |
|------|--------|--------|
| L1 采集 | `collect_all.py` → `collectors/*` | 各渠道 Adapter → `data/raw/` |
| L2 规则 | `merge_daily.py` → `processors/merge.py` | 归并、打标签、输出 `data/digest/` |
| L3 成文 | **Agent** | 读 digest + 模板，写日报/周报；**禁止编造** |

## 标准工作流

### 生成日报

1. 确定日期（默认 `today`，或用户指定的 `yesterday` / `YYYY-MM-DD`）。
2. 若 `data/digest/{date}.json` 不存在，或用户要求刷新：

```bash
python scripts/collect_all.py --date today
```

或分步：

```bash
python scripts/collect_all.py --date today --collect-only
python scripts/merge_daily.py --date today
```

3. 读取 `data/digest/{date}.json`、`data/manual/{date}.md`（若存在）、`templates/daily.md`。
4. 按模板输出日报：
   - **仅**使用 digest.events 与 manual 中的条目
   - 将 commit message 改写为业务可读描述（结合 `detail` 中的 repo、文件变更数）
   - 按 tags 分组：开发 / 协作 / 文档 / 会议
   - 同类 commit 可合并为一条摘要
5. 询问用户是否有遗漏；若有，追加到 `data/manual/{date}.md` 后重新执行 `merge_daily.py`。

### 生成周报

1. 确保本周各工作日已有 daily digest；缺失则逐日采集。
2. 运行：

```bash
python scripts/merge_daily.py --date today --week
```

3. 读取 `data/digest/week-{本周一日期}.json` 与 `templates/weekly.md`。
4. 按周汇总，禁止编造。

## 成文规则（硬性）

- **禁止**添加 digest 中不存在的工作项。
- **禁止**臆测未在 commit/detail 中出现的功能名称。
- manual 中的协作、会议类内容**必须**体现在日报中。
- 用户确认后的成稿可保存到 `data/reports/daily-YYYY-MM-DD.md` 或 `data/reports/weekly-YYYY-MM-DD.md`。

## 手动补记格式

写入 `data/manual/YYYY-MM-DD.md`：

```markdown
- 16:00 与产品对齐下周需求
- Code Review：支付模块 PR
```

保存后执行：

```bash
python scripts/merge_daily.py --date YYYY-MM-DD
```

## 常用命令

```bash
python scripts/collect_all.py --date today
python scripts/collect_all.py --date today --sources git,manual --collect-only
python scripts/merge_daily.py --date yesterday
python scripts/merge_daily.py --date today --week
```

## 示例

**用户（Cursor）**：`@SKILL.md 生成今天的工作日报`

**用户（Claude Code 等）**：`按 SKILL.md 生成今天的工作日报`

**Agent**：
1. 检查 `data/digest/{today}.json`，若无则运行 `collect_all.py`
2. 读取 digest 中 events，按 `templates/daily.md` 结构输出
3. 询问是否有遗漏需补记

**用户**：`帮我写本周周报`（或 `@SKILL.md 帮我写本周周报`）

**Agent**：
1. 检查本周各日 digest，缺失则逐日采集
2. 运行 `merge_daily.py --week`
3. 按 `templates/weekly.md` 汇总输出

## 故障排查

| 现象 | 处理 |
|------|------|
| digest 为空 / 0 条事件 | 检查 `config.yaml` 的 `git.repos` 是否指向**有 .git 的业务项目** |
| 提示「不是 Git 仓库」 | 该路径未 `git init`，更换为实际开发项目路径 |
| 有提交但未采集 | 检查 `author_email` 是否与 Git 提交邮箱一致；检查 `exclude_patterns` |
| 时区错误 | 执行 `pip install tzdata`，确认 `timezone: Asia/Shanghai` |

更多设计细节见 `docs/技术文档.md`。
