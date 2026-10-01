"""Mainile lui Jarvis: uneltele pe care creierul (Gemini) le poate folosi.

Fiecare functie are descriere si tipuri, ca Gemini sa stie cand si cum s-o apeleze.
"""
import datetime as _dt
import difflib
import glob
import os
import threading
import urllib.parse
import webbrowser

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES = os.path.join(ROOT, "data", "notite.md")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}

# Jarvis seteaza asta la pornire, ca timerele sa poata vorbi.
announce = print

ZILE = ["luni", "marti", "miercuri", "joi", "vineri", "sambata", "duminica"]
LUNI = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie",
        "august", "septembrie", "octombrie", "noiembrie", "decembrie"]


def ora_si_data() -> str:
    """Spune ora, ziua saptamanii si data de azi."""
    n = _dt.datetime.now()
    return f"{ZILE[n.weekday()]}, {n.day} {LUNI[n.month - 1]} {n.year}, ora {n:%H:%M}"


def cauta_pe_internet(interogare: str) -> str:
    """Cauta pe internet si intoarce primele rezultate (titlu, scurt rezumat, link).
    Foloseste pentru stiri, preturi, vreme, informatii actuale sau orice nu stii sigur."""
    results = []
    try:
        from ddgs import DDGS
        with DDGS() as d:
            for r in d.text(interogare, max_results=6):
                results.append((r.get("title", ""), r.get("body", ""), r.get("href", "")))
    except Exception:
        try:
            html = requests.post("https://html.duckduckgo.com/html/", data={"q": interogare},
                                 headers=UA, timeout=12).text
            soup = BeautifulSoup(html, "html.parser")
            for res in soup.select(".result")[:6]:
                a = res.select_one(".result__a")
                sn = res.select_one(".result__snippet")
                if a:
                    href = a.get("href", "")
                    if "uddg=" in href:
                        href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                    results.append((a.get_text(" ", strip=True), sn.get_text(" ", strip=True) if sn else "", href))
        except Exception as e:
            return f"Cautarea a esuat: {e}"
    if not results:
        return "Nu am gasit rezultate."
    return "\n".join(f"- {t}: {b} ({h})" for t, b, h in results)


