"""Jarvis pe telefon, prin Telegram: ii scrii comenzi, iti raspunde in scris.

Siguranta:
  * Botul raspunde DOAR conversatiei aprobate de Stefan din panoul de pe laptop (pagina /telegram).
    Oricine altcineva ii scrie e ignorat.
  * Fisierele se trimit doar din Desktop, Documente si Descarcari, si doar cand le ceri tu.
  * Mailurile nu se pot sterge de pe telefon: aprobarea se face numai pe laptop.
"""
import json
import os
import re
import threading
import time
import unicodedata

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, "config", "setari.env")
STATE_FILE = os.path.join(ROOT, "data", "telegram.json")
HOME = os.path.expanduser("~")
FILE_DIRS = [os.path.join(HOME, d) for d in ("Desktop", "Documents", "Downloads")] + \
            [os.path.join(HOME, "OneDrive", d) for d in ("Desktop", "Documents")]
MAX_FILE = 49 * 1024 * 1024
last_remote = {"t": 0.0}


def _env():
    vals = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*([A-Z_]+)\s*=(.*)$", line)
                if m:
                    vals[m.group(1)] = m.group(2).strip()
    return vals


def _state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"pending": {}, "bot": ""}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def recent_remote(sec=900):
    """True daca in ultimele 15 minute ai dat comenzi de pe telefon (atunci Jarvis nu mai vorbeste tare)."""
    return time.time() - last_remote["t"] < sec


