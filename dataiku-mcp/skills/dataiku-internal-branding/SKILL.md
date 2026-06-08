---
name: dataiku-internal-branding
description: >
  Dataiku brand design system — colors, typography, Tailwind config, component patterns, and logo
  assets for building on-brand Dataiku UIs. Use when: (1) building a Dataiku webapp or dashboard,
  (2) styling any Dataiku plugin frontend, (3) creating HTML/CSS/JS output that should look like
  Dataiku, (4) the user mentions "Dataiku branding", "Dataiku style", "Dataiku colors", or
  "Dataiku design system", (5) building any UI in a Dataiku project or DSS context. Source:
  Dataiku Brand Guidelines (zeroheight, updated 2026-02).
---

# Dataiku Internal Branding

Apply Dataiku's brand design system to all UI output. Read [references/styling.md](references/styling.md) before writing code.

### Color Tokens

| Token | Hex | Role |
|-------|-----|------|
| `dkBlack` | `#1A1A1A` | Primary text, dark backgrounds |
| `dkWhite` | `#FEFEF9` | Page background (warm off-white, never pure white) |
| `dkDarkGreen` | `#06312E` | Brand dark, hero sections |
| `dkBeige` | `#F8F4E4` | Cards, panels, warm surfaces |
| `dkGreen` | `#3EDAB2` | CTAs, highlights, interactive elements |
| `dkLightGreen` | `#C7FFF1` | Tints, hover backgrounds |
| `dkBlue` | `#7092F2` | Data viz only |
| `dkOrange` | `#EDAB4F` | Data viz only |

### Typography

| Role | Font | Google Fonts |
|------|------|-------------|
| Headlines | Spectral | `family=Spectral:wght@400;500;600;700` |
| Body / UI | Roboto | `family=Roboto:wght@300;400;500;700` |
| Code / Data | DM Mono | `family=DM+Mono:wght@400;500` |

TL;DR: dkGreen on dark bg. dkWhite (not #FFF). Serif headings. Mono for data. Never Orange+Green or Blue+Green co-dominant.

Logo: assets/{theme}-lockup/logomark.svg — theme=black (light bg) or white (dark bg). PNG (not SVG) for PPTX/Office.

PPTX/PptxGenJS rules (bare hex, fonts, shadows, slide rhythm): see [references/styling.md](references/styling.md).
