# Dataiku Brand Styling Guide

Reference guide for Dataiku's brand styling guidelines and design system implementation patterns.

Dataiku follows a **warm neutral** design philosophy with a deep teal signature palette, clean typography, and a modern enterprise look.

> **Source:** [Dataiku Brand Guidelines](https://zeroheight.com/473670a97/v/latest/p/359e68-index) (updated 2026-02)

---

## Colors

### Foundation Colors

| Name | Token | Hex | Usage |
|---|---|---|---|
| Core Black | `dkBlack` | `#1A1A1A` | Primary text, dark backgrounds |
| Core White | `dkWhite` | `#FFFEF9` | Page/app background, light surfaces |

### Signature Colors

| Name | Token | Hex | Usage |
|---|---|---|---|
| Dark Green | `dkDarkGreen` | `#06312E` | Brand dark, hero sections, strong contrast backgrounds |
| Beige | `dkBeige` | `#F8F4E4` | Cards, panels, warm surfaces |
| Green (primary accent) | `dkGreen` | `#3EDAB2` | CTAs, highlights, links, interactive elements |
| Light Green | `dkLightGreen` | `#C7FFF1` | Tints, hover backgrounds, subtle accents |

> The **logo** always uses Foundation Colors (Core Black or Core White). Expressive components use Signature Colors.

### Complementary Colors (data viz / functional use)

| Name | Token | Hex | Usage |
|---|---|---|---|
| Blue | `dkBlue` | `#7092F2` | Charts, graphs, data visualization |
| Orange | `dkOrange` | `#EDAB4F` | Charts, warnings, data differentiation |

> Complementary colors are for data visualization and functional needs only — not for brand expression. Lighter shades (10–30%) may be used as subtle background fills.

### Neutral Colors (data viz support)

| Name | Hex | |
|---|---|---|
| Light Blue Grey | `#A8BCDD` | |
| Light Brown | `#E9D3B3` | |
| Light Grey | `#EEEDEA` | |
| Blue Grey | `#42485B` | |
| Brown | `#816948` | |
| Grey | `#929088` | |
| Dark Blue Grey | `#121B32` | |
| Dark Brown | `#412C0E` | |
| Dark Grey | `#2F2E2B` | |

### Recommended Color Pairings

These are the approved combinations for most Dataiku use cases:

- `dkDarkGreen` + `dkBeige` + `dkGreen`
- `dkBlack` + `dkBeige` + `dkGreen`
- `dkBlack` + `dkWhite` + `dkGreen`
- `dkGreen` + `dkDarkGreen`
- `dkDarkGreen` + `dkBlue` (with `dkBeige` or `dkWhite`)
- `dkDarkGreen` + `dkOrange` (with `dkBeige` or `dkWhite`)

**Prohibited pairings:** Orange + Green together as dominant surfaces; Green + Blue together as dominant surfaces; complementary colors on plain white without brand anchoring colors.

---

## Typography

### Brand Fonts (licensed)

| Role | Font | Usage |
|---|---|---|
| Headlines | **Signifier** | Hero titles, major section headings |
| Subheads & Body | **Untitled Sans** | Subheadings, body copy, UI text |
| Microtext & Data | **Söhne Mono** | Labels, code, data tables, metadata |

### Web / Google Fonts Substitutions

Use these when brand fonts are unavailable (Google Slides, web without licensed fonts, etc.):

| Brand Font | Web Substitute | Google Fonts |
|---|---|---|
| Signifier | **Spectral** | `family=Spectral:wght@400;600;700` |
| Untitled Sans | **Roboto** | `family=Roboto:wght@400;500;700` |
| Söhne Mono | **DM Mono** | `family=DM+Mono:wght@400;500` |

### Font Loading (web substitutes)

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link
  href="https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700&family=Roboto:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap"
  rel="stylesheet"
/>
```

```css
font-family: "Roboto", system-ui, -apple-system, sans-serif;           /* body */
font-family: "Spectral", Georgia, serif;                                /* headings */
font-family: "DM Mono", "Courier New", monospace;                       /* code/data */
```

### Font Weights

- **400 (Regular):** Body text, descriptions
- **500 (Medium):** Labels, UI emphasis
- **600–700 (Semi-bold/Bold):** Headings, titles, strong emphasis

### Text Sizing Scale

| Class | Size | Usage |
|---|---|---|
| `text-xs` | 12px | Labels, badges, metadata (DM Mono) |
| `text-sm` | 14px | Secondary text, descriptions |
| `text-base` | 16px | Body text |
| `text-lg` | 18px | Subheadings, card titles |
| `text-xl` | 20px | Section headings |
| `text-2xl` | 24px | Page titles |
| `text-3xl+` | 30px+ | Hero headlines (Spectral/Signifier) |

---

## Tailwind Configuration

```javascript
// tailwind.config.cjs
module.exports = {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Foundation
        dkBlack:      "#1A1A1A",
        dkWhite:      "#FFFEF9",
        // Signature
        dkDarkGreen:  "#06312E",
        dkBeige:      "#F8F4E4",
        dkGreen:      "#3EDAB2",
        dkLightGreen: "#C7FFF1",
        // Complementary (data viz)
        dkBlue:       "#7092F2",
        dkOrange:     "#EDAB4F",
      },
      fontFamily: {
        sans:  ["Roboto", "system-ui", "sans-serif"],
        serif: ["Spectral", "Georgia", "serif"],
        mono:  ["DM Mono", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};
```

---

## Component Patterns

### Buttons

```html
<!-- Primary Button -->
<button class="bg-dkGreen hover:bg-dkGreen/80 text-dkBlack font-medium px-4 py-2 rounded-lg transition-colors">
  Primary Action
</button>

<!-- Dark Button (on light backgrounds) -->
<button class="bg-dkDarkGreen hover:bg-dkDarkGreen/80 text-dkWhite px-4 py-2 rounded-lg transition-colors">
  Dark Action
</button>

<!-- Secondary Button -->
<button class="bg-dkBeige hover:bg-dkBeige/70 text-dkBlack border border-dkBlack/10 px-4 py-2 rounded-lg transition-colors">
  Secondary Action
</button>

<!-- Ghost Button -->
<button class="text-dkBlack hover:text-dkDarkGreen hover:bg-dkBeige px-4 py-2 rounded-lg transition-colors">
  Ghost Action
</button>
```

### Cards

```html
<!-- Light card (on dkWhite background) -->
<div class="bg-dkBeige border border-dkBlack/10 rounded-xl shadow-sm p-4">
  <h3 class="font-serif text-lg font-semibold text-dkBlack">Card Title</h3>
  <p class="text-sm text-dkBlack/60 mt-1">Card description</p>
</div>

<!-- Dark card (hero / featured) -->
<div class="bg-dkDarkGreen rounded-xl p-4">
  <h3 class="font-serif text-lg font-semibold text-dkWhite">Card Title</h3>
  <p class="text-sm text-dkWhite/70 mt-1">Card description</p>
</div>
```

### Forms

```html
<input
  class="w-full px-3 py-2 bg-dkWhite border border-dkBlack/20 rounded-lg text-dkBlack
         focus:border-dkGreen focus:ring-1 focus:ring-dkGreen outline-none transition-colors"
  placeholder="Enter value..."
/>

<select class="bg-dkBeige border border-dkBlack/20 rounded-lg px-3 py-2 text-sm text-dkBlack">
  <option>Option 1</option>
</select>
```

### Badges

```html
<!-- Green accent badge -->
<span class="font-mono text-xs px-2 py-0.5 rounded-full bg-dkGreen/20 text-dkDarkGreen">
  Badge
</span>

<!-- Dark badge -->
<span class="font-mono text-xs px-2 py-0.5 rounded-full bg-dkDarkGreen text-dkWhite">
  Badge
</span>
```

### Tables

```html
<table class="w-full">
  <thead>
    <tr class="text-left text-xs font-mono text-dkBlack/50 uppercase tracking-wider border-b border-dkBlack/10 bg-dkBeige">
      <th class="px-4 py-3">Column</th>
    </tr>
  </thead>
  <tbody class="divide-y divide-dkBlack/10">
    <tr class="hover:bg-dkBeige/50 transition-colors">
      <td class="px-4 py-3 text-dkBlack">Cell content</td>
    </tr>
  </tbody>
</table>
```

---

## Interactive States

```html
<!-- Focus -->
<input class="border border-dkBlack/20 rounded-lg px-3 py-2
             focus:border-dkGreen focus:ring-2 focus:ring-dkGreen/20 focus:outline-none
             transition-colors duration-150" />

<!-- Active / Pressed -->
<button class="bg-dkGreen hover:bg-dkGreen/80 active:bg-dkGreen/60 text-dkBlack
              px-4 py-2 rounded-lg transition-colors duration-100">
  Click Me
</button>

<!-- Disabled -->
<button class="bg-dkBlack/10 text-dkBlack/30 px-4 py-2 rounded-lg cursor-not-allowed" disabled>
  Disabled
</button>
```

---

## Icon Reference

Dataiku uses a custom icon font. Common icons for plugin UIs:

| Icon Class | Usage |
|---|---|
| `icon-dku-dataset` | Datasets |
| `icon-dku-recipe` | Recipes |
| `icon-dku-model` | Models / ML |
| `icon-bar-chart` | Charts / Visualizations |
| `icon-puzzle-piece` | Plugins |
| `icon-cog` | Settings |
| `icon-warning-sign` | Warnings |
| `icon-ok-circle` | Success |
| `icon-remove-circle` | Error |
| `icon-search` | Search |
| `icon-refresh` | Reload / Refresh |
| `icon-download` | Download / Export |
| `icon-upload` | Upload / Import |
| `icon-folder-open` | Managed Folders |

Use via: `<i class="icon-dku-dataset"></i>` or in plugin JSON: `"icon": "icon-bar-chart"`

---

## Design Philosophy

- **Warm off-white** (`dkWhite`) backgrounds — not pure white
- **Beige surfaces** (`dkBeige`) for cards and panels
- **Deep teal** (`dkDarkGreen`) for strong brand moments and dark sections
- **Mint green** (`dkGreen`) as the primary action/accent color — used on dark green or black backgrounds for maximum impact
- **Serif headings** (Spectral/Signifier) for editorial feel
- **Complementary colors** reserved for data visualization only
- **High contrast** maintained per WCAG 2.1 AA

## Best Practices

1. Anchor layouts with Foundation Colors (black/white); use Signature Colors for expression
2. Use `dkGreen` on dark (`dkDarkGreen`, `dkBlack`) for maximum brand impact
3. Never use Orange + Green together as co-dominant surfaces
4. Use `font-mono` (DM Mono) for data labels, stats, and code
5. Use `font-serif` (Spectral) for titles and hero text to match the brand editorial tone
6. Complementary colors (blue, orange) are **data viz only** — not for general UI chrome
7. Use opacity modifiers for tints (`bg-dkGreen/20`, `bg-dkDarkGreen/10`)
