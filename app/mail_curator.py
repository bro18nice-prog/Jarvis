"""Curatenie in Gmail, facuta LOCAL (nimic nu se trimite la Gemini sau in alta parte).

Reguli de siguranta:
  * Scanarea doar CITESTE antetele (expeditor, subiect, data). Nu citeste continutul mailurilor.
  * Nimic nu se sterge fara aprobarea lui Stefan, mail cu mail, din pagina /mail a panoului.
  * "Stergerea" inseamna mutare in Cosul Gmail (se poate recupera 30 de zile). Niciodata stergere definitiva.
  * Mailurile cu stea, marcate importante, cu atasamente, de la expeditori protejati sau cu cuvinte
    sensibile (facturi, banca, parole, contracte, scoala...) NU apar niciodata in lista de curatenie.
"""
import email
import imaplib
import json
import os
import re
import time
import uuid
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, "config", "setari.env")
DIR = os.path.join(ROOT, "data", "mail")
PROTECTED_FILE = os.path.join(DIR, "expeditori-protejati.txt")
LAST_FILE = os.path.join(DIR, "ultima-scanare.json")
HISTORY_FILE = os.path.join(DIR, "istoric.jsonl")

MAX_PER_GROUP = 400
SENSITIVE = [
    "factur", "invoice", "chitant", "receipt", "plata", "payment", "banca", "bank", "transfer", "extras",
    "parola", "password", "cod de", "verification", "verificare", "securitate", "security", "autentificare",
    "login", "2fa", "otp", "cont ", "account", "contract", "anaf", "impozit", "taxe", "primari", "politie",
    "universit", "facultat", "examen", "licenta", "bursa", "scoal", "medic", "spital", "programare",
    "bilet", "ticket", "rezervare", "booking", "zbor", "flight", "comanda nr", "order #", "garantie",
    "hostico", "domeniu", "domain", "abonament expira", "reinnoire", "renewal", "proforma",
]
CATEGORIES = [
    ("reclame", "Reclame și promoții", '"category:promotions -is:starred -is:important"'),
    ("social", "Rețele sociale", '"category:social -is:starred -is:important"'),
    ("forumuri", "Forumuri și grupuri", '"category:forums -is:starred -is:important"'),
]


def _env():
    vals = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*([A-Z_]+)\s*=(.*)$", line)
                if m:
                    vals[m.group(1)] = m.group(2).strip()
    return vals


def configured():
    v = _env()
    return bool(v.get("GMAIL_ADRESA")) and bool((v.get("GMAIL_PAROLA_APP") or "").replace(" ", ""))


def _connect():
    v = _env()
    user = (v.get("GMAIL_ADRESA") or "").strip()
    pw = (v.get("GMAIL_PAROLA_APP") or "").replace(" ", "").strip()
    if not user or not pw:
        raise RuntimeError("Gmail nu e configurat: pune adresa si parola de aplicatie in panou.")
    M = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
    M.login(user, pw)
    return M


