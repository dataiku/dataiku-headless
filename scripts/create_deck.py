#!/usr/bin/env python3
"""
Generate Dataiku-branded PPTX deck for the WM FP&A demo.

Brand system:
  Fonts: Spectral (serif headlines), Roboto (body/UI), DM Mono (data/stats)
  Colors: dkDarkGreen #06312E, dkGreen #3EDAB2, dkBeige #F8F4E4, dkWhite #FFFEF9
  Philosophy: warm neutral, deep teal signature, serif editorial feel
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import os

# ── Brand Tokens ──────────────────────────────────────────
DK_BLACK      = RGBColor(0x1A, 0x1A, 0x1A)
DK_WHITE      = RGBColor(0xFF, 0xFE, 0xF9)
DK_DARK_GREEN = RGBColor(0x06, 0x31, 0x2E)
DK_BEIGE      = RGBColor(0xF8, 0xF4, 0xE4)
DK_GREEN      = RGBColor(0x3E, 0xDA, 0xB2)
DK_LIGHT_GREEN= RGBColor(0xC7, 0xFF, 0xF1)
DK_BLUE       = RGBColor(0x70, 0x92, 0xF2)
DK_ORANGE     = RGBColor(0xED, 0xAB, 0x4F)
DK_GREY       = RGBColor(0x92, 0x90, 0x88)
DK_DARK_GREY  = RGBColor(0x2F, 0x2E, 0x2B)
DK_TEAL_MID   = RGBColor(0x0A, 0x45, 0x40)  # midpoint for subtle cards on dark

FONT_SERIF = "Spectral"   # Headlines, hero text
FONT_SANS  = "Roboto"     # Body, UI, descriptions
FONT_MONO  = "DM Mono"    # Data, stats, labels

ASSETS = os.path.expanduser("~/.claude/skills/dataiku-internal-branding/assets")

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)


# ── Helpers ───────────────────────────────────────────────

def bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def rect(slide, l, t, w, h, fill, border=None, radius=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l, t, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if border:
        s.line.color.rgb = border
        s.line.width = Pt(1)
    else:
        s.line.fill.background()
    return s


def bar(slide, l, t, w=Inches(0.05), h=Inches(1), color=DK_GREEN):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    return s


def circle(slide, l, t, size, fill):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, l, t, size, size)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    return s


def txt(slide, l, t, w, h, text, size=18, bold=False, color=DK_BLACK,
        align=PP_ALIGN.LEFT, font=FONT_SANS, spacing=None, italic=False):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.italic = italic
    p.font.color.rgb = color
    p.font.name = font
    p.alignment = align
    if spacing:
        p.space_after = Pt(spacing)
    return tf


def multi(slide, l, t, w, h, lines, size=16, color=DK_BLACK, font=FONT_SANS,
          line_gap=6):
    """lines = [(text, bold, opt_color, opt_font, opt_size), ...]"""
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(lines):
        text = item[0]
        is_bold = item[1] if len(item) > 1 else False
        c = item[2] if len(item) > 2 else color
        f = item[3] if len(item) > 3 else font
        s = item[4] if len(item) > 4 else size
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = text
        p.font.size = Pt(s)
        p.font.bold = is_bold
        p.font.color.rgb = c
        p.font.name = f
        p.space_after = Pt(line_gap)
    return tf


def logo_white(slide, l, t, h=Inches(0.35)):
    slide.shapes.add_picture(os.path.join(ASSETS, "white-lockup.png"), l, t, height=h)


def logo_black(slide, l, t, h=Inches(0.35)):
    slide.shapes.add_picture(os.path.join(ASSETS, "black-lockup.png"), l, t, height=h)


def divider(slide, l, t, w, color=DK_GREEN):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, Pt(2))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()


# ── SLIDE 1: Title ────────────────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_DARK_GREEN)
logo_white(s, Inches(1), Inches(0.6))

txt(s, Inches(1), Inches(2), Inches(9), Inches(0.6),
    "WEALTH MANAGEMENT FP&A", size=14, color=DK_GREEN, bold=True,
    font=FONT_MONO)

txt(s, Inches(1), Inches(2.7), Inches(10), Inches(1.8),
    "Monthly New Business\nForecast", size=52, color=DK_WHITE, bold=True,
    font=FONT_SERIF)

divider(s, Inches(1), Inches(4.7), Inches(2), DK_GREEN)

txt(s, Inches(1), Inches(5.1), Inches(10), Inches(0.8),
    "From Excel workbook to automated, auditable pipeline", size=20,
    color=DK_BEIGE, font=FONT_SANS, italic=True)

# Bottom stat bar
stat_y = Inches(6.3)
stats = [("17", "Visual Recipes"), ("0", "Lines of Python"), ("48", "Months Forecast"), ("0.00", "Diff vs Excel")]
for i, (num, label) in enumerate(stats):
    x = Inches(1 + i * 3)
    txt(s, x, stat_y, Inches(2.5), Inches(0.4), num, size=28, color=DK_GREEN,
        bold=True, font=FONT_MONO)
    txt(s, x, stat_y + Inches(0.4), Inches(2.5), Inches(0.3), label, size=11,
        color=DK_GREY, font=FONT_MONO)


# ── SLIDE 2: Status Quo ──────────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_WHITE)
logo_black(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
    "THE CHALLENGE", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(8), Inches(0.8),
    "The Status Quo", size=40, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF)
txt(s, Inches(1), Inches(1.7), Inches(9), Inches(0.4),
    "A complex Excel workbook that finance teams struggle to maintain, audit, and scale.",
    size=16, color=DK_GREY, font=FONT_SANS)

divider(s, Inches(1), Inches(2.2), Inches(11), RGBColor(0xEE, 0xED, 0xEA))

pains = [
    ("\u2718  Manual & Error-Prone",
     "6 interconnected tabs with cross-sheet formulas. One broken cell reference cascades errors across the entire forecast."),
    ("\u2718  Single Point of Failure",
     "Lives on one person's laptop. No version control, no audit trail, no concurrent access."),
    ("\u2718  No Automation",
     "Each monthly refresh requires manual data entry, copy-paste of actuals, and re-running formulas."),
    ("\u2718  Opaque Logic",
     "Complex nested formulas only the author understands. New team members need weeks to onboard."),
]

for i, (title, desc) in enumerate(pains):
    col, row = i % 2, i // 2
    x = Inches(1 + col * 5.8)
    y = Inches(2.7 + row * 2.2)
    rect(s, x, y, Inches(5.3), Inches(1.9), DK_BEIGE)
    bar(s, x + Inches(0.15), y + Inches(0.3), h=Inches(1.3), color=DK_ORANGE)
    txt(s, x + Inches(0.45), y + Inches(0.2), Inches(4.5), Inches(0.45),
        title, size=16, color=DK_DARK_GREEN, bold=True, font=FONT_SANS)
    txt(s, x + Inches(0.45), y + Inches(0.7), Inches(4.5), Inches(1.1),
        desc, size=13, color=DK_DARK_GREY, font=FONT_SANS)


# ── SLIDE 3: The Solution ────────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_WHITE)
logo_black(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
    "THE SOLUTION", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(8), Inches(0.8),
    "The Dataiku Pipeline", size=40, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF)
txt(s, Inches(1), Inches(1.7), Inches(9), Inches(0.4),
    "Every Excel tab replaced by visual, auditable, server-side recipes.",
    size=16, color=DK_GREY, font=FONT_SANS)

divider(s, Inches(1), Inches(2.2), Inches(11), RGBColor(0xEE, 0xED, 0xEA))

sols = [
    ("\u2714  Visual & Transparent",
     "17 visual recipes in a clear flow. Every step is inspectable \u2014 click any dataset to see the data at that stage."),
    ("\u2714  Server-Side & Shared",
     "Runs on DSS infrastructure, not a laptop. Full version control, role-based access, concurrent users."),
    ("\u2714  One-Click Rebuild",
     "Upload new actuals, click Build. Entire 42-month forecast recalculates in seconds."),
    ("\u2714  Self-Documenting",
     "Recipe names describe the logic. Built-in wiki, data dictionary, and methodology documentation."),
]

for i, (title, desc) in enumerate(sols):
    col, row = i % 2, i // 2
    x = Inches(1 + col * 5.8)
    y = Inches(2.7 + row * 2.2)
    rect(s, x, y, Inches(5.3), Inches(1.9), DK_BEIGE)
    bar(s, x + Inches(0.15), y + Inches(0.3), h=Inches(1.3), color=DK_GREEN)
    txt(s, x + Inches(0.45), y + Inches(0.2), Inches(4.5), Inches(0.45),
        title, size=16, color=DK_DARK_GREEN, bold=True, font=FONT_SANS)
    txt(s, x + Inches(0.45), y + Inches(0.7), Inches(4.5), Inches(1.1),
        desc, size=13, color=DK_DARK_GREY, font=FONT_SANS)


# ── SLIDE 4: Pipeline Architecture ───────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_DARK_GREEN)
logo_white(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
    "ARCHITECTURE", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(8), Inches(0.8),
    "Pipeline Architecture", size=40, color=DK_WHITE, bold=True, font=FONT_SERIF)

zones = [
    ("01", "Data Ingestion", "7 datasets", "6 source CSVs parsed\nfrom Excel + expected\nvalues for validation"),
    ("02", "Enrichment", "5 Join recipes", "Attach all 5 assumption\nfactors to each of the\n5,616 record-month rows"),
    ("03", "Calculation", "8 visual recipes", "Prepare + Group + Window\nLog \u2192 CumSum \u2192 Exp\nsolves the recursion"),
    ("04", "Output", "4 recipes", "Validation, dashboard,\nLLM agent for natural\nlanguage analysis"),
]

for i, (num, title, count, desc) in enumerate(zones):
    x = Inches(0.6 + i * 3.15)
    y = Inches(2.1)
    rect(s, x, y, Inches(2.9), Inches(4.4), DK_TEAL_MID)

    # Number circle
    circle(s, x + Inches(0.2), y + Inches(0.25), Inches(0.5), DK_GREEN)
    txt(s, x + Inches(0.2), y + Inches(0.28), Inches(0.5), Inches(0.45),
        num, size=16, color=DK_DARK_GREEN, bold=True, font=FONT_MONO,
        align=PP_ALIGN.CENTER)

    txt(s, x + Inches(0.85), y + Inches(0.28), Inches(1.9), Inches(0.4),
        title, size=17, color=DK_WHITE, bold=True, font=FONT_SANS)

    divider(s, x + Inches(0.2), y + Inches(0.9), Inches(2.5), DK_GREEN)

    txt(s, x + Inches(0.2), y + Inches(1.15), Inches(2.5), Inches(0.5),
        count, size=24, color=DK_GREEN, bold=True, font=FONT_MONO)

    txt(s, x + Inches(0.2), y + Inches(2), Inches(2.5), Inches(2),
        desc, size=13, color=DK_BEIGE, font=FONT_SANS)

# Arrows between zones
for i in range(3):
    x = Inches(0.6 + (i+1) * 3.15 - 0.22)
    txt(s, x, Inches(3.8), Inches(0.4), Inches(0.5),
        "\u25B6", size=20, color=DK_GREEN, align=PP_ALIGN.CENTER, font=FONT_SANS)


# ── SLIDE 5: The Math ────────────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_WHITE)
logo_black(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(6), Inches(0.4),
    "THE MATH", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(10), Inches(0.8),
    "Solving the Recursive Dependency", size=40, color=DK_DARK_GREEN,
    bold=True, font=FONT_SERIF)
txt(s, Inches(1), Inches(1.7), Inches(10), Inches(0.4),
    "Each month\u2019s total depends on the prior month. Visual recipes can\u2019t loop \u2014 but they can sum.",
    size=16, color=DK_GREY, font=FONT_SANS)

# Left panel: The Problem
rect(s, Inches(0.8), Inches(2.5), Inches(5.6), Inches(4.3), DK_BEIGE)
txt(s, Inches(1.1), Inches(2.7), Inches(5), Inches(0.5),
    "The Problem", size=22, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF)
multi(s, Inches(1.1), Inches(3.4), Inches(5), Inches(3), [
    ("T(Jul) = T(Jun) \u00d7 multiplier(Jul)", False, DK_BLACK, FONT_MONO, 14),
    ("T(Aug) = T(Jul) \u00d7 multiplier(Aug)", False, DK_BLACK, FONT_MONO, 14),
    ("T(Sep) = T(Aug) \u00d7 multiplier(Sep)", False, DK_BLACK, FONT_MONO, 14),
    ("", False),
    ("This is a cumulative PRODUCT.", True, DK_DARK_GREEN, FONT_SANS, 15),
    ("Window recipes only support cumulative SUM.", True, DK_ORANGE, FONT_SANS, 15),
], line_gap=8)

# Right panel: The Solution
rect(s, Inches(6.9), Inches(2.5), Inches(5.6), Inches(4.3), DK_DARK_GREEN)
txt(s, Inches(7.2), Inches(2.7), Inches(5), Inches(0.5),
    "The Log-Sum-Exp Trick", size=22, color=DK_GREEN, bold=True, font=FONT_SERIF)
multi(s, Inches(7.2), Inches(3.4), Inches(5), Inches(3), [
    ("ln(a \u00d7 b \u00d7 c) = ln(a) + ln(b) + ln(c)", False, DK_GREEN, FONT_MONO, 14),
    ("", False),
    ("1. Prepare   log(multiplier)", False, DK_WHITE, FONT_MONO, 13),
    ("2. Window    cumulative SUM of logs", False, DK_WHITE, FONT_MONO, 13),
    ("3. Prepare   exp(cumsum) \u00d7 base total", False, DK_WHITE, FONT_MONO, 13),
    ("", False),
    ("Product \u2192 Sum \u2192 Window function.", True, DK_GREEN, FONT_SANS, 15),
    ("Pure visual recipes. Zero Python.", True, DK_GREEN, FONT_SANS, 15),
], line_gap=8)


# ── SLIDE 6: Verified Results ────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_WHITE)
logo_black(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
    "VERIFICATION", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(8), Inches(0.8),
    "Penny-Perfect Accuracy", size=40, color=DK_DARK_GREEN, bold=True,
    font=FONT_SERIF)
txt(s, Inches(1), Inches(1.7), Inches(9), Inches(0.4),
    "Every value verified against the original Excel workbook with zero difference.",
    size=16, color=DK_GREY, font=FONT_SANS)

# Table
headers = ["Check", "Computed Value", "Diff vs Excel", "Status"]
col_widths = [Inches(3.5), Inches(3), Inches(2.5), Inches(1.5)]
col_x = [Inches(1.2)]
for w in col_widths[:-1]:
    col_x.append(col_x[-1] + w)

# Header row
rect(s, Inches(1), Inches(2.4), Inches(10.5), Inches(0.55), DK_DARK_GREEN)
for j, hdr in enumerate(headers):
    txt(s, col_x[j], Inches(2.47), col_widths[j], Inches(0.4),
        hdr, size=12, color=DK_WHITE, bold=True, font=FONT_MONO)

checks = [
    ("June 2025 Total (Actuals)", "\u00a337,478,820.00", "0.00", "\u2714 PASS"),
    ("July 2025 Total (First Forecast)", "\u00a343,237,566.02", "0.00", "\u2714 PASS"),
    ("August 2025 Total", "\u00a339,141,848.10", "0.00", "\u2714 PASS"),
    ("Record 1, July 2025", "\u00a3263,910.17", "0.00", "\u2714 PASS"),
    ("All 48 Monthly Totals", "Verified", "0.00", "\u2714 PASS"),
    ("Total Row Count", "5,616", "0", "\u2714 PASS"),
    ("Actuals Pass Through", "Unchanged", "0", "\u2714 PASS"),
]

for i, (check, value, diff, status) in enumerate(checks):
    y = Inches(3.05 + i * 0.55)
    row_bg = DK_BEIGE if i % 2 == 0 else DK_WHITE
    rect(s, Inches(1), y, Inches(10.5), Inches(0.5), row_bg)
    txt(s, col_x[0], y + Inches(0.07), col_widths[0], Inches(0.4),
        check, size=13, color=DK_BLACK, font=FONT_SANS)
    txt(s, col_x[1], y + Inches(0.07), col_widths[1], Inches(0.4),
        value, size=13, color=DK_BLACK, bold=True, font=FONT_MONO)
    txt(s, col_x[2], y + Inches(0.07), col_widths[2], Inches(0.4),
        diff, size=13, color=DK_GREEN, bold=True, font=FONT_MONO)
    txt(s, col_x[3], y + Inches(0.07), col_widths[3], Inches(0.4),
        status, size=13, color=DK_GREEN, bold=True, font=FONT_MONO)


# ── SLIDE 7: FY Forecast ─────────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_DARK_GREEN)
logo_white(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
    "FORECAST", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(8), Inches(0.8),
    "Annual Summary", size=40, color=DK_WHITE, bold=True, font=FONT_SERIF)

fy_data = [
    ("FY2025", "\u00a3518M", "\u2014", "6 actuals +\n6 forecast months"),
    ("FY2026", "\u00a3605M", "+17%", "Full forecast year\n12 months"),
    ("FY2027", "\u00a3658M", "+9%", "Full forecast year\n12 months"),
    ("FY2028", "\u00a3697M", "+6%", "Full forecast year\n12 months"),
]

for i, (fy, total, growth, note) in enumerate(fy_data):
    x = Inches(0.6 + i * 3.15)
    y = Inches(2.2)
    rect(s, x, y, Inches(2.9), Inches(4.2), DK_TEAL_MID)

    txt(s, x + Inches(0.3), y + Inches(0.3), Inches(2.3), Inches(0.4),
        fy, size=14, color=DK_GREEN, bold=True, font=FONT_MONO)

    txt(s, x + Inches(0.3), y + Inches(0.9), Inches(2.3), Inches(0.8),
        total, size=48, color=DK_WHITE, bold=True, font=FONT_SERIF)

    divider(s, x + Inches(0.3), y + Inches(2), Inches(2.3), DK_GREEN)

    txt(s, x + Inches(0.3), y + Inches(2.3), Inches(2.3), Inches(0.5),
        growth, size=26, color=DK_GREEN, bold=True, font=FONT_MONO)

    txt(s, x + Inches(0.3), y + Inches(3.2), Inches(2.3), Inches(0.8),
        note, size=12, color=DK_GREY, font=FONT_SANS)


# ── SLIDE 8: AI Agent ────────────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_DARK_GREEN)
logo_white(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(6), Inches(0.4),
    "AI-POWERED", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(10), Inches(0.8),
    "Talk to Your Financial Model", size=40, color=DK_WHITE, bold=True,
    font=FONT_SERIF)
txt(s, Inches(1), Inches(1.7), Inches(10), Inches(0.4),
    "An LLM agent answers natural language questions against live forecast data.",
    size=16, color=DK_BEIGE, font=FONT_SANS, italic=True)

questions = [
    ("What is the 2026 vs 2025 comparison?",
     "\u00a3605M vs \u00a3518M, an increase of \u00a387M (+17% YoY)"),
    ("Break down July 2025 by platform",
     "Platform 1: \u00a331.9M (99.2%)  |  Platform 2: \u00a3381K (0.8%)"),
    ("Compare March 2026 vs March 2025",
     "\u00a364.6M vs \u00a353.9M, +\u00a310.8M increase (+20%)"),
]

for i, (q, a) in enumerate(questions):
    y = Inches(2.6 + i * 1.5)
    rect(s, Inches(0.8), y, Inches(11.5), Inches(1.25), DK_TEAL_MID)

    # Question icon
    circle(s, Inches(1.1), y + Inches(0.3), Inches(0.5), DK_GREEN)
    txt(s, Inches(1.1), y + Inches(0.33), Inches(0.5), Inches(0.45),
        "Q", size=16, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF,
        align=PP_ALIGN.CENTER)

    txt(s, Inches(1.8), y + Inches(0.15), Inches(4.5), Inches(0.5),
        q, size=15, color=DK_WHITE, bold=True, font=FONT_SANS)
    txt(s, Inches(1.8), y + Inches(0.6), Inches(10), Inches(0.5),
        a, size=14, color=DK_GREEN, font=FONT_MONO)


# ── SLIDE 9: Key Advantages ──────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_WHITE)
logo_black(s, Inches(11.5), Inches(0.4), h=Inches(0.28))

txt(s, Inches(1), Inches(0.5), Inches(6), Inches(0.4),
    "WHY DATAIKU", size=12, color=DK_GREEN, bold=True, font=FONT_MONO)
txt(s, Inches(1), Inches(0.9), Inches(8), Inches(0.8),
    "Key Advantages", size=40, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF)

advantages = [
    ("Maintainability", "Visual recipes are self-documenting. Each step has a clear name with inspectable inputs and outputs. New team members understand the pipeline in minutes, not weeks."),
    ("Automation", "Upload new actuals, click Build. The entire 42-month forecast recalculates automatically. Scenarios trigger on schedule or data change."),
    ("Server-Side", "Runs on infrastructure with version control, access management, and audit logging. No more single-laptop risk."),
    ("Auditability", "Full data lineage from source to output. Click any dataset to inspect intermediate values. Automated validation catches discrepancies."),
    ("Scalability", "Add new segments, products, or assumption factors by uploading new lookup tables. The flow adapts without restructuring."),
    ("AI-Ready", "LLM agent enables natural language queries. Dashboards provide visual drill-down. Data is live, governed, and team-accessible."),
]

for i, (title, desc) in enumerate(advantages):
    col, row = i % 3, i // 3
    x = Inches(0.6 + col * 4.1)
    y = Inches(2 + row * 2.5)
    bar(s, x, y + Inches(0.05), h=Inches(2), color=DK_GREEN)
    txt(s, x + Inches(0.25), y, Inches(3.6), Inches(0.45),
        title, size=17, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF)
    txt(s, x + Inches(0.25), y + Inches(0.5), Inches(3.6), Inches(1.6),
        desc, size=12, color=DK_DARK_GREY, font=FONT_SANS)


# ── SLIDE 10: Closing ────────────────────────────────────
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s, DK_DARK_GREEN)
logo_white(s, Inches(1), Inches(0.6))

txt(s, Inches(1), Inches(2.2), Inches(11), Inches(1.2),
    "From Spreadsheet\nto Platform", size=52, color=DK_WHITE, bold=True,
    font=FONT_SERIF)

divider(s, Inches(1), Inches(3.9), Inches(3), DK_GREEN)

txt(s, Inches(1), Inches(4.3), Inches(11), Inches(0.6),
    "Same calculations. Same accuracy. Completely different capability.",
    size=20, color=DK_BEIGE, font=FONT_SANS, italic=True)

# Before / After cards
rect(s, Inches(1), Inches(5.3), Inches(5), Inches(1.4), DK_BEIGE)
txt(s, Inches(1.3), Inches(5.4), Inches(4.4), Inches(0.4),
    "Before: Excel", size=18, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF)
txt(s, Inches(1.3), Inches(5.85), Inches(4.4), Inches(0.7),
    "1 user, 1 laptop, manual refresh,\nno audit trail, weeks to onboard",
    size=13, color=DK_DARK_GREY, font=FONT_SANS)

rect(s, Inches(6.8), Inches(5.3), Inches(5), Inches(1.4), DK_GREEN)
txt(s, Inches(7.1), Inches(5.4), Inches(4.4), Inches(0.4),
    "After: Dataiku", size=18, color=DK_DARK_GREEN, bold=True, font=FONT_SERIF)
txt(s, Inches(7.1), Inches(5.85), Inches(4.4), Inches(0.7),
    "Team-wide, server-side, automated,\nAI-powered, fully auditable",
    size=13, color=DK_DARK_GREEN, font=FONT_SANS)


# ── Save ──────────────────────────────────────────────────
output_path = os.path.expanduser(
    "~/Documents/Areas_new/Dataiku/test/Quilter/WM_FPA_New_Business_Forecast.pptx"
)
prs.save(output_path)
print(f"Saved: {output_path}")
print(f"Slides: {len(prs.slides)}")
