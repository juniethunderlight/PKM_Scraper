#!/usr/bin/env python3
"""
gui.py — Panel web local para PKMN TTRPG Manager
Lanzar con: python gui.py
"""

import sys
import os
import subprocess

# ── Venv bootstrap (solo stdlib, corre antes de todo) ──────────────────────────
_DIR     = os.path.dirname(os.path.abspath(__file__))
_VENV    = os.path.join(_DIR, ".venv")
if os.name == "nt":  # Windows
    _VENV_PY = os.path.join(_VENV, "Scripts", "python.exe")
else:  # macOS / Linux
    _VENV_PY = os.path.join(_VENV, "bin", "python")
_REQS    = os.path.join(_DIR, "requirements.txt")

if os.path.abspath(sys.executable) != os.path.abspath(_VENV_PY):
    if not os.path.exists(_VENV_PY):
        print("Creando entorno virtual...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", _VENV], check=True)
        print("Instalando dependencias...", flush=True)
        subprocess.run(
            [_VENV_PY, "-m", "pip", "install", "-r", _REQS, "-q"],
            check=True,
        )
        print("Listo.", flush=True)
    os.execv(_VENV_PY, [_VENV_PY] + sys.argv)

# ── A partir de aquí corremos dentro del venv ──────────────────────────────────
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

PYTHON = sys.executable
SCRIPT = os.path.join(_DIR, "pkmn.py")

# ── HTML embebido ──────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>PKMN TTRPG Manager</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#1e1e2e;color:#cdd6f4;font-family:system-ui,sans-serif;padding:24px;max-width:820px;margin:auto}
  h1{color:#89b4fa;margin-bottom:22px;font-size:1.45rem;letter-spacing:.5px}
  .cmds{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}
  .cb{background:#2a2a3e;border:1px solid #313145;color:#cdd6f4;padding:9px 18px;border-radius:8px;cursor:pointer;font-size:.9rem;transition:border-color .15s,color .15s}
  .cb:hover{border-color:#89b4fa;color:#89b4fa}
  .cb.on{background:#89b4fa;color:#1e1e2e;border-color:#89b4fa;font-weight:700}
  .form{background:#2a2a3e;border-radius:10px;padding:20px;margin-bottom:18px;display:none}
  .form.vis{display:block}
  label{display:block;color:#f9e2af;margin-bottom:5px;font-size:.82rem;text-transform:uppercase;letter-spacing:.5px}
  input{width:100%;background:#313145;border:1px solid #45475a;color:#cdd6f4;padding:8px 12px;border-radius:6px;font-size:.95rem;margin-bottom:14px;outline:none;font-family:monospace}
  input:focus{border-color:#89b4fa}
  .run{background:#89b4fa;color:#1e1e2e;border:none;padding:9px 26px;border-radius:8px;font-size:.95rem;font-weight:700;cursor:pointer}
  .run:hover{background:#b4ceff}
  .run:disabled{opacity:.45;cursor:not-allowed}
  .out{background:#2a2a3e;border-radius:10px;padding:16px;min-height:130px;font-family:'Courier New',monospace;font-size:.84rem;white-space:pre-wrap;line-height:1.6}
  .ok{color:#a6e3a1}.warn{color:#f9e2af}.err{color:#f38ba8}.cmd{color:#89b4fa}.dim{color:#585b70}
</style>
</head>
<body>
<h1>PKMN TTRPG Manager</h1>
<div class="cmds" id="cmds"></div>
<div class="form" id="form">
  <div id="fields"></div>
  <button class="run" id="runBtn" onclick="run()">Ejecutar</button>
</div>
<div class="out" id="out"><span class="dim">Selecciona un comando arriba...</span></div>

<script>
const CMDS=[
  {cmd:"addpkm",    label:"Agregar Pokémon",   fields:[{id:"nombre",ph:"Ej: Pikachu"},{id:"nivel",ph:"Ej: 5  (opcional)"}]},
  {cmd:"updatepkm", label:"Actualizar Pokémon", fields:[{id:"nombre",ph:"Ej: Pikachu"},{id:"nivel",ph:"Ej: 5  (opcional)"}]},
  {cmd:"addmove",   label:"Agregar movimiento", fields:[{id:"nombre",ph:"Ej: Impactrueno"}]},
  {cmd:"hidepkm",   label:"Ocultar Pokémon",    fields:[{id:"nombre",ph:"Ej: Pikachu"}]},
  {cmd:"showpkm",   label:"Mostrar Pokémon",    fields:[{id:"nombre",ph:"Ej: Pikachu"}]},
  {cmd:"orderby",   label:"Ordenar pestañas",   fields:[]},
];
let sel=null;
const cmdsEl=document.getElementById("cmds");
CMDS.forEach(c=>{
  const b=document.createElement("button");
  b.className="cb"; b.textContent=c.label;
  b.onclick=()=>pick(c,b);
  cmdsEl.appendChild(b);
});
function pick(c,btn){
  document.querySelectorAll(".cb").forEach(b=>b.classList.remove("on"));
  btn.classList.add("on"); sel=c;
  const fd=document.getElementById("fields"); fd.innerHTML="";
  c.fields.forEach(f=>{
    const lbl=document.createElement("label"); lbl.textContent=f.id;
    const inp=document.createElement("input"); inp.type="text"; inp.placeholder=f.ph||""; inp.id="f_"+f.id;
    inp.onkeydown=e=>{if(e.key==="Enter")run();};
    fd.appendChild(lbl); fd.appendChild(inp);
  });
  document.getElementById("form").classList.add("vis");
  if(c.fields.length) document.getElementById("f_"+c.fields[0].id).focus();
}
async function run(){
  if(!sel)return;
  const btn=document.getElementById("runBtn");
  btn.disabled=true; btn.textContent="…";
  const args=sel.fields.map(f=>(document.getElementById("f_"+f.id)||{}).value?.trim()||"").filter(Boolean);
  const out=document.getElementById("out");
  out.innerHTML=`<span class="cmd">❯ ${sel.cmd} ${args.join(" ")}\\n</span>`;
  try{
    const r=await fetch("/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({cmd:sel.cmd,args})});
    const d=await r.json();
    d.output.split("\\n").forEach(line=>{
      const s=document.createElement("span");
      if(line.startsWith(""))s.className="ok";
      else if(line.startsWith("⚠"))s.className="warn";
      else if(/error/i.test(line))s.className="err";
      s.textContent=line+"\\n"; out.appendChild(s);
    });
  }catch(e){out.innerHTML+=`<span class="err">Error: ${e}</span>`;}
  btn.disabled=false; btn.textContent="Ejecutar";
}
</script>
</body>
</html>"""


# ── Servidor HTTP ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data   = json.loads(self.rfile.read(length))
        args   = [PYTHON, SCRIPT, data["cmd"]] + [a for a in data.get("args", []) if a]
        try:
            proc = subprocess.run(
            args,
            capture_output=True,
            cwd=_DIR
            )
            output = (
                proc.stdout.decode("utf-8", errors="replace") +
                (proc.stderr.decode("utf-8", errors="replace") if proc.stderr else "")
            )
        except Exception as e:
          output = f"Error: {e}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"output": output}).encode("utf-8"))

    def log_message(self, *_):
        pass


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port   = server.server_address[1]
    url    = f"http://127.0.0.1:{port}"
    print(f"Servidor en {url}  (Ctrl+C para cerrar)")
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")


if __name__ == "__main__":
    main()