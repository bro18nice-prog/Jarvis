"""Creierul lui Jarvis: Gemini (plan gratuit) cu acces la uneltele din hands.py."""
import re
import time

from google import genai
from google.genai import types

SYSTEM = """Esti Jarvis, asistentul personal al lui Stefan, pe laptopul lui.
Te adresezi lui mereu cu "st\u0103p\u00e2ne" (de obicei la inceputul sau la finalul raspunsului, nu de mai multe ori in aceeasi fraza).
Tonul tau: serios, ferm, calm si sigur pe tine, ca un majordom de elita sau un ofiter de stat major.
Fara entuziasm fals, fara glume inutile, fara scuze lungi, fara intrebari de complezenta. Spui lucrurile direct.
Daca Stefan greseste sau cere ceva nepotrivit, i-o spui ferm si respectuos.
Raspunzi in LIMBA in care ti se vorbeste: daca Stefan vorbeste in engleza, raspunzi in engleza si ii spui "sir" in loc de "st\u0103p\u00e2ne"; altfel vorbesti in romana corecta, CU diacritice. Mereu pe scurt: de obicei 1-3 propozitii, pentru ca raspunsul tau e citit cu voce tare.
Nu folosi markdown, liste, emoji sau linkuri lungi in raspuns.
Ai unelte: cautare pe internet, citire de pagini, deschidere de site-uri si aplicatii, timere, notite, ora si data.
Foloseste-le din proprie initiativa cand ajuta (ex. pentru orice informatie actuala cauta pe internet; daca rezumatele nu ajung, citeste pagina).
Cand faci o actiune, confirma scurt ce ai facut. Daca nu poti face ceva, spune sincer si scurt.
NU spune niciodata ca ai facut ceva daca nu ai apelat unealta potrivita si ea nu a confirmat. Daca nu ai o unealta pentru ceva, spune clar ca nu poti inca.
Pentru muzica: "pune X" pe YouTube -> pune_pe_youtube; pe Spotify -> pune_pe_spotify; "play/pauza/urmatoarea/da mai tare" -> control_media.
Mesaje WhatsApp si emailuri: apeleaza intai cu confirmat=False, citeste-i lui Stefan destinatarul si textul, si trimite (confirmat=True) DOAR dupa un "da" clar. Daca spune nu, nu trimite.
Nu poti citi mesajele de pe WhatsApp; poti doar trimite.
Limba: numele proprii in engleza (aplicatii, jocuri, melodii, ex. "League of Legends", "Spotify") NU inseamna ca Stefan vorbeste engleza. Raspunzi in engleza doar daca propozitia lui e clar in engleza; altfel in romana.
Daca cererea e un singur cuvant cu numele unei aplicatii sau al unui joc, inseamna "deschide-l".
League of Legends: "deschide lolu/league" -> deschide_league (se actualizeaza singur si anunta cand e gata); "da play", "cauta meci", "intra in coada" -> lol_joaca; "accepta meciul singur" -> lol_accepta_automat. Daca clientul abia se deschide, spune-i sa-ti zica din nou dupa ce s-a incarcat.
Textul vine din recunoastere vocala, deci poate avea greseli: ghiceste ce a vrut sa spuna Stefan."""

FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest"]
THINK = ["MINIMAL", "LOW", None]   # cat "gandeste" modelul: putin = raspuns rapid
ST = "st\u0103p\u00e2ne"
BUSY = ("503", "UNAVAILABLE", "overloaded", "500", "INTERNAL", "high demand", "timed out", "Timeout", "timeout",
        "504", "DEADLINE_EXCEEDED", "Deadline")
