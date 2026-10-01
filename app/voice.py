"""Vocea lui Jarvis.

Principal: Emil (voce neurala Microsoft, barbat, romana) prin edge-tts - gratuit, cere internet.
Rezerva:   Piper Mihai (local, offline), apoi vocea Windows.
"""
import asyncio
import io
import os
import re
import wave

import numpy as np
import sounddevice as sd


def clean_for_speech(text, lang="ro"):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", "linkul", text)
    text = re.sub(r"[*_#`>|]+", "", text)
    text = re.sub(r"(?<=\D),|,(?=\D)", " ", text)       # fara pauze la virgule (dar 3,5 ramane)
    if lang == "ro":
        text = re.sub(r"\bJarvis\b", "Gearvis", text, flags=re.I)  # pronuntie englezeasca
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class Voice:
    def __init__(self, voice_path, log=print):
        self.log = log
        self.motor = os.getenv("VOCE_MOTOR", "edge").strip().lower() or "edge"
        self.edge_voice = os.getenv("VOCE_EDGE", "ro-RO-EmilNeural").strip() or "ro-RO-EmilNeural"
        self.edge_voice_en = os.getenv("VOCE_EDGE_EN", "en-GB-RyanNeural").strip() or "en-GB-RyanNeural"
        self.rate = os.getenv("VOCE_VITEZA", "+8%").strip() or "+8%"
        self.pitch = os.getenv("VOCE_TON", "-12Hz").strip() or "-12Hz"
        self.piper = None
        self.engine = None
        try:
            from piper import PiperVoice
            self.piper = PiperVoice.load(voice_path)
        except Exception as e:
            log(f"Voce: Piper indisponibil ({e.__class__.__name__})")
        if self.motor == "edge":
            try:
                import edge_tts  # noqa: F401
                import miniaudio  # noqa: F401
                log(f"Voce: {self.edge_voice} (online, viteza {self.rate}, ton {self.pitch})")
            except Exception as e:
                log(f"Voce: edge-tts lipseste ({e.__class__.__name__}), folosesc Piper")
                self.motor = "piper"
        if self.motor != "edge":
            log("Voce: Piper Mihai (offline)" if self.piper else "Voce: vocea Windows")
        if self.piper is None:
            try:
                import pyttsx3
                self.engine = pyttsx3.init()
            except Exception:
                pass

    def stop(self):
        try:
            sd.stop()
        except Exception:
            pass

    def _edge_audio(self, text, lang="ro"):
        import edge_tts
        import miniaudio

        async def fetch():
            buf = bytearray()
            voice = self.edge_voice_en if lang == "en" else self.edge_voice
            com = edge_tts.Communicate(text, voice, rate=self.rate, pitch=self.pitch)
            async for chunk in com.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        mp3 = asyncio.run(fetch())
        dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=24000)
        return np.array(dec.samples, dtype=np.int16), 24000

    def _piper_audio(self, text):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            if hasattr(self.piper, "synthesize_wav"):
                self.piper.synthesize_wav(text, wf)
            else:
                self.piper.synthesize(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        return data, rate

    def say(self, text, lang="ro"):
        text = clean_for_speech(text, lang)
        if not text:
            return
        audio = None
        if self.motor == "edge":
            try:
                audio = self._edge_audio(text, lang)
            except Exception as e:
                self.log(f"Voce: Emil nu a mers ({e.__class__.__name__}), trec pe Piper")
        if audio is None and self.piper is not None:
            audio = self._piper_audio(text)
        if audio is not None:
            sd.play(audio[0], audio[1])
            sd.wait()
        elif self.engine is not None:
            self.engine.say(text)
            self.engine.runAndWait()