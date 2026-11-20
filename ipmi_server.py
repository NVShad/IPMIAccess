#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ipmi_server.py — локальный мост для веб-доступа к IPMI (Supermicro / ATEN iKVM).

Что делает:
  * HTTP :7100  — отдаёт статику (ipmi.html, novnc-aten/) и JSON API:
      GET  /api/token      -> {"token": "..."}  (свежий KVM-токен из JNLP)
      GET  /api/status     -> {"ok": true, "bmc": "..."}  (проверка связи)
      POST /api/power      -> {"ok": ...}  (on/off/reset/cycle — через CGI BMC)
  * WS   :5700  — бинарный мост WebSocket <-> TCP <BMC_HOST>:5900 (RFB).

Запуск:  python ipmi_server.py
Открыть: ipmi.html (двойным кликом) или http://localhost:7100/ipmi.html
"""

import asyncio
import json
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.parse
import http.cookiejar
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import websockets

# Настройки BMC — задаются переменными окружения (см. config.example.bat):
#   set BMC_HOST=192.168.1.100
#   set BMC_USER=ADMIN
#   set BMC_PWD=your_password
BMC_HOST = os.environ.get("BMC_HOST", "")
BMC_USER = os.environ.get("BMC_USER", "ADMIN")
BMC_PWD = os.environ.get("BMC_PWD", "")
KVM_PORT = int(os.environ.get("BMC_KVM_PORT", "5900"))

if not BMC_HOST:
    sys.exit("Ошибка: не задан BMC_HOST. Задайте переменные окружения "
             "(см. config.example.bat) и запустите снова.")

HTTP_PORT = 7100
WS_PORT = 5700

# ---------------------------------------------------------------- BMC helpers

def bmc_login():
    """Логин в BMC, возвращает opener с SID-кукой."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"name": BMC_USER, "pwd": BMC_PWD}).encode()
    req = urllib.request.Request(f"http://{BMC_HOST}/cgi/login.cgi", data=data)
    opener.open(req, timeout=10).read()
    return opener


def get_kvm_token():
    """Свежий KVM-токен: логин -> JNLP (jwsk) -> второй <argument>.

    Важно: BMC отдаёт JNLP только с Referer на страницу консоли,
    иначе возвращает 200 с пустым телом.
    """
    opener = bmc_login()
    url = (f"http://{BMC_HOST}/cgi/url_redirect.cgi"
           f"?url_name=ikvm&url_type=jwsk")
    referer = (f"http://{BMC_HOST}/cgi/url_redirect.cgi"
               f"?url_name=man_ikvm")
    req = urllib.request.Request(url, headers={"Referer": referer})
    raw = opener.open(req, timeout=10).read()
    if len(raw) < 100:
        raise RuntimeError(
            "BMC вернул пустой JNLP — KVM-консоль занята другой сессией. "
            "Закройте другие консоли и повторите.")
    args = re.findall(rb"<argument>([^<]*)</argument>", raw)
    args = [a.decode("ascii", "replace") for a in args]
    if len(args) < 3 or not args[1]:
        raise RuntimeError("Не удалось разобрать JNLP: " + raw[:200].decode("ascii", "replace"))
    return args[1]


def bmc_ipmi(payload):
    """POST на /cgi/ipmi.cgi с XML-командой (напр. 'POWER_INFO.XML=(0,0)')."""
    opener = bmc_login()
    data = (payload + "&time_stamp=x").encode()
    req = urllib.request.Request(f"http://{BMC_HOST}/cgi/ipmi.cgi", data=data)
    return opener.open(req, timeout=15).read().decode("utf-8", "replace")


# Коды питания этой прошивки (подсмотрены в man_chassis оригинальной веб-морды):
#   0 = выключить немедленно, 1 = включить, 2 = цикл, 3 = reset, 5 = ACPI-выключение
POWER_CODES = {"off": 0, "on": 1, "cycle": 2, "reset": 3, "off_soft": 5}


