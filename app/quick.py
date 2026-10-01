"""Comenzi rapide: se executa direct pe laptop, fara sa mai intrebe Google.
Merg instant si chiar daca serverele Gemini sunt aglomerate sau s-a atins limita gratuita."""
import re
import unicodedata

import hands

ST = "stăpâne"


def _norm(text):
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s'-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


LOL = r"(?:lol\w*|league(?: of legends?)?|liga|ligu)"
OPEN = r"(?:deschide(?:-mi|mi)?|porneste|intra (?:pe|in)|open|start|launch|baga)"
MEDIA = [
    (r"(?:pune |da )?pauza|opreste muzica|stop muzica|pause", "play_pauza", 1, "Pauză, " + ST + "."),
    (r"(?:da )?play|continua(?: muzica)?|resume|porneste muzica", "play_pauza", 1, "Am pornit redarea, " + ST + "."),
    (r"(?:urmatoarea|next|skip|sari)(?: melodie| piesa)?", "urmatoarea", 1, "Următoarea, " + ST + "."),
    (r"(?:anterioara|inapoi|previous|back)(?: melodie| piesa)?", "anterioara", 1, "Melodia anterioară, " + ST + "."),
    (r"(?:da )?mai tare|volum(?:ul)? (?:mai )?sus|volume up|louder", "volum_sus", 6, "Am dat mai tare, " + ST + "."),
    (r"(?:da )?mai incet|volum(?:ul)? (?:mai )?jos|volume down|quieter", "volum_jos", 6, "Am dat mai încet, " + ST + "."),
    (r"(?:da )?mute|mut|fara sunet", "mut", 1, "Am oprit sunetul, " + ST + "."),
]
VAGUE = {"melodie", "o melodie", "muzica", "ceva", "ceva muzica", "o piesa", "piesa", "music", "a song", "something"}


def _one(p):
    """Intoarce raspunsul pentru o singura comanda, sau None daca nu o stie."""
    p = re.sub(r"^(?:te rog |hai |please |si |apoi )+", "", p).strip()
    p = re.sub(r" (?:te rog|please)$", "", p).strip()
    if not p:
        return None
    # League of Legends
    if re.fullmatch(rf"(?:{OPEN} )?{LOL}", p):
        r = hands.deschide_league()
        if "deja deschis" in r:
            return f"League of Legends e deja deschis, {ST}."
        if r.startswith("Pornesc"):
            return f"Pornesc League of Legends, {ST}. Dacă are update îl descarcă singur și vă anunț când e gata."
        return r
    if re.fullmatch(rf"(?:da|dai|apasa) (?:play|start)(?: (?:la|in|pe) {LOL})?|cauta (?:un )?meci|intra in coada|find (?:a )?match", p) and (re.search(LOL, p) or "meci" in p or "coada" in p or "match" in p or hands._lcu()):
        r = hands.lol_joaca("normal", True)
        return r.replace("Am intrat in coada pentru normal.", f"Am intrat în coadă, {ST}.")
    # Spotify / YouTube
    m = re.fullmatch(r"(?:pune|pune-mi|baga|da drumul la|da play la|canta|play)(?: mi)? (?:melodia |piesa |cantecul )?(.+?) (?:pe|on|in) (spotify|youtube)", p)
    if m:
        q, where = m.group(1).strip(), m.group(2)
        if q in VAGUE:
            if where == "spotify":
                hands.deschide_aplicatie("spotify")
                hands.control_media("play_pauza")
                return f"Am deschis Spotify și am pornit muzica, {ST}."
            hands.deschide_site("youtube.com")
            return f"Am deschis YouTube, {ST}."
        if where == "spotify":
            hands.pune_pe_spotify(q)
            return f"Pun „{q}” pe Spotify, {ST}."
        hands.pune_pe_youtube(q)
        return f"Pun „{q}” pe YouTube, {ST}."
    # Taste media
    for pat, act, n, reply in MEDIA:
        if re.fullmatch(pat, p):
            hands.control_media(act, n)
            return reply
    # Ora si data
    if re.fullmatch(r"(?:cat e ceasul|ce ora e|ce ora este|cat e ora|ce zi e azi|ce data e azi|what time is it)", p):
        return f"Este {hands.ora_si_data()}, {ST}."
    # Deschide o aplicatie (doar daca o gasim instalata)
    m = re.fullmatch(rf"{OPEN} (.+)", p)
    name = m.group(1) if m else (p if p in ("spotify", "discord", "steam", "chrome", "whatsapp") else None)
    if name and "." not in name and len(name.split()) <= 3:
        r = hands.deschide_aplicatie(name)
        if r.startswith("Am deschis"):
            return r.replace("Am deschis", "Am deschis").rstrip(".") + f", {ST}."
    return None


def handle(text):
    """Executa pe loc partile simple ale comenzii (deschide, pune muzica, pauza, ora).
    Intoarce (raspuns_local, rest): rest e partea pe care trebuie s-o rezolve creierul Gemini ("" daca nu mai e nimic)."""
    t = _norm(text)
    parts = [x for x in re.split(r" (?:si|and|apoi|dupa aceea) ", t) if x.strip()]
    if not parts or len(parts) > 3:
        return None, text
    replies, rest = [], []
    for i, part in enumerate(parts):
        r = _one(part) if not rest else None
        if r is None:
            rest = parts[i:]
            break
        replies.append(r)
    if not replies:
        return None, text
    return " ".join(replies), " si ".join(rest)