"""Agenda, remindere, rutine, brief de dimineata, mod economic. Totul local, in data/asistent.json."""
import datetime as dt
import difflib
import json
import os
import re
import threading
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "data", "asistent.json")
ZILE = ["luni", "marti", "miercuri", "joi", "vineri", "sambata", "duminica"]
LUNI = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
        "septembrie", "octombrie", "noiembrie", "decembrie"]
REZERVAT = ("economic", "eco", "telefon", "silentios", "normal", "voce", "complet")
_lock = threading.RLock()
_ctx = {"notify": None, "speak": None, "run": None, "log": print, "recent": lambda: True, "depth": 0}


def _load():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    for k, v in (("items", []), ("rutine", {}), ("eco", False), ("next", 1), ("brief", "")):
        d.setdefault(k, v)
    if not d.get("rutine_implicite"):      # o rutina de pornire, ca "mod gaming" sa mearga din prima
        d["rutine"].setdefault("gaming", ["deschide league", "deschide discord"])
        d["rutine_implicite"] = True
    return d


def _save(d):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def eco():
    return bool(_load()["eco"])


def _when(t):
    """Scoate data si ora dintr-un text normalizat. Intoarce (datetime sau None, restul textului)."""
    now = dt.datetime.now()
    m = re.search(r"\b(?:in|peste) (\d+|o|un|doua)(?: de)? (min\w*|ora|ore|zi|zile)\b", t)
    if m:
        n = {"o": 1, "un": 1, "doua": 2}.get(m.group(1)) or int(m.group(1))
        u = m.group(2)
        delta = dt.timedelta(minutes=n) if u.startswith("min") else dt.timedelta(hours=n) if u.startswith("or") else dt.timedelta(days=n)
        return now + delta, (t[:m.start()] + t[m.end():]).strip()
    day, hm, cut, wd = None, None, [], False
    m = re.search(r"\b(poimaine|maine|azi|astazi|diseara|deseara)\b", t)
    if m:
        w = m.group(1)
        day = now.date() + dt.timedelta(days=2 if w == "poimaine" else 1 if w == "maine" else 0)
        if w in ("diseara", "deseara"):
            hm = (20, 0)
        cut.append(m.span())
    m = re.search(r"\b(" + "|".join(ZILE) + r")\b", t)
    if m and day is None:
        day = now.date() + dt.timedelta(days=(ZILE.index(m.group(1)) - now.weekday()) % 7)
        wd = True
        cut.append(m.span())
    m = re.search(r"\bpe (\d{1,2})(?: (" + "|".join(LUNI) + r")| (\d{1,2})\b)?", t)
    if m and day is None:
        mon = LUNI.index(m.group(2)) + 1 if m.group(2) else int(m.group(3)) if m.group(3) else now.month
        try:
            day = dt.date(now.year, mon, int(m.group(1)))
            if day < now.date():
                day = dt.date(now.year + (1 if m.group(2) or m.group(3) else 0), mon + (0 if m.group(2) or m.group(3) else 1), int(m.group(1)))
            cut.append(m.span())
        except ValueError:
            day = None
    m = re.search(r"\b(?:de la|la|ora)(?: ora)? (\d{1,2})(?: (\d{2})\b| si jumatate| si jumate| jumate)?", t)
    if m and int(m.group(1)) < 24:
        h = int(m.group(1))
        if (1 <= h <= 6 and not re.search(r"\b(?:dimineata|noaptea)\b", t)) or (h < 12 and re.search(r"\b(?:seara|dupa amiaza|dupa masa|pm)\b", t)):
            h += 12
        hm = (h, int(m.group(2) or (30 if "jum" in m.group(0) else 0)))
        cut.append(m.span())
    elif hm is None and not re.search(r"\bpe \d", t):
        m2 = re.search(r"\b([01]?\d|2[0-3]) ([0-5]\d)\b", t)
        if m2:
            hm = (int(m2.group(1)), int(m2.group(2)))
            cut.append(m2.span())
    if day is None and hm is None:
        return None, t
    when = dt.datetime.combine(day or now.date(), dt.time(*(hm or (9, 0))))
    if when <= now and day is None:
        when += dt.timedelta(days=1)
    elif when <= now and wd:
        when += dt.timedelta(days=7)
    for a, b in sorted(cut, reverse=True):
        t = t[:a] + t[b:]
    t = re.sub(r"\b(?:dimineata|noaptea|seara|dupa amiaza|dupa masa|pm)\b", " ", t)
    return when, re.sub(r"\s+", " ", t).strip()