def citeste_pagina(url: str) -> str:
    """Deschide o pagina web si intoarce textul ei (primele ~5000 de caractere).
    Foloseste dupa cautare cand ai nevoie de detalii dintr-un rezultat."""
    try:
        r = requests.get(url, headers=UA, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return text[:5000] or "Pagina nu are text."
    except Exception as e:
        return f"Nu am putut citi pagina: {e}"


def deschide_site(adresa_sau_cautare: str) -> str:
    """Deschide in browser un site (ex. 'youtube.com') sau, daca nu e o adresa,
    deschide o cautare Google cu textul dat. Pentru o melodie pe YouTube trimite
    'youtube: numele melodiei'."""
    s = adresa_sau_cautare.strip()
    if s.lower().startswith("youtube:"):
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(s.split(":", 1)[1].strip())
    elif " " not in s and "." in s:
        url = s if s.startswith("http") else "https://" + s
    else:
        url = "https://www.google.com/search?q=" + urllib.parse.quote(s)
    webbrowser.open(url)
    return f"Am deschis {url}"


_SPECIAL_APPS = {
    "calculator": "calc.exe", "calculatorul": "calc.exe",
    "notepad": "notepad.exe", "blocnotes": "notepad.exe",
    "explorer": "explorer.exe", "fisiere": "explorer.exe", "file explorer": "explorer.exe",
    "setari": "ms-settings:", "settings": "ms-settings:",
    "paint": "mspaint.exe", "task manager": "taskmgr.exe",
}


def _start_menu_shortcuts():
    dirs = [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop")]
    found = {}
    for d in dirs:
        for p in glob.glob(os.path.join(d, "**", "*.lnk"), recursive=True) + glob.glob(os.path.join(d, "**", "*.url"), recursive=True):
            name = os.path.splitext(os.path.basename(p))[0].lower()
            if "uninstall" in name or "dezinstal" in name:
                continue
            found.setdefault(name, p)
    return found


def deschide_aplicatie(nume: str) -> str:
    """Porneste o aplicatie instalata pe laptop dupa nume (ex. 'spotify', 'discord',
    'steam', 'calculator', 'chrome', 'word')."""
    key = nume.strip().lower()
    if key in _SPECIAL_APPS:
        os.startfile(_SPECIAL_APPS[key])
        return f"Am deschis {nume}."
    apps = _start_menu_shortcuts()
    candidates = [n for n in apps if key in n] or difflib.get_close_matches(key, list(apps), n=1, cutoff=0.6)
    if not candidates:
        return f"Nu am gasit nicio aplicatie numita {nume}."
    best = sorted(candidates, key=len)[0]
    os.startfile(apps[best])
    return f"Am deschis {best}."


def seteaza_timer(minute: float, mesaj: str) -> str:
    """Seteaza un timer/memento. Dupa numarul de minute dat, Jarvis spune mesajul cu voce."""
    def ring():
        announce(f"St\u0103p\u00e2ne, timpul a expirat. {mesaj}")
    t = threading.Timer(max(0.05, float(minute)) * 60, ring)
    t.daemon = True
    t.start()
    return f"Timer setat pentru {minute:g} minute: {mesaj}"


def noteaza(text: str) -> str:
    """Salveaza o notita (idei, cumparaturi, lucruri de tinut minte)."""
    os.makedirs(os.path.dirname(NOTES), exist_ok=True)
    with open(NOTES, "a", encoding="utf-8") as f:
        f.write(f"- [{_dt.datetime.now():%Y-%m-%d %H:%M}] {text}\n")
    return "Am notat."


def citeste_notitele() -> str:
    """Citeste notitele salvate anterior."""
    if not os.path.exists(NOTES):
        return "Nu ai notite."
    with open(NOTES, encoding="utf-8") as f:
        lines = f.read().strip().splitlines()
    return "\n".join(lines[-30:]) or "Nu ai notite."


# ======================= MEDIA (Spotify, YouTube, orice player) =======================
_VK = {"play_pauza": 0xB3, "urmatoarea": 0xB0, "anterioara": 0xB1, "stop": 0xB2,
       "volum_sus": 0xAF, "volum_jos": 0xAE, "mut": 0xAD}


def _press(vk, times=1):
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def control_media(actiune: str, pasi: int = 1) -> str:
    """Controleaza muzica/video care ruleaza acum (Spotify, YouTube, orice player), ca tastele media.
    actiune: 'play_pauza', 'urmatoarea', 'anterioara', 'stop', 'volum_sus', 'volum_jos', 'mut'.
    pasi: de cate ori (pentru volum, fiecare pas e ~2%; 5 pasi = ~10%)."""
    a = actiune.strip().lower()
    if a not in _VK:
        return "Actiune necunoscuta. Optiuni: " + ", ".join(_VK)
    n = max(1, min(int(pasi or 1), 50)) if a.startswith("volum") else 1
    _press(_VK[a], n)
    return f"Am apasat {a}" + (f" de {n} ori" if n > 1 else "") + "."


def pune_pe_youtube(cautare: str) -> str:
    """Cauta pe YouTube si porneste DIRECT primul clip (melodie, video). Foloseste cand Stefan vrea sa asculte/vada ceva pe YouTube."""
    import re as _re
    try:
        html = requests.get("https://www.youtube.com/results", params={"search_query": cautare},
                            headers=dict(UA, **{"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}), timeout=12).text
        m = _re.search(r'"videoId":"([\w-]{11})"', html)
        t = _re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}', html)
    except Exception:
        m = t = None
    if not m:
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(cautare))
        return "Nu am putut alege un clip, am deschis doar rezultatele cautarii."
    webbrowser.open(f"https://www.youtube.com/watch?v={m.group(1)}&autoplay=1")
    return "Am pornit pe YouTube: " + (t.group(1) if t else cautare)


def pune_pe_spotify(cautare: str) -> str:
    """Deschide in aplicatia Spotify melodia/artistul cautat. Daca nu porneste singura, foloseste apoi control_media('play_pauza')."""
    import re as _re
    track = None
    try:
        res = cauta_pe_internet(f"site:open.spotify.com/track {cautare}")
        m = _re.search(r"open\.spotify\.com/(?:intl-\w+/)?track/([A-Za-z0-9]{22})", res)
        track = m.group(1) if m else None
    except Exception:
        pass
    if track:
        os.startfile(f"spotify:track:{track}")
        return "Am deschis melodia in Spotify. Daca nu a pornit, apasa play (control_media play_pauza)."
    os.startfile("spotify:search:" + urllib.parse.quote(cautare))
    return "Am deschis cautarea in Spotify; melodia trebuie aleasa din lista."


# ======================= WHATSAPP =======================
CONTACTS = os.path.join(ROOT, "data", "contacte.txt")


def _contacts():
    out = {}
    if os.path.exists(CONTACTS):
        with open(CONTACTS, encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    out[k.strip().lower()] = "".join(c for c in v if c.isdigit() or c == "+")
    return out


def adauga_contact(nume: str, telefon: str) -> str:
    """Salveaza un contact pentru WhatsApp (nume si numar de telefon, ex. 'Mama', '0712345678')."""
    tel = "".join(c for c in telefon if c.isdigit() or c == "+")
    if tel.startswith("07"):
        tel = "+4" + tel
    if len(tel.strip("+")) < 9:
        return "Numarul nu pare valid."
    os.makedirs(os.path.dirname(CONTACTS), exist_ok=True)
    with open(CONTACTS, "a", encoding="utf-8") as f:
        f.write(f"{nume.strip()} = {tel}\n")
    return f"Am salvat contactul {nume} ({tel})."


def lista_contacte() -> str:
    """Arata contactele WhatsApp salvate."""
    c = _contacts()
    return ", ".join(f"{k}: {v}" for k, v in c.items()) or "Nu exista contacte salvate."


def _focus_window(fragment):
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if fragment.lower() in buf.value.lower():
                found.append(hwnd)
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    if found:
        user32.ShowWindow(found[0], 9)
        user32.SetForegroundWindow(found[0])
        return True
    return False


def trimite_whatsapp(contact: str, mesaj: str, confirmat: bool = False) -> str:
    """Trimite un mesaj pe WhatsApp unui contact salvat.
    IMPORTANT: apeleaza intai cu confirmat=False, citeste-i lui Stefan destinatarul si mesajul,
    si apeleaza cu confirmat=True DOAR dupa ce Stefan a spus clar 'da'."""
    c = _contacts()
    key = contact.strip().lower()
    match = c.get(key) or next((v for k, v in c.items() if key in k or k in key), None)
    if not match:
        names = difflib.get_close_matches(key, list(c), n=1, cutoff=0.6)
        match = c.get(names[0]) if names else None
    if not match:
        return f"Nu am contactul '{contact}'. Spune-i lui Stefan sa-l salveze (nume si numar)."
    if not confirmat:
        return f"CONFIRMARE NECESARA: mesaj catre {contact} ({match}): '{mesaj}'. Intreaba-l pe Stefan daca il trimiti."
    phone = match.lstrip("+")
    os.startfile(f"whatsapp://send?phone={phone}&text={urllib.parse.quote(mesaj)}")
    import time as _t
    for _ in range(12):
        _t.sleep(0.7)
        if _focus_window("WhatsApp"):
            break
    _t.sleep(1.5)
    _press(0x0D)  # Enter = trimite
    return f"Am trimis pe WhatsApp catre {contact}."


# ======================= GMAIL =======================
def _gmail_creds():
    from dotenv import dotenv_values
    v = dotenv_values(os.path.join(ROOT, "config", "setari.env"))
    return (v.get("GMAIL_ADRESA") or "").strip(), (v.get("GMAIL_PAROLA_APP") or "").replace(" ", "").strip()


def citeste_mailuri(cate: int = 5, doar_necitite: bool = True) -> str:
    """Citeste ultimele mailuri din Gmail (expeditor, subiect, inceputul textului)."""
    import email
    import imaplib
    from email.header import decode_header, make_header
    user, pw = _gmail_creds()
    if not user or not pw:
        return "Gmail nu e configurat. Stefan trebuie sa puna adresa si parola de aplicatie in panoul de control."
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(user, pw)
        M.select("INBOX", readonly=True)
        _, data = M.search(None, "UNSEEN" if doar_necitite else "ALL")
        ids = data[0].split()[-max(1, min(int(cate), 15)):][::-1]
        if not ids:
            M.logout()
            return "Nu ai mailuri necitite." if doar_necitite else "Inbox gol."
        out = []
        for i in ids:
            _, msg = M.fetch(i, "(BODY.PEEK[])")
            m = email.message_from_bytes(msg[0][1])
            frm = str(make_header(decode_header(m.get("From", ""))))
            sub = str(make_header(decode_header(m.get("Subject", ""))))
            body = ""
            for part in (m.walk() if m.is_multipart() else [m]):
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
            out.append(f"- De la {frm} | {sub} | {' '.join(body.split())[:300]}")
        M.logout()
        return "\n".join(out)
    except Exception as e:
        return f"Nu am putut citi mailurile: {e}"


def trimite_mail(catre: str, subiect: str, text: str, confirmat: bool = False) -> str:
    """Trimite un email din Gmail-ul lui Stefan.
    IMPORTANT: apeleaza intai cu confirmat=False, citeste-i destinatarul, subiectul si textul,
    si apeleaza cu confirmat=True DOAR dupa ce Stefan a spus clar 'da'."""
    import smtplib
    from email.mime.text import MIMEText
    user, pw = _gmail_creds()
    if not user or not pw:
        return "Gmail nu e configurat. Stefan trebuie sa puna adresa si parola de aplicatie in panoul de control."
    if "@" not in catre:
        return "Am nevoie de adresa completa de email a destinatarului."
    if not confirmat:
        return f"CONFIRMARE NECESARA: mail catre {catre}, subiect '{subiect}', text: '{text}'. Intreaba-l pe Stefan daca il trimiti."
    try:
        msg = MIMEText(text, "plain", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subiect, user, catre
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(user, pw)
            s.send_message(msg)
        return f"Mail trimis catre {catre}."
    except Exception as e:
        return f"Mailul nu a putut fi trimis: {e}"


# ======================= LEAGUE OF LEGENDS =======================
_lol_auto = {"on": False}


def _lcu():
    import base64
    import re as _re
    import subprocess as _sp
    cmd = _sp.run(["powershell", "-NoProfile", "-Command",
                   "(Get-CimInstance Win32_Process -Filter \"Name='LeagueClientUx.exe'\").CommandLine"],
                  capture_output=True, text=True, creationflags=0x08000000).stdout
    port = _re.search(r"--app-port=(\d+)", cmd or "")
    tok = _re.search(r"--remoting-auth-token=([\w-]+)", cmd or "")
    if not (port and tok):
        return None
    auth = base64.b64encode(f"riot:{tok.group(1)}".encode()).decode()
    return f"https://127.0.0.1:{port.group(1)}", {"Authorization": f"Basic {auth}"}


def _lcu_req(method, path, body=None):
    import urllib3
    urllib3.disable_warnings()
    c = _lcu()
    if not c:
        return None
    return requests.request(method, c[0] + path, headers=c[1], json=body, verify=False, timeout=5)


_PHASES = {"None": "in meniu", "Lobby": "in lobby", "Matchmaking": "in coada, cauta meci",
           "ReadyCheck": "meci gasit, asteapta acceptare", "ChampSelect": "in champ select",
           "InProgress": "in joc", "WaitingForStats": "asteapta statisticile", "EndOfGame": "meciul s-a terminat"}


def lol_status() -> str:
    """Spune in ce stare e League of Legends (meniu, coada, champ select, in joc) si contul conectat."""
    r = _lcu_req("GET", "/lol-gameflow/v1/gameflow-phase")
    if r is None:
        return "Clientul League of Legends nu e deschis."
    phase = r.json() if r.ok else "?"
    s = _lcu_req("GET", "/lol-summoner/v1/current-summoner")
    who = ""
    if s is not None and s.ok:
        j = s.json()
        who = f" Cont: {j.get('gameName') or j.get('displayName')}, nivel {j.get('summonerLevel')}."
    return f"League: {_PHASES.get(phase, phase)}.{who} Acceptare automata: {'pornita' if _lol_auto['on'] else 'oprita'}."


def lol_accepta_automat(pornit: bool) -> str:
    """Porneste/opreste acceptarea automata a meciului in League of Legends (cand se gaseste meciul, il accepta singur)."""
    _lol_auto["on"] = bool(pornit)
    if pornit and not _lol_auto.get("thread"):
        def loop():
            import time as _t
            while True:
                if _lol_auto["on"]:
                    try:
                        r = _lcu_req("GET", "/lol-gameflow/v1/gameflow-phase")
                        if r is not None and r.ok and r.json() == "ReadyCheck":
                            _lcu_req("POST", "/lol-matchmaking/v1/ready-check/accept")
                            announce("St\u0103p\u00e2ne, meciul a fost g\u0103sit \u0219i acceptat.")
                            _t.sleep(10)
                    except Exception:
                        pass
                _t.sleep(1.5)
        th = threading.Thread(target=loop, daemon=True)
        th.start()
        _lol_auto["thread"] = th
    return "Acceptarea automata e pornita." if pornit else "Acceptarea automata e oprita."


def _riot_exe():
    import json as _j
    cands = []
    try:
        with open(os.path.join(os.getenv("PROGRAMDATA", r"C:\ProgramData"), "Riot Games", "RiotClientInstalls.json"), encoding="utf-8") as f:
            d = _j.load(f)
        cands += [d.get("rc_default"), d.get("rc_live")]
    except Exception:
        pass
    for drv in "CDE":
        cands.append(drv + r":\Riot Games\Riot Client\RiotClientServices.exe")
    return next((c for c in cands if c and os.path.exists(c)), None)


def deschide_league() -> str:
    """Porneste League of Legends prin Riot Client: descarca singur update-ul daca exista si deschide jocul.
    Jarvis anunta cu voce cand clientul e gata. Foloseste-l pentru "deschide lolu/league"."""
    import subprocess as _sp
    if _lcu():
        return "League of Legends e deja deschis si gata."
    exe = _riot_exe()
    if not exe:
        return deschide_aplicatie("league of legends")
    _sp.Popen([exe, "--launch-product=league_of_legends", "--launch-patchline=live"], creationflags=0x08000000)

    def wait_ready():
        import time as _t
        start = _t.time()
        while _t.time() - start < 45 * 60:
            _t.sleep(10)
            try:
                if _lcu():
                    _t.sleep(8)
                    announce("St\u0103p\u00e2ne, League of Legends e actualizat \u0219i deschis. Pute\u021bi juca.")
                    return
            except Exception:
                pass
        announce("St\u0103p\u00e2ne, League nu s-a deschis \u00een 45 de minute. Verifica\u021bi Riot Client.")
    threading.Thread(target=wait_ready, daemon=True).start()
    return ("Pornesc League prin Riot Client. Daca are update il descarca singur si anunt cu voce cand e gata. "
            "Daca Riot cere logare, Stefan trebuie sa se logheze singur.")



_QUEUES = {"normal": 400, "draft": 400, "ranked": 420, "solo": 420, "flex": 440, "aram": 450,
           "swiftplay": 480, "rapid": 480, "quickplay": 490, "blind": 430}


def lol_joaca(mod: str = "normal", cauta_meci: bool = True) -> str:
    """League of Legends: apasa Play - face lobby pentru modul cerut si (optional) intra in coada.
    mod: normal, ranked, flex, aram, swiftplay, quickplay sau blind. cauta_meci=True porneste cautarea."""
    r = _lcu_req("GET", "/lol-gameflow/v1/gameflow-phase")
    if r is None:
        return "Clientul League of Legends nu e deschis sau inca se incarca."
    phase = r.json() if r.ok else "?"
    if phase in ("Matchmaking", "ReadyCheck", "ChampSelect", "InProgress"):
        return f"Nu pot acum: League e deja {_PHASES.get(phase, phase)}."
    q = _QUEUES.get((mod or "normal").lower().strip(), 400)
    lob = _lcu_req("POST", "/lol-lobby/v2/lobby", {"queueId": q})
    if lob is None or not lob.ok:
        return f"Nu am putut face lobby-ul ({lob.status_code if lob is not None else 'fara raspuns'})."
    if not cauta_meci:
        return f"Lobby facut pentru {mod}."
    import time as _t
    _t.sleep(1)
    s = _lcu_req("POST", "/lol-lobby/v2/lobby/matchmaking/search")
    if s is None or not s.ok:
        return f"Lobby-ul e facut, dar cautarea nu a pornit ({s.status_code if s is not None else 'fara raspuns'}). Poate trebuie aleasa pozitia in lobby."
    return f"Am intrat in coada pentru {mod}."


def lol_opreste_cautarea() -> str:
    """League of Legends: iese din coada (opreste cautarea de meci)."""
    r = _lcu_req("DELETE", "/lol-lobby/v2/lobby/matchmaking/search")
    if r is None:
        return "Clientul League of Legends nu e deschis."
    return "Am oprit cautarea." if r.ok else f"Nu am putut opri cautarea ({r.status_code})."


ALL_TOOLS = [ora_si_data, cauta_pe_internet, citeste_pagina, deschide_site,
             deschide_aplicatie, seteaza_timer, noteaza, citeste_notitele,
             control_media, pune_pe_youtube, pune_pe_spotify,
             adauga_contact, lista_contacte, trimite_whatsapp,
             citeste_mailuri, trimite_mail,
             lol_status, lol_accepta_automat, deschide_league, lol_joaca, lol_opreste_cautarea]