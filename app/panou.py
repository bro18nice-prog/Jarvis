"""Panoul de control al lui Jarvis: porneste/opreste, cheie Gemini, setari, jurnal.

Ruleaza fara consola (pythonw). Serverul panoului asculta doar pe 127.0.0.1:8764.
  panou.py             -> deschide panoul
  panou.py --autostart -> porneste Jarvis in fundal si iese (folosit la pornirea Windows)
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
DATA = os.path.join(ROOT, "data")
ENV_FILE = os.path.join(ROOT, "config", "setari.env")
ENV_EXAMPLE = os.path.join(ROOT, "config", "setari.exemplu.env")
PID_FILE = os.path.join(DATA, "jarvis.pid")
LOG_FILE = os.path.join(DATA, "jarvis.log")
CONSOLE_LOG = os.path.join(DATA, "jarvis-consola.log")
PYW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
PANEL_PORT = 8764
FACE_PORT = 8765
NO_WINDOW = 0x08000000
DETACHED = 0x00000008
EDGE = next((p for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe")] if os.path.exists(p)), None)

SETTINGS = ["WAKE_WORD", "ASCULTA_MEREU", "FEREASTRA_CONVERSATIE_SEC", "LIMBA", "MODEL_GEMINI", "WHISPER_MODEL", "VOCE", "VOCE_MOTOR"]
STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk")


# ---------------- setari.env ----------------
def read_env():
    if not os.path.exists(ENV_FILE) and os.path.exists(ENV_EXAMPLE):
        with open(ENV_EXAMPLE, encoding="utf-8") as s, open(ENV_FILE, "w", encoding="utf-8") as d:
            d.write(s.read())
    values = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*([A-Z_]+)\s*=(.*)$", line)
                if m:
                    values[m.group(1)] = m.group(2).strip()
    return values


def write_env(updates):
    read_env()
    with open(ENV_FILE, encoding="utf-8") as f:
        lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Z_]+)\s*=", line)
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            done.add(m.group(1))
    for k, v in updates.items():
        if k not in done:
            lines.append(f"{k}={v}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def key_status():
    k = read_env().get("GEMINI_API_KEY", "")
    if not k or k.startswith("PUNE"):
        return {"set": False, "hint": ""}
    return {"set": True, "hint": "..." + k[-4:]}


# ---------------- procesul Jarvis ----------------
def port_open(port):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def pid_alive(pid):
    if not pid:
        return False
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    return str(pid) in out


def is_running():
    return port_open(FACE_PORT) or pid_alive(read_pid())


def start_jarvis():
    if is_running():
        return "Jarvis ruleaza deja."
    if not key_status()["set"]:
        return "Pune intai cheia Gemini."
    os.makedirs(DATA, exist_ok=True)
    env = dict(os.environ, HF_HOME=os.path.join(ROOT, "models", "hf"),
               TEMP=os.path.join(ROOT, "tools", "tmp"), TMP=os.path.join(ROOT, "tools", "tmp"),
               PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    out = open(CONSOLE_LOG, "a", encoding="utf-8")
    p = subprocess.Popen([PYW, os.path.join(APP, "jarvis.py")], cwd=ROOT, env=env, stdout=out, stderr=out,
                         stdin=subprocess.DEVNULL, creationflags=NO_WINDOW | DETACHED)
    with open(PID_FILE, "w") as f:
        f.write(str(p.pid))
    return "Pornesc Jarvis..."


def close_face_windows():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
          "Where-Object { $_.CommandLine -like '*Jarvis\\data\\fereastra*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW)


def stop_jarvis():
    pid = read_pid()
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    # siguranta: orice python care ruleaza app\jarvis.py din D:\Jarvis
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "Where-Object { $_.CommandLine -like '*Jarvis\\app\\jarvis.py*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW)
    close_face_windows()
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return "Jarvis oprit."


def open_app_window(url, profile, size="900,900"):
    if EDGE:
        subprocess.Popen([EDGE, f"--app={url}", f"--user-data-dir={os.path.join(DATA, profile)}",
                          f"--window-size={size}", "--no-first-run", "--no-default-browser-check"])
    else:
        webbrowser.open(url)


def jarvis_state():
    try:
        with urlopen(f"http://127.0.0.1:{FACE_PORT}/state", timeout=0.5) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


# ---------------- pornire automata ----------------
def autostart_on():
    return os.path.exists(STARTUP_LNK)


def set_autostart(on):
    if on:
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{STARTUP_LNK}');"
              f"$s.TargetPath='{PYW}';$s.Arguments='\"{os.path.join(APP, 'panou.py')}\" --autostart';"
              f"$s.WorkingDirectory='{ROOT}';$s.IconLocation='{os.path.join(APP, 'jarvis.ico')}';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW)
    else:
        try:
            os.remove(STARTUP_LNK)
        except OSError:
            pass
    return autostart_on()


def tail(path, n=60):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-n:])


# ---------------- serverul panoului ----------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            with open(os.path.join(APP, "ui", "panou.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/status"):
            st = jarvis_state()
            env = read_env()
            self._json({"running": is_running(), "jarvis": st, "key": key_status(),
                        "autostart": autostart_on(),
                        "gmail": {"adresa": env.get("GMAIL_ADRESA", ""), "parola": bool(env.get("GMAIL_PAROLA_APP", ""))}})
        elif self.path.startswith("/api/settings"):
            env = read_env()
            self._json({k: env.get(k, "") for k in SETTINGS})
        elif self.path.startswith("/api/log"):
            self._json({"log": tail(LOG_FILE, 80), "console": tail(CONSOLE_LOG, 25)})
        else:
            self._json({"error": "nu exista"}, 404)

    def do_POST(self):
        b = self._body()
        p = self.path
        if p == "/api/start":
            msg = start_jarvis()
        elif p == "/api/stop":
            msg = stop_jarvis()
        elif p == "/api/restart":
            stop_jarvis()
            time.sleep(1.5)
            msg = start_jarvis()
        elif p == "/api/face":
            if is_running():
                open_app_window(f"http://127.0.0.1:{FACE_PORT}/", "fereastra")
                msg = "Am deschis fata lui Jarvis."
            else:
                msg = "Jarvis e oprit."
        elif p == "/api/key":
            k = str(b.get("key", "")).strip().strip('"').strip("'")
            if not re.fullmatch(r"[A-Za-z0-9_.\-]{20,}", k):
                return self._json({"msg": "Cheia nu arata bine. Copiaz-o din nou, fara spatii."})
            write_env({"GEMINI_API_KEY": k})
            msg = "Cheia e salvata."
            if is_running():
                stop_jarvis()
                time.sleep(1.5)
                start_jarvis()
                msg += " Am repornit Jarvis."
        elif p == "/api/settings":
            upd = {k: str(v).strip() for k, v in b.items() if k in SETTINGS}
            write_env(upd)
            msg = "Setarile sunt salvate."
            if is_running():
                stop_jarvis()
                time.sleep(1.5)
                start_jarvis()
                msg += " Am repornit Jarvis."
        elif p == "/api/gmail":
            adr = str(b.get("adresa", "")).strip()
            pw = str(b.get("parola", "")).replace(" ", "").strip()
            upd = {}
            if adr:
                if "@" not in adr:
                    return self._json({"msg": "Adresa de email nu e valida."})
                upd["GMAIL_ADRESA"] = adr
            if pw:
                if not re.fullmatch(r"[A-Za-z]{16}", pw):
                    return self._json({"msg": "Parola de aplicatie are 16 litere (fara spatii). Verific-o."})
                upd["GMAIL_PAROLA_APP"] = pw
            if not upd:
                return self._json({"msg": "Nu ai completat nimic."})
            write_env(upd)
            msg = "Gmail salvat. Jarvis il foloseste de la urmatoarea cerere."
        elif p == "/api/autostart":
            on = set_autostart(bool(b.get("on")))
            msg = "Jarvis porneste automat cu Windows." if on else "Pornirea automata e oprita."
        elif p == "/api/open":
            what = b.get("what")
            targets = {"notite": os.path.join(DATA, "notite.md"), "folder": ROOT,
                       "ajutor": os.path.join(ROOT, "CITESTE-MA.txt"), "setari": ENV_FILE,
                       "cheie": "https://aistudio.google.com/apikey", "contacte": os.path.join(DATA, "contacte.txt"),
                       "apppass": "https://myaccount.google.com/apppasswords"}
            t = targets.get(what)
            if what in ("notite", "contacte") and not os.path.exists(t):
                os.makedirs(DATA, exist_ok=True)
                with open(t, "a", encoding="utf-8") as f:
                    if what == "contacte":
                        f.write("# Contacte WhatsApp: cate unul pe linie, Nume = numar\n# Exemplu:\n# Mama = +40712345678\n")
            if t:
                webbrowser.open(t) if t.startswith("http") else os.startfile(t)
            msg = "Deschis."
        elif p == "/api/quit":
            self._json({"msg": "Panoul se inchide. Jarvis ramane cum era."})
            threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
            return
        else:
            return self._json({"error": "nu exista"}, 404)
        self._json({"msg": msg})


def main():
    os.makedirs(DATA, exist_ok=True)
    if "--autostart" in sys.argv:
        start_jarvis()
        return
    url = f"http://127.0.0.1:{PANEL_PORT}/"
    if port_open(PANEL_PORT):          # panoul ruleaza deja: doar deschidem fereastra
        open_app_window(url, "panou", "760,900")
        return
    server = ThreadingHTTPServer(("127.0.0.1", PANEL_PORT), Handler)
    server.handle_error = lambda *a: None
    threading.Thread(target=lambda: (time.sleep(0.4), open_app_window(url, "panou", "760,900")), daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()