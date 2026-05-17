"""群管命令说明（对齐 bayes_spam_sniper README_zh.org）。"""

GROUP_ADMIN_HELP_HTML = """
<b>📋 喵喵 · 贝叶斯广告拦截</b>

实现思路参考 <a href="https://github.com/ramsayleung/bayes_spam_sniper">bayes_spam_sniper</a>：
朴素贝叶斯 + 自学习，<b>不再使用关键词黑名单</b>。

<b>使用前</b>
1. 将机器人加入群组并授予管理员（删消息、封禁用户）
2. 机器人自动扫描每条消息；模型数据在 <code>data/bayes_spam.db</code>

<b>━━ 自动行为（无需命令）━━</b>
• 贝叶斯判定为广告（默认概率 ≥ 94%）→ <b>删除消息 + 群内警告</b>（含群管理员发的广告，第 n/3 次）
• 同一用户累计警告达 <code>SPAM_BAN_THRESHOLD</code> 次（默认 3）→ 踢出或封禁（<code>SPAM_ESCALATE_ACTION</code>，默认 kick）
• 另含汉字故意加空格规则（如「跟 单 像 捡 钱」）
• <b>新人 / 首图 / 入群不足 7 天</b> 发图 → 视觉审核（广告/诈骗/色情等）；违规则删图并在群内<b>简短说明</b>，不做闲聊识图

<b>━━ 官方四类命令（与 BSS 一致）━━</b>

<b>/markspam</b> 🔒
回复要处理的垃圾消息。删除消息、封禁用户，并以该文本<b>训练为广告</b>（高置信度，全群模型受益）。

<b>/listbanuser</b> 🔒
查看本群已封禁用户列表。解封：回复该用户任意消息，发送 <code>/unban</code>。

<b>/listspam</b> 🔒
查看近期被判定/记录的广告消息（含自动删除的条目）。
若某条为误杀：发送 <code>/markham &lt;编号&gt;</code>（编号见列表前的 #数字）。

<b>/feedspam</b> 文本
投喂广告样本训练，无需回复消息；群内或私聊均可。
例：<code>/feedspam 加微信刷单日赚上千</code>

<b>━━ 补充命令 ━━</b>

<b>/markham</b> 🔒 — 两种方式标为正常：
• <code>/markham 12</code> — 配合 <code>/listspam</code> 列表中的 #编号
• 回复一条消息 — 将该正文训练为正常（等同 BSS 在 listspam 里标正常）

<b>/grouphelp</b> — 显示本说明

<b>━━ 可选扩展（手动群管）━━</b>
<code>/unban</code> <code>/del</code> <code>/mute</code> <code>/ban</code> <code>/kick</code> <code>/warn</code>
<code>/ignore</code> <code>/unignore</code> <code>/ignorelist</code> <code>/stats</code>

<b>━━ 环境变量 ━━</b>
<code>BAYES_SPAM_ENABLED</code> · <code>BAYES_SPAM_THRESHOLD</code>（默认 0.94）
<code>SPAM_BAN_THRESHOLD</code>（默认 3）· <code>SPAM_ESCALATE_ACTION</code>（kick/ban）
<code>BAYES_CHINESE_SPACE_THRESHOLD</code>
<code>GROUP_IMAGE_MOD_ENABLED</code> · <code>GROUP_IMAGE_VIOLATION_CONFIDENCE</code>（默认 0.72）

<b>误删怎么办？</b>
用 <code>/listspam</code> 查看记录，再用 <code>/markham &lt;编号&gt;</code> 纠正；漏网广告用 <code>/markspam</code> 回复训练。
""".strip()
