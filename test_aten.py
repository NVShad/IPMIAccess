#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_aten.py — проверка ATEN-рукопожатия на порту 5900 со свежим KVM-токеном.
Реализует ровно тот обмен, что делает форк noVNC (kelleyk, bmc-support):
  RFB 3.8 -> security type 16 -> служебные байты -> user(24)+pass(24) ->
  SecurityResult -> ClientInit -> ServerInit.
"""

import socket
import struct
import sys
import time

sys.path.insert(0, ".")
from ipmi_server import get_kvm_token, BMC_HOST, KVM_PORT


def recvn(sock, n, timeout=10):
    sock.settimeout(timeout)
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(f"сервер закрыл соединение (нужно {n}, есть {len(buf)})")
        buf += chunk
    return buf


def main():
    print("[*] Получаю свежий KVM-токен...")
    token = get_kvm_token()
    print(f"[+] Токен: {token}")

    s = socket.create_connection((BMC_HOST, KVM_PORT), timeout=10)

    # 1. RFB version
    banner = recvn(s, 12)
    print(f"[<] banner: {banner!r}")
    s.sendall(b"RFB 003.008\n")

    # 2. Security types
    n = recvn(s, 1)[0]
    types = recvn(s, n)
    print(f"[<] security types: {list(types)}")
    assert 16 in types, "нет типа 16 (ATEN)"
    s.sendall(bytes([16]))
    print("[>] выбран тип 16 (Tight/ATEN)")

    # 3. Служебные байты: читаем то, что сервер пришлёт (по форку: 4 + 16)
    s.settimeout(3)
    head = b""
    try:
        while len(head) < 64:
            chunk = s.recv(64 - len(head))
            if not chunk:
                break
            head += chunk
            if len(head) >= 24:
                break
    except socket.timeout:
        pass
    print(f"[<] служебные байты ({len(head)}): {head.hex()}")

    num_tunnels = struct.unpack(">I", head[0:4])[0]
    print(f"    num_tunnels/garbage: 0x{num_tunnels:08x}")

    # Эвристики форка kelleyk:
    #  #0: num_tunnels огромен (первый байт != 0) -> съедаем 4+16 байт
    #  #1: num_tunnels == 0 и (sub_auth & 0xFFFF) == 0x0100 -> AST2400
    if num_tunnels == 0 and len(head) >= 8:
        sub = struct.unpack(">I", head[4:8])[0]
        print(f"    sub_auth_count: 0x{sub:08x}")
        skip = 4 + 4 + 16  # tunnels + subauth + pad
    else:
        skip = 4 + 16
    print(f"    пропускаю {skip} байт служебных данных")

    # 4. Отправляем логин/пароль (оба = токен), дополненные NUL до 24 байт
    cred = token.encode("ascii")
    block = cred.ljust(24, b"\x00") + cred.ljust(24, b"\x00")
    s.sendall(block)
    print(f"[>] отправлены реквизиты (24+24 байта)")

    # 5. SecurityResult
    res = struct.unpack(">I", recvn(s, 4))[0]
    print(f"[<] SecurityResult: {res} ({'OK' if res == 0 else 'FAIL'})")
    if res != 0:
        ln = struct.unpack(">I", recvn(s, 4))[0]
        print("[<] причина:", recvn(s, ln))
        sys.exit(1)

    # 6. ClientInit (shared=1) -> ServerInit
    s.sendall(b"\x01")
    si = recvn(s, 24)
    w, h = struct.unpack(">HH", si[0:4])
    name_len = struct.unpack(">I", si[20:24])[0]
    name = recvn(s, name_len) if name_len else b""
    print(f"[<] ServerInit: {w}x{h}, имя: {name!r}")
    print()
    print("[OK] ATEN-рукопожатие пройдено — видеопоток доступен!")
    s.close()


if __name__ == "__main__":
    main()