def _dec(v):
    try:
        return str(make_header(decode_header(v or ""))).strip()
    except Exception:
        return (v or "").strip()


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def protected_senders():
    os.makedirs(DIR, exist_ok=True)
    if not os.path.exists(PROTECTED_FILE):
        with open(PROTECTED_FILE, "w", encoding="utf-8") as f:
            f.write("# Expeditori care NU apar niciodata in lista de curatenie (cate unul pe linie).\n"
                    "# Poti scrie adresa completa (ana@gmail.com) sau doar domeniul (@banca.ro).\n")
    out = []
    with open(PROTECTED_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def protect_sender(addr):
    addr = addr.strip().lower()
    if addr and addr not in protected_senders():
        with open(PROTECTED_FILE, "a", encoding="utf-8") as f:
            f.write(addr + "\n")


def _is_protected(addr, subject, ctype, prot):
    a = (addr or "").lower()
    if any(p == a or (p.startswith("@") and a.endswith(p)) for p in prot):
        return "expeditor protejat"
    if (ctype or "").lower().startswith("multipart/mixed"):
        return "are atasament"
    s = _norm(subject)
    for w in SENSITIVE:
        if w in s:
            return f"cuvant sensibil: {w.strip()}"
    return None


_FETCH = "(X-GM-MSGID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE CONTENT-TYPE LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST)])"


def _fetch_headers(M, uids):
    """Intoarce lista de dictionare cu antetele mailurilor (fara continut)."""
    out = []
    for i in range(0, len(uids), 100):
        chunk = b",".join(uids[i:i + 100])
        typ, data = M.uid("FETCH", chunk, _FETCH)
        if typ != "OK":
            continue
        for item in data:
            if not isinstance(item, tuple):
                continue
            meta = item[0].decode("utf-8", "replace")
            gm = re.search(r"X-GM-MSGID (\d+)", meta)
            flags = re.search(r"FLAGS \(([^)]*)\)", meta)
            h = email.message_from_bytes(item[1])
            name, addr = parseaddr(_dec(h.get("From")))
            try:
                dt = parsedate_to_datetime(h.get("Date"))
                ts = dt.timestamp()
                date = dt.strftime("%d.%m.%Y")
            except Exception:
                ts, date = 0, ""
            out.append({
                "id": gm.group(1) if gm else "",
                "name": name or addr, "addr": addr.lower(),
                "subject": _dec(h.get("Subject")) or "(fara subiect)",
                "date": date, "ts": ts,
                "seen": bool(flags and "\\Seen" in flags.group(1)),
                "starred": bool(flags and "\\Flagged" in flags.group(1)),
                "ctype": h.get("Content-Type", ""),
                "unsub": _dec(h.get("List-Unsubscribe")),
                "oneclick": "one-click" in (h.get("List-Unsubscribe-Post") or "").lower(),
            })
    return out


def _search(M, raw):
    typ, data = M.uid("SEARCH", None, "X-GM-RAW", raw)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _spam_folder(M):
    typ, data = M.list()
    for line in data or []:
        s = line.decode("utf-8", "replace")
        if "\\Junk" in s:
            m = re.search(r'"([^"]+)"\s*$', s) or re.search(r"(\S+)\s*$", s)
            return m.group(1) if m else None
    return None


def _group(msgs):
    groups = {}
    for m in msgs:
        g = groups.setdefault(m["addr"], {"addr": m["addr"], "name": m["name"], "msgs": []})
        g["msgs"].append({k: m[k] for k in ("id", "subject", "date", "seen")})
    lst = sorted(groups.values(), key=lambda g: -len(g["msgs"]))
    for g in lst:
        g["count"] = len(g["msgs"])
    return lst


def scan(log=print):
    """Scaneaza si pregateste propunerea de curatenie. Nu modifica nimic in Gmail."""
    os.makedirs(DIR, exist_ok=True)
    prot = protected_senders()
    M = _connect()
    try:
        M.select("INBOX", readonly=True)
        result = {"id": uuid.uuid4().hex[:10], "time": time.strftime("%d.%m.%Y %H:%M"), "groups": [],
                  "skipped": {}, "important": [], "subscriptions": []}
        for key, label, raw in CATEGORIES:
            uids = _search(M, raw)[-MAX_PER_GROUP:]
            msgs = _fetch_headers(M, uids) if uids else []
            keep = []
            for m in msgs:
                why = "are stea" if m["starred"] else _is_protected(m["addr"], m["subject"], m["ctype"], prot)
                if why:
                    result["skipped"][why] = result["skipped"].get(why, 0) + 1
                else:
                    keep.append(m)
            result["groups"].append({"key": key, "label": label, "folder": "INBOX", "senders": _group(keep),
                                     "count": len(keep)})
        # abonamente: tot ce are buton de dezabonare in ultimele 6 luni
        uids = _search(M, '"newer_than:180d -is:starred"')[-1500:]
        subs = {}
        for m in _fetch_headers(M, uids) if uids else []:
            if not m["unsub"]:
                continue
            s = subs.setdefault(m["addr"], {"addr": m["addr"], "name": m["name"], "count": 0, "unread": 0,
                                            "last": "", "last_ts": 0, "subject": "", "oneclick": False, "link": ""})
            s["count"] += 1
            s["unread"] += 0 if m["seen"] else 1
            if m["ts"] >= s["last_ts"]:
                s["last_ts"], s["last"], s["subject"] = m["ts"], m["date"], m["subject"]
                s["oneclick"] = m["oneclick"]
                links = re.findall(r"<([^>]+)>", m["unsub"])
                https = [x for x in links if x.lower().startswith("https://")]
                s["link"] = (https or links or [""])[0]
        result["subscriptions"] = sorted(subs.values(), key=lambda s: (-s["count"], -s["unread"]))
        # necitite importante din ultimele 3 zile: doar expeditor si subiect, ca sa stii ce ai
        uids = _search(M, '"in:inbox is:unread newer_than:3d (category:primary OR is:important)"')[-30:]
        imp = _fetch_headers(M, uids) if uids else []
        result["important"] = [{"name": m["name"], "addr": m["addr"], "subject": m["subject"], "date": m["date"]}
                               for m in sorted(imp, key=lambda m: -m["ts"])]
        # spam
        spam = _spam_folder(M)
        if spam:
            try:
                M.select(f'"{spam}"', readonly=True)
                typ, data = M.uid("SEARCH", None, "ALL")
                uids = (data[0].split() if typ == "OK" and data and data[0] else [])[-MAX_PER_GROUP:]
                msgs = _fetch_headers(M, uids) if uids else []
                result["groups"].append({"key": "spam", "label": "Spam", "folder": spam,
                                         "senders": _group(msgs), "count": len(msgs)})
            except Exception as e:
                log(f"Mail: nu am putut citi Spam ({e})")
    finally:
        try:
            M.logout()
        except Exception:
            pass
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return result


def last_scan():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def summary(res):
    """Rezumat scurt, de citit cu voce (fara subiecte)."""
    if not res:
        return "Nu am facut inca nicio scanare."
    parts = []
    for g in res["groups"]:
        if g["count"]:
            parts.append(f"{g['count']} la {g['label'].lower()}")
    junk = sum(g["count"] for g in res["groups"])
    s = f"Am pregatit lista de curatenie: {junk} mailuri"
    s += (" (" + ", ".join(parts) + ")") if parts else ""
    s += f". Ai {len(res['subscriptions'])} abonamente si {len(res['important'])} mailuri importante necitite."
    s += " Nu am sters nimic. Verifica lista in panou si aproba ce vrei sa mut in Cos."
    return s


def _allowed_ids(scan_id):
    res = last_scan()
    if not res or res.get("id") != scan_id:
        raise RuntimeError("Lista s-a schimbat intre timp. Reincarca pagina si verifica din nou.")
    allowed = {}
    for g in res["groups"]:
        for s in g["senders"]:
            for m in s["msgs"]:
                allowed[m["id"]] = (g["folder"], s["addr"], m["subject"])
    return allowed


def trash(scan_id, ids, log=print):
    """Muta in Cos DOAR mailurile aprobate, si doar daca erau in lista aratata lui Stefan."""
    allowed = _allowed_ids(scan_id)
    ids = [i for i in dict.fromkeys(ids) if i in allowed]
    if not ids:
        return {"moved": 0, "failed": 0}
    by_folder = {}
    for i in ids:
        by_folder.setdefault(allowed[i][0], []).append(i)
    moved, failed = 0, 0
    M = _connect()
    try:
        for folder, fids in by_folder.items():
            M.select("INBOX" if folder == "INBOX" else f'"{folder}"')
            for gid in fids:
                typ, data = M.uid("SEARCH", None, "X-GM-MSGID", gid)
                uids = data[0].split() if typ == "OK" and data and data[0] else []
                if not uids:
                    failed += 1
                    continue
                typ, _ = M.uid("STORE", uids[0], "+X-GM-LABELS", "\\Trash")
                if typ == "OK":
                    moved += 1
                else:
                    failed += 1
    finally:
        try:
            M.logout()
        except Exception:
            pass
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%d.%m.%Y %H:%M"), "action": "cos", "moved": moved,
                            "items": [{"from": allowed[i][1], "subject": allowed[i][2]} for i in ids]},
                           ensure_ascii=False) + "\n")
    log(f"Mail: mutate in Cos {moved} mailuri aprobate (esuate: {failed})")
    return {"moved": moved, "failed": failed}