class Remote:
    def __init__(self, log, run_command, status_text):
        self.log = log
        self.run_command = run_command      # functie(text) -> raspuns
        self.status_text = status_text      # functie() -> text
        self.token = _env().get("TELEGRAM_TOKEN", "").strip()
        self.api = f"https://api.telegram.org/bot{self.token}/"
        self.offset = 0

    def _err(self, e):
        """Textul unei erori, fara tokenul botului (erorile de retea contin adresa completa a API-ului)."""
        s = str(e)
        return s.replace(self.token, "***") if self.token else s

    # ---------- Telegram ----------
    def _call(self, method, **kw):
        files = kw.pop("files", None)
        r = requests.post(self.api + method, data=kw if files else None, json=None if files else kw,
                          files=files, timeout=60)
        return r.json()

    def send(self, chat, text):
        for i in range(0, max(len(text), 1), 3800):
            try:
                self._call("sendMessage", chat_id=chat, text=text[i:i + 3800] or "...")
            except Exception as e:
                self.log(f"Telegram: nu am putut trimite ({self._err(e)})")

    def notify(self, text):
        chat = _env().get("TELEGRAM_CHAT_ID", "").strip()
        if self.token and chat:
            self.send(chat, text)

    # ---------- fisiere ----------
    def _find_files(self, query):
        words = [w for w in re.findall(r"\w+", _norm(query)) if len(w) > 1 and w not in
                 ("de", "pe", "la", "din", "cu", "si", "fisierul", "proiectul", "documentul", "folderul", "desktop")]
        if not words:
            return []
        hits = []
        for base in FILE_DIRS:
            if not os.path.isdir(base):
                continue
            base_depth = base.rstrip(os.sep).count(os.sep)
            for dirpath, dirnames, filenames in os.walk(base):
                if dirpath.count(os.sep) - base_depth >= 3:
                    dirnames[:] = []
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in ("node_modules", "venv", ".venv")]
                for fn in filenames:
                    n = _norm(fn)
                    score = sum(1 for w in words if w in n) + 0.5 * sum(1 for w in words if w in _norm(dirpath))
                    if score >= max(1, len(words) * 0.6):
                        p = os.path.join(dirpath, fn)
                        try:
                            hits.append((score, os.path.getmtime(p), p))
                        except OSError:
                            pass
        hits.sort(key=lambda h: (-h[0], -h[1]))
        return [h[2] for h in hits[:8]]

    def _send_file(self, chat, query):
        files = self._find_files(query)
        if not files:
            return "Nu am g\u0103sit niciun fi\u0219ier potrivit \u00een Desktop, Documente sau Desc\u0103rc\u0103ri."
        if len(files) > 1 and not query.strip().endswith("!"):
            st = _state()
            st["choices"] = files
            _save_state(st)
            lines = [f"{i + 1}. {os.path.relpath(p, HOME)}" for i, p in enumerate(files)]
            return "Am g\u0103sit mai multe. R\u0103spunde cu num\u0103rul:\n" + "\n".join(lines)
        return self._upload(chat, files[0])

    def _upload(self, chat, path):
        size = os.path.getsize(path)
        if size > MAX_FILE:
            return f"Fi\u0219ierul are {size // (1024 * 1024)} MB; Telegram accept\u0103 maxim 50 MB."
        with open(path, "rb") as f:
            r = self._call("sendDocument", chat_id=chat, caption=os.path.basename(path), files={"document": f})
        self.log(f"Telegram: am trimis fisierul {os.path.basename(path)}")
        return "" if r.get("ok") else f"Nu am putut trimite fi\u0219ierul: {r.get('description')}"

    # ---------- mesaje ----------
    def handle(self, msg):
        chat = str(msg["chat"]["id"])
        text = (msg.get("text") or "").strip()
        owner = _env().get("TELEGRAM_CHAT_ID", "").strip()
        if chat != owner:
            st = _state()
            who = " ".join(x for x in (msg["chat"].get("first_name"), msg["chat"].get("last_name")) if x) or "?"
            if msg["chat"].get("username"):
                who += f" (@{msg['chat']['username']})"
            if chat not in st["pending"]:
                st["pending"][chat] = who
                _save_state(st)
                self.log(f"Telegram: cerere de acces de la {who}. Aprob-o in panou (pagina Telegram).")
            if not owner:
                self.send(chat, "Salut. Deschide panoul lui Jarvis pe laptop, pagina Telegram, \u0219i apas\u0103 \u201eAprob\u0103\u201d ca s\u0103 te recunosc.")
            return
        if not text:
            return
        last_remote["t"] = time.time()
        mg = re.match(r"^/gmail\s+(\S+@\S+\.\S+)\s+([A-Za-z]{4}\s?[A-Za-z]{4}\s?[A-Za-z]{4}\s?[A-Za-z]{4})\s*$", text)
        if mg:
            return self._set_gmail(chat, msg.get("message_id"), mg.group(1), mg.group(2).replace(" ", ""))
        mk = re.match(r"^/places\s+(\S{20,})\s*$", text)
        if mk:
            try:
                self._call("deleteMessage", chat_id=chat, message_id=msg.get("message_id"))
            except Exception:
                pass
            try:
                import prospectare
            except ImportError:
                return self.send(chat, "Modulul de prospectare nu este instalat. Am șters mesajul cu cheia din chat.")
            prospectare.set_places_key(mk.group(1))
            self.log("Telegram: cheia Google Places a fost salvata (doar pe laptop)")
            return self.send(chat, "Am salvat cheia Google Places doar pe laptop și am șters mesajul din chat. Încearcă: misiune veterinar Suceava")
        if text.lower().startswith("/gmail"):
            return self.send(chat, "Format: /gmail adresa@gmail.com parola-de-aplicatie (16 litere)")
        if re.fullmatch(r"[A-Za-z]{16}|[A-Za-z]{4} [A-Za-z]{4} [A-Za-z]{4} [A-Za-z]{4}", text):
            try:
                self._call("deleteMessage", chat_id=chat, message_id=msg.get("message_id"))
            except Exception:
                pass
            self.log("Telegram: mesaj care arata ca o parola - sters si ignorat")
            return self.send(chat, "Mesajul arata ca o parola, asa ca l-am sters si nu l-am trimis nicaieri. "
                                   "Pentru Gmail scrie: /gmail adresa@gmail.com parola")
        self.log(f"Telegram: {text}")
        pc = self._pc_command(chat, _norm(text))
        if pc is not None:
            return self.send(chat, pc) if pc else None
        mail = self._mail_command(chat, _norm(text))
        if mail is not None:
            return self.send(chat, mail) if mail else None
        low = _norm(text)
        if low in ("/start", "/help", "ajutor", "help"):
            return self.send(chat, "Sunt aici, st\u0103p\u00e2ne. Scrie-mi ce ai zice cu vocea, de exemplu:\n"
                                   "\u2022 deschide lolu\n\u2022 pune Exit Music pe Spotify\n\u2022 pauz\u0103 / mai tare\n"
                                   "\u2022 trimite-mi proiectul la francez\u0103\n\u2022 verific\u0103 mailul\n\u2022 /status")
        if low in ("/status", "status", "stare"):
            return self.send(chat, self.status_text())
        st = _state()
        if re.fullmatch(r"\d{1,2}", low) and st.get("choices"):
            i = int(low) - 1
            ch = st.pop("choices")
            _save_state(st)
            if 0 <= i < len(ch):
                r = self._upload(chat, ch[i])
                return self.send(chat, r) if r else None
        m = re.match(r"^(?:trimite(?:-?mi)?|da-?mi|vreau)\s+(?:fisierul\s+|documentul\s+)?(.+)$", low)
        if m and not re.search(r"\b(mesaj|mail|whatsapp|email|pt|pentru|firm\w*|ofert\w*|tot|toate)\b", low) and not re.match(r"trimite[ ,\d]+(si[ ,\d]+)*$", low):
            r = self._send_file(chat, m.group(1))
            return self.send(chat, r) if r else None
        try:
            self._call("sendChatAction", chat_id=chat, action="typing")
        except Exception:
            pass
        self.send(chat, self.run_command(text) or "Gata.")

    # ---------- laptop ----------
    def _pc_command(self, chat, low):
        """Comenzi pentru laptop, de pe telefon. Intoarce None daca mesajul nu e despre asta."""
        import subprocess
        low = re.sub(r"^(?:te rog |hai )", "", low)
        st = _state()
        if st.get("pc_confirm"):
            st.pop("pc_confirm")
            _save_state(st)
            if low in ("da", "confirm", "yes"):
                subprocess.Popen(["shutdown", "/s", "/t", "30"], creationflags=0x08000000)
                self.log("Telegram: oprire laptop confirmata")
                return "Laptopul se opreste in 30 de secunde. Scrie: anuleaza oprirea, daca te-ai razgandit."
            if low in ("nu", "no", "anuleaza", "stop"):
                return "Am anulat. Laptopul ramane pornit."
        if re.fullmatch(r"anuleaza (?:oprirea|inchiderea)", low):
            subprocess.Popen(["shutdown", "/a"], creationflags=0x08000000)
            return "Am anulat oprirea."
        if re.search(r"\b(?:opreste|inchide|stinge)\w*\b.*\b(?:laptop\w*|pc\w*|calculator\w*)\b|\bshutdown\b", low):
            st["pc_confirm"] = True
            _save_state(st)
            return "Opresc laptopul de tot? Dupa aceea nu mai pot primi comenzi pana il porneste cineva. Raspunde: da / nu"
        if re.search(r"\bbloche\w*\b|\block\b", low):
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return "Am blocat laptopul."
        if re.search(r"\b(?:sleep|repaus|standby|hibern\w*|adormi)\b", low) and not re.search(r"spotify|youtube|melodi|pies|cant", low):
            def _sleep():
                time.sleep(4)
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=0x08000000)
            threading.Thread(target=_sleep, daemon=True).start()
            return "Pun laptopul in repaus. Cat doarme nu mai primesc comenzi."
        if re.search(r"\b(?:captura|screenshot|printscreen|print screen)\b|\bpoza\b.*\becran|ce e pe ecran", low):
            out = os.path.join(ROOT, "data", "captura-ecran.png")
            ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                  "Add-Type 'using System.Runtime.InteropServices; public class JDpi{[DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware();}';"
                  "[JDpi]::SetProcessDPIAware()|Out-Null;"
                  "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
                  "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
                  "$g=[System.Drawing.Graphics]::FromImage($bmp);"
                  "$g.CopyFromScreen($b.Left,$b.Top,0,0,$bmp.Size);"
                  "$bmp.Save('" + out + "')")
            try:
                if os.path.exists(out):
                    os.remove(out)
                subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000, timeout=30)
                if not os.path.exists(out):
                    return "Nu am putut face captura."
                return self._upload(chat, out)
            except Exception as e:
                return f"Nu am putut face captura: {e}"
        return None

    # ---------- Gmail ----------
    def _set_gmail(self, chat, mid, addr, pw):
        """Primeste adresa + parola de aplicatie direct de la Stefan, le verifica si le salveaza DOAR pe laptop."""
        try:
            self._call("deleteMessage", chat_id=chat, message_id=mid)
        except Exception:
            pass
        import imaplib
        try:
            M = imaplib.IMAP4_SSL("imap.gmail.com", timeout=20)
            M.login(addr, pw)
            M.logout()
        except Exception:
            self.log("Telegram: datele Gmail nu au fost acceptate de Google")
            return self.send(chat, "Google nu a acceptat datele. Verifica adresa si parola de aplicatie (16 litere) si trimite din nou /gmail ...")
        lines, done = [], set()
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, encoding="utf-8") as f:
                lines = f.read().splitlines()
        upd = {"GMAIL_ADRESA": addr, "GMAIL_PAROLA_APP": pw}
        for i, line in enumerate(lines):
            m = re.match(r"\s*([A-Z_]+)\s*=", line)
            if m and m.group(1) in upd:
                lines[i] = m.group(1) + "=" + upd[m.group(1)]
                done.add(m.group(1))
        lines += [k + "=" + v for k, v in upd.items() if k not in done]
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.log("Telegram: Gmail conectat (date salvate doar pe laptop)")
        self.send(chat, "Gmail conectat. Am sters din chat mesajul cu parola. Scrie: verifica mailul")

    def _mail_command(self, chat, low):
        """Lista de curatenie pe telefon. Intoarce None daca mesajul nu e despre asta.
        Nimic nu se muta in Cos fara 'sterge <numere>' urmat de 'da'."""
        st = _state()
        if st.get("mail_confirm") and low in ("da", "confirm", "confirma", "yes"):
            import mail_curator
            c = st.pop("mail_confirm")
            _save_state(st)
            try:
                r = mail_curator.trash(c["scan"], c["ids"], self.log)
            except Exception as e:
                return f"Nu am putut muta mailurile: {e}"
            extra = f" ({r['failed']} nu au putut fi mutate)" if r["failed"] else ""
            return f"Gata: {r['moved']} mailuri mutate in Cosul Gmail{extra}. Le poti recupera 30 de zile."
        if st.get("mail_confirm") and low in ("nu", "anuleaza", "no", "stop"):
            st.pop("mail_confirm")
            _save_state(st)
            return "Am anulat. Nu am sters nimic."
        mc = re.fullmatch(r"(?:sterge|muta|curata)\s+(?:din\s+|de la\s+)?(spam\w*|social\w*|retele\w*(?: sociale)?|reclame\w*|promo\w*|forum\w*|tot)"
                          r"(?:\s+(?:fara|in afara de|mai putin|dar nu)\s+((?:\d+[\s,]*)+))?", low)
        if mc:
            mp = st.get("mail_map") or {}
            w = mc.group(1)
            want = None if w == "tot" else "spam" if w.startswith("spam") else "social" if w[:3] in ("soc", "ret") else "forumuri" if w.startswith("forum") else "reclame"
            if not mp or not any("g" in e for e in mp.values()):
                return "Scrie intai: raport. Apoi repeta comanda."
            skip = set(re.findall(r"\d+", mc.group(2) or ""))
            ids, names, kept = [], [], []
            for n, e in mp.items():
                if want and e.get("g") != want:
                    continue
                if n in skip:
                    kept.append(e["name"])
                    continue
                ids += e["ids"]
                names.append(e["name"])
            if not ids:
                return "Nu am nimic de mutat in categoria asta."
            st["mail_confirm"] = {"scan": st.get("mail_scan"), "ids": ids}
            _save_state(st)
            return (f"Mut in Cosul Gmail {len(ids)} mailuri de la {len(names)} expeditori ({w}): " + ", ".join(names[:25]) +
                    (" ..." if len(names) > 25 else "") + ("\nPastrez: " + ", ".join(kept) if kept else "") +
                    "\n\nConfirmi? Raspunde: da / nu")
        m = re.fullmatch(r"(?:sterge|muta|cos)\s+((?:\d+[\s,]*)+)", low)
        if m:
            mp = st.get("mail_map") or {}
            nums = [n for n in re.findall(r"\d+", m.group(1)) if n in mp]
            if not nums:
                return "Nu am numerele astea pe lista. Scrie intai: lista mail"
            ids, names = [], []
            for n in nums:
                ids += mp[n]["ids"]
                names.append(f"{mp[n]['name']} ({len(mp[n]['ids'])})")
            st["mail_confirm"] = {"scan": st.get("mail_scan"), "ids": ids}
            _save_state(st)
            return (f"Mut in Cosul Gmail {len(ids)} mailuri de la:\n- " + "\n- ".join(names) +
                    "\n\nConfirmi? Raspunde: da / nu")
        if low in ("lista mail", "lista mailuri", "lista mailurilor", "/mail", "mail lista", "arata lista") or re.fullmatch(
                r"(?:verifica|scaneaza|curata)(?:[- ]?mi)? (?:mail\w*|email\w*|gmail)|raport(?:ul)?(?: (?:de |pe )?mail\w*)?", low):
            import mail_curator
            if not mail_curator.configured():
                return "Gmail nu e conectat. Trimite: /gmail adresa@gmail.com parola-de-aplicatie"
            try:
                res = mail_curator.scan(self.log)
            except Exception as e:
                return f"Nu am putut citi Gmail: {e}"
            mp, out, n = {}, [], 0
            for g in res["groups"]:
                if not g["count"]:
                    continue
                out.append(f"\n== {g['label'].upper()} ({g['count']}) ==")
                for s in g["senders"][:40]:
                    n += 1
                    mp[str(n)] = {"ids": [x["id"] for x in s["msgs"]], "name": s["name"], "g": g["key"]}
                    subj = "; ".join('"' + x["subject"][:45] + '"' for x in s["msgs"][:2])
                    out.append(f"{n}. {s['name']} <{s['addr']}> - {s['count']} mailuri: {subj}")
            st = _state()
            st["mail_map"], st["mail_scan"] = mp, res["id"]
            st.pop("mail_confirm", None)
            _save_state(st)
            imp = res["important"]
            head = f"Importante necitite: {len(imp)}" + ("".join(f"\n- {x['name']}: {x['subject'][:60]}" for x in imp[:10]) if imp else "")
            if not n:
                return head + "\n\nNu e nimic de curatat."
            return (head + "\n" + "\n".join(out) + "\n\nNu am sters nimic. Ca sa mut in Cos, scrie de ex.: sterge 1 3 5"
                    "\nAbonamente gasite: " + str(len(res["subscriptions"])) + " (dezabonarea se face din panoul de pe laptop).")
        if re.search(r"\b(sterg\w*|sters\w*|dezabon\w*|curat\w*)\b", low) and re.search(r"\b(mail\w*|spam\w*|reclam\w*|promo\w*|social\w*|abonament\w*)\b", low):
            return ("Mailurile le mut in Cos doar cu comenzi exacte, ca sa nu sterg nimic din greseala:\n"
                    "1. raport  (primesti lista numerotata)\n"
                    "2. sterge 1 3 5  /  sterge spam  /  sterge social  /  sterge reclame fara 3 7\n"
                    "3. da  (confirmi)\nPana nu confirmi, nu se sterge nimic.")
        return None

    def loop(self):
        if not self.token:
            return
        try:
            me = self._call("getMe")
            if me.get("ok"):
                st = _state()
                st["bot"] = "@" + me["result"].get("username", "")
                _save_state(st)
                self.log(f"Telegram: conectat ca {st['bot']}")
            else:
                self.log(f"Telegram: tokenul nu e bun ({me.get('description')})")
                return
        except Exception as e:
            self.log(f"Telegram: fara internet ({self._err(e)}), reincerc")
        while True:
            try:
                r = requests.get(self.api + "getUpdates", params={"timeout": 30, "offset": self.offset},
                                 timeout=40).json()
                for u in r.get("result", []):
                    self.offset = u["update_id"] + 1
                    msg = u.get("message") or u.get("edited_message")
                    if msg:
                        threading.Thread(target=self._safe_handle, args=(msg,), daemon=True).start()
            except Exception:
                time.sleep(5)

    def _safe_handle(self, msg):
        try:
            self.handle(msg)
        except Exception as e:
            self.log(f"Telegram: eroare {self._err(e)}")
            try:
                self.send(str(msg["chat"]["id"]), f"Eroare: {self._err(e)}")
            except Exception:
                pass

    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()