"""
Regenerate the README screenshots (docs/images/) with headless Chrome.

Development tool, not part of the app. It drives a separate headless
Chrome/Edge through the DevTools protocol (using the `websockets` package
that Streamlit already installs), clicks through the site and the app, and
saves PNGs.

    # terminal 1: the website      python -m http.server 8000 --bind 127.0.0.1 --directory site
    # terminal 2: the app          streamlit run app/streamlit_app.py
    # terminal 3:                  python tools/screenshots.py shots
Then review the images and copy the ones you want into docs/images/
(the README uses site-hero.jpg, site-results.png, app-screener.png, app-results.png).
"""

import asyncio
import base64
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from websockets.asyncio.client import connect as ws_connect

CHROME_CANDIDATES = [
    os.environ.get("CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]
CHROME = next((c for c in CHROME_CANDIDATES if c and os.path.exists(c)), None)


class Browser:
    def __init__(self, width=1440, height=900, port=9333):
        self.port, self.w, self.h = port, width, height
        self.profile = tempfile.mkdtemp(prefix="cdp-")
        self.proc = subprocess.Popen(
            [
                CHROME,
                "--headless=new",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={self.profile}",
                f"--window-size={width},{height}",
                "--hide-scrollbars",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--no-first-run",
                "--mute-audio",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.ids = itertools.count(1)

    async def connect(self):
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
                ws = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
                break
            except Exception:
                await asyncio.sleep(0.2)
        self.ws = await ws_connect(ws, max_size=200 * 1024 * 1024)
        await self.send(
            "Emulation.setDeviceMetricsOverride",
            width=self.w,
            height=self.h,
            deviceScaleFactor=1,
            mobile=False,
        )

    async def send(self, method, **params):
        i = next(self.ids)
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def goto(self, url, wait=4):
        await self.send("Page.navigate", url=url)
        await asyncio.sleep(wait)

    async def js(self, expr):
        r = await self.send(
            "Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True
        )
        return r.get("result", {}).get("value")

    async def shot(self, path, clip=None):
        params = {"format": "png"}
        if clip:
            params["clip"] = {**clip, "scale": 1}
        data = (await self.send("Page.captureScreenshot", **params))["data"]
        open(path, "wb").write(base64.b64decode(data))
        print("saved", path)

    def close(self):
        self.proc.terminate()


async def click_text(b, selector, text):
    """Real mouse click (Input.dispatchMouseEvent) on the element with this exact text."""
    for _ in range(
        40
    ):  # wait for the element to exist (Streamlit renders after its websocket connects)
        pos = await b.js(f"""(()=>{{const el=[...document.querySelectorAll({selector!r})].find(x=>x.innerText.trim()==={text!r});
        if(!el) return null; el.scrollIntoView({{block:'center'}}); const r=el.getBoundingClientRect();
        return {{x:r.left+r.width/2, y:r.top+r.height/2}}}})()""")
        if pos:
            break
        await asyncio.sleep(0.5)
    if not pos:
        raise RuntimeError(f"not found: {text}")
    await asyncio.sleep(0.5)
    for kind in ("mousePressed", "mouseReleased"):
        await b.send(
            "Input.dispatchMouseEvent",
            type=kind,
            x=pos["x"],
            y=pos["y"],
            button="left",
            clickCount=1,
        )


CONSENT_TEXT = (
    "I understand that this is an educational estimate, not medical advice, "
    "and how my answers are handled."
)


async def main(out, which):
    os.makedirs(out, exist_ok=True)
    b = Browser()
    try:
        await b.connect()
        await _capture(b, out, which)
    finally:
        b.close()


async def _capture(b, out, which):
    if "site" in which:
        await b.goto("http://127.0.0.1:8000/", wait=6)
        await b.shot(f"{out}/site-hero.png")
        # Results heading + comparison card + flow chart, after their animations ran.
        await b.js("document.querySelector('#results').scrollIntoView({block:'start'}); 1")
        await asyncio.sleep(2)
        await b.js("document.querySelector('#chart-flow').scrollIntoView({block:'end'}); 1")
        await asyncio.sleep(3)
        r = await b.js("""(()=>{const a=document.querySelector('#results').getBoundingClientRect(), f=document.querySelector('#chart-flow').getBoundingClientRect();
            return {x:a.left, y:a.top+window.scrollY, w:a.width, h:f.bottom-a.top}})()""")
        await b.shot(
            f"{out}/site-results.png",
            clip={"x": r["x"] - 32, "y": r["y"] - 24, "width": r["w"] + 64, "height": r["h"] + 48},
        )
    if "app" in which:
        await b.goto("http://localhost:8501/", wait=10)
        # The consent screen comes first (once per browser session).
        await click_text(b, "label, p, span", CONSENT_TEXT)
        await asyncio.sleep(1)
        await click_text(b, "button", "Continue")
        await asyncio.sleep(8)  # the first run after start-up is slow
        await click_text(b, "button", "Assess risk")
        for _ in range(90):  # first assessment also loads the models (~15 s)
            await asyncio.sleep(1)
            if await b.js(
                "document.querySelectorAll('.js-plotly-plot').length > 0 && !document.querySelector('[data-testid=stSpinner]')"
            ):
                break
        else:
            raise RuntimeError("no result appeared")
        await asyncio.sleep(2)
        await b.js(
            "[...document.querySelectorAll('h3')].find(h=>h.innerText.includes('Stage 1 result')).scrollIntoView({block:'start'}); window.scrollBy(0,-24); 1"
        )
        await asyncio.sleep(1.5)
        await b.shot(f"{out}/app-screener.png")
        # Navigate inside the same session (a fresh page load would ask for consent again).
        await click_text(b, "[data-testid=stSidebarNav] span", "Results")
        await asyncio.sleep(6)
        await click_text(b, "[role=tab]", "Calibration")
        await asyncio.sleep(2)
        await b.js(
            "document.querySelector('[role=tablist]').scrollIntoView({block:'start'}); window.scrollBy(0,-70); 1"
        )
        await asyncio.sleep(2)
        await b.shot(f"{out}/app-results.png")


if __name__ == "__main__":
    if CHROME is None:
        sys.exit("Chrome/Edge not found: set the CHROME environment variable to its path.")
    asyncio.run(
        main(sys.argv[1] if len(sys.argv) > 1 else "shots", sys.argv[2:] or ["site", "app"])
    )
