# Jira 采集 — 用户指南（私有化 Server / Data Center）

通过 Jira **REST API v2 + JQL** 拉取指定日期与你相关的 **Issue** 变更（Bug / Story / Task 等 L1 元数据），供日报/周报使用。

> 当前实现面向 **私有化 Jira**（自建站点）。Atlassian Cloud（`*.atlassian.net`）后续再加，配置形态类似。

---

## 普通用户怎么用

对 AI 说：

```text
写今天的工作日报
```

若 Jira 未配置凭证，AI 会问你要不要 Jira 数据，并教你拿 **PAT** 或代你写入本地缓存。**你不需要自己跑脚本。**

---

## 最简配置

```yaml
jira:
  enabled: true
  base_url: https://jira.your-company.com
  username: "你的登录名"
  api_token: ""   # 也可由 AI 写入 data/.jira_token.json
```

`project_keys` 留空 = 查你有权限的全部项目。

---

## 如何获取 PAT（Personal Access Token）

1. 登录 **私有化 Jira**（浏览器打开你们的 `base_url`）。
2. 右上角 **头像** → **个人设置 / Profile**（不同版本文案略有差异）。
3. 找到 **Personal Access Tokens**（个人访问令牌）。
4. 点击 **Create token / 创建**，填写名称（如 `daily-work-digest`），复制生成的 token。
5. 发给 AI，例如：

```text
Jira PAT：粘贴这里
Jira 登录名：zhangfanghui
```

AI 会写入 `data/.jira_token.json` 并重采。

> **注意**：这是 Jira Server 的 PAT，不是 Atlassian 账号页（id.atlassian.com）的 Cloud API Token。

---

## 采集内容

| Issue 类型 | 日报示例 |
|------------|----------|
| Bug | 解决 PROJ-123「登录失败」 |
| Story | 更新 PROJ-456 需求状态 |
| Task | 完成 PROJ-789 联调任务 |

默认 JQL 仅包含 **指派给我 / 我报告** 且 **当天有更新** 的 Issue。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 未找到 PAT | 按上文创建 PAT 发给 AI |
| 401 / 403 | 检查 PAT 是否过期、账号是否有项目浏览权限 |
| 0 条记录 | 当天 Jira 可能无你的 Issue 更新 |
| 找不到 PAT 菜单 | Jira 需 **8.14+** 且管理员开启 PAT；请联系管理员 |

---

## 高级（AI 代跑）

```bash
python scripts/jira_auth.py --paste-token "PAT" --username 登录名
python scripts/jira_auth.py --check
```