def _fmt(ts):
    d = dt.datetime.fromtimestamp(ts)
    today = dt.date.today()
    zi = "azi" if d.date() == today else "maine" if d.date() == today + dt.timedelta(days=1) else f"{ZILE[d.weekday()]} {d.day} {LUNI[d.month - 1]}"
    return f"{zi} la {d:%H:%M}"


def _add(kind, when, text):
    with _lock:
        d = _load()
        it = {"id": d["next"], "ts": when.timestamp(), "text": text, "kind": kind}
        d["next"] += 1
        d["items"].append(it)
        _save(d)
    return it


def _list(day=None):
    items = sorted(_load()["items"], key=lambda x: x["ts"])
    if day is not None:
        items = [x for x in items if dt.datetime.fromtimestamp(x["ts"]).date() == day]
    if not items:
        return "Nu ai nimic in agenda" + (" pentru ziua aceea." if day else ".")
    return "\n".join(f"{x['id']}. {_fmt(x['ts'])} - {x['text']}" + (" (reminder)" if x["kind"] == "r" else "") for x in items)


def handle(text):
    """Raspunsul pentru o comanda de agenda / reminder / rutina / mod economic, sau None daca nu e pentru mine."""
    raw = (text or "").strip()
    low = re.sub(r"^(?:jarvis |te rog |hai )+", "", _norm(raw))
    low = re.sub(r"\bmodu\b", "modul", re.sub(r"\bpt\b", "pentru", low))
    ws = low.split()
    modish = len(ws) == 1 or any(w.startswith("mod") for w in ws) or (ws and ws[0] in ("treci", "intra", "activeaza", "revino"))
    if 1 <= len(ws) <= 5 and modish and ":" not in raw and "=" not in raw:
        if any(w == "eco" or difflib.SequenceMatcher(None, w, "economic").ratio() >= 0.75 for w in ws) or ws[-1] in ("telefon", "silentios"):
            with _lock:
                d = _load(); d["eco"] = True; _save(d)
            return "Trec pe modul economic: fara microfon, fara fereastra, raspund doar pe Telegram. Scrie: mod normal, ca sa revin."
        if ws[-1] in ("normal", "voce", "complet"):
            with _lock:
                d = _load(); d["eco"] = False; _save(d)
            return "Revin la modul normal: ascult din nou dupa cuvantul Jarvis."
    m = re.fullmatch(r"(?:arata mi |zi mi )?(?:agenda|remindere\w*|ce am(?: in agenda| de facut| programat)?|ce remindere am)(?: (?:pe |pentru )?(azi|astazi|maine|poimaine))?", low)
    if m:
        w = m.group(1)
        day = None if not w else dt.date.today() + dt.timedelta(days={"maine": 1, "poimaine": 2}.get(w, 0))
        return _list(day)
    m = re.fullmatch(r"(?:sterge|anuleaza|scoate) (?:din agenda|reminderul|remindarul|punctul)(?: nr| numarul)? (\d+)", low)
    if m:
        with _lock:
            d = _load()
            keep = [x for x in d["items"] if x["id"] != int(m.group(1))]
            found = len(keep) != len(d["items"])
            d["items"] = keep
            _save(d)
        return "Am sters." if found else "Nu am gasit numarul asta in agenda."
    if re.search(r"\b(?:remind\w*|remaind\w*|alarm\w*|amintest\w*|aminti\w*|reamint\w*|adu mi aminte)\b", low):
        body = re.sub(r"\b(?:sa )?(?:mi )?(?:pune|seteaza|fa|adauga|creeaza|vreau|as vrea)?\s*(?:mi )?(?:un |o )?(?:remind\w*|remaind\w*|alarm\w*|amintest\w*|aminti\w*|reamint\w*|adu mi aminte)(?: mi)?\b", " ", low, count=1)
        when, rest = _when(body)
        rest = re.sub(r"^(?:(?:pentru|sa|ca|de|despre|cu titlul|cu numele|cu textul|numit|cu) )+", "", rest + " ").strip()
        rest = rest or "reminder"
        if when is None:
            return "Spune-mi si cand, de exemplu: aminteste-mi la 18 sa sun la bunica, sau: aminteste-mi in 20 de minute sa scot pizza."
        it = _add("r", when, rest)
        return f"Am notat. Iti amintesc {_fmt(it['ts'])}: {rest}. (Vezi tot cu: agenda)"
    m = re.search(r"\b(?:adauga|pune|noteaza|trece|scrie|baga)\b(.*?)\b(?:in|pe|la) (?:agenda|calendar\w*)\b(.*)$", low)
    if m:
        when, rest = _when((m.group(1) + " " + m.group(2)).strip())
        rest = re.sub(r"^(?:(?:mi|pentru|ca|cu titlul|cu) )+", "", rest + " ").strip()
        if when is None or not rest:
            return "Spune-mi si cand, de exemplu: pune in agenda joi la 16 dentist."
        it = _add("a", when, rest)
        return f"Am trecut in agenda, {_fmt(it['ts'])}: {rest}. Te anunt cu 30 de minute inainte."
    m = re.match(r"^\s*(?:jarvis[, ]+)?(?:rutina|modul|mod)\s+([\w-]+)\s*[:=]\s*(.+)$", raw, re.I | re.S)
    if m:
        name = _norm(m.group(1))
        steps = [s.strip() for s in re.split(r"\s*(?:,|;|\n| apoi )\s*", m.group(2)) if s.strip()]
        if name in REZERVAT or not steps:
            return "Numele asta e rezervat. Alege altul."
        with _lock:
            d = _load(); d["rutine"][name] = steps; _save(d)
        return f"Am salvat rutina {name} cu {len(steps)} pasi. O pornesti cu: mod {name}."
    if re.fullmatch(r"rutine|rutinele|ce rutine am", low):
        r = _load()["rutine"]
        return "\n".join(f"{k}: " + ", ".join(v) for k, v in r.items()) if r else "Nu ai nicio rutina. Exemplu: rutina gaming: deschide league, deschide discord"
    m = re.fullmatch(r"sterge rutina (\w+)", low)
    if m:
        with _lock:
            d = _load(); ok = d["rutine"].pop(m.group(1), None); _save(d)
        return "Am sters rutina." if ok else "Nu am rutina asta."
    m = re.fullmatch(r"(?:porneste |ruleaza |activeaza |da drumul la )?(?:rutina|modul|mod) (\w+)", low)
    if not m:   # "mod gaming" auzit gresit: "dol gaming", "mot gaming", "modu gaming"
        m2 = re.fullmatch(r"(\w{2,6}) (\w+)", low)
        if m2 and m2.group(2) in _load()["rutine"] and (len(m2.group(1)) <= 4 and "o" in m2.group(1) or m2.group(1) in ("modu", "modul", "mode")):
            m = m2
            m = re.fullmatch(r"(?:mod) (\w+)", "mod " + m2.group(2))
    if m and m.group(1) not in _load()["rutine"] and m.group(1) not in REZERVAT:
        r = _load()["rutine"]
        return (f"Nu am o rutină numită {m.group(1)}. " + ("Am: " + ", ".join(r) + ". " if r else "")
                + f"O definești așa: rutina {m.group(1)}: deschide league, deschide discord, pune muzică pe spotify")
    if low in ("mod", "modul", "rutina"):
        r = _load()["rutine"]
        return "Spune și care, de exemplu: mod gaming. " + ("Am rutinele: " + ", ".join(r) + "." if r else "")
    if m and m.group(1) in _load()["rutine"]:
        if _ctx["run"] is None or _ctx["depth"] > 0:
            return "Nu pot porni rutina acum."
        _ctx["depth"] += 1
        try:
            out = [str(_ctx["run"](s) or "Gata.") for s in _load()["rutine"][m.group(1)]]
        finally:
            _ctx["depth"] -= 1
        return f"Rutina {m.group(1)}: " + " ".join(out)
    return None


