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

Apply Dataiku's brand design system to all UI output. Read [references/styling.md](references/styling.md) for the full specification before writing any styled code.

## Quick Reference

### Color Tokens

| Token | Hex | Role |
|-------|-----|------|
| `dkBlack` | `#1A1A1A` | Primary text, dark backgrounds |
| `dkWhite` | `#FFFEF9` | Page background (warm off-white, never pure white) |
| `dkDarkGreen` | `#06312E` | Brand dark, hero sections |
| `dkBeige` | `#F8F4E4` | Cards, panels, warm surfaces |
| `dkGreen` | `#3EDAB2` | CTAs, highlights, interactive elements |
| `dkLightGreen` | `#C7FFF1` | Tints, hover backgrounds |
| `dkBlue` | `#7092F2` | Data viz only |
| `dkOrange` | `#EDAB4F` | Data viz only |

### Typography (web substitutes)

| Role | Font | Google Fonts |
|------|------|-------------|
| Headlines | Spectral | `family=Spectral:wght@400;600;700` |
| Body / UI | Roboto | `family=Roboto:wght@400;500;700` |
| Code / Data | DM Mono | `family=DM+Mono:wght@400;500` |

### Rules

- **Never** use Orange + Green as co-dominant surfaces
- **Never** use Blue + Green as co-dominant surfaces
- Complementary colors (`dkBlue`, `dkOrange`) are **data visualization only**
- Use `dkGreen` on dark backgrounds (`dkDarkGreen`, `dkBlack`) for maximum brand impact
- Backgrounds use warm `dkWhite`, not pure `#FFFFFF`
- Serif font (`font-serif` / Spectral) for headings and hero text
- Mono font (`font-mono` / DM Mono) for data labels, stats, code
- WCAG 2.1 AA contrast required

### Logo Assets

| File | Variant | Use on |
|------|---------|--------|
| `assets/black-lockup.svg` / `.png` | Full wordmark, black | Light backgrounds (`dkWhite`, `dkBeige`) |
| `assets/black-logomark.svg` / `.png` | Icon only, black | Light backgrounds |
| `assets/white-lockup.svg` / `.png` | Full wordmark, white | Dark backgrounds (`dkDarkGreen`, `dkBlack`) |
| `assets/white-logomark.svg` / `.png` | Icon only, white | Dark backgrounds |

Prefer SVG for web. Use PNG when SVG is not supported. Never recolor the logo with Signature Colors.

## Workflow

1. Read [references/styling.md](references/styling.md) for full color palette, Tailwind config, component patterns (buttons, cards, forms, badges, tables), interactive states, and icon reference
2. Apply the Tailwind config or translate tokens to the target framework (vanilla CSS, Vue, DSS webapp)
3. For DSS webapps: use Dataiku icon font classes (`icon-dku-*`) — see styling.md Icon Reference section
4. Validate color pairings against the approved combinations in styling.md before shipping