def bmc_power(action):
    """Управление питанием: on/off/off_soft/reset/cycle."""
    if action not in POWER_CODES:
        raise RuntimeError("Неизвестное действие: " + action)
    return bmc_ipmi(f"POWER_INFO.XML=(1,{POWER_CODES[action]})")


def bmc_power_status():
    """Текущее состояние питания: 'ON'/'OFF'."""
    xml = bmc_ipmi("POWER_INFO.XML=(0,0)")
    m = re.search(r'<POWER\s+STATUS="([^"]+)"', xml)
    return m.group(1) if m else "UNKNOWN"


# ---------------------------------------------------------------- Датчики

def _to_signed(v, bits):
    """Знаковое число из bits-битного беззнакового (2's complement)."""
    sign = 1 << (bits - 1)
    return v - (1 << bits) if v & sign else v


def _sensor_func(raw_hex, m_hex, b_hex, rb_hex):
    """Линеаризация IPMI: y = (M*x + B*10^Kb) * 10^Km.
    M и B — 10-битные знаковые, упакованные в 16 бит; Km/Kb — 4-битные из RB."""
    m, b, rb = int(m_hex, 16), int(b_hex, 16), int(rb_hex, 16)
    M = _to_signed(((m & 0xC0) << 2) + (m >> 8), 10)
    B = _to_signed(((b & 0xC0) << 2) + (b >> 8), 10)
    Km = _to_signed(rb >> 4, 4)
    Kb = _to_signed(rb & 0x0F, 4)
    x = int(raw_hex, 16)
    return (M * x + B * 10 ** Kb) * 10 ** Km


SENSOR_UNITS = {0x01: "°C", 0x02: "°F", 0x03: "K", 0x04: "В", 0x05: "А",
                0x06: "Вт", 0x12: "RPM", 0x13: "Гц"}

SENSOR_GROUPS = {0x01: "temp", 0x02: "voltage", 0x04: "fan"}


def _chassis_state(raw):
    """Дискретный датчик STYPE=05 (вскрытие корпуса)."""
    d = int(raw, 16)
    if d == 0:
        return "норма"
    parts = []
    if d & 1: parts.append("вскрытие корпуса")
    if d & 2: parts.append("отсек накопителей")
    if d & 4: parts.append("зона карт расширения")
    if d & 8: parts.append("зона процессора")
    if d & 16: parts.append("LAN leash")
    if d & 32: parts.append("несанкц. док")
    return ", ".join(parts) or f"код {d}"


def bmc_sensors():
    """Список датчиков с показаниями, порогами и статусом."""
    import xml.etree.ElementTree as ET
    xml = bmc_ipmi("SENSOR_INFO.XML=(1,ff)")
    root = ET.fromstring(xml)
    out = []
    for s in root.iter("SENSOR"):
        a = s.attrib
        name = a.get("NAME", "?").strip()
        option = int(a.get("OPTION", "0"), 16)
        stype = int(a.get("STYPE", "0"), 16)
        unit_code = int(a.get("UNIT", "0"), 16)
        reading = a.get("READING", "")
        if len(reading) < 6:
            continue
        raw = reading[0:2]

        present = bool(option & 0x40)
        if stype == 0x05:  # дискретный: вскрытие корпуса
            state = _chassis_state(raw) if present else None
            out.append({"name": name, "group": "chassis", "present": present,
                        "value": state, "ok": present and int(raw, 16) == 0})
            continue

        group = SENSOR_GROUPS.get(stype)
        if group is None:
            continue  # прочие типы нам неинтересны

        # Аналоговый датчик: приведение знака для 2's complement формата
        signed = (int(a.get("UNIT1", "0"), 16) >> 6) == 0x02

        def conv(hexbyte):
            v = int(hexbyte, 16)
            if signed:
                v = _to_signed(v, 8)
            return _sensor_func(f"{v:02x}", a["M"], a["B"], a["RB"])

        if not present or raw in ("00", "ff") and stype != 0x04:
            out.append({"name": name, "group": group, "present": False})
            continue

        value = conv(raw)
        thr = {k: conv(a[k]) for k in ("UNR", "UC", "UNC", "LNC", "LC", "LNR")}

        # Статус по логике родной веб-морды (ProcThreshlodSensor)
        if value <= thr["UNC"] and value >= thr["LNC"]:
            status = "ok"
        elif value > thr["UNC"]:
            status = "crit" if value > thr["UC"] else "warn"
        else:
            status = "crit" if value < thr["LC"] else "warn"

        out.append({"name": name, "group": group, "present": True,
                    "value": round(value, 2),
                    "unit": SENSOR_UNITS.get(unit_code, ""),
                    "status": status,
                    "lo_warn": round(thr["LNC"], 2), "hi_warn": round(thr["UNC"], 2)})
    return out