def unsubscribe(addr, log=print):
    """Dezabonare one-click (standardul RFC 8058), doar pentru expeditorul aprobat.
    Daca expeditorul nu are one-click, intoarce linkul ca Stefan sa-l deschida singur."""
    res = last_scan() or {}
    sub = next((s for s in res.get("subscriptions", []) if s["addr"] == addr), None)
    if not sub:
        return {"ok": False, "msg": "Expeditorul nu e in lista de abonamente."}
    link = sub.get("link") or ""
    if sub.get("oneclick") and link.lower().startswith("https://"):
        import urllib.request
        req = urllib.request.Request(link, data=b"List-Unsubscribe=One-Click", method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                ok = 200 <= r.status < 300
        except Exception as e:
            return {"ok": False, "msg": f"Dezabonarea nu a mers ({e}).", "link": link}
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%d.%m.%Y %H:%M"), "action": "dezabonare",
                                "from": addr, "ok": ok}, ensure_ascii=False) + "\n")
        log(f"Mail: dezabonare de la {addr}: {'ok' if ok else 'esuat'}")
        return {"ok": ok, "msg": "Te-am dezabonat." if ok else "Expeditorul a refuzat cererea."}
    return {"ok": False, "manual": True, "link": link,
            "msg": "Expeditorul nu permite dezabonare automata. Deschide linkul si confirma tu."}