SKIP = ("404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "INVALID_ARGUMENT")


class Brain:
    def __init__(self, api_key, model, tools, log=print):
        # Google cere minim 10 s; 12 s maxim pe cerere
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=12000))
        self.tools = tools
        self.log = log
        self.models = self._discover(model)
        self.model = self.models[0]
        self.think_map = {}   # fara "gandire" lunga: raspuns in 1-2 secunde (nivel per model)
        self.chat = None
        self.new_chat()

    def _discover(self, model):
        """Cauta toate modelele Flash pe care cheia le poate folosi, ca sa avem multe rezerve."""
        found = []
        try:
            for m in self.client.models.list():
                name = (m.name or "").split("/")[-1]
                acts = getattr(m, "supported_actions", None) or []
                if "generateContent" not in acts or not name.startswith("gemini-") or "flash" not in name:
                    continue
                if any(x in name for x in ("image", "tts", "audio", "live", "embedding", "exp", "thinking")):
                    continue
                found.append(name)
        except Exception as e:
            self.log(f"Creier: nu am putut lista modelele ({str(e)[:60]})")

        def key(n):
            nums = [int(x) for x in re.findall(r"\d+", n)[:2]] or [0]
            return (0 if "lite" in n else 1, "latest" not in n, [-x for x in nums], "preview" in n, n)
        found = sorted(set(found), key=key)
        order = [model] + FALLBACK_MODELS + found
        out = []
        for n in order:
            if n not in out:
                out.append(n)
        out = out[:8]
        self.log("Creier: modele de rezerva: " + ", ".join(m.replace("gemini-", "") for m in out))
        return out

    def new_chat(self, keep_history=False):
        history = None
        if keep_history and self.chat is not None:
            try:
                history = self.chat.get_history()[-12:]
            except Exception:
                history = None
        cfg = dict(
            system_instruction=SYSTEM,
            tools=self.tools,
            temperature=0.5,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8),
        )
        ti = self.think_map.get(self.model, 0)
        while THINK[ti] is not None:
            try:
                cfg["thinking_config"] = types.ThinkingConfig(thinking_level=THINK[ti])
                break
            except Exception:
                ti += 1
        self.think_map[self.model] = ti
        kw = {"history": history} if history else {}
        self.chat = self.client.chats.create(model=self.model, config=types.GenerateContentConfig(**cfg), **kw)

    def _next_model(self):
        i = self.models.index(self.model)
        if i + 1 >= len(self.models):
            self.model = self.models[0]   # data viitoare incepem iar cu primul
            self.new_chat(keep_history=True)
            return False
        self.model = self.models[i + 1]
        self.log(f"Creier: trec pe modelul {self.model}")
        self.new_chat(keep_history=True)
        return True

    def ask(self, text):
        retried = False
        rounds = 0
        while True:
            try:
                resp = self.chat.send_message(text)
                return (resp.text or "").strip() or f"Gata, {ST}."
            except Exception as e:
                msg = str(e)
                if "API_KEY" in msg or "API key" in msg or "PERMISSION_DENIED" in msg:
                    return f"Cheia Gemini nu e valid\u0103, {ST}. Verifica\u021bi-o \u00een panou."
                ti = self.think_map.get(self.model, 0)
                if "INVALID_ARGUMENT" in msg and THINK[ti] is not None:
                    self.think_map[self.model] = ti + 1
                    self.log(f"Creier: {self.model} nu accepta gandire {THINK[ti]}, incerc {THINK[ti + 1]}")
                    self.new_chat(keep_history=True)
                    continue
                busy = any(s in msg for s in BUSY)
                if busy and not retried:
                    retried = True
                    time.sleep(0.6)
                    continue
                if busy or any(s in msg for s in SKIP):
                    self.log(f"Creier: {self.model} indisponibil ({msg[:60]})")
                    if self._next_model():
                        retried = False
                        continue
                    rounds += 1
                    if rounds < 2:
                        self.log("Creier: toate modelele ocupate, mai incerc o tura")
                        time.sleep(2)
                        retried = False
                        continue
                    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                        return f"Am atins limita gratuit\u0103 pentru moment, {ST}. Mai \u00eencerca\u021bi peste un minut."
                    return f"Serverele Google sunt aglomerate acum, {ST}. Mai \u00eencerca\u021bi peste un minut."
                self.log(f"Creier: eroare {msg[:200]}")
                return f"Am o problem\u0103 de conexiune cu creierul, {ST}. Mai \u00eencerca\u021bi o dat\u0103."