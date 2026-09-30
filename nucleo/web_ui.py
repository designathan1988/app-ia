"""A local web interface: talk to the assistant and watch the page being built.

    python -m nucleo.web_ui [--porta=8790] [--codigo=C:/Codex-Shared/deepseek/builder-6] [documento.json]

Then open http://localhost:8790 . Standard library only; one request at a time (the builder bridge is a single
process); below normal priority.
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .assistant import Assistant
from .builder.client import Builder
from .session import low_priority

PAGE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Núcleo</title>
<style>
:root { --bg:#f6f7f9; --panel:#ffffff; --text:#1c2230; --muted:#667085; --line:#e3e6eb; --accent:#2f6fed;
        --ok:#1a7f4b; --warn:#b54708; --user:#eef3ff; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1218; --panel:#171b23; --text:#e6e9ef; --muted:#98a2b3; --line:#283040; --accent:#6d9bff;
          --ok:#4cc38a; --warn:#f5a524; --user:#1c2640; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.45 system-ui, "Segoe UI", sans-serif; }
header { display:flex; align-items:center; gap:12px; padding:10px 16px; border-bottom:1px solid var(--line);
         background:var(--panel); }
header h1 { font-size:16px; margin:0; }
header .sp { flex:1; }
button { font:inherit; border:1px solid var(--line); background:var(--panel); color:var(--text); border-radius:8px;
         padding:6px 12px; cursor:pointer; }
button:hover { border-color:var(--accent); }
button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
main { display:grid; grid-template-columns:minmax(320px, 1fr) minmax(320px, 1.2fr); height:calc(100vh - 53px); }
@media (max-width: 860px) { main { grid-template-columns:1fr; height:auto; } #preview { height:70vh; } }
#chat { display:flex; flex-direction:column; border-right:1px solid var(--line); min-height:0; }
#log { flex:1; overflow:auto; padding:16px; display:flex; flex-direction:column; gap:10px; }
.msg { max-width:95%; padding:8px 12px; border-radius:10px; white-space:pre-wrap; word-break:break-word; }
.me { align-self:flex-end; background:var(--user); }
.bot { align-self:flex-start; background:var(--panel); border:1px solid var(--line); }
.bot .tag { font-size:12px; color:var(--muted); display:block; margin-bottom:2px; }
.bot.ok .tag { color:var(--ok); } .bot.bad .tag { color:var(--warn); }
.bot a { color:var(--accent); display:block; font-size:13px; }
.cmds { font-size:12px; color:var(--muted); margin-top:4px; }
form { display:flex; gap:8px; padding:12px; border-top:1px solid var(--line); background:var(--panel); }
textarea { flex:1; resize:none; font:inherit; padding:8px 10px; border-radius:8px; border:1px solid var(--line);
           background:var(--bg); color:var(--text); height:44px; }
#examples { padding:8px 12px 0; display:flex; flex-wrap:wrap; gap:6px; }
#examples button { font-size:12px; padding:3px 8px; color:var(--muted); }
#right { display:flex; flex-direction:column; min-height:0; }
#right .bar { padding:8px 12px; font-size:13px; color:var(--muted); border-bottom:1px solid var(--line); }
#preview { flex:1; width:100%; border:0; background:#fff; }
</style>
</head>
<body>
<header><h1>Núcleo</h1><span class="sp"></span>
  <button id="undo">Desfazer</button><button id="export">Exportar site</button>
  <a href="/api/documento" download="documento.json"><button>Baixar documento</button></a></header>
<main>
  <section id="chat">
    <div id="log"></div>
    <div id="examples"></div>
    <form id="f"><textarea id="t" placeholder="Escreva um pedido, uma pergunta ou uma pesquisa… (Enter envia)"></textarea>
      <button class="primary">Enviar</button></form>
  </section>
  <section id="right"><div class="bar">Pré-visualização da página (atualiza a cada mudança)</div>
    <iframe id="preview" title="pré-visualização"></iframe></section>
</main>
<script>
const EX = [
  "insira uma seção na página e depois renomeie a seção para Topo",
  "insira um título com o texto \"Café Aurora\" na seção Topo",
  "defina o fundo da seção Topo como #1e293b",
  "mude a cor do texto do título para #ffffff",
  "centralizar significa definir o alinhamento do texto como center",
  "centralize o título",
  "card significa um artigo com um título com o texto \"Plano\" e um botão com o texto \"Assinar\"",
  "insira um card na seção Topo",
  "pesquise css container queries",
  "onde está definido createStore?",
  "crie um projeto com a entidade Cliente com email (e-mail, obrigatório) e idade (inteiro de 0 a 150)"];
const log = document.getElementById('log'), t = document.getElementById('t');
function add(cls, html) { const d = document.createElement('div'); d.className = 'msg ' + cls; d.innerHTML = html;
  log.appendChild(d); log.scrollTop = log.scrollHeight; return d; }
function esc(s) { return s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
const SLOW = t => /\?\s*$/.test(t);
const LABEL = {executado:'✔ feito', aprendido:'✎ aprendido', perguntar:'? pergunta', nao_entendi:'? não entendi',
  sem_plano:'✘ sem plano', busca:'pesquisa', codigo:'código', projeto:'projeto', comando:'comando'};
async function refresh() { const r = await fetch('/api/preview'); document.getElementById('preview').srcdoc = await r.text(); }
let busy = false;
async function send(text) {
  if (!text.trim() || busy) return;
  busy = true; document.querySelector('form button').disabled = true;
  add('me', esc(text)); t.value = '';
  const wait = add('bot', '<span class="tag">processando…' + (SLOW(text) ? ' (a 1ª pergunta sobre código lê o projeto: ~20 s)' : '') + '</span>');
  try {
    const r = await (await fetch('/api/mensagem', {method:'POST', body: JSON.stringify({texto: text})})).json();
    wait.className = 'msg bot ' + (r.ok ? 'ok' : 'bad');
    let h = '<span class="tag">' + (LABEL[r.tipo] || r.tipo) + '</span>' + esc(r.texto);
    if (r.comandos && r.comandos.length) h += '<div class="cmds">comandos: ' + esc(r.comandos.join(', ')) + '</div>';
    for (const [title, url, src] of (r.links || [])) h += '<a href="' + url + '" target="_blank" rel="noopener">[' + esc(src) + '] ' + esc(title) + '</a>';
    wait.innerHTML = h;
  } catch (e) { wait.innerHTML = '<span class="tag">erro</span>' + esc(String(e)); }
  busy = false; document.querySelector('form button').disabled = false;
  refresh();
}
document.getElementById('f').onsubmit = e => { e.preventDefault(); send(t.value); };
t.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(t.value); } });
document.getElementById('undo').onclick = () => send('desfazer');
document.getElementById('export').onclick = () => send('exportar');
const ex = document.getElementById('examples');
for (const s of EX) { const b = document.createElement('button'); b.textContent = s.length > 48 ? s.slice(0, 46) + '…' : s;
  b.title = s; b.onclick = () => { t.value = s; t.focus(); }; ex.appendChild(b); }
add('bot', '<span class="tag">núcleo</span>Pronto. Clique num exemplo para preencher, ou escreva o seu pedido.');
refresh();
</script>
</body>
</html>
"""


