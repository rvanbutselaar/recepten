# Repository Guidelines

## Project Structure & Module Organization

This repository is a curated collection of recipes in Markdown. Store each recipe in `recipes/` and its single representative image in `recipes/images/`. Keep reusable Codex workflows in `.agents/skills/<skill-name>/`; the recipe importer currently lives in `.agents/skills/recipe-to-markdown/`, with its executable code in `scripts/` and metadata in `agents/openai.yaml`.

Use lowercase, hyphenated filenames that match the recipe title, for example `recipes/bbq-klassieker-moink-balls.md`. Keep image filenames aligned with their recipe where practical.

## Development and Verification

There is no build system or automated test suite. Validate changes with focused commands:

```bash
python3 -m py_compile .agents/skills/recipe-to-markdown/scripts/convert_recipe.py
python3 .agents/skills/recipe-to-markdown/scripts/convert_recipe.py "<recipe-url>" --output-dir recipes
git diff --check
```

The first command checks Python syntax, the second imports a public recipe, and the last catches whitespace errors. After an import, inspect the generated Markdown and confirm its image link resolves to exactly one file in `recipes/images/`.

## Content and Code Style

Preserve a recipe's source language, spelling, units, quantities, and stated timings. Include only the recipe content and source attribution; exclude ads, comments, and unrelated article text. Do not invent missing ingredients, instructions, or metadata.

For Python, follow the existing four-space indentation and standard-library-first import style. Keep changes small, readable, and dependency-free unless a new dependency is essential.

## Testing Guidelines

When changing the importer, test it against a public recipe page and verify the generated title, ingredient list, steps, source URL, and local image reference. If a page has multiple recipes, exercise `--recipe-index`; if schema data is unavailable, confirm the structured-article fallback works or fails safely.

## Commits and Pull Requests

Work directly on the `main` branch; do not create feature branches. Use semantic commit subjects such as `feat: import pulled-pork recipe` or `fix: preserve recipe yield`. Pull requests should explain the user-visible change, list validation performed, and include source URLs for added recipes. Add screenshots only when they clarify rendered Markdown or image issues.
