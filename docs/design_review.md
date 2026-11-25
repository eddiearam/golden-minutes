# Design review log

Screenshots are taken with `web/scripts/screens.mjs` (Playwright driving the installed Chrome) against a production build (`npm run build && npx vite preview`). Each pass covers: citywide default, a selected zip with the Island expanded, the optimised view, the heatmap drawer open, 1280 px width, the About sheet, and frame sequences of the Island morph (`island-morph-*`) and digit roll (`island-roll-*`).

## Pass 1 (`docs/screenshots/pass1/`)

Problems found against DESIGN.md:
- The hour slider card covered the map legend.
- Savings under a tenth of a minute showed as "−0.1" or "−0.0 min", which hides the real size (about 4 seconds) and reads as an error.
- Island pill: the rolling digits sat below the text baseline and briefly overflowed while rolling.
- Opening the drawer shrank the map without refitting it, so the city was cut off under the slider.
- Heatmaps were small, with tiny labels.
- Selecting a zip zoomed in too far for a "gentle" zoom.
- The demand chart's y axis labelled zero as "0.0".

Fixes: slider moved to the bottom left with the legend at the bottom right; savings under a minute shown in seconds ("−4 s"), and "No change" when nothing changes; roller rows given a fixed height that matches the line height; the map refits on resize when no zip is selected; taller heatmap cells; maximum selection zoom lowered from 12.2 to 11.4 with more padding; zero tick shown as "0".

## Pass 2 (`docs/screenshots/pass2/`)

Problems found:
- The About sheet still described the earlier station-only travel model.
- The map attribution control collided with the legend.
- "−4s" was missing its space, because the roller dropped plain spaces.
- With the drawer open, the heatmap captions wrapped and took vertical space from the map.

Fixes: About text updated to describe stations plus hospitals, the year term, and the model's weak geographic fit; attribution moved into the legend card as a credit line; non-breaking space with a fixed width in the roller; heatmap title and caption put on one line, and the drawer made more compact.

## Pass 3 (`docs/screenshots/pass3/`)

Problems found:
- The error heatmap's header wrapped, so its grid sat lower than the other two.
- The boundary credit wrapped onto two lines.
- A finding read "dispatch -0.0" (a negative zero from formatting).

Fixes: the third heatmap is titled "Error"; the credit text is shortened; findings format values that round to zero as "0.0".

## Final (`docs/screenshots/final/`)

Checked: no page errors or console errors in any view; no overlapping controls at 1440 x 900 or 1280 x 800. The Island moves to the far side when the hovered or selected zip lies under its centre, and fills its three-segment bar left to right. The roller animates digit by digit, and the green chip fades in only in the optimised view. Searching a zip and pressing Enter selects it, and the arrow keys move the hour slider. Text colours meet 4.5:1: secondary text uses #6E6E73 on white and #636366 on the grey base, and red and green text use the darker #CE2C31 and #18794E. The DESIGN.md red and green are kept for fills.

## Follow-up: browsers that block WebGL

In Brave with graphics acceleration turned off, the map could not create its WebGL context, and the error blanked the whole page right after it drew. The map now catches the failure, as well as a lost WebGL context, and shows a short message in its place. The top bar, panel and charts keep working.