def serve(port: int, assistant: Assistant) -> None:
    # One thread per connection: a browser opens connections ahead of time and leaves them idle, and a
    # single-threaded server waits on such a connection while every real request queues behind it. The builder
    # bridge is one process, so the assistant itself is used by one request at a time.
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/preview":
                with lock:
                    page = assistant.preview_html()
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/documento":
                with lock:
                    doc = json.dumps(assistant.session.document()["document"], ensure_ascii=False, indent=1)
                self._send(200, doc.encode("utf-8"), "application/json",
                           {"Content-Disposition": 'attachment; filename="documento.json"'})
            else:
                self._send(404, b"nao encontrado", "text/plain")

        def do_POST(self):
            if self.path != "/api/mensagem":
                self._send(404, b"nao encontrado", "text/plain")
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) or b"{}"
            try:
                try:
                    payload = raw.decode("utf-8")
                except UnicodeDecodeError:
                    payload = raw.decode("cp1252")
                text = json.loads(payload).get("texto", "")
                with lock:
                    r = assistant.handle(text)
                body = {"tipo": r.kind, "texto": r.text, "ok": r.ok, "comandos": r.commands, "links": r.links}
            except Exception as e:  # noqa: BLE001 - the page shows the failure instead of hanging
                body = {"tipo": "erro", "texto": f"Erro interno: {e}", "ok": False, "comandos": [], "links": []}
            self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.allow_reuse_address = False
    server.serve_forever()


def main(argv: list[str]) -> int:
    low_priority()
    port = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--porta=")), 8790))
    code_root = next((a.split("=", 1)[1] for a in argv if a.startswith("--codigo=")), None)
    args = [a for a in argv if not a.startswith("--")]
    doc_path = pathlib.Path(args[0]) if args else None
    document = json.loads(doc_path.read_text(encoding="utf-8")) if doc_path and doc_path.exists() else None
    with Builder() as b:
        assistant = Assistant(b, document, doc_path, pathlib.Path("site"), code_root)
        print("Carregando modelos...", flush=True)
        assistant.warm_up()
        print(f"Núcleo em http://localhost:{port}", flush=True)
        serve(port, assistant)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
