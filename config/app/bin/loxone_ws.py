"""Loxone WebSocket-Live-Client (Phase 2b).

Holt die echten State-Werte, die es ueber HTTP nicht gibt. Nutzt das per
loxone-api geholte JWT zur WS-Authentifizierung (authwithtoken) und abonniert
danach die binaeren Status-Updates (enablebinstatusupdate).

Protokoll (Kurzfassung, siehe "Communicating with the Miniserver"):
  - Jede Nachricht wird von einem 8-Byte-Header eingeleitet (Byte0=0x03,
    Byte1=Identifier, Byte4..7=Laenge, little-endian).
  - Identifier: 0=Text, 2=Value-States, 3=Text-States, 6=Keepalive,
    7=Weather-States (nur wenn die Anlage den Loxone-Wetterdienst hat).
  - Value-State-Eintrag: 16-Byte-UUID + 8-Byte-double (LE).
  - Text-State-Eintrag: 16-Byte-UUID + 16-Byte-Icon-UUID + 4-Byte-Laenge +
    Text + Padding auf 4-Byte-Grenze.
  - Weather-Eintrag ("EvDataWeather"): 16-Byte-UUID + 4-Byte lastUpdate
    (uint32) + 4-Byte nrEntries (int32), danach nrEntries Bloecke a 68 Byte
    ("EvDataWeatherEntry"): 5 * int32 (timestamp, weatherType, windDirection,
    solarRadiation, relativeHumidity) + 6 * double (temperature,
    perceivedTemperature, dewPoint, precipitation, windSpeed,
    barometricPressure), alles little-endian.

Nicht behandelte Identifier werden einmal pro Verbindung protokolliert — sonst
bliebe unsichtbar, dass der Miniserver etwas schickt, das hier niemand liest.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import ssl
import struct
import time
from typing import Any, Callable

import aiohttp

log = logging.getLogger("loxpanel.ws")

ValueCallback = Callable[[str, Any], None]
# uuid -> Liste von Wetter-Eintraegen (siehe _parse_weather).
WeatherCallback = Callable[[str, list], None]


KEEPALIVE_S = 30    # Abstand der "keepalive"-Kommandos an den Miniserver
DEAD_S = 3 * KEEPALIVE_S   # so lange ohne JEDE Nachricht -> Verbindung gilt als tot
# Obergrenze fuer Verbindungsaufbau + Anmeldung. Ohne sie konnte ein Miniserver, der
# TCP/WS annimmt aber nicht antwortet (halb offen, haengende Firmware), den
# Reconnect-Loop unbegrenzt blockieren: der Keepalive-Waechter laeuft erst im Stream.
HANDSHAKE_TIMEOUT_S = 20

# Websocket-Close-Codes des Miniservers (Loxone "Communicating with the
# Miniserver", Abschnitt "Websocket Close Codes").
WS_CLOSE_REASONS = {
    4003: "Anmeldung gesperrt (zu viele Fehlversuche)",
    4004: "ein Benutzer wurde geaendert",
    4005: "der angemeldete Benutzer wurde geaendert",
    4006: "der Benutzer wurde deaktiviert",
    4007: "Miniserver fuehrt gerade ein Update durch",
    4008: "keine freien Event-Slots (max. 31 Live-Clients)",
}
# Codes, bei denen sofortiges Wiederholen nichts bringt bzw. schadet
# (Sperre wuerde verlaengert, Benutzer deaktiviert).
WS_CLOSE_NO_HAMMER = (4003, 4006)


_cb_errors = 0   # Callback-Fehler seit Prozessstart (nur zur Log-Drosselung)


def _log_cb_error(what: str, uuid: str) -> None:
    """Die ersten Fehler mit Traceback, danach nur noch Debug: ein dauerhaft
    fehlerhafter Callback wuerde sonst bei jedem Voll-Dump tausende Zeilen schreiben."""
    global _cb_errors
    _cb_errors += 1
    if _cb_errors <= 3:
        log.exception("%s-Callback fuer %s fehlgeschlagen", what, uuid)
    else:
        log.debug("%s-Callback fuer %s fehlgeschlagen", what, uuid, exc_info=True)


def describe_close(code: int | None) -> str:
    """Lesbarer Text zu einem WS-Close-Code (leer, wenn nichts Besonderes)."""
    if code is None:
        return ""
    return WS_CLOSE_REASONS.get(code, "")


# Ein Wetter-Eintrag: 5 * int32, dann 6 * double, ohne Padding.
_WX_ENTRY = struct.Struct("<5i6d")
_WX_FIELDS = ("ts", "type", "wind_dir", "radiation", "humidity",
              "temp", "feels", "dew", "precip", "wind", "pressure")


def format_uuid(b: bytes) -> str:
    d1 = struct.unpack("<I", b[0:4])[0]
    d2 = struct.unpack("<H", b[4:6])[0]
    d3 = struct.unpack("<H", b[6:8])[0]
    d4 = b[8:16].hex()
    return f"{d1:08x}-{d2:04x}-{d3:04x}-{d4}"


class LoxoneWS:
    def __init__(self, host: str, port: int, user: str, jwt: str,
                 hash_alg: str = "SHA1", verify_tls: bool = False, secure: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.jwt = jwt
        self.hash_alg = (hash_alg or "SHA1").upper()
        self.verify_tls = verify_tls
        self.secure = secure          # False = Gen1 (ws:// statt wss://)
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._last_rx = 0.0           # monotonic: letzte Nachricht vom Miniserver
        self.close_code: int | None = None   # WS-Close-Code der letzten Trennung
        self.out_of_service = False          # Miniserver hat Kennung 5 (Neustart/Update) gemeldet
        self._table_errors = 0               # uebersprungene Tabellen (nur fuer Log-Drosselung)

    def _ssl(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if not self.verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def connect(self) -> None:
        """Verbindung + Anmeldung, hart begrenzt auf HANDSHAKE_TIMEOUT_S."""
        try:
            await asyncio.wait_for(self._connect(), timeout=HANDSHAKE_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise ConnectionError(
                f"Miniserver antwortet beim Verbindungsaufbau nicht ({HANDSHAKE_TIMEOUT_S}s)"
            ) from None

    async def _connect(self) -> None:
        self._session = aiohttp.ClientSession()
        scheme = "wss" if self.secure else "ws"
        url = f"{scheme}://{self.host}:{self.port}/ws/rfc6455"
        log.info("WS verbinde %s", url)
        self._ws = await self._session.ws_connect(
            url, ssl=(self._ssl() if self.secure else None),
            protocols=["remotecontrol"], max_msg_size=0)

        # 1) getkey -> HMAC(token) -> authwithtoken
        key_hex = await self._cmd_value("jdev/sys/getkey")
        digestmod = hashlib.sha256 if self.hash_alg == "SHA256" else hashlib.sha1
        token_hash = hmac.new(bytes.fromhex(key_hex), self.jwt.encode(), digestmod).hexdigest()
        auth = await self._cmd_json(f"authwithtoken/{token_hash}/{self.user}")
        code = str((auth.get("LL") or {}).get("Code") or (auth.get("LL") or {}).get("code"))
        if code != "200":
            raise ConnectionError(f"authwithtoken fehlgeschlagen: {auth}")
        log.info("WS authentifiziert")

        # 2) Status-Updates einschalten (loest sofort einen Voll-Dump aus)
        await self._ws.send_str("jdev/sps/enablebinstatusupdate")

    async def _recv_text(self) -> str:
        assert self._ws is not None
        while True:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                continue  # 8-Byte-Header ueberspringen
            if msg.type == aiohttp.WSMsgType.TEXT:
                return msg.data
            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.ERROR):
                self.close_code = self._ws.close_code
                why = describe_close(self.close_code)
                raise ConnectionError(
                    f"WS geschlossen im Handshake ({msg.type}, Code {self.close_code}"
                    + (f": {why}" if why else "") + ")")

    async def _cmd_json(self, command: str) -> dict:
        assert self._ws is not None
        await self._ws.send_str(command)
        return json.loads(await self._recv_text())

    async def _cmd_value(self, command: str) -> str:
        payload = await self._cmd_json(command)
        return str((payload.get("LL") or {}).get("value") or "")

    async def stream(self, on_value: ValueCallback,
                     on_weather: WeatherCallback | None = None) -> None:
        """Empfaengt Status-Tabellen und ruft on_value(uuid, wert) je Aenderung.

        on_weather(uuid, eintraege) wird zusaetzlich gerufen, wenn die Anlage
        Wetterdaten schickt (nur mit Loxone-Wetterdienst)."""
        assert self._ws is not None
        self._last_rx = time.monotonic()
        ka = asyncio.create_task(self._keepalive())
        try:
            await self._receive_loop(on_value, on_weather)
        finally:
            ka.cancel()

    async def _keepalive(self) -> None:
        """Loxone-Protokoll: der Client meldet sich regelmaessig mit "keepalive"
        (Antwort: Header mit Kennung 6), sonst kann der Miniserver eine
        Verbindung ohne Client-Aktivitaet nach einigen Minuten schliessen.
        Kommt DEAD_S lang gar nichts zurueck (auch keine keepalive-Antwort), ist
        die Verbindung halb offen/tot: schliessen, damit der Aufrufer neu verbindet
        statt mit eingefrorenen Werten weiterzulaufen."""
        while self._ws is not None and not self._ws.closed:
            await asyncio.sleep(KEEPALIVE_S)
            if time.monotonic() - self._last_rx > DEAD_S:
                log.warning("Miniserver antwortet seit %ds nicht -> Verbindung wird neu aufgebaut",
                            int(time.monotonic() - self._last_rx))
                try:
                    await asyncio.wait_for(self._ws.close(), 5)   # halb offen: nicht ewig auf close warten
                except Exception:
                    pass
                return
            try:
                await self._ws.send_str("keepalive")
            except Exception as err:
                log.debug("keepalive nicht gesendet: %s", err)
                return

    async def _receive_loop(self, on_value: ValueCallback,
                            on_weather: WeatherCallback | None) -> None:
        assert self._ws is not None
        pending_ident: int | None = None
        seen_unknown: set[int] = set()
        async for msg in self._ws:
            self._last_rx = time.monotonic()
            if msg.type == aiohttp.WSMsgType.BINARY:
                data = msg.data
                if len(data) == 8 and data[0] == 0x03:
                    # Kennung 6 = keepalive-Antwort: nur Header, keine Nutzdaten
                    if data[1] == 5:
                        # Out-of-Service: Miniserver startet neu / wird aktualisiert.
                        # Es folgt KEIN Payload, danach schliesst er die Verbindung
                        # (Loxone-Doku). Nur vermerken, der Reconnect laeuft ueber
                        # das normale Verbindungsende.
                        self.out_of_service = True
                        log.info("Miniserver meldet Out-of-Service (Neustart/Update) "
                                 "- Verbindung wird gleich getrennt")
                        pending_ident = None
                        continue
                    pending_ident = None if data[1] == 6 else data[1]
                    continue
                ident, pending_ident = pending_ident, None
                if ident in (2, 3, 7):
                    # Ein kaputtes/unerwartetes Paket oder ein Fehler im Callback darf
                    # nicht die ganze Verbindung samt Voll-Dump kippen: Tabelle
                    # verwerfen, melden, weiterlesen (vgl. PyLoxone #517).
                    try:
                        if ident == 2:
                            self._parse_values(data, on_value)
                        elif ident == 3:
                            self._parse_texts(data, on_value)
                        elif on_weather is not None:
                            self._parse_weather(data, on_weather)
                    except Exception as err:
                        self._table_errors += 1
                        if self._table_errors <= 3:
                            log.warning("WS-Tabelle (Kennung %s, %d Byte) uebersprungen: %s",
                                        ident, len(data), err, exc_info=True)
                        else:
                            log.debug("WS-Tabelle (Kennung %s) uebersprungen: %s", ident, err)
                elif ident is not None and ident not in seen_unknown:
                    # Einmal pro Verbindung melden: sonst bliebe unbemerkt, dass
                    # der Miniserver eine Tabelle schickt, die hier keiner liest.
                    seen_unknown.add(ident)
                    log.info("WS-Tabelle mit unbekannter Kennung %s (%d Byte) ignoriert",
                             ident, len(data))
            elif msg.type == aiohttp.WSMsgType.TEXT:
                pending_ident = None  # Kommando-Antwort im Stream ignorieren
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                log.warning("WS-Stream beendet (%s)", msg.type)
                break
        # aiohttp beendet die Iteration bei Close ohne weitere Nachricht: Code merken,
        # damit der Aufrufer begruendet (und passend lange) wartet.
        self.close_code = self._ws.close_code

    @staticmethod
    def _parse_values(data: bytes, on_value: ValueCallback) -> None:
        for off in range(0, len(data) - 23, 24):
            uuid = format_uuid(data[off:off + 16])
            val = struct.unpack("<d", data[off + 16:off + 24])[0]
            try:
                on_value(uuid, val)
            except Exception:
                # Fehler fuer EINE UUID darf die restlichen Werte der Tabelle nicht kosten.
                _log_cb_error("Wert", uuid)

    @staticmethod
    def _parse_weather(data: bytes, on_weather: WeatherCallback) -> None:
        """Wetter-Tabelle (Kennung 7) in Eintragslisten je UUID zerlegen.

        Aufbau siehe Modul-Docstring. Laengen werden vor jedem Zugriff geprueft:
        ein abgeschnittenes oder unerwartet aufgebautes Paket wird verworfen,
        nicht halb gelesen."""
        off = 0
        while off + 24 <= len(data):
            uuid = format_uuid(data[off:off + 16])
            count = struct.unpack("<i", data[off + 20:off + 24])[0]
            off += 24
            if count < 0 or off + count * _WX_ENTRY.size > len(data):
                log.warning("Wetter-Tabelle unplausibel (%s Eintraege, %d Byte Rest) — verworfen",
                            count, len(data) - off)
                return
            entries = []
            for _ in range(count):
                entries.append(dict(zip(_WX_FIELDS, _WX_ENTRY.unpack_from(data, off))))
                off += _WX_ENTRY.size
            on_weather(uuid, entries)

    @staticmethod
    def _parse_texts(data: bytes, on_value: ValueCallback) -> None:
        off = 0
        while off + 36 <= len(data):
            uuid = format_uuid(data[off:off + 16])
            tlen = struct.unpack("<I", data[off + 32:off + 36])[0]
            text = data[off + 36:off + 36 + tlen].decode("utf-8", "replace")
            try:
                on_value(uuid, text)
            except Exception:
                _log_cb_error("Text", uuid)
            off += (36 + tlen + 3) & ~3  # auf 4-Byte-Grenze aufrunden

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()
        self._ws = self._session = None
