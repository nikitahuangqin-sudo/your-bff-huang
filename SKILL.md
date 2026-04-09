---
name: telegram-wechat-publisher
description: Publish long-form articles from Telegram or direct chat into a WeChat Official Account. Use when the user wants article cleanup, WeChat-friendly typography, draft creation, publish submission, or publish-status checks.
version: 1.0.0
author: Codex
license: MIT
setup:
  help: "Prepare a Telegram bot token and a WeChat Official Account app id/app secret. Note: WeChat publish APIs can be unavailable for personal accounts and uncertified enterprise accounts."
  collect_secrets:
    - env_var: TELEGRAM_BOT_TOKEN
      prompt: "Telegram bot token"
      provider_url: "https://core.telegram.org/bots#6-botfather"
      secret: true
    - env_var: WECHAT_APP_ID
      prompt: "WeChat Official Account AppID"
      provider_url: "https://developers.weixin.qq.com/doc/service/api/base/api_getaccesstoken"
      secret: true
    - env_var: WECHAT_APP_SECRET
      prompt: "WeChat Official Account AppSecret"
      provider_url: "https://developers.weixin.qq.com/doc/service/api/base/api_getaccesstoken"
      secret: true
required_environment_variables:
  - name: WECHAT_AUTHOR
    prompt: Default article author
    help: "Displayed in the WeChat article metadata"
  - name: WECHAT_DEFAULT_COVER_IMAGE
    prompt: Default cover image path or URL
    help: "Used when the article body has no obvious cover image"
---

# Telegram WeChat Publisher

Use this skill when the user wants to take article text from Telegram or from the current chat, turn it into WeChat-friendly long-form HTML, create a WeChat draft, and optionally submit that draft for publication.

## Fixed Telegram Format

For Telegram, prefer this fixed submission format:

```text
投稿
标题：这里填写文章标题
摘要：这里填写简短摘要，可留空
作者：这里填写作者名，可留空
原文链接：这里填写原始链接，可留空
正文：
这里开始写正文
```

Template file:
- `templates/submission-template.txt`

Parser:

```bash
python3 scripts/parse_telegram_submission.py
```

Additional Telegram commands:

```text
投稿模板

发布
媒体ID：<draft media_id>

查询发布
发布ID：<publish_id>
```

## Workflow

1. Normalize the article into Markdown first.
2. Use the local publisher script to render or publish:

```bash
python3 scripts/publish_wechat_article.py render \
  --input /tmp/article.md \
  --title "Your Title"
```

3. Create a WeChat draft:

```bash
python3 scripts/publish_wechat_article.py draft \
  --input /tmp/article.md \
  --title "Your Title" \
  --json
```

4. Only publish after explicit confirmation:

```bash
python3 scripts/publish_wechat_article.py publish \
  --media-id <draft_media_id> \
  --json
```

5. Check asynchronous publish status:

```bash
python3 scripts/publish_wechat_article.py status \
  --publish-id <publish_id> \
  --json
```

## Rules

- Default to `draft`, not `publish`.
- When the incoming Telegram message matches the fixed format, parse it with `scripts/parse_telegram_submission.py` instead of guessing.
- If the user supplies raw text, rewrite it into clean Markdown with headings, short paragraphs, bullets, and a concise lead.
- Preserve the user's claims and facts. Only improve structure and readability.
- If the article contains local images, let the script upload them to WeChat article-image storage automatically.
- If there is no explicit cover image, use `WECHAT_DEFAULT_COVER_IMAGE` or the first image in the article body.
- If `WECHAT_DEFAULT_COVER_IMAGE=auto`, make sure Pillow is available; otherwise point it to a local image path or remote URL.
- Warn the user that WeChat publish permissions may be blocked on personal or uncertified accounts.

## Runtime Usage

This skill assumes you already have an agent runtime or bot process that can receive Telegram messages. No public webhook is required if you use polling.

Required env in a local `.env` file or exported shell environment:
- `TELEGRAM_BOT_TOKEN`
- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- `WECHAT_AUTHOR`
- `WECHAT_DEFAULT_COVER_IMAGE`

See `templates/env.example` for a minimal template.
