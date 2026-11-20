#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_e2e.py — сквозной тест: поднимает ipmi_server.py, проверяет API
и проходит ATEN-рукопожатие ЧЕРЕЗ WebSocket-мост (как это сделает браузер).
Сервер останавливается по завершении.
"""

import asyncio
import json
import struct
import subprocess
import sys
import time
import urllib.request

import websockets

HTTP = "http://localhost:7100"
WS = "ws://localhost:5700"


def api(path):
    with urllib.request.urlopen(HTTP + path, timeout=15) as r:
        return json.loads(r.read())


class WsStream:
    """Чтение точного числа байт из потока WS-сообщений."""
    def __init__(self, ws):
        self.ws = ws
        self.buf = b""

    async def read(self, n):
        while len(self.buf) < n:
            msg = await self.ws.recv()
            if isinstance(msg, str):
                msg = msg.encode()
            self.buf += msg
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    async def read_some(self, n, timeout=3):
        """Читать до n байт, что есть (с таймаутом)."""
        try:
            while len(self.buf) < n:
                msg = await asyncio.wait_for(self.ws.recv(), timeout)
                if isinstance(msg, str):
                    msg = msg.encode()
                self.buf += msg
        except asyncio.TimeoutError:
            pass
        out, self.buf = self.buf, b""
        return out


async def kvm_handshake(token):
    async with websockets.connect(WS, subprotocols=["binary"],
                                  max_size=None, ping_interval=None) as ws:
        st = WsStream(ws)
        banner = await st.read(12)
        print(f"    [<] banner: {banner!r}")
        await ws.send(b"RFB 003.008\n")

        n = (await st.read(1))[0]
        types = await st.read(n)
        print(f"    [<] security types: {list(types)}")
        await ws.send(bytes([16]))

        head = await st.read_some(24)
        print(f"    [<] служебные байты ({len(head)}): {head.hex()}")

        cred = token.encode("ascii")
        await ws.send(cred.ljust(24, b"\x00") + cred.ljust(24, b"\x00"))

        res = struct.unpack(">I", await st.read(4))[0]
        print(f"    [<] SecurityResult: {res}")
        assert res == 0, "аутентификация не пройдена"

        await ws.send(b"\x01")  # ClientInit shared
        si = await st.read(24)
        w, h = struct.unpack(">HH", si[0:4])
        name_len = struct.unpack(">I", si[20:24])[0]
        name = await st.read(name_len) if name_len else b""
        print(f"    [<] ServerInit: {w}x{h}, имя: {name!r}")
        return True


def main():
    print("[*] Запускаю ipmi_server.py ...")
    srv = subprocess.Popen([sys.executable, "ipmi_server.py"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        # ждём поднятия портов
        for _ in range(30):
            try:
                s = api("/api/status")
                break
            except Exception:
                time.sleep(0.5)
        else:
            print("[FAIL] HTTP-сервер не поднялся")
            return 1
        print(f"[+] /api/status: {s}")

        t = api("/api/token")
        if not t.get("ok"):
            print(f"[FAIL] /api/token: {t}")
            return 1
        print(f"[+] /api/token: {t['token']}")

        print("[*] ATEN-рукопожатие через WS-мост...")
        ok = asyncio.run(kvm_handshake(t["token"]))
        print("[OK] Мост работает, видеопоток доступен через WebSocket!"
              if ok else "[FAIL]")
        return 0
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()
        print("[*] Сервер остановлен")


if __name__ == "__main__":
    sys.exit(main())
