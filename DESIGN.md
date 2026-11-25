# Golden Minutes: design spec

## Principle
An operations tool a city director would trust: calm, precise, Apple-like, with a soft neumorphic feel on controls and cards. The map is the canvas; the response-time breakdown is the insight. Data and text are always flat and high contrast.

## Layout (desktop first, 1440x900 target; must still work at 1280 and on a tablet)
- Top bar (64px): "Golden Minutes" on the left; centre a segmented control "Today | Optimised staging"; a second segmented control "All | Life-threatening"; right a headline metric showing median minutes saved with a small caption.
- Centre (about 65% width): full-height map of NYC zip codes. The hour-of-week slider floats at the bottom of the map in a soft card, with play/pause to animate through the week.
- Right panel (about 35% width, scrollable): selected zip and borough; median and 90th percentile response; stacked horizontal bar splitting response into call handling, dispatch and travel (labelled minutes); small line of the zip's demand across the week; borough fairness bar chart (Today vs Optimised side by side).
- Bottom drawer (collapsible): hour-by-weekday heatmap of demand, actual vs forecast, with forecast error.
- Before a zip is selected, the right panel shows a citywide summary.

## Colour scheme
- Base surface: soft cool grey #EEF0F3 (page, cards, controls).
- Data surfaces: white #FFFFFF inside cards, behind charts and the map.
- Text: primary #1D1D1F, secondary #6E6E73. Hairlines and gridlines #E5E5EA.
- Delay: red #E5484D. Map scale runs from near-white to deep red.
- Improvement: green #30A46C, used only for minutes saved.
- Breakdown segments: call handling #8E8E93, dispatch #5E5CE6, travel #E5484D.
- Water on the map: very pale blue. No other colours.

## Neumorphism (controls and cards only)
- Cards and controls share the base colour and are shaped by dual soft shadows. Raised: 8px 8px 16px rgba(163,177,198,0.45) and -8px -8px 16px rgba(255,255,255,0.9). Pressed or active: the same shadows inset.
- Segmented controls, the slider track, buttons and the zip search box feel soft and tactile; the selected segment looks pressed in.
- Charts, the map, legends and all text sit flat on white inner surfaces. Never put soft shadows on data.
- Card radius 16px, padding 20 to 24px, 8px spacing grid, generous white space, no gradients except the map scale.

## Typography and motion
- Inter (400, 500, 600) with tabular figures for numbers. Sizes: 32 headline metric, 20 section titles, 15 body, 13 captions.
- 200 to 300ms ease-out for hovers and panels. Respect prefers-reduced-motion.

## Map
- MapLibre GL with no third-party basemap tiles and no API keys: zip polygons on a pale background, thin white borders, darker borough outlines, very light blue water.
- Colour zips by the metric for the selected hour. Legend in a small floating card. Grey hatching for zips with too little data, with a tooltip explaining why.
- Optimised view: staging points as small dark dots with a soft halo; switching views animates the colour change over 600ms.
- Hover lifts the zip outline and shows a compact tooltip (zip, median, calls). Click selects the zip, zooms gently and fills the right panel.

## Signature component: the Island (build with extra care)
- A dark pill (#1D1D1F, white text, fully rounded, subtle shadow) centred near the top of the map. At rest it shows "NYC · [severity] · Median X.X min" using real computed values.
- On zip hover or select it morphs smoothly (spring, about 350ms, overshoot no more than 2%) into a wider card with 24px radius showing the zip and borough, median and 90th percentile, and a three-segment mini bar (grey, indigo, red) that fills left to right over 400ms.
- On the Today / Optimised toggle, the minutes value rolls digit by digit to the new figure, and a green "-X.X min" chip fades in beside it in the optimised view.
- Collapses back to the pill when nothing is hovered or selected. Use Framer Motion layout animations; reduced motion falls back to simple fades. It must never cover the selected zip.

## Charts
- Flat, high contrast, direct labels instead of legends where possible, light gridlines, no 3D or decoration. Units on every axis. Minutes rounded to 1 decimal.

## Quality and accessibility
- Text contrast at least 4.5:1. Fully keyboard navigable: tab through controls, arrow keys move the slider, a searchable zip box selects zips with Enter.
- Skeleton loading states with no layout jump. Initial load under 2 seconds on a local build; precomputed JSON split by view.
- An "About the data" link opens a sheet with sources, the method in plain English and the limitations.

## Review loop (required)
- Use Playwright to screenshot: citywide default, a selected zip with the Island expanded, the optimised view, the heatmap drawer open, and 1280px width. Save to docs/screenshots/.
- Review each screenshot critically against this spec and fix anything cluttered, misaligned, low contrast or unfinished. Do at least three passes, paying special attention to the Island's motion and polish, before marking the app milestone done.
