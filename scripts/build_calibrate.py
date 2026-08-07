#!/usr/bin/env python3
"""Build calibrate.html — drag the stage pins onto their real positions.

The planner's pin coordinates were inferred by reading the organiser's stylised
map against real street geometry. This tool puts those pins on the real street
map as draggable markers, with the official map alongside for reference, and
emits corrected coordinates to paste back into data/kallio/acts.json.
"""

import json
import pathlib

import sys
from assets import DATA, ROOT, STAGE_COLORS, data_uri

FLOW = "--flow" in sys.argv
OUT = ROOT / "tools" / ("calibrate-flow.html" if FLOW else "calibrate.html")

TPL = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage pin calibration</title>
<style>
:root{--bg:#0a0c10;--bg2:#0f1218;--panel:#151a24;--line:#232936;--line2:#333c4e;
  --tx:#e9edf5;--tx2:#9aa5ba;--tx3:#7b8799;--ok:#a3e635}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
  font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
.wrap{padding:18px clamp(12px,2vw,26px);max-width:1700px;margin:0 auto}
h1{margin:0 0 4px;font-size:21px;letter-spacing:-.02em}
.lede{color:var(--tx2);font-size:13px;margin:0 0 16px;max-width:80ch}
.lede b{color:var(--tx)}
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,.85fr) 330px;gap:16px;
  align-items:start}
@media(max-width:1280px){.grid{grid-template-columns:1fr 1fr}.side{grid-column:1/-1}}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
.pane{border:1px solid var(--line2);border-radius:14px;overflow:hidden;background:#0c0e12;
  position:relative}
.pane h2{margin:0;padding:9px 13px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;
  color:var(--tx3);border-bottom:1px solid var(--line);background:var(--bg2)}
.view{position:relative;overflow:hidden;touch-action:none;cursor:grab}
.view.drag{cursor:grabbing}
.plane{position:absolute;inset:0;transform-origin:0 0}
.plane img{width:100%;height:100%;object-fit:contain;display:block;-webkit-user-drag:none;
  user-select:none}
