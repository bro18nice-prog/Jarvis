# Jarvis

Asistent vocal personal pentru Windows, cu interfață animată, panou de control și conversații în română sau engleză. Recunoaște vocea local cu Whisper, trimite cererile conversaționale către Gemini și execută comenzi prin funcții Python.

Acesta este proiectul Jarvis separat. [Titan](https://github.com/bro18nice-prog/Titan) rămâne proiectul distinct de asistent vocal și integrări smart-home.

## Funcții existente

- Activare prin „Jarvis” sau butonul **VORBEȘTE**; mod de ascultare continuă opțional.
- Comenzi rapide locale pentru aplicații și media; conversații Gemini cu modele de rezervă.
- Recunoaștere vocală prin faster-whisper, cu încercare GPU NVIDIA și revenire pe CPU.
- Voce online Edge TTS, cu Piper și vocea Windows ca alternative.
- Căutare web, citirea paginilor, YouTube, Spotify, timere și notițe.
- Integrări opționale pentru Gmail, contacte WhatsApp și clientul League of Legends.
- Panou pentru pornire/oprire, configurare, jurnal și pornire automată cu Windows.

Proiect personal în dezvoltare. Integrările depind de aplicațiile instalate și de serviciile externe.

## Instalare pe Windows

Ai nevoie de Windows pe 64 de biți, microfon, ieșire audio, internet și o cheie Gemini. Verifică în contul furnizorului modelele disponibile, limitele și costurile aplicabile.

1. Clonează repo-ul sau descarcă și extrage arhiva într-un folder numit `Jarvis`.
2. Rulează `INSTALEAZA.bat`. Instalatorul descarcă uv, Python 3.11, bibliotecile și modelele în folderul proiectului. Prima instalare poate descărca mai mulți GB, inclusiv biblioteci CUDA dacă detectează NVIDIA.
3. Rulează `DESCHIDE-PANOU.bat` și adaugă cheia Gemini în panou. Alternativ, completează `GEMINI_API_KEY` în `config/setari.env`, creat din exemplul inclus.
4. Pornește asistentul din panou. `PORNESTE-JARVIS.bat` îl pornește cu o consolă pentru depanare.

Instalatorul păstrează o configurație existentă. Nu este necesar să rulezi vechile scripturi de actualizare: sursele din `app/` includ deja modificările lor.

Panoul folosește `http://127.0.0.1:8764`, iar interfața asistentului `http://127.0.0.1:8765`. Rulează o singură instanță; panoul presupune portul 8765 pentru asistent.

### Configurare

`config/setari.exemplu.env` documentează opțiunile. Setările personale se păstrează doar în `config/setari.env`:

- `LIMBA=ro`, `en` sau `auto` pentru recunoașterea vocală.
- `WHISPER_MODEL` gol pentru selecție automată; `small` sau `tiny` pentru resurse mai reduse.
- `VOCE_MOTOR=edge` pentru voce online sau `piper` pentru sinteză locală.
- `MODEL_GEMINI` pentru modelul preferat; codul încearcă și alternative disponibile.
- Gmail este opțional și folosește o parolă de aplicație configurată local. Contactele WhatsApp se adaugă în panou sau prin comenzi.

## Structură

| Fișier | Rol |
| --- | --- |
| `app/jarvis.py` | Bucla vocală, activare și serverul interfeței |
| `app/ears.py` | Captură audio și transcriere Whisper |
| `app/brain.py` | Conversația Gemini și apelarea uneltelor |
| `app/voice.py` | Sinteză vocală și redare |
| `app/quick.py` | Interpretarea comenzilor rapide locale |
| `app/hands.py` | Acțiuni, căutare și integrări |
| `app/panou.py` | Panoul de configurare și control |
| `app/ui/` | Interfețele HTML/CSS/JavaScript |
| `scripts/install.ps1` | Instalare și descărcarea modelelor |

## Date și limite

Whisper transcrie local. Cererile care ajung la Gemini și rezultatele uneltelor folosite în conversație sunt trimise serviciului Google. Edge TTS transmite textul de rostit serviciului vocal; Piper sintetizează local. Căutarea, Gmail și celelalte integrări comunică cu serviciile respective.

Cheile, parolele, contactele, notițele, jurnalele și profilurile browserului sunt excluse prin `.gitignore`. Modelele, mediul Python, cache-urile și copiile istorice nu sunt incluse; instalatorul recreează dependențele necesare. Fiecare dependență și model rămâne supus propriei licențe.

Trimiterea mesajelor solicită confirmare în fluxul conversațional; parametrul de confirmare este controlat de model, nu de un mecanism separat de autorizare. Automatizarea WhatsApp folosește focusul ferestrei și tasta Enter, deci trebuie supravegheată. Serverele locale nu au autentificare și nu sunt destinate expunerii pe internet.

## Verificare locală

```powershell
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testele izolează comenzile rapide și prelucrarea textului vocal: nu deschid aplicații, nu trimit mesaje și nu apelează servicii externe. Ele nu înlocuiesc proba cu microfonul sau verificarea integrărilor pe dispozitiv.
