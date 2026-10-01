"""Urechile lui Jarvis: asculta microfonul si transforma vocea in text (Whisper)."""
import glob
import os
import queue
import site
import sys
import time
from collections import deque

import numpy as np
import sounddevice as sd

SR = 16000          # Whisper lucreaza la 16 kHz
BLOCK_SEC = 0.03    # bucati de 30 ms


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def _add_cuda_dlls():
    """Bibliotecile CUDA instalate prin pip (nvidia-cublas/cudnn) trebuie facute vizibile pentru Windows."""
    roots = list(site.getsitepackages()) + [os.path.join(sys.prefix, "Lib", "site-packages")]
    for root in roots:
        for bin_dir in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(bin_dir)
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


class Ears:
    def __init__(self, models_dir, lang="ro", log=print):
        self.lang = lang
        self.log = log
        self.device_info = "?"
        self.last_lang = "ro"
        _add_cuda_dlls()
        from faster_whisper import WhisperModel

        try:
            import ctranslate2
            has_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            has_cuda = False

        forced = os.getenv("WHISPER_MODEL", "").strip()
        attempts = []
        if has_cuda:
            attempts += [("cuda", "float16", forced or "medium"),
                         ("cuda", "int8_float16", forced or "small")]
        attempts += [("cpu", "int8", forced or "small")]

        self.model = None
        for device, compute, size in attempts:
            try:
                model = WhisperModel(size, device=device, compute_type=compute,
                                     download_root=os.path.join(models_dir, "whisper"))
                segs, _ = model.transcribe(np.zeros(SR, dtype=np.float32), language=lang if lang in ("ro", "en") else "ro")
                list(segs)  # forteaza rularea, ca sa vedem acum daca merge
                self.model = model
                self.device_info = f"{size} pe {device.upper()}"
                self.log(f"Urechi: Whisper {self.device_info}")
                break
            except Exception as e:
                self.log(f"Urechi: {size}/{device} nu a mers ({e.__class__.__name__}: {str(e)[:120]}), incerc altceva")
        if self.model is None:
            raise RuntimeError("Nu am putut porni Whisper nici pe placa video, nici pe procesor.")

    def listen(self, stop_event=None, max_seconds=20, silence_end=0.6):
        """Asteapta pana vorbesti, inregistreaza pana taci, intoarce textul.
        Pragul de zgomot se reajusteaza continuu (muzica, ventilator, oameni in camera)."""
        block = int(SR * BLOCK_SEC)
        q = queue.Queue()

        def cb(indata, frames, t, status):
            q.put(indata[:, 0].copy())

        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=block, callback=cb):
            recent = deque(maxlen=70)    # ~2 s de "fundal"
            pre = deque(maxlen=12)       # ~0.36 s inainte sa incepi sa vorbesti
            voiced, speaking, silent_blocks, loud, t0 = [], False, 0, 0, 0.0
            threshold = 0.02
            while True:
                if stop_event is not None and stop_event.is_set():
                    return None
                try:
                    chunk = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                energy = _rms(chunk)
                if not speaking:
                    recent.append(energy)
                    pre.append(chunk)
                    floor = float(np.percentile(recent, 30)) if len(recent) >= 8 else 0.006
                    threshold = min(max(floor * 3.0, 0.012), 0.08)
                    loud = loud + 1 if energy > threshold else 0
                    if loud >= 2 and len(recent) >= 8:      # 2 bucati la rand = voce, nu un clic
                        speaking, voiced, t0 = True, list(pre), time.time()
                else:
                    voiced.append(chunk)
                    silent_blocks = silent_blocks + 1 if energy < threshold else 0
                    if silent_blocks * BLOCK_SEC >= silence_end or time.time() - t0 > max_seconds:
                        break

        audio = np.concatenate(voiced) if voiced else np.zeros(0, dtype=np.float32)
        if len(audio) < SR * 0.4:
            return ""
        return self.transcribe(audio)

    def _run(self, audio, lang):
        segs, info = self.model.transcribe(audio, language=lang, beam_size=1, vad_filter=True,
                                           condition_on_previous_text=False, hotwords="Jarvis")
        return " ".join(s.text.strip() for s in segs).strip(), info

    def transcribe(self, audio):
        """Recunoaste romana sau engleza (automat) si tine minte limba in self.last_lang."""
        if self.lang in ("ro", "en"):
            self.last_lang = self.lang
            return self._run(audio, self.lang)[0]
        text, info = self._run(audio, None)
        det, prob = info.language, info.language_probability
        if det not in ("ro", "en") or (det == "en" and prob < 0.6):
            probs = dict(getattr(info, "all_language_probs", None) or [])
            det = "en" if probs.get("en", 0) > 1.5 * probs.get("ro", 0) else "ro"
            text, info = self._run(audio, det)
        if det == "en" and len(text.split()) <= 3:
            det = "ro"   # cateva cuvinte englezesti (nume de aplicatii, jocuri) nu inseamna ca vorbesti engleza
        self.last_lang = det
        return text