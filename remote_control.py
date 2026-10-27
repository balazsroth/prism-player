"""
Web remote: a tiny HTTP server that serves a phone-friendly control page and a JSON API.
Requests arrive on worker threads; commands are forwarded to the Qt thread through a signal,
and the page reads a status snapshot the main window refreshes.
"""

import base64
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PyQt6.QtCore import QObject, pyqtSignal

COMMANDS = {"toggle", "play", "pause", "stop", "next", "prev", "volume", "seek", "jump", "fullscreen", "mute"}

PAGE = """<!doctype html>
<html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prism távirányító</title>
<style>
:root{--accent:%(accent)s;--bg:#0f1014;--card:#1a1b21;--text:#f2f3f5;--muted:#9aa0aa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px 'Segoe UI',system-ui,sans-serif;
display:flex;justify-content:center;padding:16px}
main{width:100%%;max-width:440px}
h1{font-size:15px;color:var(--muted);font-weight:600;margin:4px 0 18px}
.card{background:var(--card);border:1px solid #ffffff1f;border-radius:16px;padding:18px;margin-bottom:14px}
#title{font-size:20px;font-weight:600;word-break:break-word}#time{color:var(--muted);margin-top:6px;font-variant-numeric:tabular-nums}
input[type=range]{width:100%%;accent-color:var(--accent)}
.row{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
button{background:#ffffff14;color:var(--text);border:0;border-radius:12px;padding:14px 0;min-width:64px;font-size:18px;cursor:pointer}
button.main{background:var(--accent);color:#000;min-width:88px;font-weight:700}
label{color:var(--muted);font-size:13px}
</style></head><body><main>
<h1>Prism távirányító</h1>
<div class="card"><div id="title">–</div><div id="time">0:00 / 0:00</div>
<input id="seek" type="range" min="0" max="1000" value="0"></div>
<div class="card"><div class="row">
<button onclick="cmd('prev')">⏮</button><button onclick="cmd('jump',-10)">−10</button>
<button class="main" id="pp" onclick="cmd('toggle')">⏯</button>
<button onclick="cmd('jump',10)">+10</button><button onclick="cmd('next')">⏭</button></div>
<div class="row" style="margin-top:10px"><button onclick="cmd('stop')">⏹</button>
<button onclick="cmd('mute')">🔇</button><button onclick="cmd('fullscreen')">⛶</button></div></div>
<div class="card"><label>Hangerő <span id="vl"></span></label>
<input id="vol" type="range" min="0" max="200" value="100"></div>
<script>
let dragging=false;
function fmt(ms){let s=Math.floor(ms/1000),h=Math.floor(s/3600),m=Math.floor(s%%3600/60);s%%=60;
return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(s).padStart(2,'0')}
function cmd(a,v){fetch('api/cmd?action='+a+(v!==undefined?'&value='+v:'')).then(refresh)}
function refresh(){fetch('api/status').then(r=>r.json()).then(s=>{
document.getElementById('title').textContent=s.title||'Nincs lejátszás';
document.getElementById('time').textContent=fmt(s.time)+' / '+fmt(s.length);
document.getElementById('pp').textContent=s.playing?'⏸':'▶';
if(!dragging){document.getElementById('seek').value=Math.round(s.position*1000);
document.getElementById('vol').value=s.volume}
document.getElementById('vl').textContent=s.volume+'%%'}).catch(()=>{})}
const seek=document.getElementById('seek'),vol=document.getElementById('vol');
for(const el of [seek,vol]){el.addEventListener('pointerdown',()=>dragging=true);
el.addEventListener('pointerup',()=>dragging=false)}
seek.addEventListener('change',()=>cmd('seek',seek.value/1000));
vol.addEventListener('change',()=>cmd('volume',vol.value));
setInterval(refresh,1000);refresh();
</script></main></body></html>"""


class RemoteServer(QObject):
    command = pyqtSignal(str, str)   # action, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = {"title": "", "playing": False, "time": 0, "length": 0, "position": 0.0, "volume": 100}
        self.accent = "#FF8800"
        self._server = None
        self._thread = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self, port: int, password: str = "") -> bool:
        self.stop()
        remote = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code: int, body: bytes, ctype: str, extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                # Any user name, the configured password (VLC's own web interface works the same way)
                if password:
                    got = self.headers.get("Authorization", "")
                    try:
                        decoded = base64.b64decode(got[6:]).decode() if got.startswith("Basic ") else ""
                    except ValueError:
                        decoded = ""
                    if not hmac.compare_digest(decoded.partition(":")[2].encode(), password.encode()):
                        self._send(401, b"Jelszo szukseges", "text/plain",
                                   {"WWW-Authenticate": 'Basic realm="Prism"'})
                        return
                url = urlparse(self.path)
                if url.path in ("/", "/index.html"):
                    self._send(200, (PAGE % {"accent": remote.accent}).encode("utf-8"), "text/html; charset=utf-8")
                elif url.path == "/api/status":
                    self._send(200, json.dumps(remote.status).encode(), "application/json")
                elif url.path == "/api/cmd":
                    q = parse_qs(url.query)
                    action = q.get("action", [""])[0]
                    if action not in COMMANDS:
                        self._send(400, b'{"ok":false}', "application/json")
                        return
                    remote.command.emit(action, q.get("value", [""])[0])  # queued to the Qt thread
                    self._send(200, b'{"ok":true}', "application/json")
                else:
                    self._send(404, b"Not found", "text/plain")

        try:
            self._server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        except OSError:
            self._server = None
            return False
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
