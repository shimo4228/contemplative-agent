# Weekly Analysis Report — Japanese Translation

You are translating a weekly analysis report of an autonomous AI agent into Japanese. The input is the full English report; output the complete Japanese version and nothing else.

## Rules

- Translate into natural, plain Japanese (報告書の文体、だ・である調). Avoid unnecessary katakana loanwords when a plain Japanese word exists.
- Preserve the Markdown structure exactly: heading levels, section letters (A/B/C/D/E), table layouts, lists, `diff`/code blocks, horizontal rules. Do not add, remove, merge, or reorder any content.
- **Keep verbatim quotes of the agent's posts/comments/replies in their original English.** They are evidence; translating them would distort the data. You may append a short Japanese gloss in parentheses after a quote when it aids comprehension, but never replace the original.
- Keep unchanged: file paths, code identifiers, metric names, model names (e.g. `gemma4:e4b`), anchor phrases being counted, dates, numbers, and table column values that are counts or identifiers. Table headers and prose cells are translated.
- Section titles: translate descriptive words but keep the letter prefix, e.g. `## A. Quantitative Summary` → `## A. 定量サマリー`.
- Begin the output with this line (fill in the date from the report), then the translated document:

  `> 日本語版（自動翻訳・Sonnet）。英語正本: weekly-{end-date}.md`

- Output only the translated report. No preamble, no commentary, no code fences around the whole document.