def bmc_info():
    """Системная информация: GENERIC_INFO + статус питания."""
    import xml.etree.ElementTree as ET
    xml = bmc_ipmi("GENERIC_INFO.XML=(0,0)")
    root = ET.fromstring(xml)
    g = root.find(".//GENERIC")
    k = root.find(".//KERNAL")
    info = dict(g.attrib) if g is not None else {}
    if k is not None:
        info["KERNEL"] = k.attrib.get("VERSION", "")
    info["POWER"] = bmc_power_status()
    return info


# ---------------------------------------------------------------- HTTP часть

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[http] " + fmt % args + "\n")

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            try:
                t0 = time.time()
                bmc_login()
                self._json({"ok": True, "bmc": BMC_HOST,
                            "login_ms": round((time.time() - t0) * 1000)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 502)
            return
        if self.path == "/api/token":
            try:
                self._json({"ok": True, "token": get_kvm_token()})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 502)
            return
        if self.path == "/api/sensors":
            try:
                self._json({"ok": True, "sensors": bmc_sensors()})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 502)
            return
        if self.path == "/api/info":
            try:
                self._json({"ok": True, "info": bmc_info()})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 502)
            return
        # статика
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/power":
            try:
                ln = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(ln) or b"{}")
                resp = bmc_power(payload.get("action", ""))
                self._json({"ok": True, "bmc_response": resp[:400]})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 502)
            return
        self._json({"ok": False, "error": "unknown endpoint"}, 404)


# ---------------------------------------------------------------- WS-мост

async def bridge(ws):
    """WebSocket <-> TCP 5900, бинарные кадры."""
    peer = ws.remote_address
    print(f"[ws] подключение от {peer}")
    try:
        reader, writer = await asyncio.open_connection(BMC_HOST, KVM_PORT)
    except Exception as e:
        print(f"[ws] не удалось подключиться к BMC:{KVM_PORT}: {e}")
        await ws.close(1011, "BMC unreachable")
        return

    async def ws_to_tcp():
        try:
            async for msg in ws:
                if isinstance(msg, str):
                    msg = msg.encode()
                writer.write(msg)
                await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def tcp_to_ws():
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                await ws.send(chunk)
        except Exception:
            pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    t1 = asyncio.create_task(ws_to_tcp())
    t2 = asyncio.create_task(tcp_to_ws())
    done, pending = await asyncio.wait({t1, t2},
                                       return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    try:
        writer.close()
    except Exception:
        pass
    print(f"[ws] соединение {peer} закрыто")


async def ws_main():
    subprotos = [websockets.Subprotocol("binary"),
                 websockets.Subprotocol("base64")]
    async with websockets.serve(bridge, "0.0.0.0", WS_PORT,
                                subprotocols=subprotos,
                                max_size=None, ping_interval=None):
        print(f"[ws] мост слушает ws://localhost:{WS_PORT} -> {BMC_HOST}:{KVM_PORT}")
        await asyncio.Future()  # навсегда


# ---------------------------------------------------------------- main

def main():
    httpd = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"[http] статика и API на http://localhost:{HTTP_PORT}  "
          f"(страница: http://localhost:{HTTP_PORT}/ipmi.html)")
    try:
        asyncio.run(ws_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
