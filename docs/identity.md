# Visual identity — Alenmaa Alhor Construction · AZM

Source of truth: the logo files in `app/static/` (no public brand guide exists). Read this before building or changing any screen.

**What we take from the company brand:** its colors, its mark, and its names. Nothing else. The company's own designs are not a reference for layout or style. Everything else is the AZM design system: simple and calm, with the precision of an engineering tool.

## Names

| | Arabic | English |
|---|---|---|
| Company | الإنماء الحر للمقاولات | Alenmaa Alhor Construction |
| Platform | عزم | AZM |

Both are editable by the System Owner in **Settings**; templates read them from there, never hard-code them.

## Logo

- `logo-lockup.png`: mark and company name in both languages. `logo-mark.png`: the mark alone (favicon).
- The mark is two angled shapes rising toward the upper right: electric blue at the lower left, sky blue at the upper right. In templates use the `mark()` macro in `_icons.html` (vector, follows the theme).
- `brand-strip.png` (repeating stepped arrows) is an archive asset. It is not used in the interface.

## Color

**One theme only: the brand's deep ink navy (dark).** There is no light mode, by the programmer's decision. Do not add one.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#04051a` | page background (the brand ink, `#02021a`, lifted slightly) |
| `--surface` | `#0c0e29` | cards and panels |
| `--accent` | `#5b6bff` | the brand electric blue `#0d1cf2`, lifted for contrast on dark: buttons, links, active items, focus |
| `--sky` | `#38bdff` | the brand sky `#00acff`, lifted for dark: small highlights |
| `--brand-grad` | sky → electric blue | the signature gradient, from the logo: primary buttons, hero cards, the platform name, the active menu marker |
| `--ink` | `#eef0fc` | text |

Status colors (`--ok`, `--warn`, `--bad`) are for status only.

## Type

- Inter for Latin text, IBM Plex Sans Arabic for Arabic, both self-hosted in `app/static/fonts/` (SIL OFL).
- Numbers, codes and amounts use tabular figures and stay left-to-right inside Arabic text (`.num`, `.code`).

## Character

Clean, precise, professional: an engineering tool, not a marketing site. Simple on the surface, with structure you can feel underneath.

- Neutral, warm surfaces with hairline borders and soft shadows. No colored glows or tinted backgrounds: the brand blue appears only on actions, links, the active item and focus.
- Color carries meaning, never decoration.
- Generous spacing, clear hierarchy, one primary action per screen.
- Short, formal copy. Arabic is Modern Standard Arabic, never colloquial. No chatty or personal hints in the interface.
- Engineering details: a faint blueprint grid behind the sign-in screen, exact hairline dividers, tabular figures, and visible codes (`P-2026-014`, `01.02-SE-010`) beside names.
- Motion is quick and subtle (fade and rise, about 0.3 s) and respects reduced-motion settings.
