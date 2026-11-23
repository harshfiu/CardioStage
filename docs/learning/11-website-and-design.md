# Phase 11: The Website & the Redesign

**Goal:** give CardioStage a premium, human face (a public website with smooth scrolling and animation, and a matching dark app) without giving up any of the honesty or security built in Phases 1–10.

This phase is mostly front-end (HTML, CSS, JavaScript), which is new territory for an ML project. The ideas that matter most aren't about animation, though: they're about **never hand-typing a statistic**, **checking design choices with numbers**, and **finding a real subtlety in our own results while drawing a chart**.

**Files in this phase**

| File | Job |
|---|---|
| `site/index.html` | The landing page (structure and text) |
| `site/assets/css/site.css` | Colours, fonts, layout, responsive breakpoints |
| `site/assets/js/main.js` | Fills in numbers, builds the charts, runs the motion |
| `site/vendor/` | GSAP, Lenis, three.js, Vanta: stored in the repo, not loaded from the internet |
| `src/cardiostage/site_data.py` | Exports every number on the site from `reports/` and `models/` |
| `.github/workflows/pages.yml` | Publishes `site/` to GitHub Pages |
| `.streamlit/config.toml` | The app's dark theme and self-hosted fonts |
| `app/charts.py` | The Results page's charts, redrawn in Plotly (dark, interactive) |
| `src/cardiostage/chart_data.py` | Exports the extra data those charts need |
| `tools/screenshots.py` | Regenerates the README screenshots with headless Chrome |
| `tests/test_site.py`, `tests/test_charts.py` | 19 tests: security of the site, numbers vs reports, every chart builds |

```bash
python -m cardiostage.site_data                       # refresh the website's numbers
python -m cardiostage.chart_data                      # refresh the Results charts' data
python -m http.server 8000 --bind 127.0.0.1 --directory site   # preview the site
streamlit run app/streamlit_app.py                    # the restyled app
```

---

## 1. Why a separate website?

Streamlit builds a whole page from Python. It's perfect for the screener, but it **can't run custom JavaScript libraries on its own pages** (only inside small iframes). Smooth scrolling (Lenis), scroll-driven animation (GSAP) and a WebGL background (Vanta) all need full control of the page.

So there are now two front ends with different jobs:

| | Website (`site/`) | App (`app/`) |
|---|---|---|
| Purpose | Explain the project to anyone | Actually run the screener |
| Where | Public, GitHub Pages | Your computer only (localhost) |
| Runs the model? | **No.** Static files, no input | Yes |
| Motion | Tasteful animation | None near risk numbers |

The website being **static** (just files, no server code) is what makes it safe to publish: there's nothing to hack into and no patient data anywhere near it.

## 2. Never hand-type a statistic

The website says "40% fewer invasive tests", "0 of 28 sick patients missed" and shows a patient-flow chart. If those were typed into the HTML, they'd silently go stale the next time the models were retrained.

Instead, `site_data.py` **reads the real results** and writes them to `site/assets/data/site-data.json` (plus a `.js` copy, see §6). The page's JavaScript fills every number in from that file:

```
reports/*.csv + models/  ──site_data.py──►  site-data.json  ──main.js──►  "40%", charts…
```

`tests/test_site.py` then checks the exported numbers **against the reports**: the recall matches `phase5_strategies.csv`, the patient flow adds up (26 + 33 + 184 = 243), and 146/243 equals the reported 60% needing invasive tests. If someone edits one without the other, a test fails.

> **Lesson:** this is the same principle as "one source of truth" in `config.py` (Phase 1), applied to presentation. Results flow one way: from the analysis to the page.

## 3. The libraries, in plain English

### Lenis: smooth scrolling
Normally the mouse wheel jumps the page in steps. Lenis eases the scroll position towards where you're heading, which feels smoother. The key detail is keeping it **in sync** with GSAP, so animations tied to scrolling don't lag behind:

```js
var lenis = new Lenis({ lerp: 0.1, smoothWheel: true });  // move 10% closer each frame
lenis.on("scroll", ScrollTrigger.update);                  // tell GSAP whenever we scroll
gsap.ticker.add(function (t) { lenis.raf(t * 1000); });    // one shared animation clock
```

### GSAP + ScrollTrigger: animation tied to scrolling
GSAP animates any property over time (`gsap.from(el, { y: 28, opacity: 0 })` = "start 28 px lower and invisible, end where you are"). **ScrollTrigger** starts an animation when an element scrolls into view, or ties it directly to the scroll position:

```js
gsap.timeline({ scrollTrigger: {
  trigger: ".how", start: "top top", end: "+=1400",  // for 1400 px of scrolling…
  scrub: 0.6,                                          // …the timeline follows the scrollbar
  pin: true                                            // …while the section stays fixed
}});
```
That's the "How it works" section: it **pins** in place while a blue line travels and each stage card lights up. `gsap.matchMedia` only does this on screens ≥ 900 px wide; on phones the cards simply light up as they appear.