#mapView{aspect-ratio:__AR__}
#posterView{aspect-ratio:819/1024}
.pin{position:absolute;transform:translate(-50%,-100%);cursor:grab;touch-action:none;z-index:4}
.pin.moving{cursor:grabbing;z-index:9}
.pin .knob{width:30px;height:30px;border-radius:50% 50% 50% 4px;transform:rotate(-45deg);
  background:var(--c);display:grid;place-items:center;
  box-shadow:0 5px 14px -3px #000,0 0 0 2px rgba(10,12,16,.65)}
.pin .knob b{transform:rotate(45deg);font-size:12px;font-weight:800;color:#0a0c10}
.pin .lab{position:absolute;left:50%;top:calc(100% + 4px);transform:translateX(-50%);
  font-size:10.5px;font-weight:700;white-space:nowrap;background:rgba(10,12,16,.88);
  border:1px solid var(--line2);padding:2px 6px;border-radius:5px;pointer-events:none}
.pin.sel .knob{transform:rotate(-45deg) scale(1.28);box-shadow:0 6px 20px -2px var(--c)}
.pin.sel .lab{background:var(--c);color:#0a0c10;border-color:var(--c)}
.pin.moved .lab::after{content:" ✓";color:var(--ok)}
.pin.sel.moved .lab::after{color:#0a0c10}
.layers{position:absolute;left:9px;top:9px;z-index:6;display:flex;gap:2px;padding:2px;
  background:rgba(15,18,24,.92);border:1px solid rgba(255,255,255,.14);border-radius:9px;
  backdrop-filter:blur(8px)}
.layers button{font-size:11.5px;font-weight:650;padding:6px 11px;border-radius:7px;
  color:rgba(255,255,255,.6);min-height:32px}
.layers button[aria-pressed=true]{background:rgba(255,255,255,.17);color:#fff}
.ctl{position:absolute;right:9px;bottom:9px;display:flex;flex-direction:column;gap:5px;z-index:6}
.ctl button{width:42px;height:42px;border-radius:11px;background:rgba(15,18,24,.94);
  border:1px solid rgba(255,255,255,.18);color:#fff;display:grid;place-items:center;
  font-size:20px;font-weight:600;backdrop-filter:blur(8px)}
.ctl button:hover{background:rgba(40,46,58,.96)}
.ctl button:active{transform:scale(.93)}
.zlvl{text-align:center;font-size:10.5px;font-weight:700;color:rgba(255,255,255,.75);
  background:rgba(15,18,24,.94);border:1px solid rgba(255,255,255,.18);border-radius:8px;
  padding:3px 0;font-variant-numeric:tabular-nums}
.side{display:flex;flex-direction:column;gap:10px}
.list{border:1px solid var(--line2);border-radius:14px;overflow:hidden}
.row{display:grid;grid-template-columns:24px 1fr auto;gap:10px;align-items:center;padding:9px 11px;
  border-top:1px solid var(--line);width:100%;text-align:left;font-size:12.5px}
.row:first-child{border-top:none}
.row:hover{background:var(--panel)}
.row.sel{background:var(--panel)}
.row .n{width:21px;height:21px;border-radius:6px;background:var(--c);color:#0a0c10;display:grid;
  place-items:center;font-weight:800;font-size:10.5px}
.row .nm{display:block;font-weight:650}
.row .co{display:block;color:var(--tx3);font-size:10.5px;font-variant-numeric:tabular-nums;margin-top:2px}
.row .st{font-size:10px;color:var(--tx3);padding:2px 7px;border:1px solid var(--line2);
  border-radius:99px}
.row.moved .st{color:#0a0c10;background:var(--ok);border-color:var(--ok);font-weight:700}
.acts{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:11px 15px;border-radius:11px;border:1px solid var(--line2);font-size:13px;
  font-weight:650;display:inline-flex;align-items:center;gap:8px}
.btn:hover{border-color:var(--tx3);background:var(--panel)}
.btn.primary{background:var(--ok);color:#0a0c10;border-color:var(--ok)}
.btn.primary:hover{filter:brightness(1.08)}
textarea{width:100%;height:190px;background:#07090c;border:1px solid var(--line2);border-radius:11px;
  color:var(--tx2);font:11.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;padding:11px;
  resize:vertical}
.hint{font-size:11.5px;color:var(--tx3);line-height:1.55}
kbd{background:var(--panel);border:1px solid var(--line2);border-bottom-width:2px;border-radius:5px;
  padding:1px 5px;font-size:11px;font-family:inherit}
</style></head><body><div class="wrap">
<h1>Stage pin calibration</h1>
<p class="lede">Pins start from the positions you calibrated last time. <b>Drag any that still sit
wrong</b> — satellite makes the car park, the school yard and the park paths easy to match against
the official map on the right. Switch to <b>Street</b> if you need the street names. A pin turns
green once you have moved it; hit <b>Copy corrected coordinates</b> and paste the result back to me.</p>

<div class="grid">
  <div class="pane"><h2>Satellite — drag the pins onto the real spots</h2>
    <div class="view" id="mapView"><div class="plane" id="mapPlane">
      <img id="imgSat" src="__SATELLITE__" alt="Satellite view" draggable="false">
      <img id="imgStreet" src="__BASEMAP__" alt="Street map" draggable="false" hidden>
      <div id="pins"></div></div>
      <div class="layers"><button id="laySat" aria-pressed="true">Satellite</button>
        <button id="layStreet" aria-pressed="false">Street</button></div>
      <div class="ctl"><button id="zi" title="Zoom in (+)">+</button>
        <div class="zlvl" id="zlvl">1.0×</div>
        <button id="zo" title="Zoom out (−)">−</button>
        <button id="zf" title="Reset view (0)">⌖</button></div>
    </div></div>
  <div class="pane"><h2>Reference view</h2>
    <div class="view" id="posterView"><div class="plane" id="posterPlane">
      <img src="__POSTER__" alt="Official festival map" draggable="false"></div>
      <div class="ctl"><button id="pi">+</button><button id="po">−</button><button id="pf">⌖</button></div>
    </div></div>
  <div class="side">
    <div class="list" id="list"></div>
    <div class="acts">
      <button class="btn primary" id="copy">Copy corrected coordinates</button>
      <button class="btn" id="reset">Reset all</button>
    </div>
    <p class="hint">Zoom with the <kbd>+</kbd> / <kbd>−</kbd> buttons, the scroll wheel, a
      two-finger pinch, a double-click, or the <kbd>+</kbd> <kbd>−</kbd> <kbd>0</kbd> keys.
      Drag the background to pan. Clicking a stage in the list below zooms straight to it.
      Your edits are kept in this browser, so you can close the tab and come back.</p>
    <textarea id="out" readonly spellcheck="false"></textarea>
  </div>
</div></div>
<script>
const STAGES = __STAGES__, B = __BASEMAP_META__, STORE_KEY = '__STORE__';
const $ = s => document.querySelector(s);
const saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
const pos = {};
STAGES.forEach(s => pos[s.id] = saved[s.id] ? {...saved[s.id], moved:true}
                                            : {lat:s.lat, lon:s.lon, moved:false});
const N = (1 << B.z) * B.tile;
const project = (lat, lon) => {
  const x = (lon + 180) / 360 * N;
  const r = lat * Math.PI / 180;
  const y = (1 - Math.log(Math.tan(r) + 1/Math.cos(r)) / Math.PI) / 2 * N;
  return {x:(x - B.originX)/B.wLogical*100, y:(y - B.originY)/B.hLogical*100};
};
const unproject = (px, py) => {
  const gx = px/100 * B.wLogical + B.originX, gy = py/100 * B.hLogical + B.originY;
  const lon = gx / N * 360 - 180;
  const lat = Math.atan(Math.sinh(Math.PI * (1 - 2*gy/N))) * 180 / Math.PI;
  return {lat:+lat.toFixed(6), lon:+lon.toFixed(6)};
};
let sel = STAGES[0].id;

function draw() {
  $('#pins').innerHTML = STAGES.map(s => {
    const p = project(pos[s.id].lat, pos[s.id].lon);
    return `<div class="pin${sel===s.id?' sel':''}${pos[s.id].moved?' moved':''}"
      data-id="${s.id}" style="--c:${s.color};left:${p.x}%;top:${p.y}%">
      <div class="knob"><b>${s.num||'·'}</b></div><div class="lab">${s.short}</div></div>`;
  }).join('');
  bindPins();
  $('#list').innerHTML = STAGES.map(s => `<button class="row${sel===s.id?' sel':''}${pos[s.id].moved?' moved':''}"
    data-id="${s.id}" style="--c:${s.color}"><span class="n">${s.num||'·'}</span>
    <span><span class="nm">${s.name}</span><span class="co">${pos[s.id].lat.toFixed(5)}, ${pos[s.id].lon.toFixed(5)}</span></span>
    <span class="st">${pos[s.id].moved?'moved':'guess'}</span></button>`).join('');
  $('#list').querySelectorAll('.row').forEach(r => r.onclick = () => { sel = r.dataset.id; draw(); centre(r.dataset.id); });
  $('#out').value = JSON.stringify(Object.fromEntries(
    STAGES.map(s => [s.id, [pos[s.id].lat, pos[s.id].lon]])), null, 1);
  localStorage.setItem(STORE_KEY, JSON.stringify(Object.fromEntries(
    STAGES.filter(s => pos[s.id].moved).map(s => [s.id, {lat:pos[s.id].lat, lon:pos[s.id].lon}]))));
}
function bindPins() {
  $('#pins').querySelectorAll('.pin').forEach(el => {
    el.addEventListener('pointerdown', e => {
      e.stopPropagation(); e.preventDefault();
      sel = el.dataset.id; el.classList.add('moving');
      try { el.setPointerCapture(e.pointerId); } catch (_) {}   // must not abort the drag
      const plane = $('#mapPlane');
      const move = ev => {
        const r = plane.getBoundingClientRect();
        const x = Math.max(0, Math.min(100, (ev.clientX - r.left) / r.width * 100));
        const y = Math.max(0, Math.min(100, (ev.clientY - r.top) / r.height * 100));
        const ll = unproject(x, y);
        pos[el.dataset.id] = {...ll, moved:true};
        el.style.left = x + '%'; el.style.top = y + '%';
      };
      const up = () => {
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
        el.classList.remove('moving'); draw();
      };
      el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
    });
  });
}
/* pan + zoom for a pane */
function panzoom(viewId, planeId, ids) {
  let z = 1, tx = 0, ty = 0;
  const view = $('#'+viewId), plane = $('#'+planeId);
  const put = () => {
    const lvl = document.getElementById('zlvl');
    if (lvl && viewId === 'mapView') lvl.textContent = z.toFixed(1) + '×';
    plane.style.transform = `translate3d(${tx}px,${ty}px,0) scale(${z})`;
    plane.querySelectorAll('.pin').forEach(p =>
      p.style.transform = `translate(-50%,-100%) scale(${(1/z).toFixed(3)})`);
  };
  // Allow a half-frame of overscroll so dragging responds at every zoom level;
  // clamping to the exact fit made the map immovable at 1x.
  const clamp = () => {
    const r = view.getBoundingClientRect();
    const padX = r.width * .5, padY = r.height * .5;
    tx = Math.min(padX, Math.max(-r.width * (z - 1) - padX, tx));
    ty = Math.min(padY, Math.max(-r.height * (z - 1) - padY, ty));
  };
  const zoom = (nz, ax, ay) => { const r = view.getBoundingClientRect();
    ax = ax ?? r.width/2; ay = ay ?? r.height/2; nz = Math.max(1, Math.min(7, nz));
    tx = ax - (ax-tx)*(nz/z); ty = ay - (ay-ty)*(nz/z); z = nz; clamp(); put(); };
  // two-finger pinch
  let pinch = null;
  const dist = ts => Math.hypot(ts[0].clientX-ts[1].clientX, ts[0].clientY-ts[1].clientY);
  const mid  = ts => ({x:(ts[0].clientX+ts[1].clientX)/2, y:(ts[0].clientY+ts[1].clientY)/2});
  view.addEventListener('touchstart', e => {
    if (e.touches.length === 2) { down = false; pinch = {d:dist(e.touches), z}; }
  }, {passive:true});
  view.addEventListener('touchmove', e => {
    if (!pinch || e.touches.length !== 2) return;
    if (e.cancelable) e.preventDefault();
    const r = view.getBoundingClientRect(), m = mid(e.touches);
    zoom(pinch.z * (dist(e.touches)/pinch.d), m.x-r.left, m.y-r.top);
  }, {passive:false});
  const endPinch = e => { if (!e.touches || e.touches.length < 2) pinch = null; };
  view.addEventListener('touchend', endPinch);
  view.addEventListener('touchcancel', endPinch);
  view.addEventListener('dblclick', e => {
    if (e.target.closest('.pin,.ctl,.layers')) return;
    const r = view.getBoundingClientRect();
    zoom(z >= 4 ? 1 : z*1.9, e.clientX-r.left, e.clientY-r.top);
  });

  let down = false, sx, sy, ox, oy;
  view.addEventListener('pointerdown', e => { if (e.target.closest('.pin,.ctl,.layers')) return;
    down = true; sx = e.clientX; sy = e.clientY; ox = tx; oy = ty;
    try { view.setPointerCapture(e.pointerId); } catch (_) {}
    view.classList.add('drag'); });
  view.addEventListener('pointermove', e => { if (!down) return;
    tx = ox + e.clientX - sx; ty = oy + e.clientY - sy; clamp(); put(); });
  const up = () => { down = false; view.classList.remove('drag'); };
  view.addEventListener('pointerup', up); view.addEventListener('pointercancel', up);
  view.addEventListener('wheel', e => { e.preventDefault(); const r = view.getBoundingClientRect();
    zoom(z * (e.deltaY < 0 ? 1.18 : 1/1.18), e.clientX-r.left, e.clientY-r.top); }, {passive:false});
  $('#'+ids[0]).onclick = () => zoom(z*1.6);
  $('#'+ids[1]).onclick = () => zoom(z/1.6);
  $('#'+ids[2]).onclick = () => { z = 1; tx = ty = 0; put(); };
  return {centre(lat, lon) { const p = project(lat, lon), r = view.getBoundingClientRect();
    z = Math.max(z, 2.6); tx = r.width/2 - p.x/100*r.width*z; ty = r.height/2 - p.y/100*r.height*z;
    clamp(); put(); }, redraw: put};
}
const mapPZ = panzoom('mapView','mapPlane',['zi','zo','zf']);
addEventListener('keydown', e => {
  const el = e.target;
  if (el && el.matches && el.matches('input,textarea')) return;
  if (e.key === '+' || e.key === '=') { document.getElementById('zi').click(); e.preventDefault(); }
  if (e.key === '-' || e.key === '_') { document.getElementById('zo').click(); e.preventDefault(); }
  if (e.key === '0')                  { document.getElementById('zf').click(); e.preventDefault(); }
});
panzoom('posterView','posterPlane',['pi','po','pf']);
const centre = id => { const p = pos[id]; mapPZ.centre(p.lat, p.lon); };
$('#laySat').onclick = () => setLayer(true);
$('#layStreet').onclick = () => setLayer(false);
function setLayer(sat) {
  $('#imgSat').hidden = !sat; $('#imgStreet').hidden = sat;
  $('#laySat').setAttribute('aria-pressed', sat);
  $('#layStreet').setAttribute('aria-pressed', !sat);
}
$('#copy').onclick = () => {
  navigator.clipboard.writeText($('#out').value).then(() => {
    $('#copy').textContent = 'Copied ✓';
    setTimeout(() => $('#copy').textContent = 'Copy corrected coordinates', 1600);
  });
};
$('#reset').onclick = () => {
  if (!confirm('Reset every pin back to the original guess?')) return;
  localStorage.removeItem(STORE_KEY);
  STAGES.forEach(s => pos[s.id] = {lat:s.lat, lon:s.lon, moved:false});
  draw(); mapPZ.redraw();
};
draw();
</script></body></html>
"""


def main():
    base = (DATA / "flow") if FLOW else DATA
    acts = json.loads((base / "acts.json").read_text())
    basemap = json.loads((base / "basemap.json").read_text())
    stages = [{"id": s["id"], "num": s["num"], "name": s["name"],
               "short": s.get("short", s["name"]), "lat": s["lat"], "lon": s["lon"],
               "color": s.get("color") or STAGE_COLORS[s["id"]]} for s in acts["stages"]]
    html = TPL
    for tok, val in [
        ("__STAGES__", json.dumps(stages, ensure_ascii=False)),
        ("__BASEMAP_META__", json.dumps(basemap)),
        ("__BASEMAP__", data_uri(ROOT / "assets" / ("flow-basemap.jpg" if FLOW else "basemap.jpg"))),
        ("__SATELLITE__", data_uri(ROOT / "assets" / ("flow-satellite.jpg" if FLOW else "satellite.jpg"))),
        ("__POSTER__", data_uri(ROOT / "assets" / ("flow-satellite.jpg" if FLOW else "map.jpg"))),
        ("__AR__", f'{basemap["wPixels"]}/{basemap["hPixels"]}'),
        ("__STORE__", "flowcalib1" if FLOW else "kbp26calib2"),
    ]:
        html = html.replace(tok, val)
    OUT.write_text(html)
    print(f"{OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
