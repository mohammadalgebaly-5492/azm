# Visual identity — AZM

AZM is Muhammad's own product, independent of any one company. It can serve Alenmaa Alhor Construction or any other contractor. Read this before building or changing any screen.

**The platform's identity is AZM's own:** its logo, its green, and its dark navy. The company using the platform appears **by name only** (Settings), never with its logo or colors. Everything else is the AZM design system: simple and calm, with the precision of an engineering tool.

## Names

| | Arabic | English |
|---|---|---|
| Platform | عزم | AZM |
| Company using it (today) | الإنماء الحر للمقاولات | Alenmaa Alhor Construction |

Both are editable by the System Owner in **Settings**; templates read them from there, never hard-code them.

## Logo

- Source artwork from Muhammad: `docs/brand/azm-logo-source.png` (green `#017F4D` and black on white, with a geometric «عزم» wordmark). Use it for print and light backgrounds.
- The mark is a green stepped band rising to the upper right, above two black angled shapes. In templates use the `mark()` macro in `_icons.html` (vector, traced from the source): green uses `--brand`, the black parts use `--ink`, so they show on the dark theme.
- `app/static/azm-logo-dark.png`: mark and wordmark recolored for dark screens (sign-in panel).
- `app/static/azm-icon.png`: favicon and home-screen icon (the mark on a navy tile).

## Color

**One theme only: dark navy.** There is no light mode, by the programmer's decision. Do not add one.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#1d2a41` | page background (lifted on Muhammad's request, easy on the eyes) |
| `--surface` | `#25344e` | cards and panels |
| `--brand` | `#18a86a` | the logo green `#017F4D`, lifted for dark: the mark only |
| `--accent` | `#2cc483` | buttons, links, active items, focus |
| `--brand-grad` | light green → logo green | primary buttons, hero cards, the active menu marker |
| `--ink` | `#f0f3f9` | text, and the black parts of the logo |

Status colors (`--ok`, `--warn`, `--bad`) are for status only. `--ok` is also green, so status pills always keep their dot to stay distinct from buttons.

## Type

- Inter for Latin text, IBM Plex Sans Arabic for Arabic, both self-hosted in `app/static/fonts/` (SIL OFL).
- Numbers, codes and amounts use tabular figures and stay left-to-right inside Arabic text (`.num`, `.code`).

## Character

Clean, precise, professional: an engineering tool, not a marketing site. Simple on the surface, with structure you can feel underneath.

- Neutral surfaces with hairline borders and soft shadows. No colored glows or tinted backgrounds: the green appears only on actions, links, the active item and focus.
- Color carries meaning, never decoration.
- Generous spacing, clear hierarchy, one primary action per screen.
- Short, formal copy. Arabic is Modern Standard Arabic, never colloquial. No chatty or personal hints in the interface.
- Engineering details: a faint blueprint grid behind the sign-in screen, exact hairline dividers, tabular figures, and visible codes (`P-2026-014`, `01.02-SE-010`) beside names.
- Motion is quick and subtle (fade and rise, about 0.3 s) and respects reduced-motion settings.
