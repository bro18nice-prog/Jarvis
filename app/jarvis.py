"""JARVIS - asistent vocal. Porneste fata (fereastra cu cercul), apoi asculta, gandeste si raspunde."""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "models", "hf"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, "config", "setari.env"))

PORT = int(os.getenv("PORT", "8765"))
WAKE = os.getenv("WAKE_WORD", "jarvis").lower()
WAKE_VARIANTS = [WAKE, "jarvi", "jarviz", "djarvis", "giarvis", "jervis", "jarves", "jarvas", "garvis", "harvis", "jarbis", "gearbis", "giarbis", "arbis", "jarvic"]
ALWAYS_LISTEN = os.getenv("ASCULTA_MEREU", "nu").lower() in ("da", "yes", "true", "1")
FOLLOW_UP_SEC = float(os.getenv("FEREASTRA_CONVERSATIE_SEC", "12"))

state = {"state": "pornire", "heard": "", "reply": "", "log": [], "info": ""}
lock = threading.Lock()
force_listen = threading.Event()
stop_speaking = threading.Event()


def log(msg):
    line = f"{time.strftime('%H:%M:%S')}  {msg}"
    print(line, flush=True)
    with lock:
        state["log"] = (state["log"] + [line])[-60:]
    try:
        with open(os.path.join(ROOT, "data", "jarvis.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def set_state(**kw):
    with lock:
        state.update(kw)


# ---------------- fata: un mic server web local ----------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/state"):
            with lock:
                body = json.dumps(state).encode()
            return self._send(200, body, "application/json")
        with open(os.path.join(ROOT, "app", "ui", "index.html"), "rb") as f:
            return self._send(200, f.read(), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path.startswith("/talk"):
            force_listen.set()
        elif self.path.startswith("/stop"):
            stop_speaking.set()
            try:
                import sounddevice as sd
                sd.stop()
            except Exception:
                pass
        return self._send(200, b"{}", "application/json")


def open_face():
    url = f"http://127.0.0.1:{PORT}/"
    edge_paths = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe")]
    edge = next((p for p in edge_paths if os.path.exists(p)), None) or shutil.which("msedge")
    if edge:
        profile = os.path.join(ROOT, "data", "fereastra")  # profilul ferestrei sta tot pe D
        subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={profile}",
                          "--window-size=900,900", "--no-first-run", "--no-default-browser-check"])
    else:
        webbrowser.open(url)


# ---------------- creier + urechi + voce ----------------
def has_wake(text):
    t = re.sub(r"[^\w\s]", " ", text.lower())
    return any(v in t for v in WAKE_VARIANTS) or any(__import__("difflib").SequenceMatcher(None, w, WAKE).ratio() >= (0.5 if i == 0 else 0.67) for i, w in enumerate(t.split()[:4]))


def strip_wake(text):
    pattern = r"\b(hei |hey |salut |buna )?(" + "|".join(map(re.escape, WAKE_VARIANTS)) + r")\w*\b[,.!?]?"
    out = re.sub(pattern, " ", text, flags=re.I).strip(" ,.!?"); ws = out.split(); return " ".join(ws[1:]).strip(" ,.!?") if ws and __import__("difflib").SequenceMatcher(None, re.sub(r"[^\w]", "", ws[0].lower()), WAKE).ratio() >= 0.5 else out


def main():
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.handle_error = lambda *a: None  # conexiuni inchise de fereastra: nu e eroare
    threading.Thread(target=server.serve_forever, daemon=True).start()
    open_face()
    log("Pornesc Jarvis...")

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or key.startswith("PUNE"):
        set_state(state="eroare", reply="Lipseste cheia Gemini. Pune-o din Panoul de control (scurtatura Jarvis de pe Desktop).")
        log("Lipseste cheia Gemini.")
        while True:
            time.sleep(1)

    import hands
    from brain import Brain
    from ears import Ears
    from voice import Voice

    set_state(state="pornire", reply="Incarc vocea...")
    voice = Voice(os.path.join(ROOT, "models", "piper", os.getenv("VOCE", "ro_RO-mihai-medium") + ".onnx"), log)
    set_state(reply="Incarc urechile (prima data dureaza mai mult)...")
    ears = Ears(os.path.join(ROOT, "models"), lang=os.getenv("LIMBA", "auto"), log=log)
    brain = Brain(key, os.getenv("MODEL_GEMINI", "gemini-flash-lite-latest"), hands.ALL_TOOLS, log)

    speak_lock = threading.Lock()

    def speak(text, lang=None):
        with speak_lock:
            set_state(state="vorbeste", reply=text)
            stop_speaking.clear()
            try:
                voice.say(text, lang or ears.last_lang)
            except Exception as e:
                log(f"Voce: eroare {e}")

    hands.announce = speak

    set_state(info=f"Urechi: {ears.device_info} | Creier: {brain.model}")
    greeting = "Sistemele sunt online, st\u0103p\u00e2ne. A\u0219tept ordinele."
    if ALWAYS_LISTEN:
        greeting = "Sistemele sunt online, st\u0103p\u00e2ne. V\u0103 ascult."
    speak(greeting)

    awake_until = 0.0
    while True:
        try:
            forced = force_listen.is_set()
            force_listen.clear()
            awake = forced or ALWAYS_LISTEN or time.time() < awake_until
            set_state(state="asculta" if awake else "asteapta")
            text = ears.listen()
            if not text:
                continue
            if not (awake or has_wake(text)):
                continue  # nu mi-a fost adresat: nu notez nimic, astept "Jarvis"
            log(f"Am auzit: {text}")
            command = strip_wake(text) if has_wake(text) else text
            set_state(heard=text)
            if len(command) < 2:
                speak("Yes, sir?" if ears.last_lang == "en" else "Da, st\u0103p\u00e2ne?")
                awake_until = time.time() + FOLLOW_UP_SEC
                continue
            if command.lower().strip(" .!") in ("stop", "taci", "gata", "multumesc", "mersi", "thanks", "thank you", "that's all"):
                speak("Very well, sir." if ears.last_lang == "en" else "Am \u00een\u021beles, st\u0103p\u00e2ne.")
                awake_until = 0
                continue
            set_state(state="gandeste", reply="")
            try:
                import quick
                local, rest = quick.handle(command)
            except Exception as e:
                log(f"Comenzi rapide: eroare {e}")
                local, rest = None, command
            if local:
                log("Executat local (fara Google)")
            reply = local or ""
            if rest:
                more = brain.ask(rest)
                reply = (reply + " " + more).strip()
            log(f"Jarvis: {reply}")
            rl = "en" if re.search(r"\bsir\b", reply, re.I) else ("ro" if re.search("[\u0103\u00e2\u00ee\u0219\u021b\u015f\u0163]", reply) else None)
            speak(reply, rl)
            # inapoi in standby; asculta mai departe doar daca m-a intrebat ceva (ex. confirmare mesaj)
            awake_until = time.time() + FOLLOW_UP_SEC if reply.rstrip().endswith("?") else 0
        except KeyboardInterrupt:
            break
        except Exception:
            log("Eroare: " + traceback.format_exc()[-400:])
            set_state(state="eroare")
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("Eroare la pornire: " + traceback.format_exc()[-800:])
        set_state(state="eroare", reply="Eroare la pornire. Vezi fereastra neagra sau data\\jarvis.log.")
        if sys.stdin is not None and sys.stdin.isatty():
            input("Apasa Enter ca sa inchizi...")
        else:
            time.sleep(600)  # lasa fata deschisa ca sa se vada eroarea; panoul il poate opri