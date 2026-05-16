# Bot Commands 注册指南

## 需要在 Bot Father 注册的命令

在 Bot Father 中注册命令后，用户输入 `/` 时会显示命令列表，提升用户体验。

### 注册步骤

1. 打开 Telegram，找到 **@BotFather**
2. 发送 `/setcommands`
3. 选择你的机器人
4. 选择语言（如 `zh` 中文 或 `en` 英文）
5. 粘贴下面的命令列表
6. 发送完成

---

## 推荐注册的命令（用户常用）

### 中文版本

```
start - 初始化机器人，清除上下文，重置设置
help - 查看帮助信息和使用说明
menu - 打开设置菜单
```

### 英文版本

```
start - Initialize bot, clear context, reset settings
help - Show help information and usage instructions
menu - Open settings menu
```

---

## 完整命令列表（包含管理命令）

如果你想让所有命令都显示在命令列表中，可以使用以下完整版本：

### 中文版本

```
start - 初始化机器人，清除上下文，重置设置
help - 查看帮助信息和使用说明
menu - 打开设置菜单
ban - 封禁用户（管理员）
unban - 解封用户（管理员）
kick - 踢出用户（管理员）
warn - 警告用户（管理员）
mute - 禁言用户（管理员）
del - 删除消息（管理员）
stats - 查看违规统计（管理员）
kwadd - 添加屏蔽词（管理员）
kwdel - 删除屏蔽词（管理员）
kwlist - 查看屏蔽词列表（管理员）
```

### 英文版本

```
start - Initialize bot, clear context, reset settings
help - Show help information and usage instructions
menu - Open settings menu
ban - Ban user (Admin only)
unban - Unban user (Admin only)
kick - Kick user (Admin only)
warn - Warn user (Admin only)
mute - Mute user (Admin only)
del - Delete message (Admin only)
stats - View violation statistics (Admin only)
kwadd - Add blocked keyword (Admin only)
kwdel - Remove blocked keyword (Admin only)
kwlist - List blocked keywords (Admin only)
```

---

## 命令说明

### 用户命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `/start` | 初始化机器人，清除上下文，重置所有设置 | 所有用户 |
| `/help` | 显示帮助信息和使用说明 | 所有用户 |
| `/menu` | 打开设置菜单，选择模型和功能 | 所有用户 |

### 管理命令（仅群组管理员）

| 命令 | 说明 | 权限要求 |
|------|------|----------|
| `/ban` | 封禁用户，用户无法重新加入 | 群组管理员 |
| `/unban` | 解封之前被封禁的用户 | 群组管理员 |
| `/kick` | 踢出用户，用户可以重新加入 | 群组管理员 |
| `/warn` | 警告用户，记录警告次数 | 群组管理员 |
| `/mute` | 禁言用户，可设置时长（默认1小时） | 群组管理员 |
| `/del` | 删除指定的消息 | 群组管理员 |
| `/stats` | 查看违规统计信息（默认最近7天） | 群组管理员 |
| `/kwadd` | 添加屏蔽词（仅本群/频道生效） | 群组管理员 |
| `/kwdel` | 删除屏蔽词（仅本群/频道生效） | 群组管理员 |
| `/kwlist` | 查看自定义屏蔽词列表（仅本群/频道生效） | 群组管理员 |

---

## 快速注册命令（复制粘贴）

### 仅用户命令（推荐）

```
start - 初始化机器人，清除上下文，重置设置
help - 查看帮助信息和使用说明
menu - 打开设置菜单
```

### 包含管理命令（完整版）

```
start - 初始化机器人，清除上下文，重置设置
help - 查看帮助信息和使用说明
menu - 打开设置菜单
ban - 封禁用户（管理员）
unban - 解封用户（管理员）
kick - 踢出用户（管理员）
warn - 警告用户（管理员）
mute - 禁言用户（管理员）
del - 删除消息（管理员）
stats - 查看违规统计（管理员）
kwadd - 添加屏蔽词（管理员）
kwdel - 删除屏蔽词（管理员）
kwlist - 查看屏蔽词列表（管理员）
```

---

## 注意事项

1. **命令格式**：每行一个命令，格式为 `命令 - 描述`
2. **命令数量**：Telegram 限制最多 100 个命令
3. **多语言**：可以为不同语言设置不同的命令列表
4. **更新命令**：修改命令列表后，用户可能需要重启 Telegram 才能看到更新
5. **管理命令**：管理命令建议只在群组中使用，私聊中可能不需要显示

---

## 推荐配置

**对于大多数用户**：只注册用户命令（start, help, menu）即可

**对于群组管理机器人**：可以注册完整命令列表，方便管理员使用

---

## 示例对话

```
你: /setcommands
BotFather: 选择你的机器人
你: [选择你的机器人]
BotFather: 选择语言
你: zh
BotFather: 发送命令列表
你: [粘贴上面的命令列表]
BotFather: ✅ 命令已设置
```

---

## 验证

注册完成后，在 Telegram 中：
1. 打开与机器人的对话
2. 输入 `/` 
3. 应该能看到注册的命令列表

