"""Deseneaza iconita lui Jarvis (un cerc luminos turcoaz) si o salveaza ca jarvis.ico. Fara biblioteci externe."""
import math
import os
import struct
import zlib

N = 256
px = bytearray()
for y in range(N):
    px.append(0)  # filtru PNG
    for x in range(N):
        dx, dy = x - N / 2 + .5, y - N / 2 + .5
        d = math.hypot(dx, dy) / (N / 2)
        if d > 1:
            px += bytes((0, 0, 0, 0))
            continue
        ring = math.exp(-((d - 0.70) / 0.06) ** 2)           # inelul principal
        inner = 0.45 * math.exp(-((d - 0.52) / 0.025) ** 2)  # inel subtire interior
        glow = 0.35 * math.exp(-((d - 0.70) / 0.18) ** 2)    # stralucire
        a = min(1.0, ring + inner + glow)
        base = (3, 14, 16)
        col = (62, 240, 196)
        r, g, b = (int(base[i] + (col[i] - base[i]) * a) for i in range(3))
        edge = max(0.0, min(1.0, (1 - d) * N / 4))           # margine neteda
        px += bytes((r, g, b, int(255 * edge)))


def chunk(t, data):
    return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)


png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(bytes(px), 9)) + chunk(b"IEND", b""))
ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis.ico")
with open(out, "wb") as f:
    f.write(ico)
print("Iconita:", out)