# 飞书 IM 采集 — 用户指南

通过 **飞书开放平台 API** 拉取指定群聊/单聊的历史消息（只读），写入 `data/raw/{date}/feishu_chat.json`，再归并进 digest。

> 与「飞书日程 CalDAV」是两套独立配置：日程用 `feishu.caldav`，IM 用 `feishu.chat`。

## 1. 前置条件

- 企业飞书管理员可 **审批应用权限**
- 目标 **群聊** 中需能添加 **自建应用机器人**
- 外部群、部分保密群可能无法拉取历史消息（以飞书 API 限制为准）

## 2. 创建企业自建应用

1. 打开 [飞书开放平台](https://open.feishu.cn/app) → **创建企业自建应用**
2. 记录 **App ID**、**App Secret**（凭证与基础信息页）
3. **应用能力 → 机器人**：开启机器人能力并发布应用（至少发布到测试版/正式版，按企业流程）

## 3. 申请 API 权限

在 **权限管理** 中申请并等待管理员通过：

| 场景 | 建议权限 |
|------|----------|
| 基础（单聊/群聊拉历史） | `im:message:readonly` 或 `im:message.history:readonly` |
| **群聊** 历史消息 | 额外 **`im:message.group_msg`**（获取群组中所有消息） |
| 可选：列出群列表 | `im:chat:readonly` |

权限名称以控制台实际文案为准；群聊必须同时具备「基础 IM 读权限」+「群消息读权限」。

## 4. 将机器人加入目标群

1. 在飞书客户端打开目标群 → **设置 → 群机器人 → 添加机器人**
2. 选择你创建的自建应用机器人
3. 确认机器人已在群内（否则 API 会报 `230002` 机器人不在群中）

## 5. 获取 chat_id（open_chat_id）

`config.yaml` 中 `feishu.chat.chat_ids` 需填写会话 ID（形如 `oc_xxx`）。

**方式 A — 开放平台调试（推荐）**

1. 在应用后台 **API 调试台** 调用「获取用户或机器人所在的群列表」等接口
2. 从返回的 `chat_id` 字段复制

**方式 B — 本仓库调试脚本**

配置好 `app_id` / `app_secret` 后：

```bash
python scripts/debug_feishu_chat.py --list-chats
```

**单聊**：若需采集 1:1 会话，将对应 `chat_id` 填入 `p2p_chat_ids`（同样需机器人在该会话可见，且具备单聊读权限）。

## 6. 获取 my_open_id（可选）

若开启 `only_my_messages` 或 `only_mention_me`，需配置 `my_open_id`（形如 `ou_xxx`）：

- 飞书开放平台 **通讯录** 相关 API 查询本人 open_id
- 或从一条自己发送的消息 raw 字段中查看 `sender.id`

```bash
python scripts/debug_feishu_chat.py --whoami
```

## 7. 写入 config.yaml

```yaml
feishu:
  chat:
    enabled: true
    app_id: "cli_xxxxxxxx"
    app_secret: "xxxxxxxxxxxxxxxx"
    base_url: https://open.feishu.cn
    chat_ids:
      - oc_xxxxxxxxxxxxxxxx
    p2p_chat_ids: []
    only_my_messages: false
    only_mention_me: false
    my_open_id: ""
    keywords: []
    exclude_keywords: []
```

**过滤说明**

- `only_my_messages: true` — 只保留本人发送的消息
- `only_mention_me: true` — 只保留 @ 本人的消息
- `keywords` — 非空时，消息文本须命中任一关键词才保留
- `exclude_keywords` — 命中则排除

`config.yaml` 已在 `.gitignore` 中，**勿提交 Git**。

## 8. 验证采集

```bash
python scripts/collect_all.py --date today --sources feishu_chat
```

成功时输出类似：`└─ N 条 IM 消息（M 个会话）`，并生成 `data/raw/{date}/feishu_chat.json`。

归并进 digest：

```bash
python scripts/collect_all.py --date today --sources feishu_chat
# 或单独归并：
python scripts/merge_daily.py --date today
```

## 9. 常见问题

| 现象 | 处理 |
|------|------|
| `230006` 机器人能力未启用 | 应用后台开启机器人并重新发布 |
| `230002` 机器人不在群中 | 把机器人加入 `chat_ids` 对应群聊 |
| `230027` 权限不足 | 补申请 `im:message.group_msg` 等权限并让管理员通过 |
| 0 条消息 | 当天该群可能无消息；换有消息的日期；检查过滤项 |
| 只能看到单聊、群聊为空 | 未开 `im:message.group_msg` 或未加机器人入群 |
| 与日程/manual 重复 | 同一事项可能在 IM 与日程各一条，成文时可合并描述 |

## 10. 与日程采集并存

可同时启用 CalDAV 日程与 IM：

```yaml
feishu:
  enabled: true          # 日程 CalDAV 总开关
  caldav:
    username: "..."
    password: "..."
  chat:
    enabled: true        # IM 独立开关
    app_id: "cli_..."
    app_secret: "..."
    chat_ids: ["oc_..."]
```

采集时分别指定渠道：

```bash
python scripts/collect_all.py --date today --sources feishu,feishu_chat
```
