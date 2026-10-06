#!/usr/bin/env python3
"""Selbsttest der Miniserver-Verbindung gegen einen simulierten Miniserver.

Prueft ohne echte Hardware (nur aiohttp noetig):
  1. Handshake-Haenger      -> connect() bricht nach HANDSHAKE_TIMEOUT_S ab
  2. Fehler im Callback     -> restliche Werte/Tabellen kommen trotzdem an
  3. Kennung 5 + Close 4003 -> out_of_service/close_code gesetzt, Stream endet sauber
  4. _auth_rejected()       -> nur 401/403/423 der loxone_api, nicht 503/Token-Ablauf
  5. stream_task            -> Anmeldung abgelehnt = lange Pause (aufweckbar durch
                               reconnect()), Netzfehler = kurze Pause

Start:  python tools/ws_selftest.py        (aus config/app/, Exit-Code 0 = alles ok)
"""
from __future__ import annotations

import asyncio
import logging
import struct
import sys
import time
from pathlib import Path

from aiohttp import WSMsgType, web

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import loxone_ws  # noqa: E402
from loxone_ws import LoxoneWS, describe_close  # noqa: E402

logging.basicConfig(level=logging.CRITICAL)
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok   " if ok else "  FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


def header(ident: int, length: int) -> bytes:
    return bytes([0x03, ident, 0, 0]) + struct.pack("<I", length)


UUID_A = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
UUID_B = bytes.fromhex("1112131415161718191a1b1c1d1e1f20")


def value_table(*pairs: tuple[bytes, float]) -> bytes:
    return b"".join(u + struct.pack("<d", v) for u, v in pairs)


