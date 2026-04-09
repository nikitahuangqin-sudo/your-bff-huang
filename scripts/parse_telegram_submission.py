#!/usr/bin/env python3
"""Parse fixed-format Telegram article submission messages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


FIELD_MAP = {
    "标题": "title",
    "摘要": "digest",
    "作者": "author",
    "原文链接": "content_source_url",
    "媒体ID": "media_id",
    "发布ID": "publish_id",
    "操作": "action",
}

ACTION_ALIASES = {
    "投稿": "draft",
    "草稿": "draft",
    "draft": "draft",
    "发布": "publish",
    "publish": "publish",
    "查询发布": "status",
    "状态": "status",
    "status": "status",
    "投稿模板": "template",
    "模板": "template",
    "template": "template",
}


class ParseError(RuntimeError):
    """Raised when the submission format is invalid."""


def normalize_label(label: str) -> str:
    return label.strip().rstrip("：:").strip()


def parse_submission(text: str) -> dict:
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in raw_lines]
    first_nonempty = next((line.strip() for line in lines if line.strip()), "")
    action = ACTION_ALIASES.get(first_nonempty, "draft")

    if action == "template":
        return {"ok": True, "action": "template"}

    data = {
        "action": action,
        "title": "",
        "digest": "",
        "author": "",
        "content_source_url": "",
        "media_id": "",
        "publish_id": "",
        "body": "",
    }

    in_body = False
    body_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_body:
                body_lines.append("")
            continue

        if in_body:
            body_lines.append(line)
            continue

        if stripped in ACTION_ALIASES:
            data["action"] = ACTION_ALIASES[stripped]
            continue

        if stripped.startswith("正文：") or stripped.startswith("正文:"):
            in_body = True
            after = stripped.split("：", 1)[1] if "：" in stripped else stripped.split(":", 1)[1]
            if after.strip():
                body_lines.append(after.strip())
            continue

        if "：" in line:
            label, value = line.split("：", 1)
        elif ":" in line:
            label, value = line.split(":", 1)
        else:
            # Free text before 正文 starts becomes body for convenience.
            in_body = True
            body_lines.append(line)
            continue

        normalized = normalize_label(label)
        key = FIELD_MAP.get(normalized)
        if key:
            data[key] = value.strip()

    data["body"] = "\n".join(body_lines).strip()

    if data["action"] == "draft":
        if not data["title"]:
            raise ParseError("缺少“标题”字段。")
        if not data["body"]:
            raise ParseError("缺少“正文”内容。")
    elif data["action"] == "publish":
        if not data["media_id"]:
            raise ParseError("发布操作需要“媒体ID”。")
    elif data["action"] == "status":
        if not data["publish_id"]:
            raise ParseError("查询发布需要“发布ID”。")

    return {"ok": True, **data}


def read_input(args: argparse.Namespace) -> str:
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    return sys.stdin.read()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Parse fixed-format Telegram publishing messages.")
    parser.add_argument("--input", help="Optional text file path. Defaults to stdin.")
    args = parser.parse_args(argv)
    try:
        text = read_input(args)
        result = parse_submission(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ParseError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
