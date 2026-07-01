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
| 飞书日程 | `collectors/feishu_schedule.py` · CalDAV | ✅ 已实现 |
| 飞书 IM | `collectors/feishu_chat.py` · 开放平台 API | ✅ 已实现 |
| 飞书文档 | `collectors/feishu_docs.py` · 搜索 API（L1 元数据） | ✅ 已实现 |
| 语雀文档 | `collectors/yuque_docs.py` · Open API（L1 元数据） | ✅ 已实现 |
| 钉钉日程 | `collectors/dingtalk_schedule.py` · CalDAV | ✅ 已实现 |
| 禅道 | `collectors/zentao.py` · REST API v2（Bug/需求/任务） | ✅ 已实现 |
| Jira（私有化） | `collectors/jira.py` · REST API v2 + JQL | ✅ 已实现 |
| PR / Issue | `collectors/issue.py`（规划） | 🔜 待接入 |

**L1 对外入口**：`scripts/collect_all.py`（调度各 Collector，继承 `BaseCollector`）

**说明**：企微/飞书/钉钉日程需在 `config.yaml` 配置 CalDAV 账号。飞书 IM / 飞书文档需自建应用；飞书文档 token 用 `feishu_oauth.py --login`。语雀文档支持 **Token** 或 **Cookie** 认证，`repos` 可留空自动发现（见 `docs/语雀文档采集-用户指南.md`）。成文时只使用**已采集**渠道的数据。

### 飞书文档授权（Agent 必读，面向非技术用户）

飞书要求用户在浏览器里**点一次「同意授权」**，这一步无法由程序代劳；除此以外 **Agent 应全部自动完成**，不要把命令行步骤丢给用户。

**检测**：`feishu.docs.enabled` 且 `data/.feishu_oauth.json`（或 `token_cache` 路径）是否存在且有效。

**若缺少 token，Agent 执行：**

1. 确认 `config.yaml` 已有 `feishu.docs.app_id` / `app_secret`（可与 `feishu.chat` 共用）；若缺，用白话请管理员提供或引导复制开放平台凭证。
2. 告知用户：「接下来会打开浏览器，请在飞书页面点 **同意/授权**，然后回来告诉我即可。」
3. 运行：

```bash
python scripts/feishu_oauth.py --login
```

4. 若报 **20027 offline_access**，改用：

```bash
python scripts/feishu_oauth.py --login --no-offline
```

5. 成功后运行采集：

```bash
python scripts/collect_all.py --date today --sources feishu_docs
```

**用户只需说**：「帮我连接飞书文档」「配置飞书文档采集」——Agent 按上述流程处理。

**一次性前置（通常由管理员完成，非每次）**：开放平台配置重定向 URL `http://127.0.0.1:8765/callback`、权限 `search:docs:read`（可选 `offline_access`）。详见 `docs/飞书文档采集-用户指南.md`。

### 语雀文档配置（Agent 必读）

语雀支持两种认证，用户**任选其一**：

