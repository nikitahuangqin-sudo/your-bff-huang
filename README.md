# your-bff-huang

有些文章生来属于聊天框。  
有些文章努力一下，可以去微信公众号。  
这个仓库负责中间那一点点不体面的搬运、整理、润色、递话，以及必要时替你假装一切都很从容。

它还有一个比较私人的底色：  
像女儿春游前一晚，家里书包还没完全收好，水壶晾在一边，明天要早起，但窗口和消息提示还亮着。  
希望女儿和网瘾妈妈和谐共处。  
希望 1988 年的黄女士，在内容、生活和一点没关掉的在线状态之间，依然保留某种轻微体面。

它做的事并不神秘：

- 从 Telegram 接住一篇还带着输入法温度的文章
- 按固定格式拆开标题、摘要、正文和一点点体面
- 重新排版成更适合微信公众号存活的样子
- 生成草稿，提交发布，再看看它最后有没有真的活下来

它不承诺：

- 替你成为媒体人
- 替你拥有稳定的选题
- 替微信平台改变脾气
- 替任何过长的作者名通过字段校验

## 它比较适合谁

适合那些：

- 会先把内容发给机器人，再决定要不要发给世界的人
- 想把“发布”这件事做得像自然发生，而不是行政流程的人
- 对自动化有兴趣，但又不想把每一步都写成企业培训手册的人

## 投稿格式

```text
投稿
标题：这里填写文章标题
摘要：这里填写简短摘要，可留空
作者：这里填写作者名，可留空
原文链接：这里填写原始链接，可留空
正文：
这里开始写正文。
```

如果你只是想看模板，仓库里还有一份现成的：

- [templates/submission-template.txt](/Users/moltbot/telegram-wechat-publisher/templates/submission-template.txt)

## 目录

- [SKILL.md](/Users/moltbot/telegram-wechat-publisher/SKILL.md)：技能本体，给 agent 看的
- [scripts/parse_telegram_submission.py](/Users/moltbot/telegram-wechat-publisher/scripts/parse_telegram_submission.py)：把固定格式消息拆开
- [scripts/publish_wechat_article.py](/Users/moltbot/telegram-wechat-publisher/scripts/publish_wechat_article.py)：渲染、建草稿、发发布、查状态
- [templates/env.example](/Users/moltbot/telegram-wechat-publisher/templates/env.example)：环境变量模板

## 最低限度的使用方法

1. 准备 Telegram bot token。
2. 准备微信公众号 `AppID` 和 `AppSecret`。
3. 按 [templates/env.example](/Users/moltbot/telegram-wechat-publisher/templates/env.example) 配好环境变量。
4. 让你的运行时接收 Telegram 消息。
5. 把文章发过来，先生成草稿，再决定要不要发布。

## 一点现实

微信接口不是诗歌，它有额度、权限、白名单、长度限制，还有一些不太愿意解释自己的时刻。  
所以这个仓库的气质大概是：表面温柔，内部全是判断分支。

如果它刚好帮你把一篇文章从“先发群里看看”送到“已经发出去了”，那它已经完成使命。

如果再多一点的话，可能就是替某位 1988 年的黄女士，给深夜、母职、网感和发布欲之间，搭了一座不算太吵的小桥。
