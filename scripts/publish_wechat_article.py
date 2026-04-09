#!/usr/bin/env python3
"""Render Markdown articles for WeChat and manage draft/publish APIs."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None


WECHAT_API_BASE = "https://api.weixin.qq.com"
DEFAULT_SOURCE_URL = "WECHAT_CONTENT_SOURCE_URL"
DEFAULT_AUTHOR = "WECHAT_AUTHOR"
DEFAULT_COVER_IMAGE = "WECHAT_DEFAULT_COVER_IMAGE"
DEFAULT_OPEN_COMMENTS = "WECHAT_OPEN_COMMENTS"
DEFAULT_ONLY_FANS = "WECHAT_ONLY_FANS_CAN_COMMENT"
AUTO_COVER_VALUES = {"auto", "generate", "auto-title", "auto_title"}
WECHAT_TITLE_LIMIT_BYTES = 64
WECHAT_DIGEST_LIMIT_BYTES = 120
WECHAT_AUTHOR_LIMIT_BYTES = 8


class CliError(RuntimeError):
    """Raised for user-facing command errors."""


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_env(name: str, required: bool = False) -> str:
    value = os.getenv(name, "").strip()
    if required and not value:
        raise CliError(f"Missing required environment variable: {name}")
    return value


def truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    buf = bytearray()
    for ch in text:
        b = ch.encode("utf-8")
        if len(buf) + len(b) > max_bytes:
            break
        buf.extend(b)
    return buf.decode("utf-8", errors="ignore").rstrip()


def request_json(url: str, *, method: str = "GET", payload: Optional[dict] = None) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CliError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"Network error calling {url}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"Non-JSON response from {url}: {raw[:300]}") from exc

    if isinstance(data, dict) and data.get("errcode") not in (None, 0):
        raise CliError(f"WeChat API error {data.get('errcode')}: {data.get('errmsg')}")
    return data


def build_query_url(path: str, **params: str) -> str:
    query = urllib.parse.urlencode(params)
    return f"{WECHAT_API_BASE}{path}?{query}"


def get_access_token() -> str:
    app_id = read_env("WECHAT_APP_ID", required=True)
    app_secret = read_env("WECHAT_APP_SECRET", required=True)
    url = build_query_url(
        "/cgi-bin/token",
        grant_type="client_credential",
        appid=app_id,
        secret=app_secret,
    )
    data = request_json(url)
    token = data.get("access_token", "")
    if not token:
        raise CliError("WeChat access token response did not include access_token")
    return token


def multipart_request(url: str, file_name: str, file_bytes: bytes, content_type: str) -> dict:
    boundary = f"----PublisherBoundary{uuid.uuid4().hex}"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="media"; filename="{file_name}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CliError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"Network error calling {url}: {exc}") from exc

    data = json.loads(raw)
    if data.get("errcode") not in (None, 0):
        raise CliError(f"WeChat API error {data.get('errcode')}: {data.get('errmsg')}")
    return data


def fetch_binary(source: str, base_dir: Optional[Path]) -> Tuple[str, bytes, str]:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in ("http", "https"):
        try:
            with urllib.request.urlopen(source) as resp:
                file_bytes = resp.read()
                content_type = resp.headers.get_content_type() or "application/octet-stream"
        except urllib.error.URLError as exc:
            raise CliError(f"Failed to download remote image {source}: {exc}") from exc
        file_name = Path(parsed.path).name or f"remote-{uuid.uuid4().hex}.bin"
        return file_name, file_bytes, content_type

    path = Path(source).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = (base_dir / path).resolve()
    if not path.exists():
        raise CliError(f"File not found: {path}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return path.name, path.read_bytes(), content_type


def _font_candidates() -> List[str]:
    return [
        "/System/Library/Fonts/Supplemental/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]


def _load_font(size: int) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    if ImageFont is None:
        raise CliError("Pillow is not available for automatic cover generation")
    for candidate in _font_candidates():
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _measure_text(draw: "ImageDraw.ImageDraw", text: str, font) -> float:
    bbox = draw.textbbox((0, 0), text, font=font)
    return float(bbox[2] - bbox[0])


def _wrap_text(draw: "ImageDraw.ImageDraw", text: str, font, max_width: int, max_lines: int) -> List[str]:
    words = text.split()
    if not words:
        return [text]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _measure_text(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and len(words) > sum(len(line.split()) for line in lines):
        trimmed = lines[-1].rstrip(" .")
        while trimmed and _measure_text(draw, f"{trimmed}…", font) > max_width:
            trimmed = trimmed[:-1]
        lines[-1] = f"{trimmed}…"
    return lines


def generate_title_cover(title: str, author: str) -> Path:
    if Image is None or ImageDraw is None:
        raise CliError("Automatic cover generation requires Pillow, which is not installed")

    width, height = 900, 383
    image = Image.new("RGB", (width, height), "#F4E6D8")
    draw = ImageDraw.Draw(image)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(244 * (1 - ratio) + 208 * ratio)
        g = int(230 * (1 - ratio) + 129 * ratio)
        b = int(216 * (1 - ratio) + 115 * ratio)
        draw.line((0, y, width, y), fill=(r, g, b))

    draw.ellipse((width - 250, -40, width + 70, 280), fill=(255, 245, 230))
    draw.ellipse((-140, height - 170, 220, height + 110), fill=(167, 201, 87))
    draw.rectangle((70, 55, 110, 325), fill=(49, 46, 129))

    title_font = _load_font(48)
    author_font = _load_font(24)
    tag_font = _load_font(18)

    lines = _wrap_text(draw, title.strip(), title_font, max_width=620, max_lines=3)

    draw.text((145, 68), "微信公众号", font=tag_font, fill=(49, 46, 129))

    y = 120
    for line in lines:
        draw.text((145, y), line, font=title_font, fill=(17, 24, 39))
        y += 68

    author_text = author.strip() or "未署名"
    draw.text((145, height - 62), f"作者｜{author_text}", font=author_font, fill=(55, 65, 81))

    output_path = Path("/tmp") / f"wechat-cover-{uuid.uuid4().hex}.png"
    image.save(output_path, format="PNG")
    return output_path


def extract_plain_text(markdown_text: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown_text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_>#-]", " ", text)
    return " ".join(text.split())


def inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f'<img src="{html.escape(m.group(2), quote=True)}" alt="{html.escape(m.group(1), quote=True)}" />',
        escaped,
    )
    escaped = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_html(markdown_text: str) -> Tuple[str, List[str]]:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    html_parts: List[str] = []
    current_paragraph: List[str] = []
    current_list: List[str] = []
    list_tag: Optional[str] = None
    current_quote: List[str] = []
    in_code_block = False
    code_lines: List[str] = []
    image_sources: List[str] = []

    def flush_paragraph() -> None:
        nonlocal current_paragraph
        if current_paragraph:
            text = " ".join(part.strip() for part in current_paragraph if part.strip())
            if text:
                html_parts.append(f"<p>{inline_markdown(text)}</p>")
                image_sources.extend(re.findall(r'<img src="([^"]+)"', html_parts[-1]))
            current_paragraph = []

    def flush_list() -> None:
        nonlocal current_list, list_tag
        if current_list and list_tag:
            html_parts.append(f"<{list_tag}>")
            for item in current_list:
                rendered = inline_markdown(item.strip())
                html_parts.append(f"<li>{rendered}</li>")
                image_sources.extend(re.findall(r'<img src="([^"]+)"', rendered))
            html_parts.append(f"</{list_tag}>")
        current_list = []
        list_tag = None

    def flush_quote() -> None:
        nonlocal current_quote
        if current_quote:
            content = " ".join(part.strip() for part in current_quote if part.strip())
            rendered = inline_markdown(content)
            html_parts.append(f"<blockquote><p>{rendered}</p></blockquote>")
            image_sources.extend(re.findall(r'<img src="([^"]+)"', rendered))
        current_quote = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            html_parts.append("<pre><code>")
            html_parts.append(html.escape("\n".join(code_lines)))
            html_parts.append("</code></pre>")
        code_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            flush_quote()
            if in_code_block:
                flush_code()
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_quote()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = min(len(heading.group(1)), 4)
            rendered = inline_markdown(heading.group(2).strip())
            html_parts.append(f"<h{level}>{rendered}</h{level}>")
            image_sources.extend(re.findall(r'<img src="([^"]+)"', rendered))
            continue

        if re.fullmatch(r"[-*_]{3,}", stripped):
            flush_paragraph()
            flush_list()
            flush_quote()
            html_parts.append("<hr />")
            continue

        quote = re.match(r"^>\s?(.*)$", stripped)
        if quote:
            flush_paragraph()
            flush_list()
            current_quote.append(quote.group(1))
            continue
        flush_quote()

        bullet = re.match(r"^[-*+]\s+(.*)$", stripped)
        if bullet:
            flush_paragraph()
            if list_tag not in (None, "ul"):
                flush_list()
            list_tag = "ul"
            current_list.append(bullet.group(1))
            continue

        ordered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered:
            flush_paragraph()
            if list_tag not in (None, "ol"):
                flush_list()
            list_tag = "ol"
            current_list.append(ordered.group(1))
            continue

        flush_list()
        current_paragraph.append(stripped)

    if in_code_block:
        flush_code()
    flush_paragraph()
    flush_list()
    flush_quote()
    return "\n".join(html_parts), image_sources


def apply_wechat_typography(rendered_html: str) -> str:
    blocks = []
    for line in rendered_html.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<h"):
            blocks.append(
                stripped.replace(
                    ">",
                    ' style="margin: 1.6em 0 0.6em; font-weight: 700; line-height: 1.35; color: #111827;">',
                    1,
                )
            )
        elif stripped.startswith("<p"):
            blocks.append(
                stripped.replace(
                    "<p>",
                    '<p style="margin: 0.85em 0; line-height: 1.9; font-size: 16px; color: #1f2937;">',
                    1,
                )
            )
        elif stripped.startswith("<blockquote>"):
            blocks.append(
                stripped.replace(
                    "<blockquote>",
                    '<blockquote style="margin: 1.2em 0; padding: 0.8em 1em; border-left: 4px solid #cbd5e1; background: #f8fafc;">',
                    1,
                )
            )
        elif stripped.startswith("<ul>"):
            blocks.append('<ul style="margin: 0.8em 0 0.8em 1.2em; line-height: 1.9; color: #1f2937;">')
        elif stripped.startswith("<ol>"):
            blocks.append('<ol style="margin: 0.8em 0 0.8em 1.2em; line-height: 1.9; color: #1f2937;">')
        elif stripped.startswith("<pre>"):
            blocks.append('<pre style="margin: 1em 0; padding: 1em; overflow-x: auto; background: #111827; color: #f9fafb; border-radius: 8px;"><code>')
        elif stripped.startswith("<img "):
            blocks.append(
                stripped.replace(
                    "<img ",
                    '<img style="display: block; max-width: 100%; height: auto; margin: 1em auto; border-radius: 6px;" ',
                    1,
                )
            )
        else:
            blocks.append(stripped)
    return "\n".join(blocks)


def render_article(markdown_text: str) -> Tuple[str, List[str], str]:
    rendered_html, image_sources = markdown_to_html(markdown_text)
    typography_html = apply_wechat_typography(rendered_html)
    summary = extract_plain_text(markdown_text)[:120]
    return typography_html, image_sources, summary


def replace_content_images(article_html: str, image_map: Dict[str, str]) -> str:
    updated = article_html
    for original, uploaded in image_map.items():
        updated = updated.replace(f'src="{html.escape(original, quote=True)}"', f'src="{uploaded}"')
    return updated


def upload_wechat_article_image(access_token: str, source: str, base_dir: Optional[Path]) -> str:
    file_name, file_bytes, content_type = fetch_binary(source, base_dir)
    url = build_query_url("/cgi-bin/media/uploadimg", access_token=access_token)
    response = multipart_request(url, file_name, file_bytes, content_type)
    uploaded = response.get("url", "")
    if not uploaded:
        raise CliError(f"WeChat uploadimg did not return url for {source}")
    return uploaded


def upload_wechat_cover(access_token: str, source: str, base_dir: Optional[Path]) -> str:
    file_name, file_bytes, content_type = fetch_binary(source, base_dir)
    url = build_query_url("/cgi-bin/material/add_material", access_token=access_token, type="image")
    response = multipart_request(url, file_name, file_bytes, content_type)
    media_id = response.get("media_id", "")
    if not media_id:
        raise CliError(f"WeChat add_material did not return media_id for {source}")
    return media_id


def ensure_cover_source(explicit_cover: str, first_image: Optional[str], *, title: str, author: str) -> str:
    if explicit_cover:
        if explicit_cover.strip().lower() in AUTO_COVER_VALUES:
            return str(generate_title_cover(title, author))
        return explicit_cover
    default_cover = read_env(DEFAULT_COVER_IMAGE)
    if default_cover:
        if default_cover.strip().lower() in AUTO_COVER_VALUES:
            return str(generate_title_cover(title, author))
        return default_cover
    if first_image:
        return first_image
    return str(generate_title_cover(title, author))


def load_markdown(input_path: Path) -> str:
    try:
        return input_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CliError(f"Input file not found: {input_path}") from exc


def create_draft(args: argparse.Namespace) -> dict:
    input_path = Path(args.input).expanduser().resolve()
    markdown_text = load_markdown(input_path)
    article_html, image_sources, auto_digest = render_article(markdown_text)

    access_token = get_access_token()
    uploaded_images: Dict[str, str] = {}
    for source in image_sources:
        uploaded_images[source] = upload_wechat_article_image(access_token, source, input_path.parent)
    article_html = replace_content_images(article_html, uploaded_images)

    article_author = truncate_utf8(args.author or read_env(DEFAULT_AUTHOR, required=True), WECHAT_AUTHOR_LIMIT_BYTES)
    article_title = truncate_utf8(args.title, WECHAT_TITLE_LIMIT_BYTES)
    cover_source = ensure_cover_source(
        args.cover_image or "",
        image_sources[0] if image_sources else None,
        title=article_title,
        author=article_author,
    )
    thumb_media_id = upload_wechat_cover(access_token, cover_source, input_path.parent)

    digest = truncate_utf8(args.digest or auto_digest, WECHAT_DIGEST_LIMIT_BYTES)
    payload = {
        "articles": [
            {
                "title": article_title,
                "author": article_author,
                "digest": digest,
                "content": article_html,
                "content_source_url": args.content_source_url or read_env(DEFAULT_SOURCE_URL),
                "thumb_media_id": thumb_media_id,
                "need_open_comment": int(bool(args.open_comments)),
                "only_fans_can_comment": int(bool(args.only_fans_can_comment)),
            }
        ]
    }
    url = build_query_url("/cgi-bin/draft/add", access_token=access_token)
    result = request_json(url, method="POST", payload=payload)
    return {
        "ok": True,
        "mode": "draft",
        "title": article_title,
        "digest": digest,
        "author": article_author,
        "thumb_media_id": thumb_media_id,
        "media_id": result.get("media_id"),
        "content_image_count": len(uploaded_images),
        "content_source_url": payload["articles"][0]["content_source_url"],
    }


def submit_publish(args: argparse.Namespace) -> dict:
    access_token = get_access_token()
    url = build_query_url("/cgi-bin/freepublish/submit", access_token=access_token)
    result = request_json(url, method="POST", payload={"media_id": args.media_id})
    return {
        "ok": True,
        "mode": "publish",
        "media_id": args.media_id,
        "publish_id": result.get("publish_id"),
        "msg_data_id": result.get("msg_data_id"),
    }


def query_publish_status(args: argparse.Namespace) -> dict:
    access_token = get_access_token()
    url = build_query_url("/cgi-bin/freepublish/get", access_token=access_token)
    result = request_json(url, method="POST", payload={"publish_id": args.publish_id})
    result["ok"] = True
    result["mode"] = "status"
    return result


def render_only(args: argparse.Namespace) -> dict:
    input_path = Path(args.input).expanduser().resolve()
    markdown_text = load_markdown(input_path)
    article_html, image_sources, digest = render_article(markdown_text)
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    if output_path:
        output_path.write_text(article_html, encoding="utf-8")
    return {
        "ok": True,
        "mode": "render",
        "title": args.title,
        "digest": digest,
        "image_sources": image_sources,
        "output_path": str(output_path) if output_path else None,
        "html": article_html if not output_path else None,
    }


def add_common_article_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, help="Path to a Markdown article file")
    parser.add_argument("--title", required=True, help="Article title")
    parser.add_argument("--author", help="Override the default WECHAT_AUTHOR")
    parser.add_argument("--digest", help="Override the auto-generated summary")
    parser.add_argument("--cover-image", help="Cover image path or URL")
    parser.add_argument("--content-source-url", help="Original source URL shown in WeChat")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render Markdown to WeChat article HTML and manage draft/publish APIs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              render  --input /tmp/article.md --title "My Article" --output /tmp/article.html
              draft   --input /tmp/article.md --title "My Article" --json
              publish --media-id XXXXXXXXX --json
              status  --publish-id PUBLISH_ID --json
            """
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Render Markdown locally without calling WeChat")
    add_common_article_args(render_parser)
    render_parser.add_argument("--output", help="Optional file path for rendered HTML")
    render_parser.add_argument("--json", action="store_true", help="Print JSON output")

    draft_parser = subparsers.add_parser("draft", help="Create a WeChat draft")
    add_common_article_args(draft_parser)
    draft_parser.add_argument(
        "--open-comments",
        type=int,
        choices=(0, 1),
        default=int(read_env(DEFAULT_OPEN_COMMENTS) or "0"),
        help="Whether to open article comments (0 or 1)",
    )
    draft_parser.add_argument(
        "--only-fans-can-comment",
        type=int,
        choices=(0, 1),
        default=int(read_env(DEFAULT_ONLY_FANS) or "0"),
        help="Whether only followers can comment (0 or 1)",
    )
    draft_parser.add_argument("--json", action="store_true", help="Print JSON output")

    publish_parser = subparsers.add_parser("publish", help="Submit an existing draft for publication")
    publish_parser.add_argument("--media-id", required=True, help="Draft media_id from draft/add")
    publish_parser.add_argument("--json", action="store_true", help="Print JSON output")

    status_parser = subparsers.add_parser("status", help="Query publish job status")
    status_parser.add_argument("--publish-id", required=True, help="publish_id returned by freepublish/submit")
    status_parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args(list(argv))


def print_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    html_output = result.pop("html", None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if html_output:
        print("\n" + html_output)


def load_default_env_files() -> None:
    env_override = os.getenv("TWP_ENV_FILE", "").strip()
    candidates = []
    if env_override:
        candidates.append(Path(env_override).expanduser())

    script_dir = Path(__file__).resolve().parent
    repo_dir = script_dir.parent
    candidates.extend(
        [
            Path.cwd() / ".env",
            repo_dir / ".env",
            Path.home() / ".env",
        ]
    )

    seen = set()
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        load_dotenv(resolved)


def main(argv: Iterable[str]) -> int:
    load_default_env_files()
    args = parse_args(argv)
    try:
        if args.command == "render":
            result = render_only(args)
            print_result(result, args.json)
            return 0
        if args.command == "draft":
            result = create_draft(args)
            print_result(result, args.json)
            return 0
        if args.command == "publish":
            result = submit_publish(args)
            print_result(result, args.json)
            return 0
        if args.command == "status":
            result = query_publish_status(args)
            print_result(result, args.json)
            return 0
        raise CliError(f"Unsupported command: {args.command}")
    except CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