| `auth_mode` | 凭证来源 | 适用 |
|-------------|----------|------|
| `token`（默认） | [Token 设置页](https://www.yuque.com/settings/tokens) | 有超级会员 |
| `cookie` | 浏览器 F12 → Cookies | 无超级会员 / Token 页不可用 |

**检测**：`yuque.docs.enabled`、对应凭证（Token 或 Cookie）。

**若未配置，先问用户能否创建 Token；若 Token 页需超级会员，改用 Cookie：**

1. **Token 模式**：创建 Token → 填入 `yuque.docs.token`，`auth_mode: token`
2. **Cookie 模式**：登录语雀 → F12 复制 Cookie → 填入 `yuque.docs.cookie`，`auth_mode: cookie`
3. **`repos` 可留空**，程序会自动扫描账号下知识库；用户想缩小范围时再填白名单

**采集：**

```bash
python scripts/collect_all.py --date today --sources yuque_docs
```

Cookie 过期（401）时提示用户从浏览器重新复制。详见 `docs/语雀文档采集-用户指南.md`。

### 禅道配置（Agent 必读）

禅道**没有**语雀那种页面申请的个人 Token。凭证通过 **Agent 代跑登录** 写入 `data/.zentao_token.json`，**禁止**要用户自己执行脚本，**禁止**把密码写进 `config.yaml`。

**检测**：`zentao.enabled` + `zentao.base_url`；或运行 `python scripts/zentao_auth.py --check`（JSON 输出，`status=auth_required` 表示需登录）。

**写日报时若 `digest.channels.zentao.status=failed` 且原因含「未找到禅道登录凭证」或 `auth_required`：**

1. **先问用户**（白话）：「今天日报要不要包含禅道的 Bug / 需求 / 任务？」
2. **用户同意** → 用白话说明有三种连法（**用户不自己跑脚本**），按用户选择执行：

| 方式 | 用户做什么 | Agent 做什么 |
|------|------------|--------------|
| **A. 已有 token** | 说「禅道 token 是 xxx」（可带账号） | `python scripts/zentao_auth.py --paste-token "TOKEN" --account 账号` |
| **B. 不知道 token 怎么拿** | 说「不知道怎么获取 token」 | **先教用户**（见下方「教用户获取 token」），拿到后再走 A |
| **C. 直接给账号密码** | 在对话里提供禅道账号+密码 | Agent 代跑登录换 token（见下方「代登录」） |

3. 看到 `ZENTAO_AUTH_OK` 后，Agent **自动**重采、归并、重写日报。
4. **用户拒绝** → 禅道写「当日未采集（用户跳过）」或省略。

**教用户获取 token（Agent 用白话逐步说明，勿丢文档链接了事）：**

1. 打开禅道 → **二次开发** → **API** / **API 调试**（不同版本入口名称略有差异）。
2. 找到 **获取 Token** 接口（v2：`POST /api.php/v2/users/login`；v1：`POST /api.php/v1/tokens`）。
3. 在调试台填入你的 **account**、**password**，点发送。
4. 响应 JSON 里的 `"token"` 字段即为凭证 → 复制整段 token 发给 Agent。
5. 说明：token **短期有效**，过期后重复上述步骤或改用方式 C。

**代登录（用户给了账号密码时，Agent 执行，密码不写 config.yaml）：**

```bash
# PowerShell
$env:ZENTAO_PASSWORD="用户提供的密码"; python scripts/zentao_auth.py --login --account 用户账号
```

或使用 `--password`（Agent 仅在当次命令使用，不写入配置文件）。凭证只写入 `data/.zentao_token.json`。

**为何禅道不像语雀？** 禅道没有「设置页申请长期个人 Token」；token 是登录接口换得的**短期会话凭证**。但用法一样——**拿到 token 交给 Agent 即可**；拿不到时 Agent 可代你登录。

**用户只需说**：「写日报」「要禅道数据」「禅道 token 是 xxx」「账号 xxx 密码 xxx 你帮我连」——Agent 处理，不把脚本当作业丢给用户。

详见 `docs/禅道采集-用户指南.md`。

### Jira 配置（Agent 必读 · 当前为私有化 Server/DC）

用户使用 **Personal Access Token（PAT）**，在 Jira 个人设置中创建，**不是** Atlassian Cloud 的 API Token 页面（Cloud 后续再加适配）。

**最简 config：**

```yaml
jira:
  enabled: true
  base_url: https://jira.your-company.com
  username: "登录名"
  api_token: ""   # 或 Agent 写入 data/.jira_token.json
```

**写日报时若 `digest.channels.jira.status=failed` 且含「未找到 Jira API Token」：**

1. 问用户要不要 Jira Issue/Bug/Story/Task 数据。
2. 用户同意 → 教用户创建 PAT（见 `docs/Jira采集-用户指南.md`），或用户直接发 PAT + 登录名。
3. Agent 代跑：`python scripts/jira_auth.py --paste-token "PAT" --username 登录名`
4. 自动重采、重写日报。

**用户说「不知道怎么获取 token」** → 用白话说明：Jira 右上角头像 → **个人设置 / Profile** → **Personal Access Tokens** → 创建并复制。

详见 `docs/Jira采集-用户指南.md`。

### 授权失败时的通用规则（Agent 必读）

| 渠道 | 用户无法代劳的部分 | Agent 应做 |
|------|-------------------|------------|
| **禅道** | 粘贴 token；或提供账号密码由 Agent 代登录；或按 Agent 指引在 API 调试台自取 token | 询问是否需要 → 按 A/B/C 处理 → 重采 |
| **Jira** | 在 Jira 个人设置创建 PAT 并粘贴给 Agent | 询问是否需要 → `--paste-token` → 重采 |
| **飞书文档** | 浏览器点「同意授权」 | 询问是否需要 → 代跑 `feishu_oauth.py --login` → 重采 |
| **语雀 Cookie** | 浏览器复制 Cookie | 询问是否需要 → 帮填 `config.yaml` 的 cookie → 重采 |
| **飞书 IM** | 管理员开权限 | 说明需管理员审批，**无法**代登录；日报标注采集失败原因 |

**硬性**：成文阶段发现 `failed` 时，**先尝试按上表补救**（征得用户同意），再输出最终日报；不要把终端命令当作给用户的「作业」。

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
3.5. **授权补救（Agent 自动，见「授权失败时的通用规则」）**：若已启用渠道因未登录/未授权导致 `failed`，**先问用户是否需要该渠道数据**；需要则 Agent 代跑登录/OAuth 并重采，再进入成文。不要把脚本命令丢给用户。
4. 按模板输出日报：
   - **仅**使用 digest.events 与 manual 中的条目填写 **「今日完成」**
   - **「进行中 / 明日计划 / 风险与阻塞」留空**（写 `-` 占位），供用户自行补充，Agent 不推断、不编造
   - **今日完成**按两个维度组织：
     - **大维度**：代码开发 · 日程 · 文档 · IM
     - **小维度（渠道）**：大维度下的具体来源，见下表
   - **渠道无 events 时**，读取 digest.`channels` 区分（**禁止混写、禁止编造**）：
     - `status=empty` →「**{label}：当日无记录**」（不写括号说明）
     - `status=failed` →「**{label}：采集失败**（{message}）」——**仅失败时用括号写原因**；若用户已明确跳过授权补救，可写「当日未采集（用户跳过）」
     - `status=not_collected` →「**{label}：未采集**（{message}）」
     - `status=ok` 且有 events → 正常列出，不写「采集成功」
     - 未出现在 `channels` → 配置未启用，成文省略
   - 将 commit message 改写为业务可读描述（结合 `detail` 中的 repo、分支、文件变更数）
   - 同类 commit 可合并为一条摘要
5. 询问用户是否有遗漏；若有，追加到 `data/manual/{date}.md` 后重新执行 `merge_daily.py`。

**digest → 维度映射（Agent 成文）**

| 大维度 | 小维度（渠道） | digest 识别 |
|--------|----------------|-------------|
| 代码开发 | Git 仓库（如 WdDataAgent） | `source=git`, `type=commit` |
| 日程 | 企微 / 飞书 / 钉钉 | `source=wecom\|feishu\|dingtalk`, `type=meeting` |
| 文档 | 飞书文档 / 语雀 | `source=feishu`, `type=document`；`source=yuque`, `type=document` |
| IM | 飞书 IM | `source=feishu`, `type=chat` |
| 禅道 | Bug / 需求 / 任务 | `source=zentao`, `type=bug\|story\|task` |
| Jira | Bug / Story / Task | `source=jira`, `type=bug\|story\|task\|issue` |
| （补记） | manual | `source=manual`，按内容归入合适大维度 |

### 生成周报

1. 确保本周各工作日已有 daily digest；缺失则逐日采集。
2. 运行：

```bash
python scripts/merge_daily.py --date today --week
```

3. 读取 `data/digest/week-{本周一日期}.json` 与 `templates/weekly.md`。
4. 按周汇总 **「本周成果」**（维度规则同日报；`channels` 含 `by_date` 时可标注哪几天失败/无记录），**「进行中 / 下周计划 / 问题与风险」留空**供用户填写；禁止编造。

## 成文规则（硬性）

- **禁止**添加 digest 中不存在的工作项。
- **禁止**臆测未在 commit/detail 中出现的功能名称。
- **禁止**自动填写「进行中 / 明日计划（周报为下周计划）/ 风险与阻塞」——留空供用户自填。
- manual 中的内容按语义归入 **今日完成 / 本周成果** 对应大维度。
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
python scripts/collect_all.py --date today --sources git,manual,wecom,feishu,dingtalk --collect-only
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
