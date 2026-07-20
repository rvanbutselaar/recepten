---
name: recipe-to-markdown
description: Convert a publicly accessible online recipe URL into a self-contained Markdown recipe file and download exactly one representative recipe image. Use when asked to import, save, archive, or turn a web recipe into Markdown for this recipe collection.
---

# Recipe to Markdown

Run the bundled converter for a public recipe page:

```bash
python3 skills/recipe-to-markdown/scripts/convert_recipe.py \
  "https://example.com/recipe" --output-dir recipes
```

The command prefers Recipe schema.org data, then falls back to the page's article body when it has clearly separated recipe headings and content. It writes a slugged `.md` file and stores one image beside it in `images/`. It detects the page language from Recipe schema data (or the page's `lang` attribute) and localizes its generated headings and labels. It preserves ingredient quantities and instruction text; do not invent missing details. After every successful import, it also rebuilds the recipe index in `README.md`.

## Output rules

- Keep the source URL in the front matter and as a visible source link.
- Reference the downloaded local image once, directly below the title.
- Include only recipe content: title, summary when available, timing/yield, ingredients, instructions, and optional notes/nutrition. Exclude ads, comments, affiliate links, and unrelated article text.
- Retain the recipe's language, spelling, units, stated timings, and generated headings/labels. Do not translate a recipe into a different language.
- When Recipe metadata is absent, use only the article's clearly separated headings and content; retain the source headings rather than inventing structure. Stop if no usable image or clearly structured recipe article is present.

## Verify

After conversion, inspect the Markdown and confirm that its image reference resolves to the one downloaded file. For pages with multiple recipes, use `--recipe-index`; an out-of-range index reports the available recipe titles.