### SplitText and DrawSVG: the hero's details
- **SplitText** splits the headline into words so each can rise in turn. `aria: "auto"` keeps the sentence readable to screen readers, which would otherwise announce the pieces separately.
- **DrawSVG** animates an SVG line from 0% to 100% of its length, so the hand-drawn heart and ECG appear to draw themselves.

### Vanta NET: the moving network background
Vanta uses **three.js** (WebGL, the GPU) to draw the blue network behind the headline. It's the heaviest effect, so it runs **only while the hero is on screen**:

```js
new IntersectionObserver(function (entries) {
  entries.forEach(function (en) { en.isIntersecting ? start() : stop(); });
}).observe(host);
```
If a device has no WebGL, `start()` fails inside a `try` and the static gradient stays. Nothing breaks.

## 4. Motion that respects people

Some people get dizzy or nauseous from motion on screens, and set "reduce motion" in their operating system. The site checks this **first**:

```js
var REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
var MOTION = !REDUCE && HAS_GSAP;   // no motion code runs at all if REDUCE
```
The HTML already contains every word in its final position. JavaScript only *adds* motion on top, so with motion off (or JavaScript blocked) the page is complete. The app has no motion at all near a risk estimate: a number about someone's heart shouldn't bounce.

## 5. Design decisions, checked with numbers

### The palette: "dark medical-tech, warmed up"
Near-black `#080B12`, warm off-white text `#F3EEE6`, peach `#F2B880` for actions, and the same meaning colours everywhere: **coral raises risk, blue lowers it, mint means reassured**.

### Contrast is computed, not eyeballed
Text must stand out from its background enough to read (the WCAG guideline: ≥ 4.5:1 for body text). The contrast ratio comes from each colour's *relative luminance* L:

```
contrast = (L_lighter + 0.05) / (L_darker + 0.05)
```
Computed for every pair: warm text on the background is 17.0:1 and peach is 11.2:1. The surprise was **white text on a peach button: 1.76:1**, far too low. Streamlit always draws primary buttons with white text, so the app's buttons use the outlined style instead. The website's peach buttons use dark text (10.7:1).

> **Lesson:** a colour that "looks fine" on your screen can be unreadable for someone with low vision or on a bright laptop in sunlight. Measure.

### Chart colours were validated too
The Results charts' categorical colours (blue, orange, aqua, yellow) passed a colour-blindness validator on the dark background: every adjacent pair stays distinguishable under the three common types of colour blindness.

## 6. Security on a public page

The website is the first part of CardioStage anyone on the internet can load, so (continuing [Phase 10](10-security.md)):

- **Content-Security-Policy (CSP):** a line in the HTML telling the browser "only run scripts and styles from this site itself" (`script-src 'self'`). Even if someone injected a `<script>`, the browser would refuse it. That's also why the page has **no inline scripts or styles**: they'd need `unsafe-inline`, which weakens the policy.
- **Vendored libraries:** GSAP, Lenis, three.js, Vanta and both fonts are stored in `site/vendor/` and `site/fonts/`, not loaded from a CDN or Google Fonts. So visitors' browsers contact **nobody else**, the page works offline, and the CSP can stay strict. Lenis, three.js and Vanta were downloaded from npm and checked against their published `sha512` checksums before use; GSAP was copied from its official repository.
- **Why there's also a `site-data.js`:** browsers block `fetch()` of local files (`file://`), so the data is also written as a script that sets `window.CARDIOSTAGE_DATA`. A `<script src>` from the site itself is allowed by the CSP.
- **Tests enforce it:** `test_site.py` fails if the CSP loosens, an inline script appears, or anything is loaded from another domain.

## 7. The app restyle

Streamlit themes are set in `.streamlit/config.toml`: `base = "dark"`, the colours, and the fonts. Fonts are **self-hosted** with Streamlit's static file serving (`enableStaticServing = true` serves `app/static/`). Turning that on opens a new route, so:
- a test checks `app/static/` contains **only** `.woff2` font files;
- it was probed by hand: a font → 200, a folder → 404, `../` path traversal → **400** (refused).

### The Results charts, redrawn
The Results page used to show the PNG figures from Phases 4–9: light backgrounds, white boxes on the dark page. They're now drawn natively with **Plotly** in `app/charts.py`, matching the theme and showing exact values on hover.

Six charts could be built straight from the committed CSV tables. Three needed data those tables didn't keep (calibration curve points, external calibration, the case study). Rather than re-running whole analyses, `chart_data.py` recomputes **only those**, using the **same functions** the analysis phases used (`_reliability`, `expected_calibration_error`, `prior_shift`, `StageExplainer`), and saves `reports/chart_data.json`. A test confirms all 12 ECE values match `phase5_calibration.csv` and `phase6_external.csv` exactly. The PNGs remain the versions used in the README and docs.