async def start_server(handler) -> tuple[web.AppRunner, int]:
    app = web.Application()
    app.router.add_get("/ws/rfc6455", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port


async def ms_answer(ws, cmd: str) -> bool:
    """Antwortet wie ein Miniserver auf den Handshake. True = Handshake fertig."""
    if cmd == "jdev/sys/getkey":
        await ws.send_str('{"LL": {"control": "jdev/sys/getkey", "value": "00ff00ff", "Code": "200"}}')
    elif cmd.startswith("authwithtoken/"):
        await ws.send_str('{"LL": {"control": "authwithtoken", "value": "x", "Code": "200"}}')
    elif cmd == "jdev/sps/enablebinstatusupdate":
        return True
    return False


# --- 1) Handshake-Haenger ---------------------------------------------------
async def test_handshake_hang() -> None:
    async def hang(request):
        ws = web.WebSocketResponse(protocols=["remotecontrol"])
        await ws.prepare(request)
        async for _ in ws:      # liest, antwortet nie
            pass
        return ws

    runner, port = await start_server(hang)
    old = loxone_ws.HANDSHAKE_TIMEOUT_S
    loxone_ws.HANDSHAKE_TIMEOUT_S = 1
    c = LoxoneWS("127.0.0.1", port, "u", "jwt", secure=False)
    t0 = time.monotonic()
    try:
        await c.connect()
        raised = False
    except ConnectionError:
        raised = True
    dt = time.monotonic() - t0
    await c.close()
    loxone_ws.HANDSHAKE_TIMEOUT_S = old
    await runner.cleanup()
    check("1  Handshake-Haenger bricht nach Timeout ab", raised and dt < 3.5, f"raised={raised} dt={dt:.1f}s")


# --- 2+3) Callback-Fehler, Kennung 5, Close-Code -------------------------------
async def test_stream() -> None:
    async def ms(request):
        ws = web.WebSocketResponse(protocols=["remotecontrol"])
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == WSMsgType.TEXT and await ms_answer(ws, msg.data):
                break
        # Tabelle 1: zwei Werte (Callback wirft fuer den ersten)
        t1 = value_table((UUID_A, 1.0), (UUID_B, 2.0))
        await ws.send_bytes(header(2, len(t1)))
        await ws.send_bytes(t1)
        # Tabelle 2: Wetter -> Callback wirft -> Tabelle wird verworfen
        wx = UUID_A + struct.pack("<Ii", 0, 0)
        await ws.send_bytes(header(7, len(wx)))
        await ws.send_bytes(wx)
        # Tabelle 3: kommt NACH dem Fehler noch an?
        t3 = value_table((UUID_B, 3.0))
        await ws.send_bytes(header(2, len(t3)))
        await ws.send_bytes(t3)
        # Kennung 5 (kein Payload), dann Close 4003
        await ws.send_bytes(header(5, 0))
        await ws.close(code=4003)
        return ws

    runner, port = await start_server(ms)
    got: list[tuple[str, float]] = []

    def on_value(uuid: str, val):
        if val == 1.0:
            raise RuntimeError("Callback-Fehler (Absicht)")
        got.append((uuid, val))

    def on_weather(uuid: str, entries):
        raise RuntimeError("Wetter-Callback-Fehler (Absicht)")

    c = LoxoneWS("127.0.0.1", port, "u", "jwt", secure=False)
    await c.connect()
    try:
        await asyncio.wait_for(c.stream(on_value, on_weather), timeout=10)
        ended = True
    except Exception as err:        # noqa: BLE001
        ended = False
        print("   stream-Fehler:", err)
    vals = [v for _, v in got]
    await c.close()
    await runner.cleanup()
    check("2a Fehler in einem Wert-Callback kostet nicht den Rest der Tabelle", 2.0 in vals, str(vals))
    check("2b Fehler im Wetter-Callback kippt nicht den Stream (Folgetabelle kommt an)", 3.0 in vals, str(vals))
    check("3a Kennung 5 erkannt (out_of_service)", c.out_of_service is True)
    check("3b Close-Code 4003 festgehalten", c.close_code == 4003, str(c.close_code))
    check("3c Stream endet sauber nach Close", ended)
    check("3d describe_close(4003) nennt die Sperre", "gesperrt" in describe_close(4003))


# --- 4) _auth_rejected -------------------------------------------------------------
def test_auth_rejected() -> None:
    import webvisu

    class LoxoneAuthError(RuntimeError):
        pass

    class LoxoneRequestError(RuntimeError):
        pass

    r = webvisu._auth_rejected
    check("4a 401 der Anmeldung = abgelehnt",
          r(LoxoneAuthError("Authentication failed with status 401: x")))
    check("4b getkey2 HTTP 401 = abgelehnt", r(LoxoneRequestError("getkey2 failed with HTTP 401: {}")))
    check("4c getkey2 code=423 (Benutzer deaktiviert) = abgelehnt",
          r(LoxoneRequestError("getkey2 returned code=423: {}")))
    check("4d 503 (Miniserver startet neu) = NICHT abgelehnt",
          not r(LoxoneAuthError("Authentication failed with status 503: x")))
    check("4e abgelaufenes WS-Token (ConnectionError) = NICHT abgelehnt",
          not r(ConnectionError("authwithtoken fehlgeschlagen: {'LL': {'Code': '401'}}")))
    check("4f Zeitueberschreitung = NICHT abgelehnt", not r(asyncio.TimeoutError()))
    check("4g None = NICHT abgelehnt", not r(None))


# --- 5) stream_task: Pausenlogik -----------------------------------------------------
async def test_stream_task() -> None:
    import webvisu

    class LoxoneAuthError(RuntimeError):
        pass

    async def run(raise_in_start, expect_long: bool, wake: bool):
        app = object.__new__(webvisu.App)
        app.host = "127.0.0.1"
        app.client = None
        app.ws = None
        app.ms_up = False
        app.ms_up_since = app.ms_down_since = 0.0
        app._pending_reload = False
        app._retry_now = asyncio.Event()
        attempts: list[str] = []

        async def start():
            attempts.append("start")
            raise raise_in_start

        async def noop(*a, **k):
            return None

        app.start = start
        app._close_conn = noop
        app._reauth = noop
        app._refresh_structure = noop
        saved = webvisu.MS_RETRY, webvisu.MS_RETRY_AUTH
        webvisu.MS_RETRY, webvisu.MS_RETRY_AUTH = (0.2,), (3,)   # Test-Zeiten
        task = asyncio.create_task(app.stream_task())
        t0 = time.monotonic()
        await asyncio.sleep(0.15)               # 1. Versuch laeuft/ist durch
        if wake:
            app._retry_now.set()                # = reconnect() mit neuen Zugangsdaten
        await asyncio.sleep(1.0)
        n = len(attempts)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        webvisu.MS_RETRY, webvisu.MS_RETRY_AUTH = saved
        return n, attempts, app

    n_net, _, app_net = await run(ConnectionError("Netz weg"), False, False)
    check("5a Netzfehler: kurze Pause, mehrere Versuche je Sekunde", n_net >= 3, f"{n_net} Versuche")
    n_auth, _, app_auth = await run(LoxoneAuthError("Authentication failed with status 401: x"), True, False)
    check("5b Anmeldung abgelehnt: nur EIN Versuch in der langen Pause", n_auth == 1, f"{n_auth} Versuche")
    check("5d Grund-Code 'auth' + naechster Versuch gesetzt",
          app_auth.ms_reason == "auth" and app_auth.ms_next_retry > time.time(), app_auth.ms_reason)
    check("5e Netzfehler -> Grund-Code 'net'", app_net.ms_reason == "net", app_net.ms_reason)

    # /api/msstatus liefert Grund + Restzeit nur bei Trennung
    class Req:
        pass
    req = Req()
    req.app = {"app": app_auth}

    async def no_sys():
        return {}
    app_auth.ms_sysinfo = no_sys
    app_auth.ms_up = False
    app_auth.ms_next_retry = time.time() + 120
    import json as _json
    d = _json.loads((await webvisu.api_msstatus(req)).text)
    check("5f msstatus: reason=auth, retryIn ~120 s", d.get("reason") == "auth" and 115 <= (d.get("retryIn") or 0) <= 120, str(d))
    app_auth.ms_up = True
    d = _json.loads((await webvisu.api_msstatus(req)).text)
    check("5g msstatus: bei Verbindung kein Grund/keine Restzeit", d.get("reason") is None and d.get("retryIn") is None, str(d))

    r = webvisu._ms_reason_code
    check("5h Grund-Codes: blocked/disabled/update/slots/user_changed",
          r(True, 4003, False) == "blocked" and r(True, 4006, False) == "disabled"
          and r(False, 4007, False) == "update" and r(False, None, True) == "update"
          and r(False, 4008, False) == "slots" and r(False, 4005, False) == "user_changed"
          and r(True, None, False) == "auth" and r(False, None, False) == "net")

    n_wake, _, _ = await run(LoxoneAuthError("Authentication failed with status 401: x"), True, True)
    check("5c reconnect() weckt die lange Pause sofort (und dreht nicht durch)", 2 <= n_wake <= 3, f"{n_wake} Versuche")


async def main() -> int:
    print("Miniserver-Verbindung: Selbsttest")
    await test_handshake_hang()
    await test_stream()
    test_auth_rejected()
    await test_stream_task()
    print("\nALLES OK" if not FAILED else f"\n{len(FAILED)} FEHLER: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