def _tell(text):
    if _ctx["notify"]:
        _ctx["notify"](text)
    if _ctx["speak"] and not eco() and not _ctx["recent"]():
        _ctx["speak"](text)


def _battery():
    import ctypes

    class S(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("pct", ctypes.c_byte), ("r", ctypes.c_byte),
                    ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
    s = S()
    ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))
    return s.ac == 1, s.pct


def _brief():
    today = dt.date.today()
    lines = ["Buna dimineata, stapane. Azi, " + f"{ZILE[today.weekday()]} {today.day} {LUNI[today.month - 1]}:", _list(today)]
    try:
        import mail_curator
        if mail_curator.configured():
            res = mail_curator.scan(_ctx["log"])
            junk = sum(g["count"] for g in res["groups"])
            lines.append(f"Mail: {len(res['important'])} importante necitite, {junk} de curatat. Scrie: raport, pentru lista.")
    except Exception as e:
        lines.append(f"Mailul nu a putut fi verificat ({e}).")
    return "\n".join(lines)


def _loop():
    warned = False
    while True:
        time.sleep(20)
        try:
            now = time.time()
            due = []
            with _lock:
                d = _load()
                keep, changed = [], False
                for x in d["items"]:
                    if x["kind"] == "a" and not x.get("pre") and x["ts"] - 1800 <= now < x["ts"] - 60:
                        x["pre"] = True
                        changed = True
                        due.append(f"In 30 de minute: {x['text']} ({_fmt(x['ts'])}).")
                    if now >= x["ts"]:
                        changed = True
                        late = " (trebuia " + _fmt(x["ts"]) + ")" if now - x["ts"] > 600 else ""
                        due.append(("Reminder: " if x["kind"] == "r" else "Agenda, acum: ") + x["text"] + late)
                    else:
                        keep.append(x)
                hhmm = os.getenv("BRIEF_ORA", "08:30").strip()
                today = time.strftime("%Y-%m-%d")
                brief = bool(hhmm) and d["brief"] != today and hhmm <= time.strftime("%H:%M") < "13:00"
                if brief:
                    d["brief"], changed = today, True
                if changed:
                    d["items"] = keep
                    _save(d)
            for t in due:
                _tell(t)
            if brief:
                _tell(_brief())
            ac, pct = _battery()
            if not ac and pct <= 20 and not warned:
                warned = True
                _tell(f"Bateria laptopului e la {pct}% si nu e la incarcat.")
            elif ac or pct > 30:
                warned = False
        except Exception as e:
            _ctx["log"](f"Asistent: eroare {e}")


def start(notify, speak, run, log, recent):
    _ctx.update(notify=notify, speak=speak, run=run, log=log, recent=recent)
    threading.Thread(target=_loop, daemon=True).start()


def eco_tick(ears, log, set_state, open_face):
    """Chemata din bucla principala. True = suntem pe modul economic (nu ascultam)."""
    if eco():
        if ears.model is not None:
            import gc
            import subprocess
            ears.model = None
            gc.collect()
            ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
                  "Where-Object { $_.CommandLine -like '*Jarvis\\data\\fereastra*' } | "
                  "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)
            set_state(state="economic", reply="Mod economic: raspund doar pe Telegram.")
            log("Mod economic pornit: microfon si fereastra oprite, memoria placii video eliberata")
        time.sleep(2)
        return True
    if ears.model is None:
        log("Mod normal: reincarc urechile")
        ears.__init__(os.path.join(ROOT, "models"), lang=ears.lang, log=ears.log)
        open_face()
    return False
