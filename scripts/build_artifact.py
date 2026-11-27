#!/usr/bin/env python3
"""
scripts/build_artifact.py — Make the claude.ai Artifact version of the app from index.html.

An artifact page can't fetch from other hosts, so the GitHub fetches are replaced by
two layers: a saved copy of dashboard.json published beside the page, and, only in the
installed desktop app and only after the person allows it, a live download of the same
file. The page's own code is untouched, so there is one source of truth.

Output: OUT_DIR/index.html and OUT_DIR/dashboard.json (publish both with the Artifact tool).
Usage:  python3 scripts/build_artifact.py OUT_DIR
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600"
         "&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap")

SITE_FETCH = """  const minute = Math.floor(Date.now() / 60000);
  const URL='https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/dashboard.json?t='+minute;
  try{
    const res=await fetch(URL, { cache: 'no-store' });
    if(!res.ok)throw new Error('HTTP '+res.status);
    DB=await res.json();
"""
SITE_FETCH_NEW = """  try{
    DB=await fetchDashboard();
"""
TIMER_FETCH = """        const m = Math.floor(Date.now() / 60000);
        const r = await fetch('https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/dashboard.json?t='+m, { cache:'no-store' });
        if (r.ok) {
          const fresh = await r.json();
"""
TIMER_FETCH_NEW = """        {
          const fresh = await fetchDashboard();
"""
BANNER_SLOT = '  <!-- Screens -->\n  <div class="screens">'
BANNER_SLOT_NEW = '  <div id="data-banner" hidden></div>\n' + BANNER_SLOT

CSS = """
#data-banner{flex:none;display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;padding:8px 16px;
  font-family:var(--sans);font-size:12px;line-height:1.4;color:var(--text1);background:var(--bg2);
  border-bottom:1px solid var(--border)}
#data-banner[data-kind="live"]{color:var(--green)}
#data-banner[data-kind="failed"]{color:var(--red);background:var(--red-d)}
#data-banner[data-kind="saved"]{color:var(--amber);background:var(--amber-d)}
#data-banner .db-text{flex:1 1 220px;min-width:0}
#data-banner button,#data-banner a{font:inherit;font-weight:500;color:var(--cyan);background:none;
  border:1px solid var(--border-hi);border-radius:4px;padding:3px 10px;cursor:pointer;text-decoration:none}
#data-banner button:focus-visible,#data-banner a:focus-visible{outline:2px solid var(--cyan);outline-offset:2px}
"""

LOADER = r"""<script>
// Artifact data layer. A published page can't fetch other hosts, so it reads the saved
// copy beside it; in the installed desktop app, once allowed, it downloads the live file.
const SNAPSHOT_URL = 'dashboard.json';
const LIVE_URL = 'https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/dashboard.json';
const live = { on: false, error: '', checkedAt: null, desk: null };
let lastData = null;

function liveDownload() {
  const desk = live.desk;
  return new Promise(async (resolve, reject) => {
    try {
      const exe = (await desk.os.platform()) === 'win32' ? 'curl.exe' : '/usr/bin/curl';
      let out = '', err = '';
      const proc = desk.childProcess.spawn(exe, ['-fsSL', '--max-time', '30', LIVE_URL]);
      proc.stdout.on('data', c => { out += c; });
      proc.stderr.on('data', c => { err += c; });
      proc.on('error', reject);
      proc.on('close', code => {
        if (code !== 0) return reject(new Error('download failed (' + code + ') ' + err.trim().slice(0, 100)));
        try {
          const data = JSON.parse(out);
          if (!data.last_built || !data.watchlist) throw new Error('unexpected file');
          resolve(data);
        } catch (e) { reject(new Error('the download was cut short')); }
      });
    } catch (e) { reject(e); }
  });
}

async function fetchDashboard() {
  if (live.on) {
    try {
      const data = await liveDownload();
      live.error = ''; live.checkedAt = new Date(); lastData = data;
      if (window.renderBanner) window.renderBanner();
      return data;
    } catch (e) {
      live.on = false; live.error = String(e.message || e);
    }
  }
  const res = await fetch(SNAPSHOT_URL, { cache: 'no-store' });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  lastData = await res.json();
  if (window.renderBanner) window.renderBanner();
  return lastData;
}
</script>
"""

DESKTOP = r"""<script type="application/json" id="claude-artifacts-manifest">{"permissions": ["full-access"]}</script>
<script>
(function () {
  const bar = document.getElementById('data-banner');
  const state = { install: 'unavailable', app: false, perm: 'unavailable' };
  const when = d => new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  const wait = ms => new Promise(r => setTimeout(r, ms));

  function button(label, onclick) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label; b.onclick = onclick;
    return b;
  }

  window.renderBanner = function () {
    if (!bar) return;
    bar.replaceChildren();
    const text = document.createElement('div');
    text.className = 'db-text';
    const built = lastData && lastData.last_built ? when(lastData.last_built) : 'an earlier time';
    let kind = 'saved';
    if (live.on) {
      kind = 'live';
      text.textContent = 'Live data, checked ' + (live.checkedAt ? when(live.checkedAt) : 'now') + '. It refreshes every 5 minutes while this is open.';
    } else if (live.error) {
      kind = 'failed';
      text.textContent = 'Live data is not reaching this app (' + live.error + '). Showing the saved copy from ' + built + '.';
    } else {
      text.textContent = 'This is a saved copy from ' + built + ' and does not update by itself.';
    }
    bar.append(text);
    if (!live.on) {
      if (state.app && state.perm === 'prompt') bar.append(button('Turn on live updates', turnOn));
      if (state.app && state.perm === 'denied') bar.append(button('Live updates are off: open permissions', () => live.desk.permissions.manage().catch(() => {})));
      if (!state.app && state.install === 'available') bar.append(button('Install as app', install));
      if (!state.app && state.install === 'installed') text.textContent += ' Open the installed app for live data.';
      const a = document.createElement('a');
      a.href = 'https://tarun-talreja.github.io/TickRun/'; a.textContent = 'Open live site'; a.target = '_blank'; a.rel = 'noopener noreferrer';
      bar.append(a);
    }
    bar.dataset.kind = kind;
    bar.hidden = false;
  };

  async function install() {
    try { await live.desk.install.request(); } catch (e) { /* the person declined or it isn't offered here */ }
    state.install = await live.desk.install.state().catch(() => 'unavailable');
    window.renderBanner();
  }

  async function turnOn() {
    try {
      const result = await live.desk.permissions.request(['full-access']);
      state.perm = result['full-access'];
    } catch (e) { live.error = String(e.message || e); }
    if (state.perm === 'granted') { live.on = true; await refreshNow(); }
    window.renderBanner();
  }

  async function refreshNow() {
    for (let i = 0; i < 50 && !DB; i++) await wait(200);
    try {
      const fresh = await fetchDashboard();
      if (DB && fresh.last_built !== DB.last_built) {
        DB = fresh;
        renderHome(DB); renderWatchlist(DB); renderSignals(DB); renderPortfolio(DB); renderResearch(DB);
      }
      if (DB) renderPriceAge(DB);
    } catch (e) { live.error = String(e.message || e); }
  }

  function drawIcon() {
    const c = document.createElement('canvas'); c.width = c.height = 256;
    const g = c.getContext('2d');
    g.fillStyle = '#060910'; g.beginPath(); g.roundRect(8, 8, 240, 240, 56); g.fill();
    g.strokeStyle = '#00d9f5'; g.lineWidth = 12; g.lineJoin = 'round'; g.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 3 * i - Math.PI / 2;
      g[i ? 'lineTo' : 'moveTo'](128 + 84 * Math.cos(a), 128 + 84 * Math.sin(a));
    }
    g.closePath(); g.stroke();
    g.strokeStyle = '#00f082'; g.lineWidth = 14; g.lineCap = 'round'; g.beginPath();
    g.moveTo(82, 150); g.lineTo(115, 118); g.lineTo(140, 138); g.lineTo(176, 98); g.stroke();
    return c.toDataURL('image/png');
  }

  (async function init() {
    const claude = window.claude;
    if (!claude || !claude.use) { window.renderBanner(); return; }
    try { live.desk = await claude.use('desktop'); } catch (e) { live.desk = null; }
    const desk = live.desk;
    if (desk) {
      state.install = await desk.install.state().catch(() => 'unavailable');
      state.app = !!desk.fs;
    }
    if (state.app) {
      desk.app.dock.setIcon(drawIcon()).catch(() => {});
      state.perm = await desk.permissions.state('full-access').catch(() => 'unavailable');
      if (state.perm === 'granted') { live.on = true; await refreshNow(); }
    }
    window.renderBanner();
  })();
})();
</script>
"""


def transform(source: str) -> str:
    """The artifact page from index.html's text. Every replacement must match exactly once."""
    def swap(text: str, old: str, new: str) -> str:
        if text.count(old) != 1:
            raise SystemExit(f"index.html changed: expected one match for {old[:60]!r}, found {text.count(old)}")
        return text.replace(old, new)

    title = re.search(r"<title>(.*?)</title>", source).group(1)
    style = re.search(r"<style>(.*?)</style>", source, re.S).group(1)
    body = re.search(r"<body>(.*)</body>", source, re.S).group(1)
    style = swap(style, "@import url('" + FONTS + "');\n", "")
    style = swap(style, ":root{\n", ":root{\n  color-scheme:dark;\n")
    body = swap(body, SITE_FETCH, SITE_FETCH_NEW)
    body = swap(body, TIMER_FETCH, TIMER_FETCH_NEW)
    body = swap(body, BANNER_SLOT, BANNER_SLOT_NEW)
    main_start = body.index("<script>")
    body = body[:main_start] + LOADER + body[main_start:]
    return (f"<title>{title}</title>\n<link rel=\"stylesheet\" href=\"{FONTS}\">\n"
            f"<style>{style}{CSS}</style>\n{body}\n{DESKTOP}")


def main() -> None:
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
        page = transform(f.read())
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    shutil.copyfile(os.path.join(ROOT, "output", "dashboard.json"), os.path.join(out_dir, "dashboard.json"))
    print(f"✅ Artifact files in {out_dir}: page {len(page) // 1024} KB")


if __name__ == "__main__":
    main()