## 8. A real finding while drawing a chart

While writing a test for the case-study chart ("the woman was cleared, so her risk should be below the 9.0% cut-off"), the test **failed**: the chart said 9.2%.

Both numbers were right, but they answer different questions:

| Number | From | Meaning |
|---|---|---|
| **7.1%** | Out-of-fold models that **never saw her** | The honest evaluation. Below the cut-off, so the staged policy cleared her |
| **9.2%** | The final model, trained on all 243 patients **including her** | What the chart explains |

The original PNG had the same subtlety, unexplained. The Results page now states both numbers in plain words. The test was fixed to check the right thing (the out-of-fold risk), not loosened to pass.

> **Lesson:** a failing test is information. Before changing a test to make it pass, find out which side is wrong. Here, neither was: the *explanation* was missing.

## 9. Mistakes caught along the way

| Mistake | Fix | Lesson |
|---|---|---|
| A hand-typed `28` in the JavaScript | Exported `n_sick` from the data | Even one hard-coded number can drift |
| "3 hospitals" counted up from 0, showing "1 hospitals" mid-way | Small numbers are shown directly | Animate only where it adds meaning |
| Explanation values overlapped their labels | Values got their own grid column | Test with the longest real label |
| Hospital/fairness labels sat on the error bars | Labels placed just past each error bar | Look at every chart at more than one width |
| ECE notes inside calibration panels collided at 1440 px | Numbers moved to a caption under the chart | Fixed-width text in a flexible panel always breaks somewhere |
| "Three commands to set up" (it's about seven) | "About 15 minutes to set up…" | Marketing copy must be as honest as the results |
| Edited CSS seemed to do nothing | Hard reload (Ctrl+Shift+R); browsers cache files | Rule out caching before debugging code |
| Edited `charts.py` seemed to do nothing | Restart Streamlit (imported helper modules are cached) | Know what your tools reload automatically |

## 10. Publishing and screenshots

- **GitHub Pages:** `pages.yml` runs on every push to `main` that touches `site/`, uploads the folder and deploys it. It only has permission to deploy Pages (`pages: write`), nothing else. The site lives at `https://harshfiu.github.io/CardioStage/`.
- **README screenshots** are made by `tools/screenshots.py`. It starts a separate headless Chrome, controls it through the **DevTools protocol** (the same channel browser developer tools use), clicks "Assess risk" with a real mouse event, waits for the result, and saves PNGs. A JavaScript `.click()` wasn't enough: Streamlit's form only reacted to a real pointer event.

## 11. Check your understanding
1. Why can't the Lenis/GSAP/Vanta effects simply be added to the Streamlit app?
2. What problem does `site_data.py` solve, and how do the tests make sure it keeps working?
3. Why does the website contain no inline `<script>` blocks or `style="…"` attributes?
4. The app's buttons are outlined rather than solid peach. Why?
5. Why does Vanta stop when the hero scrolls off screen?
6. The case-study woman's risk is 7.1% in one place and 9.2% in another. Why are both correct, and which one decided that she was cleared?
7. What does a visitor with "reduce motion" turned on see?

## Answers

**1.** Streamlit generates its pages from Python and doesn't let you run arbitrary JavaScript on them, only inside small sandboxed iframes. Full-page smooth scrolling and pinned scroll animations need control of the whole page, so they live on a separate static site.

**2.** It stops statistics on the website from going stale or being mistyped. Every number is exported from the real reports, and `test_site.py` compares the export with the reports (and checks that the patient flow adds up), so a mismatch fails the test suite.

**3.** The Content-Security-Policy says `script-src 'self'` and `style-src 'self'`: only files from the site itself may run. Inline code would require `'unsafe-inline'`, which would also let injected code run. Keeping all code in files lets the policy stay strict.

**4.** Streamlit draws primary buttons with white text, and white on peach has a contrast ratio of only 1.76:1, far below the 4.5:1 needed for readable text. The outlined style keeps the text readable.

**5.** It uses the GPU through WebGL and redraws dozens of times per second. Running it while it's invisible would waste battery and slow the page for no benefit, so an IntersectionObserver starts and stops it.

**6.** 7.1% comes from out-of-fold models that never saw her: the honest evaluation, and the one the staged policy used to clear her (below the 9.0% cut-off). 9.2% comes from the final model, which was trained on all patients including her, so its estimate for her is slightly different. The chart explains the final model; the page states both.

**7.** The complete page, with all text, numbers and charts in their final state. No smooth scrolling, no pinning, no drawing or count-ups, and no Vanta background. The motion code never runs.
