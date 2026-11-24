# Design

A typographic instrument plate for a single reading: whether the top 500 one-month leaders on Hyperliquid are, on balance, long or short Bitcoin, and how confident that balance is.

The page is a report, not a landing page. It should look as if it were issued, not generated.

## Avoid

The tells below are compiled from published writing on “AI slop” web design. None of them, alone, proves that a page was made by a model. The problem is the cluster: interchangeable structure, decorative effects doing the work of hierarchy, and copy that would still make sense if the product name were swapped. Sources: [InterfaceKit](https://blog.interfacekit.io/what-makes-a-website-look-ai-generated), [Bad HTML](https://badhtml.com/ai-slop-website-design/), [Monstric](https://monstric.com/blog/what-is-ai-slop-in-web-design), [Paralect](https://www.paralect.com/blog/signs-of-ai-slop-in-design), [Booplex](https://booplex.com/blog/what-is-ai-design-slop), [Unslop UI](https://unslopui.org/blog/ai-generated-website-audit-checklist), [Foundey](https://foundey.com/blog/how-to-tell-if-design-is-ai-generated), and [signs-of-ai-design](https://github.com/febbhav/signs-of-ai-design).

### Colour and effects

- Purple-to-blue, indigo, or cyan gradients on backgrounds, buttons, or headlines.
- Decorative glows, radial halos, spotlights, and neon outlines.
- Glassmorphism: frosted cards, `backdrop-filter: blur`, glowing borders.
- Gradient-coloured text.
- Permanent dark mode with luminous accents as a default “tech” look.
- Decorative graph-paper or grid backgrounds that do not organise the data.
- Excessive corner rounding, pill-shaped badges, stacked shadows, and coloured side-stripes on cards.
- The newer default of warm beige pages with ornamental italic serif display type and terracotta accents. That is a different template, not an escape from one.

### Layout and components

- A formulaic hero: pill badge, oversized headline, supporting paragraph, two call-to-action buttons, logo strip.
- A generic hero followed by three identical feature cards (icon tile, short heading, grey blurb).
- Uniform card grids, nested cards, and rounded icon tiles for every section.
- Giant decorative statistics (“10k+ users”, “99.9% uptime”) that are not this page’s actual measurement.
- Mechanical identical spacing and fake section indices such as “01 / THE VISION”.
- Emoji used as icons or decoration.

### Typography and copy

- Inter, Roboto, Space Grotesk, Geist, or any “default SaaS sans” used because no type decision was made.
- Oversized display headlines that consume the first viewport and leave no room for the reading.
- Vague taglines (“supercharge your workflow”, “unlock insights”, “next-generation platform”, “not just a tool — a revolution”).
- Forced contrast slogans, “world-class” / “enterprise-grade” / “seamless” language, and filler social proof.

### Interaction and completeness

- Decorative motion: pulsing “live” dots, auto-scrolling logos, bouncing badges.
- Generic abstract illustrations (orbs, cubes, floating shapes) that do not encode the data.
- Missing empty, loading, and error states; buttons or links that go nowhere.
- A page that would still work if the logo, name, and accent were replaced with those of another product (the substitution test). With decoration stripped, nothing of substance should disappear (the decoration-off test).

This project fails the substitution test on purpose: the plate only makes sense as a Bitcoin consensus reading from a named cohort of Hyperliquid wallets.

## Direction

The visual language is a **mission-control instrument plate** crossed with a **printed technical report** (NASA / NOAA / approach-plate discipline, Tufte’s data-ink habit).

It is not a cream lifestyle article, and it is not a dashboard of cards. It is one issued sheet: document marks in the header, a single primary figure, a verdict set in type, supporting tables, and captions of the form “Fig. 1”.

### Why this, and not a template

- The object on the page is the reading itself, not a product pitch.
- A wireframe inclination sphere is a measuring instrument. Its tilt is P(long). If the effect is turned off, an SVG dial and the typographic verdict remain.
- The typographic grid, hairlines, and figure captions are the layout. There is no decorative background grid sitting behind a hero.
- Paper stock is the ground of a printed plate, not a beige-editorial trend. Type is IBM Plex, not a display serif.

### Colour

One ink family, one accent. No second colour for long versus short; those words do the work.

| Role | Value | Use |
| --- | --- | --- |
| Paper | `#EFECE6` | Page ground |
| Ink | `#141414` | Text, rules, the sphere |
| Muted | `#3F3F3A` | Meta, captions, secondary labels (still ≥ 4.5:1 on paper) |
| Hairline | `#B7B3A9` | Rules, table lines, sphere backfaces |
| Accent | `#8C1D12` | Verdict word, instrument needle / consensus ring, figure callouts only |

No gradients, no glows, no shadows, no colour fills on cards. The README banner is a self-contained plate with the same paper ground, so it remains legible on both light and dark GitHub themes.

### Type

Two families only, both IBM Plex, vendored as woff2:

- **IBM Plex Sans** (Regular, Medium, SemiBold) for prose, titles, and small-caps labels.
- **IBM Plex Mono** (Regular) for every number, address, timestamp, and identifier.

Labels use `font-variant: small-caps` with modest letter-spacing. There is no Inter, Roboto, Space Grotesk, Geist, or display serif. Body text stays small enough to read as a report (16px body, 12–13px captions and meta). The verdict is large, but it shares the page with Fig. 1 rather than evicting it.

### Grid and form

- A centred sheet, maximum width 1,040px, with generous side margins and a consistent inner column.
- Hairline rules, not cards, separate regions.
- Corner registration marks and a document head (series id, issue time in IST, data age).
- Figure captions under instruments and tables: “Fig. 1. Consensus inclination.”, “Fig. 2. History of P(long).”, “Fig. 3. Largest BTC positions in the cohort.”
- Zero border-radius. Zero drop shadow. Tight, deliberate spacing: denser inside a table than between figures.

### Fig. 1 — Inclination sphere

A monochrome wireframe sphere, drawn in canvas with a simple perspective projection of meridians and parallels. An accent great-circle (the consensus ring) tilts with weighted P(long):

- P(long) = 0 lies toward SHORT.
- P(long) = 0.5 leaves the ring on the equator (neutral).
- P(long) = 1 lies toward LONG.

A short scale and a hairline needle sit beside the sphere. A very slow yaw, if motion is allowed, is only to read the form; it does not decorate. The sphere is an instrument, not an orb illustration.

Graceful degradation:

- `prefers-reduced-motion: reduce` — no yaw; the ring sits at the correct tilt.
- No canvas / no JavaScript — a static SVG dial with the same scale, plus the typographic verdict, which is always in the HTML.
- Narrow viewports — the sphere shrinks and stacks above the verdict; the page remains readable without horizontal overflow.

### Page order

1. Document head: series, issue timestamp (IST, with zone label), freshness, link to the GitHub repository.
2. Title stating the actual measurement, not a slogan.
3. Fig. 1 (sphere) beside the verdict, P(long), interval, and sample size.
4. Fig. 2: a strip-recorder sparkline of stored P(long) snapshots, not a filled gradient chart.
5. A compact data block: raw long / short / flat counts, long and short BTC notional, and a size breakdown (hairline bars or a small table, not scorecards).
6. Fig. 3: a typographic table of the top 20 BTC positions (short address, side, size, entry, leverage, unrealised PnL).
7. Method one-liner, limitations pointer, and a clear not-financial-advice note.

Empty, loading, and stale-data states are typographic, not skeleton cards: “No snapshot yet.”, “Waiting for the first sweep.”, “This snapshot is older than two hours.”

### Motion, access, and speed

- One optional motion: the sphere’s slow yaw. Everything else is static.
- Semantic HTML, a real heading hierarchy, table headers, captions, and an `aria-label` on the canvas that states the current P(long) and verdict.
- Focus styles are a 2px ink outline, not a glow.
- Contrast meets WCAG AA for body and labels on paper.
- No runtime font or script CDN. Fonts are local. The site is static files plus `data/signal.json`.
- No three.js, no WebGL requirement. Canvas 2D only.

### README, banner, and GIF

The README banner is the same plate language: paper ground, hairlines, small-caps, monospaced figures, a still drawing of the inclination sphere, and the series title. It carries its own background so it works in light and dark mode.

The demo GIF is a recording of the real page (verdict, sphere, sparkline, table), not a marketing mock, in the same palette. No emoji, no transitions that the site itself does not have.

### What this page will not contain

A feature-card row, a call-to-action pair, a testimonial band, a logo wall, a chatbot bubble, a pulsing live dot, fake statistics, or a headline that could sell another product.
