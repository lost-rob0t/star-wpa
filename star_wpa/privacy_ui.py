"""Bundled loopback-only preview; all state remains in process and browser memory."""
from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer

from .privacy import Box, PrivacyError, export_new, keys, sanitize, strict_json

PAGE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Local privacy export</title>
<style nonce="NONCE">
:root{font:16px system-ui;color:#192c32;background:#edf2f2}body{max-width:1100px;margin:auto;padding:24px}h1{margin-bottom:8px}p{line-height:1.5}.note,section{background:white;padding:20px;border-radius:10px;margin:16px 0}.note{border-left:5px solid #a75b13}label{display:inline-block;margin:6px}input{width:105px}input,select,button{font:inherit;padding:8px;border:1px solid #8b9ea1;border-radius:5px}button{cursor:pointer;background:#e2eded}button:disabled{opacity:.5;cursor:default}.primary{background:#125953;color:white}.plots{display:grid;grid-template-columns:1fr 1fr;gap:16px}canvas{width:100%;height:300px;background:#f5f8f8;border:1px solid #9db4b7;touch-action:none}table{border-collapse:collapse;width:100%;margin-top:14px}td,th{padding:8px;text-align:left;border-bottom:1px solid #ccd9db}#status{white-space:pre-wrap;min-height:2em}.controls{display:flex;flex-wrap:wrap;align-items:end}small{display:block} @media(max-width:700px){.plots{grid-template-columns:1fr}body{padding:12px}}
</style>
<h1>Local privacy export</h1><p>Review your own WiGLE or WarStar observations before sharing a new sanitized analysis CSV.</p>
<div class="note"><strong>Locations can still reveal visits and spatial routes.</strong> Exclude sensitive areas with wider buffers and use coarse coordinates. This does not provide anonymity and the output is not compatible with WiGLE re-upload. Originals remain untouched.</div>
<section><h2>1. Protect areas</h2><p>Add latitude/longitude boxes, or drag on the source plot to fill a box. West greater than east crosses the antimeridian. Boundaries are included. Buffers conservatively expand rectangles and can remove more than a circular buffer.</p>
<form id="box-form" class="controls" autocomplete="off">
<label>South<input id="south" type="number" min="-90" max="90" step="any" required></label>
<label>West<input id="west" type="number" min="-180" max="180" step="any" required></label>
<label>North<input id="north" type="number" min="-90" max="90" step="any" required></label>
<label>East<input id="east" type="number" min="-180" max="180" step="any" required></label>
<label>Buffer (meters)<input id="buffer_m" type="number" min="0" max="20015114" step="any" value="100" required></label>
<button>Add exclusion</button></form>
<table><thead><tr><th>South / west</th><th>North / east</th><th>Buffer (m)</th><th>Action</th></tr></thead><tbody id="boxes"></tbody></table>
<label>Coordinate decimal places <select id="precision"><option value="0">0 (~111 km latitude)</option><option value="1">1 (~11 km latitude)</option><option value="2" selected>2 (~1.1 km latitude)</option><option value="3">3 (~111 m latitude)</option><option value="4">4 (~11 m latitude)</option><option value="5">5 (~1.1 m latitude)</option><option value="6">6 (~0.11 m latitude)</option></select></label>
<small>Rounding is a grid, not a privacy guarantee. Longitude spacing shrinks near the poles. Points rounded into exclusions are also removed.</small>
</section>
<section><h2>2. Preview</h2><button id="preview" class="primary">Update preview</button> <button id="world">World view</button> <button id="fit">Fit observations</button>
<p>Offline coordinate plots: longitude →, latitude ↑. No tiles, geocoding or external requests. Gray: source locations; red: removed locations; green: retained coarse locations. Shaded areas: buffered exclusions. No lines connect observations.</p>
<div class="plots"><div><h3>Source locations</h3><canvas id="before" width="1000" height="600" aria-label="Source coordinate plot"></canvas></div><div><h3>Sanitized locations</h3><canvas id="after" width="1000" height="600" aria-label="Sanitized coordinate plot"></canvas></div></div>
<p id="status" role="status" aria-live="polite">Update the preview to inspect locations and counts.</p></section>
<section><h2>3. Save a new copy</h2><p>Only latitude, longitude, radio type and signal level are retained. Identifiers, names, times, capture order, duplicate rows, device metadata, source paths and exclusion geometry are omitted.</p><button id="export" class="primary" disabled>Create new sanitized CSV</button><p>The destination was chosen at launch. Existing files and symlinks are refused. Nothing is written until you press this button. Close this page and stop the process to end the session.</p></section>
<script nonce="NONCE">
'use strict';
const token='TOKEN', $=id=>document.getElementById(id), exclusions=[];
let previewId=null, data=null, bounds=[-180,-90,180,90], busy=false;
const fields=['south','west','north','east','buffer_m'];
function invalidate(){previewId=null;$('export').disabled=true;$('status').textContent='Settings changed. Update preview before saving.';}
function boxes(){const body=$('boxes');body.replaceChildren();exclusions.forEach((box,i)=>{const row=document.createElement('tr');[`${box.south} / ${box.west}`,`${box.north} / ${box.east}`,box.buffer_m].forEach(value=>{const cell=document.createElement('td');cell.textContent=value;row.append(cell);});const cell=document.createElement('td'),button=document.createElement('button');button.textContent='Remove';button.onclick=()=>{exclusions.splice(i,1);boxes();invalidate();};cell.append(button);row.append(cell);body.append(row);});}
$('box-form').onsubmit=e=>{e.preventDefault();if(exclusions.length>=100){$('status').textContent='At most 100 boxes.';return;}const box=Object.fromEntries(fields.map(k=>[k,Number($(k).value)]));if(box.south>box.north){$('status').textContent='South must not exceed north.';return;}exclusions.push(box);boxes();invalidate();};
$('precision').onchange=invalidate;
async function request(path,payload){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Privacy-Token':token},body:JSON.stringify(payload),cache:'no-store',credentials:'omit'});const result=await response.json();if(!response.ok)throw new Error(result.error||'Request refused');return result;}
function setBusy(value){busy=value;$('preview').disabled=value;$('export').disabled=value||!previewId;}
function fit(){const points=[...(data?.before||[]),...(data?.after||[])];if(!points.length)return;const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);let west=180,east=-180,south=90,north=-90;for(let i=0;i<xs.length;i++){west=Math.min(west,xs[i]);east=Math.max(east,xs[i]);south=Math.min(south,ys[i]);north=Math.max(north,ys[i]);}const dx=Math.max(.01,(east-west)*.1),dy=Math.max(.01,(north-south)*.1);bounds=[Math.max(-180,west-dx),Math.max(-90,south-dy),Math.min(180,east+dx),Math.min(90,north+dy)];draw();}
function draw(){for(const id of ['before','after']){const canvas=$(id),ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,[west,south,east,north]=bounds;const x=lon=>(lon-west)/(east-west)*w,y=lat=>(north-lat)/(north-south)*h;ctx.clearRect(0,0,w,h);ctx.strokeStyle='#c3d3d6';ctx.fillStyle='#35555b';ctx.font='20px system-ui';for(let i=0;i<=4;i++){const a=i/4;ctx.beginPath();ctx.moveTo(a*w,0);ctx.lineTo(a*w,h);ctx.moveTo(0,a*h);ctx.lineTo(w,a*h);ctx.stroke();ctx.fillText((west+a*(east-west)).toFixed(2),Math.min(w-95,a*w+4),h-8);ctx.fillText((north-a*(north-south)).toFixed(2),4,Math.max(22,a*h));}ctx.fillStyle='#ba62332b';for(const box of data?.areas||[]){const [s,n,start,width]=box;for(let shift=-720;shift<=720;shift+=360){const l=start+shift,r=l+width;ctx.fillRect(x(l),y(n),x(r)-x(l),y(s)-y(n));}}for(const p of data?.[id]||[]){ctx.fillStyle=id==='after'?'#187450':p[2]?'#b13326':'#60777e';ctx.beginPath();ctx.arc(x(p[0]),y(p[1]),4,0,2*Math.PI);ctx.fill();}}}
$('world').onclick=()=>{bounds=[-180,-90,180,90];draw();};$('fit').onclick=fit;
$('preview').onclick=async()=>{if(busy)return;invalidate();setBusy(true);const submitted=JSON.stringify({boxes:exclusions,decimals:Number($('precision').value)});try{const result=await request('/preview',JSON.parse(submitted));if(submitted!==JSON.stringify({boxes:exclusions,decimals:Number($('precision').value)})){invalidate();return;}data=result;previewId=result.preview_id;fit();$('status').textContent=`${result.total} source readings; ${result.excluded} excluded; ${result.retained} unique output rows; ${result.collapsed} duplicate/coarsened rows collapsed. Preview updated. Review both plots before saving.`;}catch(error){$('status').textContent=error.message;}finally{setBusy(false);}};
$('export').onclick=async()=>{if(busy||!previewId)return;setBusy(true);try{await request('/export',{preview_id:previewId});previewId=null;$('status').textContent='Saved a new sanitized CSV to the chosen destination. Original bytes were not changed.';}catch(error){$('status').textContent=error.message;}finally{setBusy(false);}};
let start=null;function position(e){const rect=$('before').getBoundingClientRect(),[w,s,ee,n]=bounds;return [w+Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width))*(ee-w),n-Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height))*(n-s)];}
$('before').onpointerdown=e=>{start=position(e);$('before').setPointerCapture(e.pointerId);};$('before').onpointerup=e=>{if(!start)return;const end=position(e);$('west').value=Math.min(start[0],end[0]).toFixed(6);$('east').value=Math.max(start[0],end[0]).toFixed(6);$('south').value=Math.min(start[1],end[1]).toFixed(6);$('north').value=Math.max(start[1],end[1]).toFixed(6);start=null;$('status').textContent='Box coordinates filled. Press Add exclusion to protect this area.';};$('before').onpointercancel=()=>{start=null;};
draw();
</script></html>'''


def make_server(observations, output, port=0):
    token = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)
    preview = None

    class Handler(BaseHTTPRequestHandler):
        # No source paths, request URLs, headers, bodies or captured values in logs.
        def log_message(self, *_):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def reply(self, status, data, html=False):
            encoded = data.encode() if html else json.dumps(data, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(encoded)
            self.close_connection = True

        def local_request(self, post=False):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get_all("Host") != [host]:
                return False
            origins = self.headers.get_all("Origin")
            if origins is not None and origins != ["http://" + host]:
                return False
            if post and origins != ["http://" + host]:
                return False
            return self.headers.get("Sec-Fetch-Site", "same-origin") in {"none", "same-origin"}

        def do_GET(self):
            if not self.local_request():
                self.reply(403, {"error": "Local origin required"})
            elif self.path != "/":
                self.reply(404, {"error": "Unknown endpoint"})
            else:
                self.reply(200, PAGE.replace("NONCE", nonce).replace("TOKEN", token), html=True)

        def do_POST(self):
            nonlocal preview
            if (not self.local_request(post=True) or self.headers.get_all("X-Privacy-Token") != [token]):
                self.reply(403, {"error": "Local session required"})
                return
            if self.path not in {"/preview", "/export"}:
                self.reply(404, {"error": "Unknown endpoint"})
                return
            if self.path == "/preview":
                preview = None
            try:
                if self.headers.get_all("Content-Type") != ["application/json"] or self.headers.get("Transfer-Encoding"):
                    raise PrivacyError("JSON request required")
                lengths = self.headers.get_all("Content-Length")
                if not lengths or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                    raise PrivacyError("Invalid request length")
                length = int(lengths[0])
                if not 1 <= length <= 64 * 1024:
                    raise PrivacyError("Request too large")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise PrivacyError("Incomplete request")
                request = strict_json(raw.decode("utf-8", errors="strict"))
                if self.path == "/preview":
                    keys(request, {"boxes", "decimals"})
                    if not isinstance(request["boxes"], list) or len(request["boxes"]) > 100:
                        raise PrivacyError("At most 100 boxes")
                    boxes = []
                    for box in request["boxes"]:
                        keys(box, {"south", "west", "north", "east", "buffer_m"})
                        boxes.append(Box(**box))
                    rows, excluded = sanitize(observations, boxes, request["decimals"])
                    preview_id = secrets.token_urlsafe(24)
                    before = set()
                    for row in observations:
                        _, removed = sanitize((row,), boxes, request["decimals"])
                        before.add((row.longitude, row.latitude, bool(removed)))
                    preview = (preview_id, rows)
                    self.reply(200, {"preview_id": preview_id, "total": len(observations), "excluded": excluded,
                                     "retained": len(rows), "collapsed": len(observations) - excluded - len(rows),
                                     "before": sorted(before), "after": sorted({(r.longitude, r.latitude) for r in rows}),
                                     "areas": [b.expanded() for b in boxes]})
                else:
                    keys(request, {"preview_id"})
                    if preview is None or request["preview_id"] != preview[0]:
                        raise PrivacyError("Update preview before export")
                    export_new(output, preview[1])
                    preview = None
                    self.reply(200, {"saved": True})
            except FileExistsError:
                self.reply(409, {"error": "Destination exists; restart with a new output path"})
            except (OSError, ValueError, TypeError, RecursionError):
                self.reply(400, {"error": "Invalid request or unsafe/unavailable local path"})

    # No bind-address option: remote serving is outside this tool's contract.
    return HTTPServer(("127.0.0.1", port), Handler)
