#!/usr/bin/env python3
"""Convert schema.org Recipe data from a public URL to a Markdown recipe."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_json_ld = False
        self.json_ld: list[str] = []
        self._buffer: list[str] = []
        self.meta: dict[str, str] = {}
        self.language: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html" and values.get("lang"):
            self.language = values["lang"]
        if tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self.in_json_ld, self._buffer = True, []
        if tag == "meta":
            key = values.get("property") or values.get("name")
            content = values.get("content")
            if key and content:
                self.meta[key.lower()] = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_json_ld:
            self.json_ld.append("".join(self._buffer))
            self.in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self._buffer.append(data)


class ArticleParser(HTMLParser):
    """Extract headings and text blocks from the article body when Recipe data is absent."""

    def __init__(self) -> None:
        super().__init__()
        self.active = False
        self.depth = 0
        self.block: str | None = None
        self.buffer: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if not self.active and tag == "div" and "entry-content" in (values.get("class") or "").split():
            self.active, self.depth = True, 1
            return
        if not self.active:
            return
        if tag == "div":
            self.depth += 1
        if tag in {"h2", "h3", "p", "li"} and self.block is None:
            self.block, self.buffer = tag, []
        elif tag == "br" and self.block:
            self.buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.active:
            return
        if self.block == tag:
            value = re.sub(r"[ \t]*\n[ \t]*", "\n", html.unescape("".join(self.buffer))).strip()
            if value:
                self.blocks.append((tag, value))
            self.block = None
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.active = False

    def handle_data(self, data: str) -> None:
        if self.active and self.block:
            self.buffer.append(data)


def fetch(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "recipe-to-markdown/1.0 (+personal recipe archive)"})
    with urlopen(request, timeout=30) as response:  # nosec B310 -- URL is supplied by the user
        return response.read(), response.headers.get_content_type()


def flatten(data: object) -> list[dict]:
    if isinstance(data, list):
        return [item for value in data for item in flatten(value)]
    if isinstance(data, dict):
        values = [data]
        if isinstance(data.get("@graph"), list):
            values.extend(item for value in data["@graph"] for item in flatten(value))
        return values
    return []


def recipes_from_page(parser: PageParser) -> list[dict]:
    recipes: list[dict] = []
    for raw in parser.json_ld:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in flatten(data):
            kind = item.get("@type", [])
            kinds = {kind} if isinstance(kind, str) else set(kind)
            if "Recipe" in kinds:
                recipes.append(item)
    return recipes


def blog_post_from_page(parser: PageParser) -> dict:
    for raw in parser.json_ld:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in flatten(data):
            kind = item.get("@type", [])
            kinds = {kind} if isinstance(kind, str) else set(kind)
            if "BlogPosting" in kinds or "Article" in kinds:
                return item
    return {}


def fallback_content(page: str, parser: PageParser) -> tuple[dict, list[tuple[str, list[str]]]]:
    article = ArticleParser(); article.feed(page)
    sections: list[tuple[str, list[str]]] = []
    intro: list[str] = []
    for tag, value in article.blocks:
        if tag in {"h2", "h3"}:
            sections.append((value, []))
        elif sections:
            sections[-1][1].append(value)
        else:
            intro.append(value)
    if len(sections) < 2:
        raise ValueError("No Recipe metadata or clearly structured recipe article was found.")
    post = blog_post_from_page(parser)
    heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", page, re.IGNORECASE | re.DOTALL)
    title = text(heading.group(1)) if heading else text(post.get("headline") or post.get("name") or parser.meta.get("og:title") or "Untitled recipe")
    return {"name": title, "description": intro[0] if intro else post.get("description", ""), "image": post.get("image")}, sections


def text(value: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", str(value)))).strip()


def as_list(value: object) -> list[str]:
    if value is None:
        return []
    return [text(item) for item in value] if isinstance(value, list) else [text(value)]


def display(value: object) -> str:
    return ", ".join(as_list(value))


def instructions(value: object) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict) and "itemListElement" in item:
                result.extend(instructions(item["itemListElement"]))
            elif isinstance(item, dict):
                result.extend(instructions(item.get("text") or item.get("name")))
            else:
                result.extend(instructions(item))
        return result
    return [text(value)] if value else []


def image_url(recipe: dict, page_url: str, meta: dict[str, str]) -> str | None:
    image = recipe.get("image")
    if isinstance(image, list): image = image[0] if image else None
    if isinstance(image, dict): image = image.get("url") or image.get("contentUrl")
    image = image or meta.get("og:image")
    return urljoin(page_url, image) if isinstance(image, str) and image else None


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "recipe"


def duration(recipe: dict, key: str) -> str | None:
    value = recipe.get(key)
    if not value: return None
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", str(value))
    if not match: return str(value)
    hours, minutes = match.groups()
    return " ".join(part for part in (f"{hours} h" if hours else None, f"{minutes} min" if minutes else None) if part)


LABELS = {
    "nl": {
        "details": "Receptgegevens", "ingredients": "Ingrediënten", "instructions": "Bereiding",
        "source": "Bron", "prep": "Voorbereidingstijd", "cook": "Bereidingstijd",
        "total": "Totale tijd", "yield": "Porties",
    },
    "en": {
        "details": "Details", "ingredients": "Ingredients", "instructions": "Instructions",
        "source": "Source", "prep": "Prep time", "cook": "Cook time",
        "total": "Total time", "yield": "Yield",
    },
}


def labels_for(recipe: dict, page_language: str | None) -> dict[str, str]:
    language = recipe.get("inLanguage") or page_language or "en"
    if isinstance(language, list):
        language = language[0] if language else "en"
    return LABELS.get(str(language).lower().split("-")[0], LABELS["en"])


def fallback_section_lines(sections: list[tuple[str, list[str]]]) -> list[str]:
    lines: list[str] = []
    for heading, blocks in sections:
        normalized = heading.lower()
        values = [line.strip(" –•-\t") for block in blocks for line in block.splitlines() if line.strip()]
        lines.extend([f"## {heading}", ""])
        if any(word in normalized for word in ("ingrediënt", "ingredient")):
            lines.extend(f"- {value}" for value in values)
        elif any(word in normalized for word in ("bereiding", "instruct", "method", "direction")):
            lines.extend(f"{index}. {value}" for index, value in enumerate(values, 1))
        elif any(word in normalized for word in ("benodigd", "equipment", "tools")):
            lines.extend(f"- {value}" for value in values)
        else:
            lines.extend(values)
        lines.append("")
    return lines


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("url")
    args.add_argument("--output-dir", type=Path, default=Path("recipes"))
    args.add_argument("--recipe-index", type=int, default=0)
    options = args.parse_args()
    try:
        page, content_type = fetch(options.url)
        if "html" not in content_type:
            raise ValueError(f"Expected an HTML page, received {content_type}.")
        html_page = page.decode("utf-8", errors="replace")
        parser = PageParser(); parser.feed(html_page)
        recipes = recipes_from_page(parser)
        fallback_sections: list[tuple[str, list[str]]] | None = None
        if recipes and not 0 <= options.recipe_index < len(recipes):
            titles = ", ".join(str(item.get("name", "untitled")) for item in recipes)
            raise ValueError(f"Recipe index is out of range. Available: {titles}")
        if recipes:
            recipe = recipes[options.recipe_index]
        else:
            recipe, fallback_sections = fallback_content(html_page, parser)
        labels = labels_for(recipe, parser.language)
        title = text(recipe.get("name") or "Untitled recipe")
        source_image = image_url(recipe, options.url, parser.meta)
        if not source_image:
            raise ValueError("The recipe has no usable representative image.")
        image, image_type = fetch(source_image)
        extension = mimetypes.guess_extension(image_type) or Path(urlparse(source_image).path).suffix or ".jpg"
        destination = options.output_dir
        images = destination / "images"; images.mkdir(parents=True, exist_ok=True)
        name = slug(title)
        image_path = images / f"{name}{extension}"
        image_path.write_bytes(image)
        relative_image = Path("images") / image_path.name
        fields = [(labels["prep"], duration(recipe, "prepTime")), (labels["cook"], duration(recipe, "cookTime")), (labels["total"], duration(recipe, "totalTime")), (labels["yield"], recipe.get("recipeYield"))]
        lines = ["---", f"title: {json.dumps(title, ensure_ascii=False)}", f"source: {json.dumps(options.url)}", "---", "", f"# {title}", "", f"![{title}]({relative_image.as_posix()})", ""]
        description = text(recipe.get("description", ""))
        if description: lines.extend([description, ""])
        if fallback_sections is not None:
            lines.extend(fallback_section_lines(fallback_sections))
        else:
            details = [f"- **{label}:** {display(value)}" for label, value in fields if value]
            if details: lines.extend([f"## {labels['details']}", "", *details, ""])
            ingredients = as_list(recipe.get("recipeIngredient"))
            if ingredients: lines.extend([f"## {labels['ingredients']}", "", *(f"- {item}" for item in ingredients), ""])
            steps = instructions(recipe.get("recipeInstructions"))
            if steps: lines.extend([f"## {labels['instructions']}", "", *(f"{index}. {step}" for index, step in enumerate(steps, 1)), ""])
        lines.extend([f"{labels['source']}: [{urlparse(options.url).netloc}]({options.url})", ""])
        markdown = destination / f"{name}.md"; destination.mkdir(parents=True, exist_ok=True)
        markdown.write_text("\n".join(lines), encoding="utf-8")
        print(markdown)
        print(image_path)
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
