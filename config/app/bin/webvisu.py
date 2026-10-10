#!/usr/bin/env python3
"""LoxPanel Live-Web-Visu (Phase 3) — Navigations-Shell.

Baut die Loxone-App-Navigation nach, aber aufgeraeumt fuers 480x480-Panel:
kompakter Kopf (Titel + Uhr), 2x2-Kacheln, unten 4 Tabs
(Favoriten / Zentral / Raeume / Kategorien). Licht ist voll ausgebaut:
Kategorie/Raum/Zentral -> Raum-Lichtcontroller -> Stimmungen.

Client<->Server (WebSocket, JSON):
  Client: {t:'nav', route:{...}}     Server: {t:'view', ...}
  Client: {t:'cmd', uuid, cmd}

Start:  python webvisu.py   ->  http://localhost:8099
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import contextlib
import copy
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import re
import shlex
import shutil
import struct
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import ssl as _ssl
from urllib.parse import quote, unquote, urlencode, urlparse

import aiohttp
from aiohttp import WSMsgType, web

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loxone_api import LoxoneClient  # noqa: E402
from loxone_ws import LoxoneWS, WS_CLOSE_NO_HAMMER, describe_close  # noqa: E402


def _ms_https(port) -> bool:
    """Schema-Wahl fuer den Miniserver: Loxone Gen1 spricht nur HTTP (Port 80),
    Gen2+ nutzt HTTPS/TLS (443, …). Port 80 -> HTTP/ws, sonst HTTPS/wss."""
    try:
        return int(port) != 80
    except (TypeError, ValueError):
        return True


def _make_client(host, user, password, port, verify_tls) -> LoxoneClient:
    """LoxoneClient bauen und bei Gen1 (Port 80) auf HTTP umstellen – die
    loxone_api setzt die Basis-URL sonst fest auf https://…"""
    c = LoxoneClient(host=host, user=user, password=password, port=port, verify_tls=verify_tls)
    if not _ms_https(port):
        c.base_url = f"http://{host}:{port}/"
    return c
from adapters import JalousieAdapter, LightControllerV2Adapter  # noqa: E402
from audioserver import make_backend, AudioBackend  # noqa: E402
from audioserver_events import AudioEventClient  # noqa: E402
import front_info  # noqa: E402  # Kalender (iCal-Abos) + Wetter (Open-Meteo) fuer die Front
import loxone_weather  # noqa: E402  # Wetter vom Loxone-Wetterserver (Vorrang vor Open-Meteo)
import theme_colors  # noqa: E402  # Panel-Theme aus einer Grundfarbe herleiten

log = logging.getLogger("loxpanel.webvisu")

# Vom Docker-Image ausgefuehrter Code-Stand, unabhaengig von der Plugin-Version
# in plugin.cfg (die liegt AUSSERHALB des Docker-Build-Kontexts, der Container
# kennt sie nicht). Bei jedem Release-Bump hier mitziehen - einziger
# zuverlaessiger Weg zu pruefen, ob ein Update den Container tatsaechlich neu
# gebaut hat (z.B. bei einem haengenden Docker-Build-Cache).
APP_VERSION = "0.19.112"
_WEB = Path(__file__).resolve().parent.parent / "webfrontend" / "html"
HTML = _WEB / "panel.html"
CONFIG_HTML = _WEB / "config.html"
SETTINGS_HTML = _WEB / "settings.html"
I18N_JS = _WEB / "i18n.js"
INSTALL_SH = Path(__file__).resolve().parent.parent / "deploy" / "install-agent.sh"
_CFGDIR = Path(__file__).resolve().parent.parent / "config"
PANELS_FILE = _CFGDIR / "panels.json"
# Gelerntes Licht je Lichtszene (Helligkeit + Farbe), s. App._scene_light_learn
SCENE_LIGHT_FILE = _CFGDIR / "scene_light.json"
CFG_FILE = _CFGDIR / "loxpanel.cfg"
CFG_EXAMPLE = _CFGDIR / "loxpanel.cfg.example"
# Eigene Klingelton-Dateien (Upload je Intercom) - persistiert im selben
# Volume wie loxpanel.cfg/panels.json, ueberlebt also Updates/Neustarts.
SOUNDS_DIR = _CFGDIR / "sounds"
BG_DIR = _CFGDIR / "bg"                 # eigene Dashboard-Hintergrundbilder je Panel (<id>.<ext>)
_BG_MAX_BYTES = 12 * 1024 * 1024
_BG_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def bg_file(pid: str):
    """Gespeichertes Hintergrundbild eines Panels (oder None)."""
    if not pid or not re.match(r"^[a-z0-9_-]{1,40}$", pid) or not BG_DIR.is_dir():
        return None
    for ext in _BG_TYPES:
        f = BG_DIR / f"{pid}.{ext}"
        if f.is_file():
            return f
    return None


def bg_url(pid: str) -> str:
    """URL des Hintergrundbilds mit Versions-Anhang (neues Bild = neue URL)."""
    f = bg_file(pid)
    return f"/bg/{pid}?v={int(f.stat().st_mtime)}" if f else ""
# Android-Panel-Launcher (android/panel-launcher, fertig gebaut) und der
# adb-Schluessel: der Schluessel liegt im Config-Volume, damit das einmal auf
# dem Panel bestaetigte "USB-Debugging zulassen" Container-Updates ueberlebt.
LAUNCHER_APK = Path(__file__).resolve().parent.parent / "android" / "LoxPanel-Launcher.apk"
LAUNCHER_PKG = "de.loxpanel.launcher"
LAUNCHER_VERSION_FILE = LAUNCHER_APK.with_suffix(".version")   # versionCode, schreibt build.sh
ADB_HOME = _CFGDIR / "adb"
FULLY_DIR = ADB_HOME / "fully"   # geladene / hochgeladene Fully-Kiosk-APKs
_SOUND_EXT_BY_MIME = {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/ogg": "ogg",
                      "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
                      "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac"}
_SOUND_MIME_BY_EXT = {"mp3": "audio/mpeg", "ogg": "audio/ogg", "wav": "audio/wav",
                      "m4a": "audio/mp4", "aac": "audio/aac"}
_SOUND_MAX_BYTES = 5 * 1024 * 1024   # 5 MB reichen locker fuer einen kurzen Klingelton
_UUID_RE = re.compile(r"^[0-9a-fA-F-]{4,64}$")


def _sound_file_for(uuid: str) -> Path | None:
    """Eigene Klingelton-Datei fuer eine Intercom-UUID, falls hochgeladen."""
    if not uuid or not _UUID_RE.match(uuid) or not SOUNDS_DIR.is_dir():
        return None
    for ext in _SOUND_MIME_BY_EXT:
        p = SOUNDS_DIR / f"{uuid}.{ext}"
        if p.is_file():
            return p
    return None


def _load_cfg() -> dict:
    for f in (CFG_FILE, CFG_EXAMPLE):
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return {}


def _atomic_write(path: Path, text: str) -> None:
    """Schreibt text atomar: erst nach <datei>.tmp, fsync, dann os.replace, zum
    Schluss fsync auf das Verzeichnis (macht auch das Umbenennen dauerhaft). Ein
    Crash/Stromausfall mitten im Schreiben laesst so die alte, vollstaendige
    Datei stehen statt einer halben, kaputten (F5). Die .tmp wird bei einem
    Fehler wieder entfernt, damit keine Bruchstuecke liegen bleiben."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    try:                       # Verzeichnis-fsync: macht os.replace dauerhaft
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass                   # nicht auf jeder Plattform/FS moeglich, best effort


def _write_cfg(cfg: dict) -> None:
    _atomic_write(CFG_FILE, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
LIGHT = LightControllerV2Adapter()
JAL = JalousieAdapter()

SWITCHY = {"Switch"}   # TimedSwitch wird eigen behandelt (anderer State)
VALID_TABS = ["favoriten", "zentral", "raeume", "kategorien"]
SEC_ALARM_TYPES = ("Alarm", "SmokeAlarm")   # Vollbild bei Ausloesung (s. sec_alarm_msg)
# Display-Treiber fuer Kiosk-Apps (Android) mit Standard-Port ihrer HTTP-Schnittstelle
DISPLAY_DRIVERS = {"fully": 2323, "wallpanel": 2971}
# Geraetetypen (wie "Unterstuetzte Geraete" in der Config): Betriebssystem
# bestimmt, was sich fernsteuern laesst - Android per adb (Fully neu starten,
# Geraet neu starten), Shelly zusaetzlich per eigener Schnittstelle, Linux per Agent.
DEVICE_MODELS = {
    # scale: Vorgabe-Zoom (auto = 480er-Raster gleichmaessig auf den Schirm),
    # wake: Wach-Sperre der Seite (Browser ohne Kiosk-App), tips: Hinweise unter
    # Einrichtung (Konfigurator). Eigenheiten je Geraet stehen in den Tipps.
    "shelly-x2": {"label": "Shelly Wall Display X2 / X2i", "os": "android", "shelly": True, "scale": "auto",
                  "panes": 2,
                  "tips": ["Querformat, 2 Panels nebeneinander (Profil: Panel-Größe „2 Panels“).",
                           "Fully Kiosk + LoxPanel-Launcher: Gerät hinzufügen → Automatisch einrichten per ADB.",
                           "Display aus/an über Fully (JavaScript-Schnittstelle einschalten)."]},
    "shelly-x1": {"label": "Shelly Wall Display X1i", "os": "android", "shelly": True, "scale": "auto",
                  "panes": 1,
                  "tips": ["720×720 – Zoom „Automatisch“ vergrößert das 480er-Raster auf den ganzen Schirm.",
                           "Profil: Panel-Größe „1 Panel“.",
                           "Fully Kiosk + LoxPanel-Launcher per ADB (Gerät hinzufügen)."]},
    "nspro86": {"label": "Sonoff NSPanel Pro 86", "os": "android", "scale": "off", "panes": 1,
                "tips": ["480×480 – passt 1:1, kein Zoom nötig. Profil: „1 Panel“.",
                         "Kiosk-App (Fully) mit Start-URL inkl. ?device=… einrichten."]},
    "nspro120": {"label": "Sonoff NSPanel Pro 120", "os": "android", "scale": "auto", "panes": 1,
                 "tips": ["Hochformat – Zoom „Automatisch“ füllt die Breite. Profil: „1 Panel“.",
                          "Kiosk-App (Fully) mit Start-URL inkl. ?device=… einrichten."]},
    "sm41-android": {"label": "4″-Standardpanel YC-SM41 (Android)", "os": "android", "scale": "off", "panes": 1,
                     "tips": ["480×480 – Referenzgröße, kein Zoom. Profil: „1 Panel“."]},
    "sm41-debian": {"label": "4″-Standardpanel YC-SM41 (Debian + Agent)", "os": "linux", "scale": "off", "panes": 1,
                    "tips": ["480×480 – Referenzgröße. Agent per SSH (Gerät hinzufügen → Linux-Panel);",
                             "Display und Neustart übernimmt der Agent."]},
    "sm55": {"label": "YC-SM55P", "os": "android", "scale": "auto", "panes": 2,
             "tips": ["720×1280 quer – Zoom „Automatisch“, Profil: „2 Panels“.",
                      "LAN/PoE: feste IP im Router vergeben (für ADB/Fully)."]},
    "tablet": {"label": "Android-Tablet (7–10″)", "os": "android", "scale": "auto", "wake": True, "panes": 2,
               "tips": ["Querformat, Profil: „2 Panels“; Zoom „Automatisch“ füllt den Schirm.",
                        "Mit Fully Kiosk: Display aus/an und Autostart; ohne Fully hält die Seite den Schirm wach, bis die Leerlaufzeit abläuft.",
                        "Hochkant zeigt das Tablet ein Panel; unter 600 px Breite greift der Handy-Modus."]},
    "ipad": {"label": "iPad / iPad mini", "os": "browser", "scale": "auto", "wake": True, "panes": 2,
             "tips": ["Safari: Teilen → „Zum Home-Bildschirm“ – startet ohne Adressleiste als Vollbild-App (Start-URL mit ?device=…).",
                      "Querformat, Profil: „2 Panels“; Zoom „Automatisch“ füllt den Schirm (iPad mini ≈ 118 %).",
                      "Die Seite hält den Schirm wach bis zur Leerlaufzeit (Display & Nacht); danach greift die iOS-Sperre.",
                      "Für Wandbetrieb: Einstellungen → Bedienungshilfen → Geführter Zugriff (App fixieren), Automatische Sperre nach Wunsch.",
                      "Ton (Klingel) erst nach einmaligem Antippen – iOS gibt Audio nur nach Berührung frei."]},
    "phone": {"label": "Smartphone", "os": "browser", "scale": "off", "panes": 1,
              "tips": ["Als App installieren: iPhone Safari → Teilen → „Zum Home-Bildschirm“, Android Chrome → Menü → „App installieren“.",
                       "Profil: Panel-Größe „Handy“ (Tabs unten, volle Höhe); hochkant greift der Handy-Modus auch automatisch."]},
    "other": {"label": "Anderes Gerät / PC-Browser", "os": "browser", "scale": "off",
              "tips": ["Fenstergröße bestimmt die Ansicht; Zoom bei Bedarf manuell setzen."]},
}
# Skalierung je Geraet: "off" | "auto" | Faktor. Die Visu rechnet mit festen
# 240er Kacheln (2 Panels = 960x480); auf groesseren Schirmen (7"-Tablet,
# iPad mini) zoomt sie gleichmaessig hoch, statt mit Rand zu stehen.
SCALE_MIN, SCALE_MAX = 0.5, 3.0


def _clean_scale(v):
    """"off" | "auto" | Zahl in [SCALE_MIN, SCALE_MAX] (deutsches Komma erlaubt);
    Ungueltiges -> None (= nicht gesetzt)."""
    if isinstance(v, str):
        v = v.strip().lower()
        if v in ("off", "auto"):
            return v
        try:
            v = float(v.replace(",", "."))
        except ValueError:
            return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return None
    return round(min(SCALE_MAX, max(SCALE_MIN, float(v))), 2)


# ---- Geraete-Erkennung ----
# Jede Visu meldet beim Verbinden eine dauerhafte Kennung (uid) und einen
# Steckbrief (Bildschirm, Browser, Betriebssystem, Hardware; bei Fully Kiosk
# auch Hersteller/Modell/Android-ID/MAC). Browser kennen keine MAC-Adresse und
# die IP wechselt - Standard ist daher eine zufaellige ID, die das Geraet selbst
# speichert (localStorage + Cookie); Fully liefert eine feste Geraete-ID. Der
# Server merkt sich uid -> Name in config/devinfo.json, erkennt den Geraetetyp
# und legt das Geraet beim ersten Mal mit passenden Einstellungen an.
DEVINFO_FILE = Path(__file__).resolve().parent.parent / "config" / "devinfo.json"
_UID_RE = re.compile(r"^[A-Za-z0-9._:-]{6,80}$")


def _clean_devinfo(d) -> dict:
    """Steckbrief vom Client pruefen: nur bekannte Felder, kurze Strings/Zahlen."""
    if not isinstance(d, dict):
        return {}
    out: dict = {}
    for k in ("ua", "plat", "pver", "model", "lang", "tz", "arch", "orient"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:300 if k == "ua" else 60]
    for k in ("sw", "sh", "vw", "vh", "dpr", "touch", "cores", "mem"):
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 100000:
            out[k] = round(float(v), 2) if k == "dpr" else int(v)
    for k in ("mob", "pwa"):
        if isinstance(d.get(k), bool):
            out[k] = d[k]
    f = d.get("fully")
    if isinstance(f, dict):
        fo = {k: str(f.get(k)).strip()[:60] for k in ("manuf", "model", "android", "ver", "mac", "devid", "ssid")
              if f.get(k) not in (None, "") and str(f.get(k)).strip()}
        if fo:
            out["fully"] = fo
    return out


def _ua_parts(info: dict) -> tuple[str, str]:
    """(Betriebssystem, Browser) aus User-Agent/Client-Hints, kurz und lesbar."""
    ua = info.get("ua", "")
    touch = info.get("touch", 0) or 0
    if info.get("fully"):
        osn = "Android " + info["fully"].get("android", "") if info["fully"].get("android") else "Android"
        return osn.strip(), "Fully Kiosk " + info["fully"].get("ver", "")
    if "iPad" in ua or ("Macintosh" in ua and touch > 1):
        osn = "iPadOS"
    elif "iPhone" in ua:
        osn = "iOS"
    elif "Android" in ua:
        m = re.search(r"Android ([\d.]+)", ua)
        osn = "Android " + (m.group(1) if m else "")
    elif "Windows" in ua:
        osn = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        osn = "macOS"
    elif "CrOS" in ua:
        osn = "ChromeOS"
    elif "Linux" in ua:
        osn = "Linux"
    else:
        osn = info.get("plat", "") or "unbekannt"
    pv = (info.get("pver") or "").split(".")
    if osn == "macOS" and pv[0] and pv[0] != "0" and not info.get("fully"):
        osn += " " + pv[0] + ("." + pv[1] if len(pv) > 1 and pv[1] != "0" else "")
    if "wv)" in ua or "; wv" in ua:
        br = "WebView"
    elif "Edg/" in ua:
        br = "Edge"
    elif "Firefox/" in ua or "FxiOS" in ua:
        br = "Firefox"
    elif "CriOS" in ua or ("Chrome/" in ua and "Chromium" not in ua):
        br = "Chrome"
    elif "Chromium" in ua:
        br = "Chromium"
    elif "Safari/" in ua:
        br = "Safari"
    else:
        br = "Browser"
    return osn.strip(), br


def guess_device_model(info: dict) -> str:
    """Geraetetyp (DEVICE_MODELS-Schluessel) aus dem Steckbrief schaetzen."""
    f = info.get("fully") or {}
    man = (f.get("manuf") or "").lower()
    mdl = (f.get("model") or info.get("model") or "").lower()
    ua = info.get("ua", "")
    sw, sh = info.get("sw", 0) or 0, info.get("sh", 0) or 0
    square = sw and sh and abs(sw - sh) <= 8
    short = min(sw, sh) if sw and sh else 0
    if "shelly" in man or "shelly" in mdl or mdl.startswith("sawd") or "wall display" in mdl:
        return "shelly-x1" if square else "shelly-x2"
    if "sonoff" in man or "itead" in man or "nspanel" in mdl:
        return "nspro86" if square else "nspro120"
    if "rk3566" in mdl or "sm55" in mdl:
        return "sm55"
    if "iPad" in ua or ("Macintosh" in ua and (info.get("touch") or 0) > 1):
        return "ipad"
    if "iPhone" in ua:
        return "phone"
    if "Android" in ua or f:
        if square and short <= 520:
            return "sm41-android"
        if (info.get("mob") or "Mobile" in ua) and short and short < 600:
            return "phone"
        return "tablet"
    if "Linux" in ua and square and short <= 520:
        return "sm41-debian"
    return "other"


def device_auto_name(info: dict) -> str:
    """Lesbarer Vorschlag fuer ein neu erkanntes Geraet."""
    model = guess_device_model(info)
    if model == "other":
        osn, br = _ua_parts(info)
        return f"{br} ({osn})"
    if model == "phone":
        return "iPhone" if "iPhone" in info.get("ua", "") else "Android-Handy"
    if model == "ipad":
        return "iPad"
    return DEVICE_MODELS[model]["label"].split(" / ")[0].split(" (")[0]


def _server_tz() -> str:
    """IANA-Zeitzone des Servers (TZ oder /etc/localtime-Link). /etc/timezone
    NICHT: im Container stammt sie aus dem Image ("Etc/UTC"), waehrend die
    echte Zeit ueber das gemountete /etc/localtime des LoxBerry kommt."""
    tz = os.environ.get("TZ", "").strip().lstrip(":")
    if tz and "/" in tz:
        return tz
    try:
        lk = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in lk:
            return lk.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return ""


_SRV_TZ = _server_tz()


def _code_build() -> str:
    """Kennung des ausgelieferten Oberflaechen-Codes (Version + Aenderungszeit
    der Panel-Datei). Aendert sie sich (Update), laden offene Panels neu."""
    try:
        mt = int((Path(__file__).resolve().parent.parent / "webfrontend" / "html" / "panel.html").stat().st_mtime)
    except OSError:
        mt = 0
    return f"{APP_VERSION}-{mt}"


_BUILD = _code_build()


def server_clock() -> dict:
    """Serverzeit fuer die Panels: ms seit 1970, Zeitzone, UTC-Abstand (Minuten),
    dazu die Code-Kennung (build) fuer das automatische Neuladen nach Updates."""
    off = datetime.now().astimezone().utcoffset()
    return {"now": int(time.time() * 1000), "tz": _SRV_TZ, "build": _BUILD,
            "utcoff": int(off.total_seconds() // 60) if off is not None else 0}


def load_devinfo() -> dict:
    try:
        d = json.loads(DEVINFO_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


# Nachtmodus: Rueckfall-Fenster, wenn keine Sonnenzeiten vorliegen (kein Wetter
# konfiguriert). Sobald Sonnenauf-/-untergang bekannt sind, gelten die.
NIGHT_FROM, NIGHT_TO = "22:00", "06:00"


_FREE_TAB = re.compile(r"^free:[a-z0-9]{1,12}$")
# Weitere Instanzen von Uebersicht/Zentral (z.B. zwei Raum-Uebersichten "EG"/"OG")
_MULTI_TAB = re.compile(r"^(raeume|kategorien|zentral):[a-z0-9]{1,12}$")


def _tab_base(t) -> str:
    """Grundtyp eines Tabs: "raeume:ab12" -> "raeume"; sonst unveraendert."""
    return t.split(":", 1)[0] if isinstance(t, str) and _MULTI_TAB.match(t) else t


def _is_tab(t) -> bool:
    """Gueltiges Tab-Kennzeichen: einer der 4 Standard-Tabs, eine einzelne
    Kategorie bzw. ein einzelner Raum als Direkt-Tab (`cat:<uuid>`/`room:<uuid>`)
    ODER ein frei belegter Tab (`free:<id>`)."""
    if t in VALID_TABS:
        return True
    if not isinstance(t, str):
        return False
    return ((t.startswith("cat:") and len(t) > 4)
            or (t.startswith("room:") and len(t) > 5)
            or bool(_FREE_TAB.match(t)) or bool(_MULTI_TAB.match(t)))


def _is_layout_tab(t) -> bool:
    """Tabs mit frei belegbarem Kachel-Raster (Editor wie das Dashboard):
    Frei (favoriten/free:), Raum, Kategorie, Zentral und die Uebersichten
    "raeume"/"kategorien" (Raum- bzw. Kategorie-Kacheln, antippen oeffnet sie)."""
    return _tab_base(t) in ("favoriten", "zentral", "raeume", "kategorien") or (isinstance(t, str) and (
        t.startswith("room:") or t.startswith("cat:") or bool(_FREE_TAB.match(t))))
# Reine Anzeige-Bausteine: keine Steuer-2.-Ebene -> Antippen zeigt eine
# grosse 1/1-Wertseite (_view_control -> _big_view).
STATUS_BIG = {"Meter", "InfoOnlyAnalog", "TextState", "InfoOnlyText",
              "InfoOnlyDigital", "SmokeAlarm", "PresenceDetector",
              "ClimateControllerUS", "Hourcounter"}
# Verlaufs-Diagramme fuer Bausteine mit `statistic` in der Struktur. Die Daten
# liegen am Miniserver als Monatsdateien /stats/<uuidAction>.<JJJJMM>.xml (so
# listet sie /stats/, und so fuehrt sie die Loxone-App: STATISTIC-Befehle in
# scripts4.js, ermittelt mit bin/statistic_probe.py). Der Zeitraum laeuft in der
# Route mit: {"view": "control", "id": uuid, "range": "7d"}.
STAT_RANGES = {"24h": ("24 h", 86400), "7d": ("7 Tage", 7 * 86400), "30d": ("30 Tage", 30 * 86400)}
STAT_DEFAULT_RANGE = "24h"
STAT_MAX_POINTS = 240    # Punkte je Linie nach dem Ausduennen (Diagramm ~440 px breit)
STAT_REFRESH = 300       # Monatsdatei, die noch waechst, nach so vielen Sekunden neu holen
STAT_RETRY = 60          # nach einem Abruffehler fruehestens wieder versuchen
STAT_CACHE_MAX = 240     # Monatsdateien im Speicher (abgeschlossene Monate aendern sich nicht)
STAT_ROWS_MAX = 1_500_000  # zusaetzlich: Messpunkte gesamt (Minutenwerte sind ~40k je Monat) - Speicher auf dem Pi


def _rows_total(entries, idx: int) -> int:
    return sum(len(e[idx] or ()) for e in entries)
# visuType der Statistik-Ausgaenge, wie an der Anlage beobachtet: 0 Analogwert
# (Temperatur, Leistung ...), 1 Digitalwert (Regen, Sonnenschein), 2 Zaehlerstand
# (Gesamtverbrauch kWh). Zaehlerstaende zeigen den Verbrauch je Stunde/Tag als Balken.
STAT_KIND = {1: "digital", 2: "counter"}
# Darstellung des Mini-Verlaufs in der Kachel (tiles.<uuid>.chartStyle). Fehlt der
# Schluessel, gilt "trend". Tagesmuster und Tagesspanne zeigen immer 7 Tage.
STAT_TILE_STYLES = ("trend", "pattern", "span")
STAT_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
# Anfragen an den Miniserver (Befehle, Verlaeufe, Icons) tragen das Token der
# Anmeldung. Es laeuft nach einiger Zeit ab, die WebSocket-Verbindung fuer die
# Anzeige braucht es danach aber nicht mehr - ohne Erneuerung zeigte das Panel
# nach 1-2 Tagen weiter Werte an, nahm aber keine Befehle mehr an. Meldet der
# Miniserver 401, meldet _ms_http() sich neu an und wiederholt die Anfrage.
MS_CMD_TIMEOUT = 10      # s: ein Befehl blockiert solange die Nachrichten seines Panels
TOKEN_RENEW_MIN = 60     # s: nicht oefter neu anmelden (401 kann auch fehlende Rechte heissen)
MS_OFFLINE_GRACE = 10   # s: so lange darf der Miniserver weg sein, bevor die Panels es anzeigen
MS_RETRY = (5, 10, 20, 40, 60)   # s: Wartezeiten zwischen Verbindungsversuchen zum Miniserver
# Wartezeiten, wenn der Miniserver die ANMELDUNG ablehnt (401/403/423, WS-Close 4003/4006).
# Ein Minutentakt waere dauerhaftes Passwort-Raten: der Miniserver sperrt nach zu vielen
# Fehlversuchen (Close-Code 4003) - und das trifft dann auch die Loxone-App. Neue
# Zugangsdaten ueber /settings wecken die Schleife sofort (siehe _retry_now).
MS_RETRY_AUTH = (300, 900, 1800)   # s
_AUTH_REJECT_RE = re.compile(r"\b(?:status|HTTP|code=)\s*(401|403|423)\b")


def _auth_rejected(err: BaseException | None) -> bool:
    """True, wenn der Miniserver die Zugangsdaten/den Benutzer abgelehnt hat.
    Bewusst nur die Fehlerklassen der loxone_api (kein WS-'authwithtoken 401':
    das ist ein normal abgelaufenes Token, das _reauth ohnehin erneuert) und nur
    echte Ablehnungs-Codes - 5xx/503 beim Miniserver-Neustart gehoeren NICHT dazu."""
    if err is None or type(err).__name__ not in ("LoxoneAuthError", "LoxoneRequestError"):
        return False
    return bool(_AUTH_REJECT_RE.search(str(err)))


def _ms_reason_code(rejected: bool, close_code: int | None, out_of_service: bool) -> str:
    """Kurzer Grund-Code fuer die Anzeige (Texte stehen in config.html):
    blocked/disabled/auth = Anmeldung abgelehnt, update = Miniserver aktualisiert/startet,
    slots = keine Live-Slots frei, user_changed = Benutzer geaendert, net = sonstiges."""
    if close_code == 4003:
        return "blocked"
    if close_code == 4006:
        return "disabled"
    if rejected:
        return "auth"
    if close_code == 4007 or out_of_service:
        return "update"
    if close_code == 4008:
        return "slots"
    if close_code in (4004, 4005):
        return "user_changed"
    return "net"
WIDGET_CAM_FPS = 5        # Bilder/s fuer Kamera-Widgets (Dashboard); Klingel-Vollansicht ungebremst
ICON_CACHE_MAX = 800     # Icons im Speicher (Loxone-SVGs, je wenige KB)
COVER_TIMEOUT = 10       # s: Albumcover vom Audioserver/aus dem Netz (sonst haengt die Anfrage offen)
FRONT_INTERVAL = 900     # s: Kalender + Open-Meteo so oft neu holen; Wetter-Pushes dazwischen ohne Abruf
# Reine Wert-/Analog-Anzeigen (kein an/aus) -> keine Kategorie-Ampel, neutral.
_ANALOG = {"InfoOnlyAnalog", "Slider", "Meter", "TextState", "InfoOnlyText", "Hourcounter",
           "EFM", "EnergyManager2", "PvProductionForecast", "SteakThermo"}
# Betriebsarten des Sauna-Bausteins (State "mode", 0..6), Zuordnung aus der
# offiziellen Loxone-Sauna-Dokumentation. Als Klartext auf Kachel und Detailseite.
SAUNA_MODES = {0: "Manuell", 1: "Finnisch manuell", 2: "Feuchte manuell",
               3: "Finnische Sauna", 4: "Kräutersauna", 5: "Sanftdampfbad", 6: "Warmluftbad"}
# Alte Raumregelung (IRoomController, v1) laut Loxone-Strukturdoku: Nummern der
# Temperaturen fuer settemp/starttimer und currHeatTempIx/currCoolTempIx. Die
# Struktur liefert dazu je Nummer einen State (Liste "temperatures") und in
# details.temperatures, ob der Wert absolut ist oder von Komfort abhaengt.
IRC1_TEMPS = {0: "Eco", 1: "Komfort Heizen", 2: "Komfort Kühlen", 3: "Haus leer",
              4: "Hitzeschutz", 5: "Erhöhte Wärme", 6: "Party", 7: "Manuell"}
IRC1_ECO, IRC1_KOMFORT_HEIZEN, IRC1_KOMFORT_KUEHLEN = 0, 1, 2
# State "mode": 2 = Autopilot kuehlt gerade, 4 = Autopilot Kuehlen, 6 = Manuell
# Kuehlen; alle anderen Betriebsarten heizen (bzw. 0 = keine Periode aktiv).
IRC1_KUEHL_MODI = {2, 4, 6}
# 5 = Manuell Heizen, 6 = Manuell Kuehlen: dann gilt die manuelle Temperatur.
IRC1_MANUELL_MODI, IRC1_MANUELL = {5, 6}, 7
# Eco/Komfort-Knoepfe halten die Temperatur so lange wie der Override beim V2.
IRC1_TIMER_S = 3600
# Betriebsart der alten Raumregelung, waehlbar per mode/<Nr> (Loxone-Strukturdoku):
# 1 und 2 ("Automatik, heizt/kuehlt gerade") meldet nur der State, gesendet
# werden 3 und 4. details.restrictedToMode: 1 = nur Kuehlen, 2 = nur Heizen.
IRC1_BETRIEBSARTEN = {0: "Automatik", 3: "Automatik Heizen", 4: "Automatik Kühlen",
                      5: "Manuell Heizen", 6: "Manuell Kühlen"}
IRC1_NUR_KUEHLEN, IRC1_NUR_HEIZEN = 1, 2
# Betriebsart des IRoomControllerV2 (State operatingMode, setOperatingMode/<Nr>),
# Bedeutung wie in der openHAB-Loxone-Anbindung; 3..5 sind manuell.
IRC2_BETRIEBSARTEN = {0: "Automatik Heizen & Kühlen", 1: "Automatik nur Heizen",
                      2: "Automatik nur Kühlen", 3: "Manuell Heizen & Kühlen",
                      4: "Manuell nur Heizen", 5: "Manuell nur Kühlen"}
IRC2_MANUELL = {3, 4, 5}


def _kurz_modus(nm):
    """Modusname fuer Pillen: "Eco-Temperatur" -> "Eco", "Komfort-Temperatur" -> "Komfort"."""
    low = (nm or "").lower()
    return "Eco" if "eco" in low else ("Komfort" if "komfort" in low else (nm or ""))

# Bausteintypen, die nur teilweise umgesetzt sind (Anzeige ohne volle Bedienung);
# Grundlage fuer den Status in /api/types. Vollstaendig = Kachel hat nav/cmd/
# controls/sublabel, unbekannt = nichts davon (tote Kachel).
PARTIAL_TYPES = {"AudioZone", "AlarmClock", "Intercom", "TextInput", "UpDownAnalog", "Ventilation",
                 "Irrigation"}   # Irrigation: nur Anzeige (keine Bedienung)
# Panel-Angaben, die _sanitize_panels bewusst NICHT speichert, weil sie der
# Standard sind - beim Speichern kein Verlust (siehe _panels_verworfen).
# Pfad-Muster, "*" steht fuer einen beliebigen Schluessel (z. B. Kachel-UUID).
PANEL_STANDARD = {("ui", "split"): True, ("tiles", "*", "chartStyle"): "trend"}
# "Werte gross" (ui.bigValues je Panel, tiles.<uuid>.big = "on"|"off"): reine
# Wert-Bausteine zeigen ihren Messwert gross, Piktogramm als Wasserzeichen.
# Zahl und Einheit kommen unveraendert aus dem Loxone-Format, nur getrennt.
BIG_TYPES = ("InfoOnlyAnalog", "Meter")
_BIGNUM_RE = re.compile(r"^\s*([+\-\u2212]?\d[\d.,]*)\s*(.*?)\s*$")
_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9.,%\s]+\)|[a-zA-Z]{3,20})$")
# Tracker-Zeile: fuehrender Zeitstempel (TT.MM.JJ[JJ] HH:MM[:SS]) wird vom Text
# getrennt, damit er als Untertitel erscheint. Matcht sonst nichts -> ganze Zeile.
_TS_RE = re.compile(r"^\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}[ ,]+\d{1,2}:\d{2}(?::\d{2})?"
                    r"|\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$")


def _short_ts(ts: str | None) -> str:
    """Zeitstempel des Protokolls kurz: heute nur 'HH:MM', sonst 'TT.MM. HH:MM'."""
    if not ts:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M:%S",
                "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M:%S", "%d.%m.%y %H:%M"):
        try:
            dt = datetime.strptime(ts.strip(), fmt)
        except ValueError:
            continue
        return dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%d.%m. %H:%M")
    return ts


def _color_ok(v) -> bool:
    return isinstance(v, str) and bool(_COLOR_RE.match(v.strip()))


# Unterstuetzte Panel-Sprachen (Basis-Codes). Steuert vorerst nur Datum/Uhr am
# Panel; die Uebersetzung der festen UI-/Statustexte folgt (i18n-Ausbau).
SUPPORTED_LANGS = ("de", "en", "fr", "it", "es", "nl")


def _clean_lang(v):
    """Sprach-Code validieren (z.B. 'de', 'en', 'en-US'); '' wenn nicht unterstuetzt."""
    if not isinstance(v, str):
        return ""
    v = v.strip().lower()[:8]
    return v if v.split("-")[0] in SUPPORTED_LANGS else ""


# Loxone-Icon-Bibliothek: SVGs des LoxBerry-Plugins "loxoneicons", read-only in
# den Container gemountet (docker-compose). Fehlt der Mount/das Plugin, ist der
# Ordner leer -> die Icon-Quelle erscheint gar nicht. Ueber Env ueberschreibbar.
LOXLIB_DIR = os.environ.get("LOXPANEL_LOXLIB_DIR", "/app/loxone-icons/filled")
_LOXLIB_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.svg$")


# Globale Darstellungs-Schluessel in theme.json "ui" - EINE Liste fuer
# Speichern (_write_theme) und Ausliefern an den Editor (api_meta).
# ---- Dashboard-Raster je Panel-Profil ----
# 3x3 (Standard) oder 2x2 Zellen je 480er-Flaeche, bei 2 Flaechen (z.B. Shelly
# X2i) doppelt so breit. Widgets belegen ganze Zellen; erlaubt sind nur diese
# Groessen (w, h) - fuer 2x2 siehe GRID_SIZES.
SAVER_SIZES = {
    "clock": ((1, 1), (2, 1), (3, 1), (2, 2)),
    "weather": ((3, 1), (3, 2)),
    "calendar": ((3, 1), (3, 2), (3, 3)),
    "intercom": ((2, 2), (3, 2), (3, 3)),
    "tile": ((1, 1), (2, 1)),
    # Widgets wie im Original 0.6 (dort Pane 2 / Uhr-Seite), hier frei im Raster
    "wxdetail": ((3, 1), (3, 2)),                     # Wetter-Details (Verlauf, Wind, Sonne ...)
    "energy": ((2, 2), (3, 2), (3, 3)),               # Energiefluss (EFM / EnergyManager2)
    "chart": ((2, 1), (3, 1), (2, 2), (3, 2)),        # Verlauf eines Bausteins mit Statistik
    "player": ((2, 2), (3, 2), (3, 3)),               # Audio-Zone (Cover, Titel, Steuerung)
    "camera": ((1, 1), (2, 1), (2, 2), (3, 2), (3, 3)),   # Kameras (Intercoms + eigene), per Pillen umschaltbar
    "status": ((1, 1), (2, 1), (2, 2), (3, 1), (3, 2)),   # Status-Ampel aus bis zu 4 Bausteinen
}
SAVER_UUID_TYPES = ("tile", "intercom", "energy", "chart", "player")
SAVER_EXITS = ("x", "up", "down", "left", "right")   # Schliessen: X-Button und Wischrichtungen
# ---- Tab-Raster: dasselbe 3x3-Grundraster wie der Screensaver ----
# Ein Tab ist eine Folge von Seiten zu je 3x3 Zellen (y 0-2 = Seite 1, 3-5 =
# Seite 2 ...). Kacheln 1x1 (Standard), 2x1 oder 2x2; Widgets wie im Screensaver.
TAB_MAX_ROWS = 60                      # Zeilen je Tab (= 20 Seiten bei 3x3)
FOLDER_TYPES = ("room", "cat")          # Raum-/Kategorie-Kachel der Uebersichten
# Erlaubte Groessen je Raster: 3x3 (160 px-Zellen) wie bisher, 2x2 (240 px-Zellen,
# grosse Kacheln wie die Detailseiten) - dort hoechstens 2 Zellen breit/hoch.
GRID_SIZES = {
    3: {**SAVER_SIZES, "tile": ((1, 1), (2, 1), (2, 2))},
    2: {"clock": ((1, 1), (2, 1), (2, 2)), "weather": ((2, 1), (2, 2)), "calendar": ((2, 1), (2, 2)),
        "intercom": ((2, 1), (2, 2)), "tile": ((1, 1), (2, 1), (2, 2)), "wxdetail": ((2, 1), (2, 2)),
        "energy": ((1, 1), (2, 1), (2, 2)), "chart": ((1, 1), (2, 1), (2, 2)), "player": ((2, 1), (2, 2)),
        "camera": ((1, 1), (2, 1), (2, 2)), "status": ((1, 1), (2, 1), (2, 2))},
}
# Bei zwei Panels nebeneinander (z.B. Shelly X2): Kamera/Intercom ueber BEIDE Panels -
# im Dashboard wie in den Tabs (dort von der linken, geraden Seite in die rechte).
# Bei 1-Panel-Profil bleiben solche Widgets gespeichert, aber unsichtbar.
SAVER_WIDE_SIZES = {3: {"camera": ((6, 3),), "intercom": ((6, 3),)},
                    2: {"camera": ((4, 2),), "intercom": ((4, 2),)}}


def _tab_cells(x: int, y: int, w: int, h: int, g: int) -> set:
    """Belegte Zellen eines Tab-Eintrags. Ein breites Widget (ueber beide Panels)
    beginnt auf einer geraden Seite; sein Teil rechts von Spalte g liegt auf der
    folgenden (ungeraden) Seite, die am Panel rechts daneben steht."""
    return {(cx, cy) if cx < g else (cx - g, cy + g) for cx in range(x, x + w) for cy in range(y, y + h)}
for _g in GRID_SIZES.values():               # Raum-/Kategorie-Kacheln wie Baustein-Kacheln
    _g["room"] = _g["cat"] = _g["tile"]


def _fc_size(v) -> float:
    """Schriftgroesse der Wettervorschau: 8..32 (aeltere Stande erlaubten bis 80)."""
    try:
        return max(8.0, min(32.0, float(v)))
    except (TypeError, ValueError):
        return 12.5


def _grid(v, default: int = 3) -> int:
    """Rastermass eines Tabs/Dashboards: 2 (2x2) oder 3 (3x3). Ohne eigene
    Angabe gilt das Standardraster des Panel-Profils (ui.grid, sonst 3x3)."""
    if v in (2, "2"):
        return 2
    if v in (3, "3"):
        return 3
    return 2 if default == 2 else 3


def _widget_entry(it: dict, x: int, y: int, w: int, h: int) -> dict | None:
    """Gepruefter Raster-Eintrag (Screensaver und Tabs) mit den typabhaengigen
    Zusatzfeldern; None bei ungueltigem Baustein-Bezug."""
    e = {"type": it["type"], "x": x, "y": y, "w": w, "h": h}
    if it["type"] == "camera":
        cam = it.get("cam")
        if isinstance(cam, str) and _CAM_ID_RE.match(cam):
            e["cam"] = cam                        # Startkamera (sonst die erste)
        sel = it.get("cams")
        if isinstance(sel, list):                 # Auswahl + Reihenfolge der Kameras (leer = alle)
            ids = []
            for c in sel[:16]:
                if isinstance(c, str) and _CAM_ID_RE.match(c) and c not in ids:
                    ids.append(c)
            if ids:
                e["cams"] = ids
        back = it.get("back")                     # Ruecksprung zur ersten Kamera nach n Minuten (0 = aus, Standard 3)
        if isinstance(back, (int, float)) and not isinstance(back, bool) and 0 <= back <= 240 and int(back) != 3:
            e["back"] = int(back)
    if it["type"] == "status":
        ids = []
        for u in (it.get("ctls") or [])[:32]:
            if isinstance(u, str) and _UUID_RE.match(u) and u not in ids:
                ids.append(u)
                if len(ids) == 4:
                    break
        e["ctls"] = ids                           # Chips (max. 4) in dieser Reihenfolge
        if isinstance(it.get("trk"), str) and _UUID_RE.match(it["trk"]):
            e["trk"] = it["trk"]                  # optional: Tracker fuer den Verlauf
        if it.get("look") == "color":
            e["look"] = "color"                   # kraeftig farbig statt passend zum Hintergrund
    if it["type"] == "weather":
        try:
            d = int(it.get("days"))
        except (TypeError, ValueError):
            d = 0
        if d in (1, 2):
            e["days"] = d                         # Vorschau-Tage (Standard 3 = Maximum; alte 4 -> 3)
        if it.get("detail") is True:
            e["detail"] = True                    # Antippen eines Tages oeffnet die Tagesdetails
        show = it.get("show")
        if isinstance(show, list):
            sh = [k for k in ("ico", "mm", "pop") if k in show]
            if sh and sh != ["ico", "mm"]:
                e["show"] = sh                    # je Tag: Symbol, Max/Min, Regen % (Standard Symbol + Max/Min)
        if it.get("fewer") is True:
            e["fewer"] = True                     # schmale Kachel: 2 Tage statt Max ueber Min
    if it["type"] == "clock":
        e["align"] = it.get("align") if it.get("align") in ("left", "center", "right") else "center"
        e["date"] = it.get("date") if it.get("date") in ("none", "short", "long") else "short"
    elif it["type"] in SAVER_UUID_TYPES or it["type"] in FOLDER_TYPES:
        if not (isinstance(it.get("uuid"), str) and _UUID_RE.match(it["uuid"])):
            return None
        e["uuid"] = it["uuid"]
        if it["type"] == "chart":
            e["range"] = it.get("range") if it.get("range") in STAT_RANGES else STAT_DEFAULT_RANGE
    return e


def _sanitize_layout(lay, dg: int = 3) -> dict | None:
    """Belegung eines Tabs pruefen: {items:[...], removed:[uuid], label}.
    items wie beim Screensaver, aber 3 Spalten und beliebig viele Seiten; ein
    Eintrag darf keine Seitengrenze ueberragen. removed = aus einer Vorbefuellung
    (Raum/Kategorie/Zentral/Favoriten) bewusst entfernte Bausteine."""
    if not isinstance(lay, dict):
        return None
    g = _grid(lay.get("grid"), dg)
    sizes = GRID_SIZES[g]
    taken: set = set()
    items = []
    for it in (lay.get("items") or [])[:g * TAB_MAX_ROWS]:
        if not isinstance(it, dict) or it.get("type") not in sizes:
            continue
        try:
            x, y, w, h = (int(it.get(k)) for k in ("x", "y", "w", "h"))
        except (TypeError, ValueError):
            continue
        wide = (w, h) in SAVER_WIDE_SIZES[g].get(it["type"], ()) and (y // g) % 2 == 0
        if ((w, h) not in sizes[it["type"]] and not wide) or x < 0 or y < 0 \
                or x + w > (2 * g if wide else g) or y + h > TAB_MAX_ROWS \
                or y // g != (y + h - 1) // g:
            continue
        cells = _tab_cells(x, y, w, h, g)
        if cells & taken:
            continue
        e = _widget_entry(it, x, y, w, h)
        if e is None:
            continue
        taken |= cells
        items.append(e)
    out: dict = {"items": items}
    if lay.get("grid") in (2, 3, "2", "3"):
        out["grid"] = g                    # eigenes Raster; sonst Standard des Profils
    pick = [u for u in (lay.get("pick") or []) if isinstance(u, str) and _UUID_RE.match(u)][:300]
    if pick:
        out["pick"] = pick                 # Uebersicht: ausgewaehlte Raeume/Kategorien
    rem = [u for u in (lay.get("removed") or []) if isinstance(u, str) and _UUID_RE.match(u)][:500]
    if rem:
        out["removed"] = rem
    label = str(lay.get("label") or "").strip()[:24]
    if label:
        out["label"] = label
    return out


def _sanitize_saver(sv, dg: int = 3) -> dict | None:
    """Screensaver-Belegung eines Profils pruefen: {items:[...], exit:[...]}.
    Ungueltige, zu grosse oder ueberlappende Widgets fallen weg. None = keine
    eigene Belegung (das Panel zeigt dann den bisherigen Screensaver)."""
    if not isinstance(sv, dict):
        return None
    g = _grid(sv.get("grid"), dg)
    sizes = GRID_SIZES[g] if g == 2 else SAVER_SIZES
    cols, rows = 2 * g, g                    # breite Displays: zwei Flaechen nebeneinander
    taken: set = set()
    items = []
    for it in (sv.get("items") or [])[:cols * rows]:
        if not isinstance(it, dict) or it.get("type") not in sizes:
            continue
        try:
            x, y, w, h = (int(it.get(k)) for k in ("x", "y", "w", "h"))
        except (TypeError, ValueError):
            continue
        if ((w, h) not in sizes[it["type"]] and (w, h) not in SAVER_WIDE_SIZES[g].get(it["type"], ())) \
                or x < 0 or y < 0 or x + w > cols or y + h > rows:
            continue
        cells = {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + h)}
        if cells & taken:
            continue
        e = _widget_entry(it, x, y, w, h)
        if e is None:
            continue
        taken |= cells
        items.append(e)
    exits = [x for x in SAVER_EXITS if x in (sv.get("exit") or [])]
    if not items:
        return None
    out = {"items": items, "exit": exits}
    if sv.get("std") is True:
        out["std"] = True                    # Vorlage fuer neue Panels (Konfigurator)
    if sv.get("grid") in (2, 3, "2", "3"):
        out["grid"] = g
    # Statusleiste oben im Dashboard: bis zu BAR_MAX Bausteine (unabhaengig vom
    # Ampel-Widget, gleiche Logik - s. App.status_data), je Baustein optional
    # ein eigenes Symbol (barIcons).
    bar = []
    for u in (sv.get("bar") or [])[:32]:
        if isinstance(u, str) and _UUID_RE.match(u) and u not in bar:
            bar.append(u)
            if len(bar) == BAR_MAX:
                break
    if bar:
        out["bar"] = bar
        bi = sv.get("barIcons") if isinstance(sv.get("barIcons"), dict) else {}
        icons = {u: ic for u, ic in ((u, _clean_icon(bi.get(u))) for u in bar) if ic}
        if icons:
            out["barIcons"] = icons
        # Anzeige je Baustein (nur Status-Bausteine): mode icon|text|both, lox = Loxone-Statussymbol
        bs = sv.get("barShow") if isinstance(sv.get("barShow"), dict) else {}
        show = {}
        for u in bar:
            e = bs.get(u)
            if not isinstance(e, dict):
                continue
            mode = e.get("mode") if e.get("mode") in ("icon", "text", "both") else "icon"
            lox = e.get("lox") is True
            if mode != "icon" or lox:
                show[u] = {"mode": mode, "lox": lox}
        if show:
            out["barShow"] = show
    return out


BAR_MAX = 6   # Statusleiste: hoechstens so viele Bausteine (480 px: kompakt ab 5)


# Neuladen gegen Einfrieren ohne Agent (Android, Tablet): Ist reloadHours nicht
# eingestellt, laedt die Visu einmal je Nacht ab dieser Stunde neu, sobald ihre
# Uhr-/Dashboard-Seite steht (aus LoxPanel #82).
NEULADEN_STUNDE = 3
AMBIENT_MODES = ("light", "temp")
AMBIENT_BG_MODES = AMBIENT_MODES + ("image",)   # Hintergrund zusaetzlich: eigenes Bild   # Dashboard-Farbverlauf: nach Tageslicht / Aussentemperatur
# Fully Kiosk Browser: offizielle Download-Seite, Link mit Version im Namen
FULLY_PAGE = "https://www.fully-kiosk.com/en/"
_FULLY_APK_RE = re.compile(r'(https://www\.fully-kiosk\.com/files/\d{4}/\d{2}/Fully-Kiosk-Browser-v(\d+(?:\.\d+){1,3})\.apk)')
FULLY_MAX_BYTES = 80 * 1024 * 1024
FULLY_UPLOAD = "eigene-fully.apk"   # selbst hochgeladene APK (hat Vorrang)
CAM_RECONNECT_HOURS = (6, 12, 24)   # waehlbare Intervalle fuer den Kamera-Neuaufbau
_COVER_MAX_BYTES = 5 * 1024 * 1024   # Obergrenze fuer /cover-Bilder

THEME_UI_KEYS = ("iconSize", "nameSize", "subSize", "saverFcSize",
                 "tileShadow", "font", "fontNum", "textColor", "baseColor", "design", "bold", "lang",
                 "alarmsEnabled", "motion", "contrast", "sceneLight", "dblTapOff", "iconAnim", "bigValues")


# Komplettkatalog der Loxone-Standard-Icons (IconsFilled/*.svg). Der Miniserver
# liefert JEDES davon ueber /icon aus, auch wenn es in der Struktur nicht benutzt
# wird - so steht die ganze Auswahl ohne Zusatz-Plugin bereit. Liste: Loxone-
# Konfigurator-Verzeichnis (via LoxBerry-Plugin LoxoneIcons), gegen einen
# Miniserver geprueft.
_MSICONS_FILE = Path(__file__).resolve().parent / "loxone_icons.txt"
_MSICONS: list | None = None


def _msicons_names() -> list:
    global _MSICONS
    if _MSICONS is None:
        try:
            _MSICONS = sorted({ln.strip() for ln in _MSICONS_FILE.read_text().splitlines()
                               if _LOXLIB_NAME.match(ln.strip())})
        except OSError:
            _MSICONS = []
    return _MSICONS


def _loxlib_names() -> list:
    """Dateinamen der Loxone-Bibliothek (flache .svg im gemounteten Ordner)."""
    try:
        return sorted(fn for fn in os.listdir(LOXLIB_DIR)
                      if _LOXLIB_NAME.match(fn) and ".." not in fn)
    except OSError:
        return []


def _clean_icon(ic):
    """Icon-Referenz einer Kachel validieren (Quelle + sicherer Bezeichner)."""
    if not isinstance(ic, dict):
        return None
    s = ic.get("src")
    if s == "builtin" and isinstance(ic.get("id"), str) and re.match(r"^[A-Za-z0-9_]{1,32}$", ic["id"]):
        return {"src": "builtin", "id": ic["id"]}
    if s == "loxone" and isinstance(ic.get("p"), str) and ".." not in ic["p"] \
            and (ic["p"].endswith(".svg") or ic["p"].endswith(".png")):
        return {"src": "loxone", "p": ic["p"]}
    if s == "loxlib" and isinstance(ic.get("name"), str) and _LOXLIB_NAME.match(ic["name"]) \
            and ".." not in ic["name"]:
        return {"src": "loxlib", "name": ic["name"]}
    if s == "google" and isinstance(ic.get("name"), str) and re.match(r"^[a-z0-9_]{1,48}$", ic["name"]):
        return {"src": "google", "name": ic["name"]}
    if s == "custom" and isinstance(ic.get("file"), str) and re.match(r"^[A-Za-z0-9._-]{1,80}$", ic["file"]):
        return {"src": "custom", "file": ic["file"]}
    return None
# Zustandstexte generischer Fensterkontakte (InfoOnlyDigital), ganze Woerter.
_WIN_CLOSED = {"geschlossen", "zu", "dicht", "verschlossen", "closed", "shut"}
_WIN_OPEN = {"offen", "auf", "geöffnet", "geoeffnet", "gekippt", "open", "opened", "tilted"}

def _is_sentinel(v) -> bool:
    """Loxone-Fehlwert: INT32_MAX bzw. INT32_MAX/1000 (2147483,647) - echte Zaehlerstaende bleiben."""
    a = abs(v)
    return abs(a - 2147483.647) < 0.01 or abs(a - 2147483647) < 1

_NUMFMT = re.compile(r"^(%[-+ 0-9.]*[dfeg])(.*)$")
_PREFIX = ["k", "M", "G", "T"]


def _dim_yellow(pct) -> str:
    """Gluehbirne nach Helligkeit abgestuft: gleicher Gelbton, mit steigender
    Helligkeit heller und kraeftiger. 1 % ist noch deutlich als "an" zu
    erkennen, 100 % entspricht dem Gelb der Lichtsteuerung (#f2c14e)."""
    try:
        p = max(0.0, min(100.0, float(pct)))
    except (TypeError, ValueError):
        p = 100.0
    return f"hsl(43,{55 + 0.30 * p:.0f}%,{34 + 0.28 * p:.0f}%)"


def _pos_pct(value) -> int | None:
    """Stellung als ganze Prozent 0..100 fuer den Ring auf der Kachel.

    None bedeutet "dieser Baustein hat keine Stellung" - dann zeichnet das
    Panel gar keinen Ring. Der Wert ist immer derselbe, den auch die
    Zweitzeile nennt, damit Ring und Text nicht auseinanderlaufen.
    """
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


def _apply_order(uuids: list, order: list | None) -> list:
    """Wendet eine gespeicherte Wunsch-Reihenfolge auf eine natuerliche Liste
    an: erst die Eintraege aus 'order' (in dieser Reihenfolge, nur soweit noch
    vorhanden), danach alle uebrigen (neue/noch nicht einsortierte) in ihrer
    natuerlichen Reihenfolge - die verschwinden also nicht, sondern haengen
    sich hinten an. Kein 'order' -> unveraendert."""
    if not order:
        return uuids
    present = set(uuids)
    chosen = [u for u in order if u in present]
    chosen_set = set(chosen)
    return chosen + [u for u in uuids if u not in chosen_set]


def _clean(name: str) -> str:
    return re.sub(r"^[^0-9A-Za-zÄÖÜäöü]+", "", name or "").strip() or (name or "")


_STAT_ROW = re.compile(r"<S\s([^>]*?)/?>")
_STAT_ATTR = re.compile(r'(\w+)="([^"]*)"')


def _parse_stat_xml(text: str) -> list:
    """Loxone-Statistik-Monatsdatei -> [(sekunden, [werte ...])], zeitlich sortiert.

    Jede Zeile ist <S T="JJJJ-MM-TT hh:mm:ss" V="1.23"/>; bei mehreren
    Ausgaengen stehen weitere Wert-Attribute in Ausgangsreihenfolge dahinter.
    Gelesen wird deshalb jedes Attribut ausser T in Dokumentreihenfolge, ohne
    Annahme ueber seinen Namen. Per Regex statt XML-Parser: die Datei ist flach,
    und so gibt es keine Entitaeten-Aufloesung. Zeitstempel sind Ortszeit des
    Miniservers und werden als Wanduhr-Sekunden (timegm) gefuehrt, damit Server
    und Panel ohne Zeitzonenrechnung dieselbe Uhrzeit zeigen."""
    out = []
    for m in _STAT_ROW.finditer(text or ""):
        ts, vals = None, []
        for name, raw in _STAT_ATTR.findall(m.group(1)):
            if name == "T":
                try:
                    ts = calendar.timegm(datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").timetuple())
                except ValueError:
                    ts = None
            else:
                try:
                    vals.append(float(raw))
                except ValueError:
                    vals.append(None)
        if ts is not None and vals:
            out.append((ts, vals))
    out.sort(key=lambda r: r[0])
    return out


def _stat_fmt(fmt) -> tuple[int, str]:
    """Loxone-Zahlenformat -> (Nachkommastellen, Einheit). Zwei Schreibweisen:
    printf wie bei `statistic` ("%.1f °C", "%.0f%", "%.0fLx") und die Maske von
    `statisticV2` ("0,000kW", "0,0kWh", "0,00€"). Ohne Format -> (0, "")."""
    s = str(fmt or "")
    m = re.search(r"%(?:\.(\d+))?[fd]", s)
    if m:
        return int(m.group(1) or 0), s[m.end():].replace("%%", "%").strip()
    m = re.match(r"^[#0]+(?:[.,]([#0]+))?(.*)$", s.strip())
    if m:
        return len(m.group(1) or ""), m.group(2).strip()
    return 0, ""


def _parse_stat2_bin(body: bytes, nvals: int = 1) -> list | None:
    """Antwort von jdev/sps/getStatistic/.../raw/... -> [(sekunden, [werte])].

    Binaer, je Eintrag 4 Byte Zeitstempel (uint32, Unix-UTC) und je Wert 8 Byte
    (float64), little-endian - an der Anlage so gemessen (PV 7,42 kW, Netz
    -6,26 kW, Eintraege im Abstand der Gruppe). Die Zeit wird wie bei den
    Monatsdateien in Wanduhr-Sekunden der Container-Zeitzone umgerechnet.
    Passt die Laenge nicht zum Eintragsformat -> None (unbekannte Antwort)."""
    size = 4 + 8 * nvals
    if len(body) % size:
        return None
    out = []
    for off in range(0, len(body), size):
        ts, *vals = struct.unpack_from("<I" + "d" * nvals, body, off)
        vals = [v if math.isfinite(v) else None for v in vals]
        out.append((calendar.timegm(time.localtime(ts)), vals))
    out.sort(key=lambda r: r[0])
    return out


def _stat_thin(pts: list, t0: int, t1: int, n: int, digital: bool) -> list:
    """Linie auf hoechstens n Punkte ausduennen: je Zeitfenster der Mittelwert
    (Analog) bzw. das Maximum (Digital: ein kurzes "Ein" soll sichtbar bleiben)."""
    if len(pts) <= n or t1 <= t0:
        return pts
    w = (t1 - t0) / n
    buckets: dict[int, list] = {}
    for t, v in pts:
        buckets.setdefault(min(n - 1, max(0, int((t - t0) / w))), []).append((t, v))
    out = []
    for b in sorted(buckets):
        items = buckets[b]
        if digital:
            out.append((items[-1][0], max(v for _, v in items)))
        else:
            out.append((int(sum(t for t, _ in items) / len(items)),
                        sum(v for _, v in items) / len(items)))
    return out


def _stat_buckets(pts: list, edges: list, t_end: int) -> list:
    """Zeitgewichteter Mittelwert je Abschnitt [edges[i], edges[i+1]). Ein Messwert
    gilt bis zum naechsten (Treppe) - so stimmt das auch fuer Digitalwerte, die nur
    bei Aenderung aufgezeichnet werden: der Mittelwert ist dann der Ein-Anteil.
    Abschnitte ohne bekannten Wert oder nach t_end -> None."""
    out, k, n = [], 0, len(pts)
    for a, b in zip(edges, edges[1:]):
        b2 = min(b, t_end)
        while k + 1 < n and pts[k + 1][0] <= a:
            k += 1
        if b2 <= a or not n or pts[0][0] >= b2:
            out.append(None)
            continue
        acc = dur = 0.0
        j = k
        while j < n and pts[j][0] < b2:
            t, v = pts[j]
            lo, hi = max(a, t), min(b2, pts[j + 1][0] if j + 1 < n else t_end)
            if hi > lo:
                acc += v * (hi - lo)
                dur += hi - lo
            j += 1
        out.append(acc / dur if dur else None)
    return out


def _stat_day_range(pts: list, edges: list, t_end: int) -> list:
    """Tiefst- und Hoechstwert je Abschnitt, mit dem Stand, der zu Beginn des
    Abschnitts galt. Abschnitte ohne bekannten Wert oder nach t_end -> None."""
    out = []
    for a, b in zip(edges, edges[1:]):
        if a >= t_end:
            out.append(None)
            continue
        vals = [v for t, v in pts if a <= t < min(b, t_end + 1)]
        prev = [v for t, v in pts if t < a]
        if prev:
            vals.append(prev[-1])
        out.append((min(vals), max(vals)) if vals else None)
    return out


def _stat_bars(pts: list, edges: list) -> list:
    """Zaehlerstaende -> Verbrauch je Abschnitt [edges[i], edges[i+1]).

    Summiert von Messpunkt zu Messpunkt: Grundlage ist der letzte Stand davor
    (pts beginnt mit dem letzten Wert vor dem Fenster, falls bekannt; sonst ist
    der erste Stand die Basis). Faellt der Stand auf weniger als die Haelfte,
    wurde der Zaehler zurueckgesetzt und zaehlt ab 0 weiter. Ein kleiner
    Ruecksprung (Rundung, 1000,5 -> 1000,4) ist kein Verbrauch, sonst ergaebe
    er einen Balken in Hoehe des ganzen Zaehlerstands."""
    out, i, prev = [], 0, None
    while i < len(pts) and pts[i][0] < edges[0]:
        prev = pts[i][1]
        i += 1
    for a, b in zip(edges, edges[1:]):
        use = 0.0
        while i < len(pts) and pts[i][0] < b:
            v = pts[i][1]
            if prev is not None:
                if v >= prev:
                    use += v - prev
                elif v < prev / 2:
                    use += v              # zurueckgesetzt: ab 0 weitergezaehlt
            prev = v
            i += 1
        out.append((a, use))
    return out


def _hex_rgb(value) -> str | None:
    """#RRGGBB / #RGB -> \"r,g,b\" (fuer rgba() mit variabler Deckkraft). None bei ungueltig."""
    h = str(value or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
    except ValueError:
        return None


def _config() -> dict:
    # Reihenfolge: geschriebene loxpanel.cfg (Settings-Seite) -> Env (Docker) -> Beispiel.
    base = Path(__file__).resolve().parent.parent / "config"
    f = base / "loxpanel.cfg"
    if f.is_file():
        try:
            ms = json.loads(f.read_text(encoding="utf-8")).get("miniserver", {})
        except ValueError:
            ms = {}
        if ms.get("host"):
            return ms
    env = os.environ
    if env.get("LOXPANEL_MS_HOST"):
        return {
            "host": env["LOXPANEL_MS_HOST"],
            "user": env.get("LOXPANEL_MS_USER", ""),
            "pass": env.get("LOXPANEL_MS_PASS", ""),
            "port": int(env.get("LOXPANEL_MS_PORT", "443")),
            "verify_tls": env.get("LOXPANEL_MS_VERIFY_TLS", "false").lower() in ("1", "true", "yes"),
        }
    # Beispiel-Config nur nutzen, wenn vorhanden. Beim LoxBerry-Plugin verdeckt
    # das (leere) Daten-Volume die Image-Beispieldatei -> darf NICHT crashen.
    # Ohne jede Config startet der Server trotzdem (Zugang via /settings).
    ex = base / "loxpanel.cfg.example"
    if ex.is_file():
        try:
            return json.loads(ex.read_text(encoding="utf-8")).get("miniserver", {})
        except ValueError:
            pass
    return {}


def _audio_config() -> dict:
    """Audio-Backend-Config (Loxone-Audioserver / MS4H auf Port 7091).

    Aus loxpanel.cfg `audio`-Block: {"host": "10.0.2.2", "port": 7091}.
    Fehlt `host`, wird er aus einer roomfav-Cover-URL abgeleitet (die zeigen
    auf den Audioserver, z.B. http://10.0.2.2:7092/...), sobald verfügbar.
    """
    base = Path(__file__).resolve().parent.parent / "config"
    f = base / "loxpanel.cfg"
    if not f.is_file():
        f = base / "loxpanel.cfg.example"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8")).get("audio", {})
    except (ValueError, OSError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def _audiometa_config() -> dict:
    """Metadaten-Quelle Audioserver4Home/Sonn (REST /api/v1/zones, Port 7090).

    Aus loxpanel.cfg `audiometa`-Block: {"host": "10.0.0.55", "port": 7090,
    "enabled": true}. Sonns AudioZoneV2-Ausgaenge liefern ueber das Loxone-
    Protokoll KEINE Track-Metadaten; dieser Block fuellt Cover/Titel/Interpret
    per Namensabgleich aus der Sonn-API nach.
    """
    base = Path(__file__).resolve().parent.parent / "config"
    f = base / "loxpanel.cfg"
    if not f.is_file():
        f = base / "loxpanel.cfg.example"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8")).get("audiometa", {})
    except (ValueError, OSError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


# Eigene Kameras (reine Ueberwachungskameras) liegen mit im intercom-Block der
# loxpanel.cfg unter "cam_<id>" mit Namen; Intercoms unter ihrer Loxone-UUID.
_CAM_ID_RE = re.compile(r"^(cam_[a-z0-9]{4,16}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{16})$")


def _audiometa_sekunden(am: dict, schluessel: str, standard: float) -> float:
    """Eine Zeit (s) des Audioserver-Ereignis-Clients aus loxpanel.cfg
    audiometa.<schluessel> (retry_interval, response_timeout). Ohne gueltigen
    Wert `standard` (AudioEventClient.NEU_VERSUCH_S bzw. PRUEF_ZEITLIMIT_S)."""
    wert = am.get(schluessel) if isinstance(am, dict) else None
    if isinstance(wert, (int, float)) and not isinstance(wert, bool) and math.isfinite(wert) and wert > 0:
        return float(wert)
    if wert is not None:
        log.warning("loxpanel.cfg: audiometa.%s %r ungueltig, es gelten %s s", schluessel, wert, standard)
    return float(standard)


def _intercom_config() -> dict:
    base = Path(__file__).resolve().parent.parent / "config"
    f = base / "loxpanel.cfg"
    if not f.is_file():
        f = base / "loxpanel.cfg.example"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8")).get("intercom", {})
    except (ValueError, OSError):
        return {}
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(v.get("url"), str):
            v["url"] = v["url"].strip()
        elif isinstance(v, str):
            cfg[k] = v.strip()
    return cfg


def _clean_crop(v) -> dict | None:
    """Bildausschnitt einer Kamera: Fokuspunkt x/y (0..100 %), Zoom z (1..3),
    fit "cover" (fuellen, Standard) oder "contain" (ganzes Bild), bei "contain" bg
    "card"/"blur" fuer die freien Raender. None = Standard."""
    if not isinstance(v, dict):
        return None
    try:
        x = max(0.0, min(100.0, float(v.get("x", 50))))
        y = max(0.0, min(100.0, float(v.get("y", 50))))
        z = max(1.0, min(3.0, float(v.get("z", 1))))
    except (TypeError, ValueError):
        return None
    fit = "contain" if v.get("fit") == "contain" else "cover"
    if fit == "cover" and abs(x - 50) < 0.5 and abs(y - 50) < 0.5 and z < 1.01:
        return None
    out = {"x": round(x, 1), "y": round(y, 1), "z": round(z, 2), "fit": fit}
    if fit == "contain":   # freie Raender: Kartenfarbe (Standard) oder Bild verwischt fortgesetzt
        out["bg"] = "blur" if v.get("bg") == "blur" else "card"
    return out


# ---- Taster-Historie: die letzten Ausloesungen je Taster (Detailansicht) ----
# Nur Anzeige: was ueber ein Panel gesendet wurde (mit Antwort des Miniservers)
# und was Loxone selbst meldet (App, Wandtaster, Logik: State "active" 0->1).
PUSHLOG_FILE = _CFGDIR / "pushlog.json"
PUSHLOG_KEEP = 3


def _pushlog_load() -> dict:
    try:
        d = json.loads(PUSHLOG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v[:PUSHLOG_KEEP] for k, v in d.items() if isinstance(v, list)} if isinstance(d, dict) else {}


# ---- Diagnose-Log (System -> Diagnose) ----
# Ausfuehrliches Protokoll zum Fehlersuchen: Server-Meldungen ab DEBUG, Panel-
# Ereignisse (Verbindungsabbrueche, JS-Fehler) und eine Statistik je Minute.
# Begrenzt auf DIAG_MAX * (DIAG_KEEP + 1) Byte, liegt im Konfig-Ordner (bleibt
# beim Update erhalten, wird nicht ins Backup aufgenommen).
DIAG_FILE = _CFGDIR / "diag.log"
DIAG_MAX = 5 * 1024 * 1024
DIAG_KEEP = 2
_diag_handler: logging.Handler | None = None


def _diag_config() -> bool:
    try:
        d = _load_cfg().get("diag")
    except Exception:
        return False
    return bool(d.get("on")) if isinstance(d, dict) else False


def _diag_files() -> list:
    """Vorhandene Log-Dateien, aelteste zuerst (diag.log.2, .1, diag.log)."""
    fs = [DIAG_FILE.with_name(f"diag.log.{i}") for i in range(DIAG_KEEP, 0, -1)] + [DIAG_FILE]
    return [f for f in fs if f.is_file()]


def _diag_apply(on: bool) -> None:
    """Datei-Protokoll an-/abschalten (wirkt sofort, ohne Neustart)."""
    global _diag_handler
    import logging.handlers
    lp = logging.getLogger("loxpanel")
    if on and _diag_handler is None:
        try:
            h = logging.handlers.RotatingFileHandler(DIAG_FILE, maxBytes=DIAG_MAX,
                                                     backupCount=DIAG_KEEP, encoding="utf-8")
        except OSError as err:
            log.warning("Diagnose-Log nicht moeglich: %s", err)
            return
        h.setLevel(logging.DEBUG)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root = logging.getLogger()
        for other in root.handlers:              # Konsole (LoxBerry-Log) bleibt bei INFO
            if other.level == logging.NOTSET:
                other.setLevel(logging.INFO)
        root.addHandler(h)
        lp.setLevel(logging.DEBUG)
        _diag_handler = h
        log.info("Diagnose-Log an (%s, Version %s)", DIAG_FILE.name, APP_VERSION)
    elif not on and _diag_handler is not None:
        log.info("Diagnose-Log aus")
        logging.getLogger().removeHandler(_diag_handler)
        _diag_handler.close()
        _diag_handler = None
        lp.setLevel(logging.NOTSET)


def _cmd_watch_config() -> bool:
    """Befehls-Monitoring (loxpanel.cfg `cmdwatch.on`, Standard an): das Panel
    wartet auf die Quittung jedes Befehls und meldet, wenn keine kommt."""
    try:
        cw = _load_cfg().get("cmdwatch")
    except Exception:
        return True
    return bool(cw.get("on", True)) if isinstance(cw, dict) else True


def _night_config() -> dict:
    """Nachtmodus-Block aus loxpanel.cfg `night`: {"control": "<uuid>"}. Der
    `active`-State dieses Bausteins schaltet den Nachtmodus. Leer = kein
    Ausloeser, dann entscheiden die Sonnenzeiten."""
    base = Path(__file__).resolve().parent.parent / "config"
    f = base / "loxpanel.cfg"
    if not f.is_file():
        f = base / "loxpanel.cfg.example"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8")).get("night", {})
    except (ValueError, OSError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def _calendar_config() -> dict:
    """Kalender-/Wetter-Block aus loxpanel.cfg `calendar`:
    {"sources": [{"name": "Familie", "url": "...", "color": "#e0a24d"}, ...],
     "holiday_url": "...", "name": "Family", "colors": true, "sv_events": 3,
     "lat": 47.07, "lon": 15.44, "days": 14, "fore_days": 4}.
    Steuert die Front (Screensaver). Eine aeltere einzelne `ical_url` wird von
    front_info.calendar_sources() als erste Quelle mitgelesen."""
    base = Path(__file__).resolve().parent.parent / "config"
    f = base / "loxpanel.cfg"
    if not f.is_file():
        f = base / "loxpanel.cfg.example"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8")).get("calendar", {})
    except (ValueError, OSError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


DEFAULT_THEME = {"states": {"active": "#e0a24d", "good": "#52b881",
                            "warn": "#d6a24a", "crit": "#e2695f"}}


def load_theme() -> dict:
    theme = {"states": dict(DEFAULT_THEME["states"]), "categories": {},
             "ui": {"tabs": ["favoriten", "zentral", "raeume", "kategorien"],
                    "iconSize": 38, "nameSize": 18, "subSize": 15, "font": ""}}
    base = Path(__file__).resolve().parent.parent / "config"
    f = base / "theme.json"
    if not f.is_file():
        f = base / "theme.example.json"   # Vorlage fuer frische Installationen
    if f.is_file():
        try:
            user = json.loads(f.read_text(encoding="utf-8"))
            for k in ("states", "categories", "ui"):
                v = user.get(k)
                if isinstance(v, dict):
                    theme[k].update({kk: vv for kk, vv in v.items() if not kk.startswith("_")})
        except ValueError:
            pass
    return theme


def load_panels() -> dict:
    """Panel-Profile aus config/panels.json (Auswahl per URL ?panel=<id>).

    Jedes Profil kann Theme-Overrides (ui/states) + Sichtbarkeits-Whitelists
    (rooms/cats als UUID ODER Name) + Tab-Auswahl tragen. Leere/fehlende
    Whitelist = alles sichtbar. Wird später von der LoxBerry-Config-Seite
    befuellt (Räume/Kategorien anklickbar pro Gerät).
    """
    f = Path(__file__).resolve().parent.parent / "config" / "panels.json"
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            p = data.get("panels")
            if isinstance(p, dict):
                return {k: v for k, v in p.items() if not k.startswith("_")}
        except ValueError:
            pass
    return {}


def load_devices() -> dict:
    """Geraete-Automatik aus config/panels.json (`devices`): pro physischem
    Panel (Schluessel = Agent-Name) eine Zuordnung Betriebsmodus -> Panel-Profil.
    Loxone schickt per virtuellem Ausgang nur den Modusnamen an /api/mode; der
    Server schaltet dann jedes Panel mit passender Zuordnung auf sein Profil um.
    """
    f = Path(__file__).resolve().parent.parent / "config" / "panels.json"
    if f.is_file():
        try:
            d = json.loads(f.read_text(encoding="utf-8")).get("devices")
            if isinstance(d, dict):
                return d
        except ValueError:
            pass
    return {}


class App:
    def __init__(self, ms: dict, audio: dict | None = None,
                 audiometa: dict | None = None):
        # ms kann leer sein (noch kein Miniserver konfiguriert) -> Server startet
        # trotzdem, /settings bleibt bedienbar; verbunden wird erst mit host.
        self.host, self.port = ms.get("host", ""), ms.get("port", 443)
        self.user, self.password = ms.get("user", ""), ms.get("pass", "")
        self.verify_tls = ms.get("verify_tls", False)

        self.audio_cfg = audio or {}
        self.audio: AudioBackend | None = make_backend(self.audio_cfg)
        # Ein Steuerungs-Backend je Audioserver-Host (WS 7091), aufgebaut on
        # demand aus dem in der Struktur hinterlegten mediaServer-Host.
        self.audio_backends: dict[str, AudioBackend] = {}
        # Gen-2-Audioserver-Metadaten (universeller audio_event-Kanal, Port 7091):
        # Adressen werden AUTOMATISCH aus der Loxone-Struktur (/mediaServer/<uuid>
        # /host) gelesen; pro Audioserver ein Event-Client. Zonen-Zuordnung ueber
        # control.details.server (-> host) + details.playerid. Funktioniert mit
        # Original-Audioserver, Sonn und jedem Nachbau, ohne IP-Eingabe.
        self.audiometa_cfg = audiometa or {}
        self.mediaservers: dict[str, str] = {}          # serverUUID -> "host:port"
        self.audio_clients: dict[str, AudioEventClient] = {}  # host -> Client
        # uuidAction -> Loxone-playerid (fuer Audioserver-Kommandos)
        self.playerid_by_action: dict[str, int] = {}
        # uuidAction -> Audioserver-Host (aus mediaServer der Struktur). So
        # steht der Host auch fest, wenn nichts spielt (kein Cover zum Ableiten).
        self.audiohost_by_action: dict[str, str] = {}

        self.client: LoxoneClient | None = None
        self.ws: LoxoneWS | None = None
        self.states: dict[str, object] = {}
        self.controls: dict = {}
        self.rooms: dict = {}
        self.cats: dict = {}
        self.rooms_with: list[str] = []
        self.cats_with: list[str] = []
        self.conn_route: dict[web.WebSocketResponse, dict] = {}
        self.conn_prof: dict[web.WebSocketResponse, dict] = {}
        self.conn_dev: dict[web.WebSocketResponse, str] = {}   # ws -> Geraete-Kennung (?device=)
        self.conn_info: dict[web.WebSocketResponse, dict] = {}  # ws -> {dev, kiosk, ip, ts} (Geraeteverwaltung)
        self._drv_session: aiohttp.ClientSession | None = None   # HTTP-Session fuer Display-Treiber (Kiosk-Apps)
        self.conn_player: dict[web.WebSocketResponse, str] = {}   # ws -> AudioZone-UUID der aktiven Player-Pane (via setplayer)
        self.conn_energy: dict[web.WebSocketResponse, str] = {}   # ws -> EFM/EnergyManager2-UUID der aktiven Energiefluss-Pane (via setenergy)
        self.conn_camera: dict[web.WebSocketResponse, str] = {}   # ws -> Intercom-UUID der aktiven Kamera-Pane (via setcamera)
        self.conn_chart: dict[web.WebSocketResponse, tuple[str, str]] = {}   # ws -> (Baustein-UUID, Zeitraum) der Verlaufs-Pane (via setchart)
        self.panels = load_panels()
        self.devices = load_devices()   # Agent-Name -> {auto, modes:{modus:profil}}
        self.devinfo = load_devinfo()   # uid -> {name, info, ip, first, last} (Geraete-Erkennung)
        self.last_mode = ""             # zuletzt gesetzter Betriebsmodus (fuer Nachziehen beim Verbinden)
        self._struct_sig: str | None = None   # Signatur der Loxone-Struktur (erkennt Config-Aenderungen)
        self._pending_reload = False          # -> Panels beim naechsten Tick neu laden ({t:"reload"})
        self._retry_now = asyncio.Event()     # weckt stream_task aus der Reconnect-Pause
        self.global_states: dict = {}   # globale States der Anlage (Name -> UUID), s. _apply_structure
        self.op_modes: dict = {}        # Betriebsarten der Anlage (Id -> Name), s. _apply_structure
        # Lichtszenen: gelernte Helligkeit/Farbe {lc-uuid: {mood-id: {"b":0-100,"c":"#rrggbb"}}}
        try:
            self.scene_light: dict = json.loads(SCENE_LIGHT_FILE.read_text(encoding="utf-8"))
        except Exception:
            self.scene_light = {}
        self._sl_seen: dict = {}        # lc-uuid -> [mood-id, seit, gemessen]
        self._sl_next = 0.0             # naechste Pruefung (alle 3 s)
        self._sl_dirty = False
        self._sl_saved = 0.0
        self._night_on = False          # Nachtmodus aktiv? (-> {t:"night"} an die Panels)
        self.night_cfg = _night_config()  # {"control": uuid} -> dessen active-State = Nacht
        self._dirty = True
        # Zuletzt an JEDE Verbindung zugestellte Nutzlast, je Art getrennt
        # ({"view":…, "player":…, "energy":…}). Grundlage dafuer, unveraenderte
        # Ansichten gar nicht erst zu senden. Eingetragen wird ausschliesslich
        # NACH erfolgreichem Senden - ein abgebrochener Versuch darf nie als
        # zugestellt gelten.
        self._last_sent: dict = {}
        # Sendesperre je Panel-Verbindung: Navigation (ws_handler) und Live-Updates
        # (broadcaster) schreiben sonst gleichzeitig in dieselbe Verbindung.
        self._ws_locks: dict = {}
        self._nr_day = time.localtime().tm_yday   # naechtlicher Fully-Neustart: erst ab der naechsten Nacht
        self._dev_gone: dict[str, float] = {}     # Geraetename -> Zeitpunkt der letzten Trennung
        self.jwt: str | None = None
        self.alg: str = "SHA1"
        self._auth_gen = 0               # zaehlt jede Anmeldung (-> _renew_token)
        self._auth_at = 0.0              # monotonic der letzten Anmeldung
        self._auth_lock = asyncio.Lock()
        self.icon_session: aiohttp.ClientSession | None = None
        self.icon_cache: dict[str, tuple[bytes, str]] = {}
        # Verlaufsdaten: (uuidAction, "JJJJMM") -> (monotonic, JJJJMM beim Abruf,
        # [(sekunden, [werte])] oder None nach Abruffehler). Ein Monat, der beim
        # Abruf schon vorbei war, aendert sich nicht mehr.
        self.stat_cache: dict[tuple[str, str], tuple[float, str, list | None]] = {}
        self.stat_pending: set[tuple] = set()
        # statisticV2 (Energie-Zaehler): (uuidAction, Gruppe, Ausgang, Zeitraum) ->
        # (monotonic, [(sekunden, [wert])] oder None nach Abruffehler). Hoechstens
        # zwei Abrufe gleichzeitig; die Loxone-App erlaubt 4 (Gen 2) bzw. 1 (Gen 1).
        self.stat2_cache: dict[tuple, tuple[float, list | None]] = {}
        self.stat2_sem = asyncio.Semaphore(2)
        self.stat_gen = 0              # zaehlt jeden Abruf, Schluessel fuer stat_memo
        self.stat_memo: dict[tuple, list] = {}
        self.theme = load_theme()
        self.intercom_cfg = _intercom_config()
        # Front (Screensaver): Kalender + Wetter. front_task() laedt periodisch,
        # _front ist die zuletzt gebaute Nachricht ({"t":"front",...}), _front_key
        # ihr Abbild zum Vergleich (nur bei Aenderung neu senden), _front_meta der
        # Status fuer die Config-Seite. _front_refresh weckt front_task (nach dem
        # Speichern und bei neuem Wetter vom Miniserver).
        self.calendar_cfg = _calendar_config()
        # Loxone-Wetterserver: Konfiguration aus der Struktur, Rohdaten je
        # State-UUID (kommen ueber den WS als eigene Tabelle) und die zuletzt
        # tatsaechlich verwendete Quelle fuer die Diagnose.
        self.weather_cfg: dict = {}
        self._lox_wx: dict[str, list] = {}
        self._wx_source: str = "open-meteo"
        # Standort des Miniservers (aus msInfo) als Wetter-Fallback ohne Konfiguration.
        self.ms_lat: float | None = None
        self.ms_lon: float | None = None
        self.ms_location: str = ""
        self._front: dict | None = None
        self._front_key: str | None = None
        self._front_meta: dict = {}
        # Letzter erfolgreich geladener Stand je Teil (Feiertage, Wetter) plus
        # dessen Uhrzeit. Ueberbrueckt Aussetzer der Quellen, siehe _front_keep().
        self._front_good: dict = {}
        # Dasselbe fuer die Termine, aber JE KALENDER: {Quellenschluessel ->
        # {"events": [...], "zeit": "HH:MM"}}. Mit mehreren Abos reicht ein
        # gemeinsamer Stand nicht — faellt iCloud aus und Google liefert, waere
        # die Terminliste nicht leer und der alte Stand (mit den iCloud-
        # Terminen darin) wuerde ueberschrieben.
        self._front_good_cal: dict = {}
        self._front_dirty = False
        self._tick_memo: dict = {}
        self._pin_fail: dict = {}                            # uuid -> (Fehlversuche, gesperrt bis)
        self._diag_cpu: tuple | None = None                 # (process_time, monotonic) der letzten Diagnose-Zeile
        self._rt_sum, self._rt_n, self._rt_max = 0.0, 0, 0.0   # Renderzeit (Diagnose)
        self._front_sent: dict | None = None    # zuletzt an alle verteilter Stand (fuer Nur-Wetter-Nachrichten)
        self._front_refresh = asyncio.Event()
        # Letzter fertig gebauter Front-Stand (nach _front_keep) und ab wann der
        # Kalender wieder aus dem Netz geholt wird (time.monotonic(), 0 = sofort).
        # Ein Wetter-Push des Miniservers baut die Front aus diesem Stand neu und
        # ruft KEINEN Kalender ab, siehe front_task().
        self._front_last: dict | None = None
        self._front_cal_due = 0.0
        self._front_session: aiohttp.ClientSession | None = None
        self.bell_map: dict[str, str] = {}
        self.push_state: dict[str, str] = {}      # State-UUID "active" -> Taster-UUID
        self.push_hist: dict[str, list] = _pushlog_load()   # Taster-UUID -> letzte Ausloesungen
        self._bell_prev: dict[str, object] = {}
        # Klingel (Intercom): analog zum Wecker beide Flanken als Queue, damit
        # der Ton (falls fuer diese Intercom aktiviert) so lange laeuft, wie
        # der bell-Impuls am Miniserver ansteht, und nicht verloren geht, wenn
        # kurz hintereinander mehrere Ereignisse anfallen.
        self._pending_ring: list[dict] = []
        # Miniserver-Verbindung fuer die Panels: up = Stream laeuft, down_since =
        # Beginn des Ausfalls (Kulanz MS_OFFLINE_GRACE), ms_sent = zuletzt gemeldet.
        self.ms_up = False
        self.ms_down_since = time.time()
        self.ms_sent: bool | None = None
        self.ms_up_since = 0.0
        # Grund der Trennung fuer die Startseite (/api/msstatus): kurzer Code statt Roh-
        # Fehlertext (Fehlermeldungen enthalten Miniserver-Antworten; das UI soll nur
        # feste Texte zeigen). ms_next_retry = Zeitpunkt des naechsten Versuchs (epoch).
        self.ms_reason = ""
        self.ms_next_retry = 0.0
        self.cmd_watch = _cmd_watch_config()
        self.diag = _diag_config()               # Diagnose-Log (System -> Diagnose)
        self._diag_vals = 0                      # empfangene Werte seit der letzten Statistik
        self._diag_next = 0.0
        self._msinfo: dict = {}          # Systemwerte des Miniservers (Startseite), s. ms_sysinfo
        self._msinfo_t = 0.0
        # Wecker (AlarmClock): isAlarmActive-State-UUID -> Control-UUID. Flanke
        # 0->1/1->0 wird als {"t":"alarm",...} ans Panel gepusht (Weckton an/aus).
        self.alarm_map: dict[str, str] = {}
        self._alarm_prev: dict[str, object] = {}
        # Sicherheits-Alarme (Alarmanlage, Rauchmelder): State "level" -> Baustein
        self.sec_map: dict[str, str] = {}
        self._sec_prev: dict[str, object] = {}
        self._pending_sec: list[dict] = []
        self._pending_alarm: list[dict] = []
        self.agents: dict[str, dict] = {}   # ip -> Panel-Agent (Fernstart)
        self.bg_tasks: set = set()          # laufende Hintergrund-Tasks (z.B. Favs anfordern)
        self._item_errors: set[str] = set()   # Bausteine, deren Kachel schon einmal fehlschlug (Log nur einmal)
        self._cam_hubs: dict[str, "CamHub"] = {}           # Kamera-UUID -> Verteiler (eine Verbindung je Kamera)
        # Dynamisches Song-Cover (iTunes) fuer Zonen, die nur ein Sender-Logo
        # liefern (z.B. Sonn/Audioserver): "artist\ntitle" -> (url|None, expiry).
        self._cover_cache: dict[str, tuple[str | None, float]] = {}
        self._cover_pending: set[str] = set()

    def drop_conn(self, ws) -> None:
        """Alle Daten einer Panel-Verbindung vergessen (getrennt oder tot).
        EINE Stelle fuer alle conn_*-Tabellen und den Sende-Cache - vorher an
        fuenf Stellen einzeln und unterschiedlich vollstaendig gepflegt, der
        Sende-Cache (_last_sent) wurde beim normalen Trennen nie geleert."""
        dev = self.conn_dev.get(ws)
        if dev:                                   # Zeitpunkt der Trennung -> Config zeigt kurz "verbindet …"
            self._dev_gone[dev] = time.time()
        for d in (self.conn_route, self.conn_prof, self.conn_dev, self.conn_info,
                  self.conn_player, self.conn_energy, self.conn_chart, self.conn_camera,
                  self._last_sent, self._ws_locks):
            d.pop(ws, None)

    def _spawn(self, coro) -> None:
        """Hintergrund-Task starten und sauber referenziert halten."""
        task = asyncio.ensure_future(coro)
        self.bg_tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task) -> None:
        """Hintergrund-Task fertig: Fehler sofort melden (sonst erst beim Aufraeumen
        des Speichers als "Task exception was never retrieved")."""
        self.bg_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            err = task.exception()
            key = ("task", repr(err)[:80])
            if time.monotonic() - _EXC_SEEN.get(key, -1e9) >= 300:   # gleiche Meldung hoechstens alle 5 min
                _EXC_SEEN[key] = time.monotonic()
                log.error("Hintergrund-Task fehlgeschlagen: %s", err, exc_info=err)

    def _song_cover(self, artist: str, title: str) -> str | None:
        """Album-Cover (ueber /cover-Proxy) zu Interpret+Titel, gecacht.

        Cache-Treffer -> URL bzw. None (kein Album, z.B. Wortbeitrag). Bei einem
        Miss wird der Lookup einmalig im Hintergrund angestossen; das Ergebnis
        erscheint beim naechsten Render (der Lookup setzt _dirty)."""
        artist = (artist or "").strip()
        title = (title or "").strip()
        if not artist or not title:
            return None
        key = f"{artist}\n{title}".lower()
        hit = self._cover_cache.get(key)
        if hit and hit[1] > time.time():
            return ("/cover?u=" + quote(hit[0], safe="")) if hit[0] else None
        if key not in self._cover_pending:
            self._cover_pending.add(key)
            self._spawn(self._lookup_cover(artist, title, key))
        return None

    async def _lookup_cover(self, artist: str, title: str, key: str) -> None:
        """iTunes-Suche nach Interpret+Titel -> Album-Cover-URL (600px)."""
        url = None
        try:
            sess = self.icon_session
            if sess is not None:
                api = "https://itunes.apple.com/search?" + urlencode(
                    {"term": f"{artist} {title}", "media": "music",
                     "entity": "song", "limit": 1})
                async with sess.get(api, timeout=aiohttp.ClientTimeout(total=6)) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        res = data.get("results") or []
                        if res:
                            art = res[0].get("artworkUrl100") or ""
                            url = art.replace("100x100bb", "600x600bb") or None
        except Exception as err:
            log.debug("Cover-Lookup (%s): %s", key, err)
        # Treffer lange cachen (gleicher Song -> gleiches Cover), Fehlschlag kurz
        # (aus Wortbeitrag wird spaeter wieder ein Titel).
        now = time.time()
        if len(self._cover_cache) > 300:          # ueber Tage nicht unbegrenzt wachsen: Abgelaufenes raus
            self._cover_cache = {k: v for k, v in self._cover_cache.items() if v[1] > now}
        self._cover_cache[key] = (url, now + (24 * 3600 if url else 900))
        self._cover_pending.discard(key)
        if url:
            self._dirty = True

    def _ssl_ctx(self) -> _ssl.SSLContext:
        ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
        if not self.verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
        return ctx

    def housekeeping(self) -> None:
        """Datenmuell vermeiden: Reste geloeschter Bausteine und lange nicht
        gesehener Geraete entfernen. Nur mit geladener Struktur (sonst waere
        bei Miniserver-Ausfall alles "geloescht")."""
        if len(self.controls) < 5:
            return
        try:
            gone = [u for u in self.scene_light if u not in self.controls]
            for u in gone:
                del self.scene_light[u]
            if gone:
                _atomic_write(SCENE_LIGHT_FILE, json.dumps(self.scene_light, ensure_ascii=False))
            ics = {u for u, c in self.controls.items() if c.get("type") == "Intercom"}
            n = 0
            if SOUNDS_DIR.is_dir():
                for f in SOUNDS_DIR.iterdir():
                    if f.is_file() and _UUID_RE.match(f.stem) and f.stem not in ics:
                        f.unlink(missing_ok=True)
                        n += 1
            if BG_DIR.is_dir():                     # Hintergrundbilder geloeschter Panels
                for f in BG_DIR.iterdir():
                    if f.is_file() and f.suffix[1:] in _BG_TYPES and f.stem not in self.panels:
                        f.unlink(missing_ok=True)
            # Geraete: nach 90 Tagen ohne Verbindung Steckbrief vergessen; ein
            # automatisch angelegtes Geraet ohne eigene Einstellungen (Betriebsmodus,
            # Display-Treiber) gleich mit - eingerichtete Geraete bleiben.
            old = time.time() - 90 * 86400
            stale = [u for u, e in self.devinfo.items() if not isinstance(e, dict) or e.get("last", 0) < old]
            names = {(self.devinfo[u] or {}).get("name") for u in stale if isinstance(self.devinfo.get(u), dict)}
            for u in stale:
                del self.devinfo[u]
            still = {e.get("name") for e in self.devinfo.values() if isinstance(e, dict)}
            drop = [nm for nm in names if nm and nm not in still and isinstance(self.devices.get(nm), dict)
                    and not self.devices[nm].get("modes") and not self.devices[nm].get("display")]
            if drop:
                self._write_devices({k: v for k, v in self.devices.items() if k not in drop})
            if stale:
                self._save_devinfo()
            if gone or n or stale or drop:
                log.info("Aufgeraeumt: %d Szenen-Licht, %d Klingeltoene, %d Steckbriefe, %d Geraete",
                         len(gone), n, len(stale), len(drop))
        except Exception:
            log.exception("Aufraeumen fehlgeschlagen")

    def _apply_structure(self, st: dict) -> None:
        self.controls = st.get("controls", {})
        self.rooms = st.get("rooms", {})
        self.cats = st.get("cats", {})
        # Audioserver-Adressen fuer den Gen-2-Event-Kanal: {serverUUID: "host:port"}
        ms = st.get("mediaServer") or {}
        self.mediaservers = {u: (v or {}).get("host", "")
                             for u, v in ms.items() if isinstance(v, dict) and (v or {}).get("host")}
        # Standort des Miniservers (Loxone setzt latitude/longitude immer, fuer
        # Astro/Sonnenstand) -> Wetter ohne Konfiguration (Fallback fuer loxpanel.cfg).
        info = st.get("msInfo") or {}
        try:
            self.ms_lat = float(info["latitude"]) if info.get("latitude") not in (None, "") else None
            self.ms_lon = float(info["longitude"]) if info.get("longitude") not in (None, "") else None
        except (TypeError, ValueError, KeyError):
            self.ms_lat = self.ms_lon = None
        self.ms_location = str(info.get("location") or "").strip()
        self.rooms_with = sorted(
            {c.get("room") for c in self.controls.values() if c.get("room") in self.rooms},
            key=lambda r: self.rooms[r].get("name", ""))
        self.cats_with = sorted(
            {c.get("cat") for c in self.controls.values() if c.get("cat") in self.cats},
            key=lambda c: self.cats[c].get("name", ""))
        self.bell_map = {}
        self.alarm_map = {}
        self.sec_map = {}
        self.push_state = {}
        for _pu, _pc in self.controls.items():
            if _pc.get("type") == "Pushbutton":
                _ps = (_pc.get("states") or {}).get("active")
                if isinstance(_ps, str):
                    self.push_state[_ps] = _pu
        # Betriebsarten (id -> Name) fuer die Wecker-Wiederholung: die `modes`
        # eines Eintrags verweisen hierauf (z.B. Wochentage Mo-So).
        self.op_modes = {str(k): v for k, v in (st.get("operatingModes") or {}).items()}
        # Globale States der Anlage (Name -> UUID): u.a. Sonnenauf-/-untergang und
        # die aktiven Betriebsmodi. Die Werte kommen ueber den WS-Stream in
        # self.states. Roh uebernehmen, die Belegung ist je Anlage verschieden.
        self.global_states = dict(st.get("globalStates") or {})
        # Loxone-Wetterdienst: nur vorhanden, wenn die Anlage ihn gebucht hat.
        # Enthaelt die State-UUIDs (actual/forecast), die Wetterlage-Texte und
        # die Formatstrings mit den Einheiten. Der Wetterpuffer gehoert zu diesen
        # UUIDs und wird mit der Struktur zusammen verworfen.
        wsrv = st.get("weatherServer")
        self.weather_cfg = wsrv if isinstance(wsrv, dict) else {}
        self._lox_wx = {}
        self.playerid_by_action = {}
        self.audiohost_by_action = {}
        for _u, _c in self.controls.items():
            if _c.get("type") == "Intercom":
                _bu = (_c.get("states") or {}).get("bell")
                if _bu:
                    self.bell_map[_bu] = _u
            elif _c.get("type") in SEC_ALARM_TYPES:
                _lu = (_c.get("states") or {}).get("level")
                if _lu:
                    self.sec_map[_lu] = _u
            elif _c.get("type") == "AlarmClock":
                _au = (_c.get("states") or {}).get("isAlarmActive")
                if _au:
                    self.alarm_map[_au] = _u
            elif _c.get("type") in ("AudioZone", "AudioZoneV2"):
                # Beide Zonentypen werden direkt am Audioserver (7091) gesteuert:
                # AudioZone -> Musikserver, AudioZoneV2 -> Audioserver Gen2 (Sonn).
                # Der Umweg ueber den Miniserver (sps/io) reicht roomfav/play NICHT
                # zuverlaessig durch; der Direktkanal (auch beim Sonn, ohne Token
                # getestet) funktioniert fuer play/pause/next/volume/roomfav.
                _det = _c.get("details") or {}
                _pid = _det.get("playerid")
                _ua = _c.get("uuidAction")
                if _ua and _pid is not None:
                    self.playerid_by_action[_ua] = int(_pid)
                    _hp = self.mediaservers.get(_det.get("server"))
                    if _hp:
                        self.audiohost_by_action[_ua] = _hp.split(":")[0].strip()
        log.info("Struktur: %d Controls, %d Räume, %d Kategorien, %d Intercom-Klingeln, %d Wecker, %d AudioZones",
                 len(self.controls), len(self.rooms_with), len(self.cats_with),
                 len(self.bell_map), len(self.alarm_map), len(self.playerid_by_action))

    @staticmethod
    def _structure_sig(st: dict) -> str:
        """Signatur der Loxone-Struktur (Controls/Raeume/Kategorien). Aendert sich
        nur bei Config-Aenderungen (Namen, neue/entfernte Controls …), nicht bei
        State-Werten – die kommen separat ueber den WS-Stream."""
        try:
            rel = {"controls": st.get("controls", {}), "rooms": st.get("rooms", {}),
                   "cats": st.get("cats", {})}
            raw = json.dumps(rel, sort_keys=True, ensure_ascii=False, default=str)
            return hashlib.md5(raw.encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            return ""

    def _adopt_structure(self, st: dict) -> bool:
        """Struktur anwenden und melden, ob sie sich seit der letzten Verbindung
        geaendert hat (Grundlage fuer den Panel-Reload). Beim allerersten Anwenden
        (`_struct_sig` noch None) gilt sie nie als 'geaendert' — frisch verbundene
        Panels holen sich die Ansichten ohnehin neu."""
        sig = self._structure_sig(st)
        changed = bool(self._struct_sig and sig and sig != self._struct_sig)
        self._apply_structure(st)
        self._struct_sig = sig
        self.housekeeping()
        return changed

    async def _refresh_structure(self) -> bool:
        """Struktur neu vom Miniserver laden und anwenden, WENN sie sich geaendert
        hat (Loxone-Config geaendert). Gibt True bei Aenderung zurueck. Rein lesend;
        Fehler werden vom Aufrufer isoliert, damit die Verbindungs-Schleife lebt."""
        if self.client is None:
            return False
        st = await self.client.load_structure()
        if not self._adopt_structure(st):
            return False                      # unveraendert -> nichts tun (kein Panel-Reload)
        self.states = {}                      # nach Struktur-Wechsel States frisch (MS sendet neu)
        self._dirty = True
        return True

    async def start(self) -> None:
        try:
            self.client = _make_client(self.host, self.user, self.password,
                                       self.port, self.verify_tls)
            await self.client.__aenter__()
            self.alg = (await self.client.getkey2()).hashAlg
            self._set_token(await self.client.authenticate())
            st = await self.client.load_structure()
            # Reconnect nach Miniserver-Reboot (z.B. Loxone-Config hochgeladen):
            # hat sich die Struktur geaendert, Panels neu laden lassen. Beim
            # allerersten Start ist _struct_sig None -> kein Reload.
            if self._adopt_structure(st):
                self._pending_reload = True
            self.icon_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self._ssl_ctx()))
            await self._connect_ws()
            log.info("Mit Miniserver verbunden (%s).", self.host)
        except Exception:
            await self._close_conn()   # sauber zuruecksetzen, damit Retry neu aufbaut
            raise

    async def _close_conn(self) -> None:
        for c in (self.ws, self.icon_session, self.client):
            try:
                if c:
                    await c.close()
            except Exception:
                pass
        self.ws = self.icon_session = self.client = None

    async def reconnect(self) -> int:
        """Verbindung mit (ge-aenderter) Config neu aufbauen. Gibt Control-Anzahl
        zurueck; wirft bei falschen Zugangsdaten. Alte Verbindung bleibt bei
        Fehler bestehen (neuer Client wird nur bei Erfolg uebernommen)."""
        ms = _config()
        missing = [k for k in ("host", "user", "pass") if not ms.get(k)]
        if missing:
            raise ValueError(
                "Miniserver-Konfiguration unvollstaendig (fehlt: "
                + ", ".join(missing) + "). Bitte unter Einstellungen -> "
                "Miniserver Host, Benutzer und Passwort eintragen.")
        newc = _make_client(ms["host"], ms["user"], ms["pass"],
                            ms.get("port", 443), ms.get("verify_tls", False))
        try:
            await newc.__aenter__()
            alg = (await newc.getkey2()).hashAlg
            jwt = await newc.authenticate()
            st = await newc.load_structure()
        except Exception:
            try:
                await newc.close()
            except Exception:
                pass
            raise
        # Erfolg -> uebernehmen
        self.host, self.port = ms["host"], ms.get("port", 443)
        self.user, self.password = ms["user"], ms["pass"]
        self.verify_tls = ms.get("verify_tls", False)
        old_client, self.client = self.client, newc
        self.alg = alg
        self._set_token(jwt)
        # Anderer/geaenderter Miniserver -> Struktur evtl. anders, dann Panels neu laden.
        if self._adopt_structure(st):
            self._pending_reload = True
        self.states = {}
        old_is, self.icon_session = self.icon_session, \
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self._ssl_ctx()))
        self.icon_cache = {}
        self.stat_cache, self.stat2_cache, self.stat_memo = {}, {}, {}   # anderer Miniserver -> andere Verlaeufe
        self.stat_gen += 1
        old_ws, self.ws = self.ws, None   # stream_task baut WS mit neuen Daten neu auf
        self.intercom_cfg = _intercom_config()
        self._dirty = True
        for closer in (old_client, old_is, old_ws):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        self.ms_next_retry = 0.0
        self._retry_now.set()   # neue/korrigierte Zugangsdaten: nicht erst die Pause abwarten
        return len(self.controls)

    async def _connect_ws(self) -> None:
        self.ws = LoxoneWS(host=self.host, port=self.port, user=self.user, jwt=self.jwt,
                           hash_alg=self.alg, verify_tls=self.verify_tls,
                           secure=_ms_https(self.port))
        await self.ws.connect()

    def _set_token(self, jwt: str) -> None:
        self.jwt = jwt
        self._auth_gen += 1
        self._auth_at = time.monotonic()

    async def _reauth(self) -> None:
        # Token erneuern (kann nach langer Laufzeit ablaufen)
        if self.client:
            self._set_token(await self.client.authenticate())

    async def _renew_token(self, seen_gen: int) -> bool:
        """Nach einem 401 neu anmelden. Hat eine parallele Anfrage das schon
        getan (Zaehler weiter als seen_gen), genuegt es, erneut zu senden. Innerhalb
        von TOKEN_RENEW_MIN nach der letzten Anmeldung nicht noch einmal: dann liegt
        der 401 nicht am Token. -> True, wenn sich ein Neuversuch lohnt."""
        async with self._auth_lock:
            if self._auth_gen != seen_gen:
                return True
            if not self.client or time.monotonic() - self._auth_at < TOKEN_RENEW_MIN:
                return False
            self._auth_at = time.monotonic()     # auch ein Fehlversuch sperrt fuer TOKEN_RENEW_MIN
            try:
                self._set_token(await self.client.authenticate())
            except Exception as err:            # z. B. Passwort geaendert, Miniserver startet neu
                log.warning("Neuanmeldung am Miniserver fehlgeschlagen: %s", err or type(err).__name__)
                return False
            log.info("Miniserver-Token abgelaufen -> neu angemeldet")
            return True

    async def _ms_http(self, path: str, timeout: float, renew: bool = True) -> tuple[int, bytes, str]:
        """GET an den Miniserver mit dem aktuellen Token; bei 401 (und renew)
        einmal neu anmelden und wiederholen. -> (HTTP-Status, Inhalt, Content-Type). Wirft
        ConnectionError ohne Verbindung, sonst aiohttp.ClientError/TimeoutError."""
        async def once() -> tuple[int, bytes, str]:
            if self.icon_session is None:
                raise ConnectionError("keine Verbindung zum Miniserver")
            scheme = "https" if _ms_https(self.port) else "http"
            headers = {"Authorization": f"Bearer {self.jwt}"} if self.jwt else {}
            async with self.icon_session.get(f"{scheme}://{self.host}:{self.port}/{path.lstrip('/')}",
                                             headers=headers,
                                             timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                return r.status, await r.read(), r.headers.get("Content-Type", "")
        gen = self._auth_gen
        res = await once()
        if res[0] == 401 and renew and await self._renew_token(gen):
            res = await once()
        return res

    async def _ms_jdev(self, path: str, timeout: float = MS_CMD_TIMEOUT,
                       renew: bool = True) -> tuple[str, object]:
        """jdev-Befehl ueber _ms_http. -> (Code, LL.value); Code ist der
        LL-Code der Antwort, ohne lesbares JSON der HTTP-Status."""
        status, body, _ = await self._ms_http("jdev/" + path.lstrip("/"), timeout, renew)
        try:
            ll = json.loads(body.decode("utf-8", "replace").lstrip("\ufeff").strip("\x00")).get("LL") or {}
        except (ValueError, AttributeError):
            ll = {}
        code = ll.get("Code") or ll.get("code")
        return (str(code) if code is not None else str(status)), ll.get("value")

    def _win_counts(self, c: dict) -> tuple[int, int]:
        """(offen, gekippt) einer Fensterueberwachung. Massgeblich ist die
        Bitmaske windowStates je Fenster (4 offen, 2 gekippt) - die Zaehler
        numOpen/numTilted bleiben bei manchen Miniservern auf 0 haengen.
        Ohne Bitmaske zaehlen die Zaehler."""
        raw = str(self._state(c, "windowStates") or "")
        op = ti = 0
        seen = False
        for v in (x for x in raw.split(",") if x != ""):
            try:
                bits = int(float(v))
            except ValueError:
                continue
            seen = True
            if bits & 4:
                op += 1
            elif bits & 2:
                ti += 1
        if not seen:
            try:
                op, ti = int(self._state(c, "numOpen") or 0), int(self._state(c, "numTilted") or 0)
            except (TypeError, ValueError):
                op = ti = 0
        return op, ti

    # ---- Zustands-Helfer ----
    def _state(self, control: dict, name: str):
        su = (control.get("states") or {}).get(name)
        return self.states.get(su) if su else None

    def _text(self, control: dict, name: str) -> str:
        """Text-State, URL-dekodiert (Loxone liefert songName/artist prozentkodiert)."""
        v = self._state(control, name)
        return unquote(str(v)) if v not in (None, "") else ""

    def _json_state(self, control: dict, name: str):
        """JSON-State (Loxone liefert Listen/Objekte als ggf. prozentkodierten
        Text). None, wenn leer oder nicht parsebar (dann einmal geloggt)."""
        raw = self._state(control, name)
        if raw in (None, ""):
            return None
        if not isinstance(raw, str):
            return raw
        txt = unquote(raw).strip()
        try:
            return json.loads(txt)
        except ValueError:
            _log_once_warn(("json", control.get("uuidAction"), name),
                           "%s.%s nicht als JSON parsebar: %r", control.get("type"), name, txt[:160])
            return None

    @staticmethod
    def _named_items(data) -> list[tuple[str, dict]]:
        """Liste/Objekt aus einem JSON-State in (Label, Eintrag)-Paare wandeln.
        Label aus name/title/label, sonst laufende Nummer."""
        if isinstance(data, dict):
            seq = list(data.items())
        elif isinstance(data, (list, tuple)):
            seq = list(enumerate(data))
        else:
            return []
        out = []
        for i, (key, e) in enumerate(seq):
            if isinstance(e, dict):
                label = _clean(e.get("name") or e.get("title") or e.get("label")) or str(key if isinstance(key, str) else i + 1)
                out.append((label, e))
            else:
                out.append((str(key if isinstance(key, str) else i + 1), {"value": e}))
        return out

    def _flow_text(self, value, fmt: str, pos: str, neg: str, zero: str | None = None) -> str:
        """Leistung mit Richtung: Vorzeichen -> Text (z.B. Bezug/Einspeisung).
        Loxone zaehlt aus Sicht des Hauses: positiv = fliesst ins Haus, also
        Netzbezug bzw. Speicher entlaedt; negativ = Einspeisung bzw. Laden.
        zero: Text fuer 0 (ohne Richtung), sonst gilt 0 als positiv."""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        num = self._fmt_num(abs(v), fmt)
        if not num:   # Fehlwert (Sentinel) -> kein Text
            return ""
        text = zero if (zero and v == 0) else (pos if v >= 0 else neg)
        return f"{text} {num}"

    def _tracker_lines(self, control: dict) -> list[str]:
        """Ereignis-Zeilen eines Tracker-Bausteins (State 'entries'). Loxone
        liefert einen mehrzeiligen, ggf. prozentkodierten Text; neueste zuerst.
        Der Zeilentrenner variiert je nach Firmware: echtes Newline, Literal
        "\\n"/"\\r" (Backslash+Buchstabe) oder CR -> alle normalisieren, sonst
        landet der ganze Verlauf in EINER Zeile."""
        raw = self._state(control, "entries")
        if raw in (None, ""):
            return []
        txt = unquote(str(raw))
        for sep in ("\r\n", "\\r\\n", "\\n", "\\r", "\r"):
            txt = txt.replace(sep, "\n")
        # Loxone-Standard: Eintraege im State "entries" mit "|" getrennt
        txt = txt.replace("|", "\n")
        return [ln.strip() for ln in txt.split("\n") if ln.strip()]

    @staticmethod
    def _split_ts(line: str) -> tuple[str | None, str]:
        """Fuehrenden Zeitstempel abtrennen -> (zeitstempel|None, text)."""
        m = _TS_RE.match(line or "")
        return (m.group(1), m.group(2)) if m else (None, line or "")

    def _song(self, control: dict) -> str:
        """songName, aber rohe Stream-URLs (Radio) ausblenden."""
        s = self._text(control, "songName")
        return "" if s.startswith(("http://", "https://")) else s

    def _lc_scenes(self, c: dict) -> dict:
        """LightController-V1 sceneList (Loxone-Format id=\"name\") -> {id:name}."""
        raw = str(self._state(c, "sceneList") or "")
        return {int(m.group(1)): m.group(2) for m in re.finditer(r'(\d+)="([^"]*)"', raw)}

    def _json_list_map(self, c: dict, name: str) -> dict:
        """State-Wert = JSON-Array [{id,name}] -> {id:name}."""
        raw = self._state(c, name)
        try:
            arr = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return {}
        return {int(x["id"]): x.get("name") for x in (arr or [])
                if isinstance(x, dict) and x.get("id") is not None}

    def _irc_modes(self, c: dict) -> dict:
        """IRoomControllerV2: Temperatur-/Timer-Modi aus details.timerModes ->
        {id: Name} (z. B. 0=Eco, 1=Komfort, 2=Gebaeudeschutz)."""
        tm = (c.get("details") or {}).get("timerModes") or []
        return {int(m["id"]): _clean(m.get("name"))
                for m in tm if isinstance(m, dict) and m.get("id") is not None}

    @staticmethod
    def _irc_activity(prep, win) -> list:
        """Aktivitaets-Hinweise fuer die Raumregelung: heizt/kuehlt + Fenster."""
        bits = []
        try:
            p = float(prep)
        except (TypeError, ValueError):
            p = 0.0
        if p > 0:
            bits.append("heizt")
        elif p < 0:
            bits.append("kühlt")
        if win:
            bits.append("Fenster")
        return bits

    @staticmethod
    def _irc_tone(prep) -> str:
        """Farbton des grossen Werts: Loxone meldet heizen (> 0) bzw. kuehlen (< 0),
        sonst keiner. Das Panel macht daraus Theme-Farben (heat/cool)."""
        try:
            p = float(prep)
        except (TypeError, ValueError):
            return ""
        return "heat" if p > 0 else ("cool" if p < 0 else "")

    def _irc_top(self, ta, prep, tt, soll, soll_label, zustand, art, window, minus=None, plus=None) -> list:
        """Kopfbloecke der Raumregelung (Detail-Schema, Heizung):
          ist    grosser Ist-Wert (Farbton heizt/kuehlt) mit -/+ als runde Knoepfe daneben
                 (stellen den Komfort-Soll; ohne bekannten Absolutwert entfallen sie)
          sline  EINE ruhige Textzeile aus Soll, aktivem Modus, Aktivitaet (Heizen /
                 Kuehlen / Ruht) + Ziel, Fenster; dazu nur der tippbare Betriebsart-
                 Aufklapper als Chip (aus _irc_betriebsart)."""
        try:
            p = float(prep)
        except (TypeError, ValueError):
            p = 0.0
        akt = "Heizen" if p > 0 else ("Kühlen" if p < 0 else "Ruht")
        if tt:
            akt += f" · Ziel {tt}°"
        parts = []
        if soll:
            parts.append(f"Soll {soll}° {soll_label}")
        if zustand and zustand.casefold() != soll_label.casefold():
            parts.append(zustand)
        parts.append(akt)
        if window:
            parts.append("Fenster offen")
        ist = {"k": "ist", "text": f"{ta} °C" if ta else "–", "tone": self._irc_tone(prep)}
        if minus and plus:
            ist["minus"], ist["plus"] = minus, plus
        line = {"k": "sline", "text": " · ".join(parts)}
        if art:
            cur = next((m["label"] for m in art.get("menu") or [] if m.get("on")), "")
            line["chip"] = {"text": cur or art.get("label") or "Betriebsart", "menu": art["menu"]}
        return [ist, line]

    def _irc_schedule(self, c: dict, modes: dict) -> dict | None:
        """Tagesplan der Raumregelung aus dem Daytimer-Unterbaustein (State
        entriesAndDefaultValue) -> {"segs": [{"a","b","k","name"}], ...} mit
        Minuten ab Mitternacht; k = comfort | eco | other (Name des Modus aus
        details.timerModes). Format: Vorgabewert, Anzahl, dann je Eintrag
        [Modus,] von, bis, [Aktivierung,] Wert (Zeiten Minuten oder HH:MM).
        None, wenn der Baustein keinen Plan liefert oder das Format nicht passt
        (dann zeigt das Panel keine Zeitleiste - nichts erfunden)."""
        txt, src = None, c
        for sc in (c.get("subControls") or {}).values():
            if "entriesAndDefaultValue" in (sc.get("states") or {}):
                src = sc
                break
        txt = self._state(src, "entriesAndDefaultValue")
        if not txt or not isinstance(txt, str):
            return None
        toks = [t for t in re.split(r"[;,|\s]+", unquote(txt).strip()) if t != ""]

        def num(t):
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
            if m:
                return int(m.group(1)) * 60 + int(m.group(2))
            try:
                return float(t)
            except ValueError:
                return None
        vals = [num(t) for t in toks]
        if len(vals) < 2 or None in vals:
            _log_once_warn(("irc-sched", c.get("uuidAction")), "IRC-Plan nicht lesbar: %r", txt[:160])
            return None
        dflt, n, rest = vals[0], int(vals[1]), vals[2:]
        if n <= 0 or n > 64:
            return None
        sz = len(rest) // n if len(rest) % n == 0 else 0
        if sz not in (3, 4, 5):
            _log_once_warn(("irc-sched", c.get("uuidAction")), "IRC-Plan Format unbekannt: %r", txt[:160])
            return None

        def kind(v):
            nm = modes.get(int(v)) or ""
            low = nm.lower()
            return ("comfort" if "komfort" in low else ("eco" if "eco" in low else "other")), nm
        segs = []
        for i in range(n):
            e = rest[i * sz:(i + 1) * sz]
            v = e[-1]
            a, b = (e[0], e[1]) if sz == 3 else (e[1], e[2])
            if not (0 <= a <= 1440 and 0 <= b <= 1440):
                return None
            if b <= a:
                b = 1440 if b == 0 else b
            k, nm = kind(v)
            segs.append({"a": int(a), "b": int(b), "k": k, "name": nm})
        segs.sort(key=lambda x: x["a"])
        k, nm = kind(dflt)
        return {"segs": segs, "dk": k, "dname": nm}

    def _irc1(self, c: dict) -> dict:
        """Zustand der alten Raumregelung (IRoomController, v1):
          kuehlen   laeuft die Kuehlperiode (State mode, IRC1_KUEHL_MODI)
          ix/name   aktive Temperatur (currCoolTempIx bzw. currHeatTempIx)
          stell_ix  Temperatur, die -/+ verstellt: manuell die manuelle, sonst
                    Komfort der Periode
          stell     ihr aktueller Wert; None, wenn unbekannt oder relativ zu
                    Komfort (dann gibt es kein -/+, statt einen Wert zu raten)
          komfort_ix Komfort der Periode (fuer den Komfort-Knopf)
          prep      fuer _irc_activity: Ventil Heizen > 0 = 1, Kuehlen > 0 = -1"""
        def num(name):
            try:
                return float(self._state(c, name))
            except (TypeError, ValueError):
                return None

        mode = num("mode")
        mode = int(mode) if mode is not None else None
        kuehlen = mode in IRC1_KUEHL_MODI
        ix = num("currCoolTempIx" if kuehlen else "currHeatTempIx")
        ix = int(ix) if ix is not None else None
        komfort_ix = IRC1_KOMFORT_KUEHLEN if kuehlen else IRC1_KOMFORT_HEIZEN
        if mode in IRC1_MANUELL_MODI:
            stell_ix, stell = IRC1_MANUELL, num("tempTarget")
        else:
            stell_ix = komfort_ix
            stell = self._irc1_temp(c, komfort_ix) if self._irc1_absolut(c, komfort_ix) else None
        prep = 1 if (num("valveHeat") or 0) > 0 else (-1 if (num("valveCool") or 0) > 0 else 0)
        return {"kuehlen": kuehlen, "ix": ix, "name": IRC1_TEMPS.get(ix), "stell_ix": stell_ix,
                "stell": stell, "komfort_ix": komfort_ix, "prep": prep}

    def _irc_betriebsart(self, c: dict) -> tuple[dict | None, str | None]:
        """Aufklapper "Betriebsart" einer Raumregelung und der Name fuer die
        Statuszeile, wenn manuell geregelt wird (dann laeuft kein Zeitplan).
        V2: State operatingMode, setOperatingMode/<Nr>. Alt: State mode,
        mode/<Nr>; "Automatik, heizt/kuehlt gerade" (1/2) gilt als Automatik,
        details.restrictedToMode blendet Heizen bzw. Kuehlen aus.
        (None, None), wenn der Baustein den State nicht hat."""
        v2 = c.get("type") == "IRoomControllerV2"
        name = "operatingMode" if v2 else "mode"
        ua = c.get("uuidAction")
        if not ua or name not in (c.get("states") or {}):
            return None, None
        try:
            cur = int(float(self._state(c, name)))
        except (TypeError, ValueError):
            cur = None
        if v2:
            arten, befehl, manuell = IRC2_BETRIEBSARTEN, "setOperatingMode", IRC2_MANUELL
            markiert = cur
        else:
            nur = (c.get("details") or {}).get("restrictedToMode")
            weg = {IRC1_NUR_KUEHLEN: {3, 5}, IRC1_NUR_HEIZEN: {4, 6}}.get(nur, set())
            arten = {n: nm for n, nm in IRC1_BETRIEBSARTEN.items() if n not in weg}
            befehl, manuell = "mode", IRC1_MANUELL_MODI
            markiert = 0 if cur in (1, 2) else cur
        zelle = {"label": "Betriebsart", "menu": [
            {"label": nm, "on": n == markiert, "cmd": {"uuid": ua, "cmd": f"{befehl}/{n}"}}
            for n, nm in arten.items()]}
        return zelle, (arten.get(cur) if cur in manuell else None)

    def _irc1_temp(self, c: dict, ix: int):
        """Wert der Temperatur Nr. ix: der State "temperatures" ist bei der
        alten Raumregelung eine Liste mit einer UUID je Nummer."""
        lst = (c.get("states") or {}).get("temperatures")
        if not isinstance(lst, list) or not 0 <= ix < len(lst):
            return None
        try:
            return float(self.states.get(lst[ix]))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _irc1_absolut(c: dict, ix: int) -> bool:
        """details.temperatures[ix].isAbsolute: True = fester Wert, False =
        haengt von Komfort ab. Nummern als Schluessel ("0".."6") oder Liste."""
        tt = (c.get("details") or {}).get("temperatures")
        if isinstance(tt, dict):
            e = tt.get(str(ix), tt.get(ix))
        elif isinstance(tt, list) and 0 <= ix < len(tt):
            e = tt[ix]
        else:
            e = None
        return bool(isinstance(e, dict) and e.get("isAbsolute"))

    def _audio_favs(self, c: dict) -> list:
        """Raum-Favoriten (Radio/Playlist/Spotify) aus dem sourceList-State.

        Loxone legt das Ergebnis von `roomfav/get` in den sourceList-Textstate.
        Die Struktur variiert je nach Firmware:
          {"getroomfavs_result":[{...,"items":[...]}]}  (Gruppe(n) mit items)
          {"getroomfavs_result":[{...item...}]}          (flache Item-Liste)
          {"items":[...]}                                 (direktes Listing)
        Der State ist ausserdem ein transienter Browse-Puffer: er ist nur
        verlaesslich befuellt, nachdem wir `roomfav/get` angefordert haben
        (siehe prime_favs). Wir sammeln alle Items mit gueltigem 'slot' ein.
        """
        raw = self._state(c, "sourceList")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return []
        buckets = []
        res = data.get("getroomfavs_result")
        if isinstance(res, list):
            for grp in res:
                if isinstance(grp, dict) and isinstance(grp.get("items"), list):
                    buckets.append(grp["items"])
                elif isinstance(grp, dict) and "slot" in grp:
                    buckets.append([grp])
        if isinstance(data.get("items"), list):
            buckets.append(data["items"])
        out, seen = [], set()
        for items in buckets:
            for it in items:
                if not isinstance(it, dict):
                    continue
                slot = it.get("slot")
                if slot is None or slot in seen:
                    continue
                seen.add(slot)
                out.append({"slot": slot, "cover": it.get("coverurl") or "",
                            "type": (it.get("type") or "").lower(),
                            "name": unquote(str(it.get("name") or it.get("title") or f"Favorit {slot}"))})
        out.sort(key=lambda f: f["slot"])
        return out

    async def prime_favs(self, uuid: str) -> None:
        """Fordert die Zonen-Favoriten aktiv an (`roomfav/get`), damit der
        sourceList-State frisch befuellt wird. Das Ergebnis kommt asynchron
        per WS -> _on_value setzt _dirty -> broadcaster re-rendert die offene
        Ansicht (Musikauswahl) mit den nun vorhandenen Favoriten."""
        c = self.controls.get(uuid, {})
        t = c.get("type")
        if t not in ("AudioZone", "AudioZoneV2"):
            return
        # Zone mit laufendem Audioserver-Event-Client (Gen1 Musikserver ODER
        # Gen2 Audioserver): Raumfavoriten direkt ueber den 7091-Kanal anfordern
        # (Ergebnis kommt async -> _dirty). Der Loxone-sourceList-State ist bei
        # vielen Setups leer, deshalb ist das der zuverlaessige Weg.
        cl, pid = self._audio_client_for(c)
        if cl is not None and pid is not None and (cl.paired is False or cl.authed):
            await cl.request_favs(pid)
            return
        # Fallback ohne Event-Client (z.B. MS4H ohne 7091), bei gekoppeltem
        # Audioserver ohne Anmeldung oder unklarer Kopplung (paired None): Favoriten ueber den Miniserver holen.
        ua = c.get("uuidAction")
        if ua:
            await self.command(ua, "roomfav/get/0/20")

    def _fmt_num(self, value, fmt: str) -> str:
        """Loxone-Formatstring anwenden, Einheiten skalieren (kWh→MWh), Komma-Dezimal."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return ""
        if _is_sentinel(value):   # Int-Ueberlauf/Sentinel aus Loxone (2147483,647) = kein Messwert
            return ""
        m = _NUMFMT.match(fmt or "%.1f")
        numfmt, unit = (m.group(1), m.group(2)) if m else ("%.1f", "")
        unit = unit.strip().replace("%%", "%")   # "%.2f kW"/"%.2fkW" -> "3,25 kW"; Loxone-Escape "%%" -> "%"
        if unit[:1] in _PREFIX:
            i = _PREFIX.index(unit[0]); rest = unit[1:]
            while abs(value) >= 1000 and i < len(_PREFIX) - 1:
                value /= 1000.0
                i += 1
            unit = _PREFIX[i] + rest
        try:
            s = numfmt % value
        except (TypeError, ValueError):
            s = str(value)
        s = s.replace(".", ",")
        return (s + " " + unit) if unit else s

    def _with_uuid(self, uuid: str) -> dict:
        c = dict(self.controls[uuid])
        c["uuid"] = uuid
        return c

    def _jal_status(self, c: dict) -> str:
        s = c.get("states") or {}
        ai = s.get("autoInfoText")
        if ai and self.states.get(ai):
            return str(self.states.get(ai))
        aa = s.get("autoActive")
        if aa:
            return "Automatik aktiv" if self.states.get(aa) else "Sonnenstandsautomatik inaktiv"
        return "Manuell"

    @staticmethod
    def _icon_url(image: str | None) -> str | None:
        if image and (image.endswith(".svg") or image.endswith(".png")):
            return f"/icon?p={quote(image)}"
        return None

    def _control_icon_url(self, c: dict) -> str | None:
        """Echtes Loxone-Icon eines Controls. Reihenfolge wie in der Loxone-App:
        control-eigenes Bild -> `defaultIcon` (hier legt Loxone das pro Control
        gewaehlte/GEAENDERTE Icon ab, auch eigene Uploads) -> Kategorie-Icon."""
        di = (c.get("details") or {}).get("image")
        if isinstance(di, str):
            img = di
        elif isinstance(di, dict):
            img = di.get("on") or di.get("off")
        else:
            img = None
        if not img:
            img = c.get("defaultIcon")      # pro-Control gewaehltes Icon (inkl. Aenderung/Upload)
        if not img:
            img = (self.cats.get(c.get("cat")) or {}).get("image")   # Kategorie als Fallback
        return self._icon_url(img)

    def _node_icon_url(self, nd: dict) -> str | None:
        """Echtes Loxone-Icon eines EFM-Knotens (Verbraucher/Quelle). Die Icons
        gibt der Miniserver pro Knoten vor; das Feld heisst je nach Firmware
        unterschiedlich, deshalb erst die von Controls bekannten Felder, dann
        notfalls irgendein Bildpfad (.svg/.png) im Knoten. `image` kann ein Pfad
        oder ein {on/off}-Objekt sein (wie bei Controls)."""
        if not isinstance(nd, dict):
            return None
        cands = [nd.get("image"), nd.get("defaultIcon"), nd.get("icon"),
                 nd.get("iconSrc")] + list(nd.values())
        for v in cands:
            if isinstance(v, dict):
                v = v.get("on") or v.get("off")
            u = self._icon_url(v) if isinstance(v, str) else None
            if u:
                return u
        return None

    def _cat_entry(self, cat_uuid: str | None):
        """Passender categories-Eintrag (Match: Schluessel als Teilstring des
        Kategorienamens). Rueckgabe: str (nur Icon-Farbe) | dict {on,off}
        (Zustandsfarben) | None."""
        name = _clean((self.cats.get(cat_uuid) or {}).get("name") or "").lower()
        if not name:
            return None
        for key, val in self.theme.get("categories", {}).items():
            if not key.startswith("_") and key.lower() in name:
                return val
        return None

    def _cat_color(self, cat_uuid: str | None) -> str | None:
        val = self._cat_entry(cat_uuid)
        if isinstance(val, dict):
            return val.get("on") or val.get("off")   # Icon-Farbe = Aktiv-Farbe
        return val if isinstance(val, str) else None

    def _cat_states(self, cat_uuid: str | None):
        """Zustandsfarben {on, off} einer Kategorie (Ampel) oder None."""
        val = self._cat_entry(cat_uuid)
        return val if isinstance(val, dict) else None

    # ---- Panel-Profile ----
    def _resolve_ids(self, entries, table: dict):
        """Whitelist-Einträge (UUID ODER Name) auf UUID-Menge abbilden.

        Leer/fehlend -> None (= keine Einschränkung, alles sichtbar). Namen
        matchen exakt oder als Teilstring (Loxone-Räume haben Präfixe wie
        „1.0.2 Terrasse" -> Eintrag „Terrasse" genügt).
        """
        if not entries:
            return None
        names = {k: _clean(v.get("name", "")).lower() for k, v in table.items()}
        out = set()
        for e in entries:
            e = str(e).strip()
            if not e:
                continue
            if e in table:                       # exakte UUID
                out.add(e)
                continue
            el = _clean(e).lower()
            exact = [k for k, n in names.items() if n == el]
            if exact:
                out.update(exact)
            elif el:                             # Teilstring-Treffer
                out.update(k for k, n in names.items() if el in n)
        return out

    @staticmethod
    def _theme_vars(states: dict, ui: dict) -> dict:
        # Grundfarbe zuerst: daraus faellt der ganze Satz ab - Flaechen, Schrift,
        # Zweitzeile, Icon- und Zustandsfarben. Ohne Grundfarbe bleibt v leer und
        # es aendert sich nichts gegenueber frueher.
        # Design (Tab-Leiste oben, Karte je Tab) hat Vorrang. Ohne Design und
        # ohne Grundfarbe gilt die Standard-Vorlage ("bunt").
        if isinstance(ui.get("design"), dict) or not ui.get("baseColor"):
            v = theme_colors.design_vars(ui.get("design"))
        else:
            v = dict(theme_colors.derive(ui["baseColor"]) or {})
        # Ausdruecklich eingestellte Zustandsfarben schlagen die Herleitung.
        # Aber: "nicht gesetzt" gibt es bei states gar nicht - load_theme()
        # fuellt sie immer aus DEFAULT_THEME, und theme.example.json liefert
        # dieselben Werte. Als ausdrueckliche Wahl zaehlt deshalb nur ein Wert,
        # der von der eingebauten Vorgabe abweicht. Sonst wuerden die alten
        # Festfarben jedes hergeleitete Theme ueberschreiben und die ganze
        # Nachrechnung in theme_colors.py waere fuer diese Rollen wirkungslos.
        _hergeleitet = bool(v)
        _vorgabe = DEFAULT_THEME["states"]

        def _gewaehlt(key: str):
            wert = states.get(key)
            if not wert:
                return None
            if _hergeleitet and str(wert).strip().lower() == str(_vorgabe.get(key, "")).lower():
                return None
            return wert

        for _var, _key in (("--glow", "active"), ("--good", "good"),
                           ("--crit", "crit"), ("--warn", "warn")):
            _wert = _gewaehlt(_key)
            if _wert:
                v[_var] = _wert
        if _gewaehlt("good"):
            # Der Akzent zieht mit der OK-Farbe mit, damit aktiver Tab,
            # Energiefluss-Ring und Kalender ("heute") die eingestellte Farbe
            # uebernehmen statt auf dem Default (#52b881) zu bleiben - AUCH ohne
            # Panel-Farbe (loest #16: --accent wurde vorher nie an die Panels
            # geschickt). Mit Panel-Farbe schlaegt eine ausdrueckliche OK-Farbe
            # den hergeleiteten Akzent, sonst bleibt der hergeleitete Wert.
            v["--accent"] = _gewaehlt("good")
            _rgb = _hex_rgb(_gewaehlt("good"))
            if _rgb:
                v["--accent-rgb"] = _rgb
        v.update({
             "--ico-size": f"{ui.get('iconSize', 38)}px",
             "--name-size": f"{ui.get('nameSize', 18)}px",
             "--sub-size": f"{ui.get('subSize', 15)}px",
             # Vorhersage-Kacheln im Screensaver (Symbol/Datum/Temperatur
             # skalieren proportional mit) - unitless fuer calc() im CSS.
             "--sv-fc-size": str(_fc_size(ui.get("saverFcSize", 12.5))),
             "--tile-shadow": str(ui.get("tileShadow") or "0 3px 10px rgba(0,0,0,.14)")[:200],
             "--name-weight": "700" if ui.get("bold") else "450"})
        # Zustands-Farben zusaetzlich als R,G,B-Tripel (Fuellung/Rahmen der
        # good/crit-Kacheln mit fester Deckkraft).
        for skey, rvar in (("active", "--on-rgb"), ("good", "--good-rgb"),
                           ("crit", "--crit-rgb"), ("warn", "--warn-rgb")):
            rgb = _hex_rgb(_gewaehlt(skey))
            if rgb:
                v[rvar] = rgb
        if ui.get("font"):
            v["--font"] = ui["font"]
        if ui.get("fontNum"):
            v["--font-num"] = ui["fontNum"]     # Zahlen & Titel (Standard Sora)
        if ui.get("textColor"):
            v["--name-color"] = ui["textColor"]
        if ui.get("cols") == 3:
            v["--cols"] = "3"          # 3 Spalten (3x2 / 3x3); Default 2
        if ui.get("rows") == 3:
            v["--rows"] = "3"          # 3 Zeilen (2x3 / 3x3); Default 2
        nudge = ui.get("nudgeX")
        if nudge not in (None, ""):
            # Horizontaler Feinversatz der ganzen Visu (px, negativ = nach links)
            # gegen Display-Overscan. Wird vom Frontend als --nudge-x angewandt.
            try:
                v["--nudge-x"] = f"{float(nudge):g}px"
            except (TypeError, ValueError):
                pass
        return {k: val for k, val in v.items() if val}

    def resolve_profile(self, pid: str | None, raw: dict | None = None) -> dict:
        """Aufgeloestes Panel-Profil: Theme-Vars, Tabs, Raum-/Kategorie-Filter.
        raw: ungespeichertes Profil aus dem Konfigurator (Vorschau im Tab-Editor)."""
        prof = raw if isinstance(raw, dict) else (self.panels.get(pid or "") or self.panels.get("default") or {})
        ui = {**self.theme.get("ui", {}), **(prof.get("ui") or {})}
        states = {**self.theme.get("states", {}), **(prof.get("states") or {})}
        tabs = [t for t in (prof.get("tabs") or ui.get("tabs") or []) if _is_tab(t)] or \
            ["favoriten", "zentral", "raeume", "kategorien"]
        return {
            "id": pid or "default",
            "title": prof.get("title") or "LoxPanel",
            "tabs": list(tabs),
            "rooms": self._resolve_ids(prof.get("rooms"), self.rooms),
            "cats": self._resolve_ids(prof.get("cats"), self.cats),
            "vars": self._theme_vars(states, ui),
            "tiles": prof.get("tiles") or {},
            "layouts": prof.get("layouts") or {},   # Kachel-Raster je Tab (s. _tab_layout)
            "alarmPop": prof.get("alarmPop") or {},  # Alarm-Vollbild je Baustein an/aus
            "alarmTone": bool(prof.get("alarmTone")),  # Ton am Panel beim Alarm-Vollbild
            "tabIcons": prof.get("tabIcons") or {},  # eigenes Symbol je Tab (s. _tab_meta)
            "roomCats": [c for c in (prof.get("roomCats") or []) if isinstance(c, str)],
            "hide": {u for u in (prof.get("hide") or []) if isinstance(u, str)},
            # Eigene Favoriten durchreichen (siehe _panel_export): Liste = eigene
            # Auswahl (auch leer moeglich), None = nicht konfiguriert -> Fallback
            # auf Loxone-isFavorite in _view_tab.
            "favorites": ([u for u in prof.get("favorites") if isinstance(u, str) and u in self.controls]
                          if isinstance(prof.get("favorites"), list) else None),
            # Kachel-Anordnung je Scope (tab:zentral/tab:raeume/tab:kategorien/
            # room:<uuid>/cat:<uuid>) -> gewuenschte Reihenfolge. Angewendet in
            # _view_tab/_view_group per _apply_order().
            "tileOrder": {str(k): [u for u in v if isinstance(u, str)]
                          for k, v in (prof.get("tileOrder") or {}).items()
                          if isinstance(k, str) and isinstance(v, list)},
            # Sprache fuer Datum/Uhr: immer die der Konfiguration (Backend, rechts oben) -
            # keine eigene Einstellung mehr je Panel bzw. unter "Bedienung"
            "lang": (_clean_lang(self.theme.get("ui", {}).get("lang")) or "de"),
            "fill": bool(ui.get("fill")),       # Visu fuellt grosse Screens (quadratische Kacheln)
            # Split-Screen an/aus (aus = 4"-Panel: nur die Visu, keine Pane 2, keine
            # Verdopplung). Default an; nur bei explizitem False aus.
            "split": ui.get("split") is not False,
            # Handy-Profil: Flaechen untereinander, Tabs unten, volle Hoehe
            "phone": ui.get("phone") is True,
            "bigValues": ui.get("bigValues") in (True, "on"),   # Werte gross: global (Darstellung) + Panel-Override wie sceneLight
            # Split-Pane pro Tab: Tab-Kennung -> "weather"|"calendar"|"player:<uuid>".
            # Nur wirksam, wenn split an ist. Das Panel rendert die passende Pane.
            # Zusatzflaeche je Tab (Pane 2) entfaellt: Widgets liegen jetzt frei im
            # Raster, breite Displays zeigen zwei Seiten nebeneinander.
            "panes": {},
            # Animationen in drei Stufen - global (Settings) mit optionaler
            # Pro-Panel-Ueberschreibung (ui.motion in panels.json):
            # "off" keine, "mid" nur Ueberblendungen, "full" alles (Standard).
            "motion": (ui.get("motion") if ui.get("motion") in ("off", "mid") else "full"),
            # Mehr Kontrast: Kacheln/Knoepfe mit weichem Schatten (global mit
            # Pro-Panel-Ueberschreibung wie motion). Kostet etwas Rechenleistung.
            "contrast": ui.get("contrast") == "on",
            # Lichtszenen: Piktogramm zeigt Lichtfarbe + Helligkeit (lernend)
            "sceneLight": ui.get("sceneLight") == "on",
            # Animierte Symbole (Klingel wackelt, Jalousie-Pfeil wippt ...):
            # global an (Standard) mit Pro-Panel-Ueberschreibung wie motion.
            "iconAnim": ui.get("iconAnim") != "off",
            # Eigene Screensaver-Belegung (None = bisheriger Screensaver).
            "grid": _grid(ui.get("grid")),      # Standardraster des Panels (2x2 / 3x3)
            "saver": _sanitize_saver(prof.get("saver"), _grid(ui.get("grid"))),
            # Dashboard-Farbverlauf: Hintergrund / Uhrzeit-Schrift ("" = feste Design-Farben)
            "ambBg": ui.get("ambBg") if ui.get("ambBg") in AMBIENT_BG_MODES else "",
            "ambClock": ui.get("ambClock") if ui.get("ambClock") in AMBIENT_MODES else "",
        }

    def player_blocks(self, uuid: str):
        """Player-Bloecke (Cover/Titel/Transport/Lautstaerke) einer festen
        AudioZone fuer die linke Split-Player-Region. None, wenn keine gueltige
        Audio-Zone. Der `more`-Block (schwebender ⋮-Button) wird entfernt."""
        c = self.controls.get(uuid or "")
        if not c or c.get("type") not in ("AudioZone", "AudioZoneV2"):
            return None
        try:
            v = self._view_control_inner(uuid)
        except Exception:
            log.exception("player_blocks fehlgeschlagen (%s)", uuid)
            return None
        return [b for b in (v.get("blocks") or []) if b.get("k") != "more"]

    def saver_data(self, prof: dict) -> dict | None:
        """Live-Daten fuer die Screensaver-Belegung eines Profils: Kacheln der
        belegten Bausteine (gleiche Daten wie im Raster) und die Tuerstationen
        (Video + Tuer-Buttons). None, wenn das Profil keine eigene Belegung hat."""
        sv = (prof or {}).get("saver")
        if not sv:
            return None
        out = {"t": "saver", **self._widgets_data(sv["items"], prof)}
        if sv.get("bar"):
            try:
                out["bar"] = self.status_data(sv["bar"], None)
                for ch in out["bar"].get("chips") or []:   # eigene Symbole je Baustein
                    sh = (sv.get("barShow") or {}).get(ch.get("id"))
                    if sh and "stext" in ch:             # nur Status-Bausteine
                        ch["smode"], ch["slox"] = sh["mode"], sh["lox"]
                    ic = (sv.get("barIcons") or {}).get(ch.get("id"))
                    ref = self._icon_ref(ic) if ic else {}
                    if ref:
                        for k in ("icon", "iconUrl", "iconImg"):
                            ch.pop(k, None)
                        ch.update(ref)
            except Exception:
                log.exception("Dashboard-Statusleiste fehlgeschlagen")
        return out

    # ---- Status-Ampel (Widget "status") ----
    # Die Logik kommt aus dem Miniserver: Fensterueberwachung, Alarm, Rauchmelder,
    # Briefkasten, Statusbausteine (deren Farbe aus Loxone Config) usw. Das Panel
    # zeigt nur an. Stufen: alarm (rot) > hint (gelb) > ok; "info" (blau) zaehlt
    # nicht zur Ampel (z.B. Alarmanlage scharf).
    _ST_RANK = {"alarm": 3, "hint": 2, "info": 1, "ok": 0}

    @staticmethod
    def _color_level(col) -> str | None:
        """Farbe eines Statusbausteins -> Stufe (rot -> alarm, gelb/orange -> hint,
        gruen -> ok, sonst info). None ohne verwertbare Farbe."""
        m = re.match(r"#?([0-9a-fA-F]{6})", str(col or "").strip())
        if not m:
            return None
        r, g, b = (int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
        mx, mn = max(r, g, b), min(r, g, b)
        if mx - mn < 0.15:
            return "info"                         # grau/weiss: neutral
        if mx == r:
            h = (60 * ((g - b) / (mx - mn))) % 360
        elif mx == g:
            h = 60 * ((b - r) / (mx - mn)) + 120
        else:
            h = 60 * ((r - g) / (mx - mn)) + 240
        if h < 20 or h >= 330:
            return "alarm"
        if h < 65:
            return "hint"
        if h < 170:
            return "ok"
        return "info"

    def status_chip(self, uuid: str) -> dict | None:
        c = self.controls.get(uuid)
        if not c:
            return None
        t = c.get("type") or ""
        name = _clean(c.get("name")) or t
        lvl, txt, icon, detail = "ok", "", "info", []
        count = 0                                 # Anzahl fuer die Plakette in der Statusleiste
        if t == "WindowMonitor":
            op, ti = self._win_counts(c)
            n = op + ti
            lvl, icon = ("hint" if n else "ok"), "window"
            count = n
            txt = f"{n} offen" if n else "zu"
            # welche Fenster? windowStates = Bitmaske je Fenster (2 gekippt, 4 offen)
            wins = (c.get("details") or {}).get("windows") or []
            raw = str(self._state(c, "windowStates") or "")
            for i, v in enumerate(x for x in raw.split(",") if x != ""):
                try:
                    bits = int(float(v))
                except ValueError:
                    continue
                if bits & 6 and i < len(wins):
                    w = wins[i] or {}
                    wloc = (_clean((self.rooms.get(w.get("room")) or {}).get("name")) if w.get("room") else "") \
                        or _clean(w.get("installPlace"))
                    # "Raum<TAB>Fenster": das Panel setzt den Raum fett davor.
                    # "offen" steht schon rechts ("n offen"), nur "gekippt" dazu.
                    detail.append((f"{wloc}\t" if wloc else "")
                                  + (_clean(w.get('name')) or 'Fenster')
                                  + ("" if bits & 4 else " gekippt"))
            detail.sort(key=lambda d: (d.endswith(" gekippt"), d))   # offene vor gekippten, dann nach Raum
        elif t == "Alarm":
            armed, lv = bool(self._state(c, "armed")), self._state(c, "level") or 0
            icon = "shield"
            lvl, txt = ("alarm", "Ausgelöst") if lv else (("info", "Scharf") if armed else ("ok", "Unscharf"))
        elif t == "CentralAlarm":
            mem = [self.controls.get(m.get("uuid")) for m in ((c.get("details") or {}).get("controls") or [])]
            mem = [m for m in mem if m]
            icon = "shield"
            if any(self._state(m, "level") for m in mem):
                lvl, txt = "alarm", "Ausgelöst"
            elif any(self._state(m, "armed") for m in mem):
                lvl, txt = "info", "Scharf"
            else:
                lvl, txt = "ok", "Unscharf"
        elif t == "SmokeAlarm":
            lv = self._state(c, "level") or 0
            icon = "alarm"
            lvl, txt = ("alarm", "Alarm") if lv else ("ok", "ok")
        elif t == "MailBox":
            mail, pk = bool(self._state(c, "mailReceived")), bool(self._state(c, "packetReceived"))
            icon = "info"
            txt = " · ".join(x for x, f in (("Post", mail), ("Paket", pk)) if f) or "leer"
            lvl = "hint" if (mail or pk) else "ok"
        elif t in ("TextState", "InfoOnlyText"):
            txt = str(self._state(c, "textAndIcon") or self._state(c, "text") or "")
            ic = self._json_state(c, "iconAndColor") if "iconAndColor" in (c.get("states") or {}) else None
            lvl = (self._color_level(ic.get("color")) if isinstance(ic, dict) else None) or "info"
        else:
            it = self._control_item(uuid, None, show_room=False) or {}
            tone = it.get("tone")
            lvl = {"crit": "alarm", "warn": "hint", "good": "ok"}.get(tone) or ("info" if it.get("on") else "ok")
            txt, icon = str(it.get("sublabel") or ""), it.get("icon") or "info"
        chip = {"id": uuid, "name": name, "level": lvl, "text": txt[:60], "icon": icon,
                "iconUrl": self._control_icon_url(c), "detail": detail[:6], "count": count}
        if t in ("TextState", "InfoOnlyText"):
            # Statusbaustein: Text und Symbol/Farbe der aktiven Zeile, wie vom Miniserver geliefert
            ic = self._json_state(c, "iconAndColor") if "iconAndColor" in (c.get("states") or {}) else None
            ic = ic if isinstance(ic, dict) else {}
            col = str(ic.get("color") or "")
            chip["stext"] = txt[:120]
            chip["sicon"] = self._icon_url(ic["icon"]) if isinstance(ic.get("icon"), str) and _icon_path_ok(ic["icon"]) else None
            chip["scolor"] = col if re.match(r"^#[0-9a-fA-F]{6}$", col) else None
        return chip

    # ---- Alarm-Vollbild ----
    # Loest eine Alarmanlage oder ein Rauchmelder aus, zeigt jedes Panel, das
    # diesen Baustein "sieht", ein Vollbild mit Stumm/Quittieren. Je Panel
    # abweichend einstellbar (Profil -> Alarme): alarmPop {uuid: true|false}.
    def cam_crops(self) -> dict:
        """Bildausschnitte je Kamera-ID (Intercom-UUID) fuer die Panels."""
        out = {}
        for k, e in self.intercom_cfg.items():
            cr = _clean_crop(e.get("crop")) if isinstance(e, dict) else None
            if cr:
                out[k] = cr
        return out

    def sec_alarm_wanted(self, prof: dict | None, uuid: str) -> bool:
        ov = ((prof or {}).get("alarmPop") or {}).get(uuid)
        if isinstance(ov, bool):
            return ov
        return self._room_ok(uuid, prof) and self._shown(uuid, prof)

    def sec_alarm_msg(self, uuid: str, on: bool) -> dict:
        c = self.controls.get(uuid) or {}
        t = c.get("type") or ""
        ua = c.get("uuidAction") or uuid
        if t == "SmokeAlarm":
            kind, sub = "smoke", self._text(c, "alarmCause") or "Melder ausgelöst"
            acts = [{"label": "Stumm", "cmd": "mute"}, {"label": "Quittieren", "cmd": "confirm"}]
        else:
            kind, sub = "alarm", "Alarmanlage ausgelöst"
            acts = [{"label": "Quittieren", "cmd": "quit"}, {"label": "Unscharf", "cmd": "off"}]
        room = (self.rooms.get(c.get("room")) or {}).get("name") or ""
        return {"t": "secalarm", "id": uuid, "on": on, "kind": kind,
                "name": _clean(c.get("name")) or t, "room": _clean(room), "sub": sub,
                "uuid": ua, "secured": bool(c.get("isSecured")), "acts": acts}

    def sec_alarms_active(self) -> list:
        return [u for su, u in self.sec_map.items() if self.states.get(su)]

    def status_data(self, ctls: list, trk: str | None) -> dict:
        chips = [x for x in (self.status_chip(u) for u in ctls) if x]
        worst = max((x["level"] for x in chips if x["level"] != "info"),
                    key=lambda v: self._ST_RANK[v], default="ok")
        hints = [x for x in chips if x["level"] == "hint"]
        alarms = [x for x in chips if x["level"] == "alarm"]
        head = ("Alarm" if worst == "alarm" else
                ((f"{len(hints)} Hinweis" if len(hints) == 1 else f"{len(hints)} Hinweise") if worst == "hint" else "Alles ok"))
        lead = (alarms or hints or [None])[0]
        if lead:
            foot = (f"{lead['detail'][0].replace(chr(9), ': ')} · {lead['text']}" if lead["detail"] else f"{lead['name']}: {lead['text']}")
        else:
            foot = "Nichts offen, Haus im Normalbetrieb"
        lines = []
        tc = self.controls.get(trk) if trk else None
        if tc:
            raw = self._text(tc, "entries")
            lines = [e.strip() for e in raw.split("|") if e.strip()][:6]
        return {"level": worst, "head": head, "foot": foot, "chips": chips, "log": lines}

    def camera_list(self) -> list:
        """Alle Kameras mit Video-URL fuer das Kamera-Widget: zuerst die
        Intercoms aus Loxone, dann die eigenen Kameras (Settings)."""
        out = []
        for u, c in self.controls.items():
            if c.get("type") == "Intercom":
                e = self.intercom_cfg.get(u)
                if (e.get("url") if isinstance(e, dict) else e):
                    out.append({"id": u, "name": _clean(c.get("name")) or "Intercom",
                                "src": f"/mjpeg?id={quote(u)}&fps={WIDGET_CAM_FPS}", "reconnectH": self._cam_reconnect_h(u)})
        for k, e in self.intercom_cfg.items():
            if k.startswith("cam_") and isinstance(e, dict) and e.get("url"):
                out.append({"id": k, "name": str(e.get("name") or "Kamera")[:40],
                            "src": f"/mjpeg?id={quote(k)}&fps={WIDGET_CAM_FPS}", "reconnectH": 0})
        return out

    def _widgets_data(self, items: list, prof: dict | None, show_room: bool = True) -> dict:
        """Live-Daten der Raster-Eintraege (Screensaver und Tabs): Kacheln,
        Tuerstationen, Energiefluss, Verlaeufe, Audio, Kameras."""
        tiles, cams, energy, charts, players = {}, {}, {}, {}, {}
        cameras = self.camera_list() if any(it.get("type") == "camera" for it in items) else []
        statuses = {}
        for it in items:
            if it.get("type") == "status":
                key = ",".join(it.get("ctls") or []) + "#" + (it.get("trk") or "")
                if key not in statuses:
                    try:
                        statuses[key] = self.status_data(it.get("ctls") or [], it.get("trk"))
                    except Exception:
                        log.exception("Status-Widget fehlgeschlagen")
        for it in items:
            if it.get("type") in FOLDER_TYPES:
                f = self._folder_item(it["type"], it.get("uuid"))
                if f:
                    # eigenes Aussehen je Raum-/Kategorie-Kachel (Designer im Raster-Editor)
                    tiles[it["uuid"]] = self._apply_tile_style(f, it["uuid"], prof)
                continue
            u = it.get("uuid")
            if u not in self.controls:
                continue
            try:
                if it["type"] == "tile":
                    # Raum zeigen, wenn Kacheln aus verschiedenen Raeumen
                    # gemischt sind (Screensaver, Favoriten, freie Tabs).
                    tiles[u] = self._control_item(u, prof, show_room=show_room)
                elif it["type"] == "intercom":
                    cams[u] = {"name": _clean(self.controls[u].get("name")),
                               "blocks": self.intercom_blocks(u) or []}
                elif it["type"] == "energy":
                    eb = self.energy_blocks(u)
                    if eb is not None:
                        energy[u] = eb
                elif it["type"] == "chart":
                    rng = it.get("range") or STAT_DEFAULT_RANGE
                    cb = self.chart_blocks(u, rng)   # aus dem Cache, Abruf laeuft im Hintergrund
                    if cb is not None:
                        charts[u + "|" + rng] = cb
                elif it["type"] == "player":
                    pb = self.player_blocks(u)
                    if pb is not None:
                        players[u] = pb
            except Exception:
                # Ein fehlerhaftes Widget darf den Rest des Screensavers nicht mitreissen.
                log.exception("Screensaver-Widget %s (%s) fehlgeschlagen", it["type"], u)
        return {"tiles": tiles, "intercoms": cams, "cameras": cameras, "statuses": statuses,
                "energy": energy, "charts": charts, "players": players}

    def _folder_item(self, kind: str, fid) -> dict | None:
        """Raum- bzw. Kategorie-Kachel (Ordner) wie in der Loxone-App: antippen
        oeffnet den Raum/die Kategorie."""
        if kind == "room" and fid in self.rooms:
            r = self.rooms[fid]
            return {"id": fid, "label": _clean(r.get("name")), "icon": "folder",
                    "iconUrl": self._icon_url(r.get("image")),
                    "on": False, "nav": {"view": "group", "kind": "room", "id": fid}}
        if kind == "cat" and fid in self.cats:
            c = self.cats[fid]
            return {"id": fid, "label": _clean(c.get("name")), "icon": "folder",
                    "iconUrl": self._icon_url(c.get("image")), "color": self._cat_color(fid),
                    "on": False, "nav": {"view": "group", "kind": "cat", "id": fid}}
        return None

    # ---- Tabs mit Kachel-Raster -------------------------------------------
    def _tab_seed(self, tab: str, prof: dict | None) -> list:
        """Vorbefuellung eines Tabs in Loxone-Reihenfolge (wie bisher der Tab):
        Favoriten = eigene Auswahl bzw. Loxone-Favoriten, Zentral = Zentral-
        bausteine, Raum/Kategorie = deren Bausteine. Freie Tabs: nichts."""
        to = ((prof or {}).get("tileOrder") or {})
        lay = (((prof or {}).get("layouts") or {}).get(tab) or {})
        pick = lay.get("pick") or None          # eigene Auswahl je Uebersichts-Tab
        tab = _tab_base(tab)
        if tab == "favoriten":
            fav = prof.get("favorites") if prof else None
            if fav is not None:
                return [u for u in fav if u in self.controls and self._shown(u, prof)]
            return [u for u, c in self.controls.items()
                    if c.get("isFavorite") and self._room_ok(u, prof) and self._shown(u, prof)]
        if tab == "zentral":
            uu = [u for u, c in self.controls.items()
                  if (c.get("type") or "").startswith("Central") and self._shown(u, prof)]
            return _apply_order(uu, to.get("tab:zentral"))
        if tab.startswith("cat:"):
            cu = tab[4:]
            uu = [u for u, c in self.controls.items()
                  if c.get("cat") == cu and self._room_ok(u, prof) and self._shown(u, prof)]
            return _apply_order(uu, to.get(f"cat:{cu}"))
        ar = prof.get("rooms") if prof else None
        if tab == "raeume":
            if pick:
                return [ru for ru in pick if ru in self.rooms]
            return _apply_order([ru for ru in self.rooms_with if ar is None or ru in ar], to.get("tab:raeume"))
        if tab == "kategorien":
            if pick:
                return [cu for cu in pick if cu in self.cats]
            ac = prof.get("cats") if prof else None
            if ac is not None:
                cats = [cu for cu in self.cats_with if cu in ac]
            elif ar is not None:
                present = {c.get("cat") for c in self.controls.values() if c.get("room") in ar}
                cats = [cu for cu in self.cats_with if cu in present]
            else:
                cats = list(self.cats_with)
            return _apply_order(cats, to.get("tab:kategorien"))
        if tab.startswith("room:"):
            ru = tab[5:]
            uu = [u for u, c in self.controls.items()
                  if c.get("room") == ru and self._cat_ok(u, prof) and self._shown(u, prof)]
            uu = _apply_order(uu, to.get(f"room:{ru}"))
            # Loxone-Standard: im Raum nach Kategorie gruppiert
            rank = {cu: i for i, cu in enumerate(self.cats_with)}
            return sorted(uu, key=lambda u: rank.get(self.controls[u].get("cat"), len(rank)))
        return []

    def _tab_layout(self, tab: str, prof: dict | None) -> list:
        """Wirksame Belegung eines Tabs: gespeicherte Eintraege (geloeschte
        Bausteine fallen weg) + alle Bausteine der Vorbefuellung, die weder
        platziert noch bewusst entfernt sind, als 1x1-Kacheln hinten angehaengt
        (so erscheinen auch spaeter in Loxone angelegte Bausteine)."""
        lay = ((prof or {}).get("layouts") or {}).get(tab) or {}
        g = _grid(lay.get("grid"), (prof or {}).get("grid", 3))
        removed = set(lay.get("removed") or [])
        items, taken, placed = [], set(), set()
        seed_type = {"raeume": "room", "kategorien": "cat"}.get(_tab_base(tab), "tile")
        seeds = self._tab_seed(tab, prof)
        seed_set = set(seeds)
        for it in lay.get("items") or []:
            u = it.get("uuid")
            if it["type"] in SAVER_UUID_TYPES and (u not in self.controls or
                                                   (it["type"] == "tile" and not self._shown(u, prof))):
                continue
            # Raum-/Kategorie-Kachel nur, solange Raum/Kategorie existiert und
            # (in der Uebersicht) ausgewaehlt ist
            if it["type"] in FOLDER_TYPES and (u not in (self.rooms if it["type"] == "room" else self.cats)
                                               or (it["type"] == seed_type and u not in seed_set)):
                continue
            items.append(dict(it))
            taken |= _tab_cells(it["x"], it["y"], it["w"], it["h"], g)
            if it["type"] == seed_type:
                placed.add(u)
        pos = (max(cy * g + cx for cx, cy in taken) + 1) if taken else 0
        for u in seeds:
            if u in placed or u in removed:
                continue
            while pos < g * TAB_MAX_ROWS and (pos % g, pos // g) in taken:
                pos += 1
            if pos >= g * TAB_MAX_ROWS:
                break
            x, y = pos % g, pos // g
            items.append({"type": seed_type, "uuid": u, "x": x, "y": y, "w": 1, "h": 1, "auto": True})
            taken.add((x, y))
            pos += 1
        return items

    def _tab_title(self, tab: str, prof: dict | None) -> str:
        lbl = (((prof or {}).get("layouts") or {}).get(tab) or {}).get("label")
        if lbl:
            return lbl
        base = _tab_base(tab)
        if base == "favoriten":
            return "Favoriten"
        if base == "zentral":
            return "Zentral"
        if base in ("raeume", "kategorien"):
            return "Räume" if base == "raeume" else "Kategorien"
        if tab.startswith("cat:"):
            return _clean(self.cats.get(tab[4:], {}).get("name")) or "Kategorie"
        if tab.startswith("room:"):
            return _clean(self.rooms.get(tab[5:], {}).get("name")) or "Raum"
        return "Tab"

    def _cam_reconnect_h(self, uuid: str) -> int:
        """Automatischer Neuaufbau des Kamera-Streams alle N Stunden (0 = aus),
        je Intercom in den Settings gewaehlt. Das Panel laedt den Stream dann
        komplett neu - der Server baut dabei auch die Verbindung zur Kamera neu auf."""
        ent = self.intercom_cfg.get(uuid)
        try:
            h = int(ent.get("reconnect") or 0) if isinstance(ent, dict) else 0
        except (TypeError, ValueError):
            return 0
        return h if h in CAM_RECONNECT_HOURS else 0

    def intercom_blocks(self, uuid: str):
        """Volle Intercom-Ansicht (Video + Tuer-/Ausgang-Buttons + Klingel-Banner)
        einer Intercom-UUID fuer die Kamera-Pane. Gleiche Bloecke wie die
        Detailansicht -> das Bild wird wie beim Baustein direkt geladen (robust,
        auch wo ein nacktes MJPEG-<img> nicht anzeigt). None, wenn kein Intercom."""
        c = self.controls.get(uuid or "")
        if not c or c.get("type") != "Intercom":
            return None
        try:
            v = self._view_control_inner(uuid)
        except Exception:
            log.exception("intercom_blocks fehlgeschlagen (%s)", uuid)
            return None
        return [b for b in (v.get("blocks") or []) if b.get("k") != "more"]

    def _screensaver_cam(self) -> dict | None:
        """Intercom-Livebild fuer den Screensaver ("Fenster zur Aussenwelt"):
        nur wenn kein iCal-Kalender genutzt wird (Settings -> Kalender & Wetter)
        UND dort eine Intercom mit gesetzter Video-URL dafuer ausgewaehlt ist.
        None = aus (das Panel zeigt dann wie bisher nur Uhr/Wetter/Kalender)."""
        if front_info.calendar_sources(self.calendar_cfg or {}):
            return None
        uuid = (self.calendar_cfg or {}).get("screensaverIntercom") or ""
        if not uuid:
            return None
        c = self.controls.get(uuid)
        if not c or c.get("type") != "Intercom":
            return None
        ent = self.intercom_cfg.get(uuid)
        has_url = bool(ent.get("url") if isinstance(ent, dict) else ent)
        if not has_url:
            return None
        return {"uuid": uuid, "name": _clean(c.get("name")), "reconnectH": self._cam_reconnect_h(uuid)}

    def energy_blocks(self, uuid: str, max_cons: int = 6):
        """Energiefluss-Daten (Radial, Loxone-Standard) einer EFM/EnergyManager2-
        Kachel fuers Panel. EFM: genau die in der Loxone-Config angelegten Knoten
        (actual0..5, Name UND Icon vom Miniserver) – das ist wie in der Loxone-App
        die vollstaendige Liste inkl. PV/Netz/Speicher, daher KEINE zusaetzlichen
        Summen-Knoten (sonst Dopplung). EnergyManager2 (oder EFM ohne eigene
        Knoten): Summen-Knoten aus Ppwr/Gpwr/Spwr. 0-W-Knoten werden mitgezeigt
        (grau/inaktiv); nur nicht existierende (kein State) entfallen. Leistung in
        WATT, Flussrichtung fuers Diagramm. None bei ungueltiger Kachel. Reine
        Anzeige, keine Steuerung. max_cons = Loxones Grenze (actual0..5, max. 6).

        Vorzeichen wie bei Loxone aus Sicht des Hauses (siehe _flow_text):
        Gpwr>0 = Netzbezug (rein), <0 = Einspeisung (raus); Spwr>0 = Speicher
        entlaedt (rein), <0 = laedt (raus); Ppwr = Erzeugung (rein). Dasselbe
        gilt fuer EFM-Knoten mit nodeType Storage. flow: "in" = zur Mitte
        (gruen), "out" = nach aussen (orange), None = 0/inaktiv (grau)."""
        c = self.controls.get(uuid or "")
        if not c or c.get("type") not in ("EFM", "EnergyManager2"):
            return None
        det = c.get("details") or {}
        fmt = det.get("actualFormat") or "%.2f kW"
        to_w = 1000.0 if "kw" in fmt.lower() else 1.0   # States meist in kW -> Watt

        def watt(key):
            v = self._state(c, key)
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            if _is_sentinel(v):   # Sentinel/Int-Ueberlauf aus Loxone -> Fehlwert (Panel zeigt "–")
                return None
            return v * to_w

        def classify(nt, v):
            """Richtung (flow: in/out/None) UND Farbe/Rolle (kind) je Knoten aus
            Loxone-nodeType + Vorzeichen:
              kind "prod" = Quelle, gruen  (PV/Production; Netz-Einspeisung; Speicher entladen)
              kind "grid" = Netzbezug, ROT (Netz liefert Strom ins Haus)
              kind "load" = Verbraucher, orange (Load/Group; Speicher laden)
              kind "idle" = 0 W, grau
            PV/Production ist immer Quelle (kann nie beziehen). Netz: Bezug (v>0)
            rein/rot, Einspeisung (v<0) raus/gruen. Speicher wie das Netz aus
            Sicht des Hauses: entladen (v>0) rein/gruen, laden (v<0) raus/orange."""
            ntl = (nt or "").lower()
            if not v:
                return (None, "idle")
            if ntl == "production":
                return ("in", "prod")
            if ntl == "grid":
                return ("in", "grid") if v > 0 else ("out", "prod")
            if ntl in ("storage", "battery"):
                return ("in", "prod") if v > 0 else ("out", "load")
            return ("out", "load") if v > 0 else ("in", "prod")

        pv = watt("Ppwr")                       # Erzeugung
        g = watt("Gpwr")                        # Netz: >0 Bezug (rein), <0 Einspeisung (raus)
        sp = watt("Spwr")                       # Speicher: >0 entlaedt (rein), <0 laedt (raus)
        try:
            soc = float(self._state(c, "Ssoc"))
        except (TypeError, ValueError):
            soc = None

        def agg_nodes():
            """Feste Summen-Knoten (PV/Netz/Speicher) aus Ppwr/Gpwr/Spwr – fuer
            EnergyManager2 und als Rueckfall, wenn ein EFM keine eigenen Knoten hat."""
            def mk(name, icon, val, nt, extra=None):
                fl, kd = classify(nt, val)
                n = {"name": name, "icon": icon, "w": (abs(val) if val else 0.0) if val is not None else None,
                     "flow": fl, "kind": kd}
                if extra:
                    n.update(extra)
                return n
            # Reihenfolge wie in der Loxone-App (im Uhrzeigersinn ab oben):
            # Netz, Speicher, PV
            ns = [mk("Netz", "grid", g, "grid")]
            if soc is not None or (sp not in (None, 0.0)):
                ns.append(mk("Speicher", "battery", sp, "storage",
                             {"soc": max(0.0, min(100.0, soc))} if soc is not None else None))
            ns.append(mk("PV", "pv", pv, "production"))
            return ns

        # EFM: die actual0..5-Knoten SIND – wie in der Loxone-App – die vollstaendige
        # Liste (inkl. PV/Netz/Speicher, falls dort angelegt). Daher KEINE
        # zusaetzlichen Summen-Knoten oben drauf (sonst Dopplung). Name, Icon UND
        # Rolle (nodeType) kommen vom Miniserver; 0-W-Knoten bleiben (grau).
        def bilanz():
            """Hausverbrauch aus der Energiebilanz (Sicht des Hauses: was
            hereinkommt, wird verbraucht) = Erzeugung + Netz + Speicher. Ohne
            Netzwert unbekannt (None), ebenso solange PV oder Speicher angelegt
            sind, aber noch keinen Wert haben. Fehlt der State ganz (beim EM2
            auch HasSpwr false), hat die Anlage keinen: Beitrag 0."""
            if g is None:
                return None
            summe = g
            for key, val, da in (("Ppwr", pv, True), ("Spwr", sp, det.get("HasSpwr", True))):
                if not da or key not in (c.get("states") or {}):
                    continue
                if val is None:
                    return None
                summe += val
            return max(0.0, summe)

        cons = []
        rang = {}          # id(Knoten) -> Platz im Kreis (Netz, Speicher, Erzeuger, Rest)
        prod_sum = cons_sum = 0.0
        hat_verbraucher = False
        if c.get("type") == "EFM":
            for i, (label, nd) in enumerate(self._named_items(det.get("nodes"))[:max_cons]):
                v = watt(f"actual{i}")
                if v is None and self._state(c, f"actual{i}") is None:
                    continue
                nt = nd.get("nodeType") if isinstance(nd, dict) else None
                flow, kind = classify(nt, v)
                ntl = (nt or "").lower()
                cons.append({"name": label or f"Knoten {i + 1}", "icon": "load",
                             "iconUrl": self._node_icon_url(nd),
                             "w": abs(v) if v is not None else None, "flow": flow, "kind": kind})
                if v is None:   # Fehlwert: Knoten bleibt, Wert "–"
                    rang[id(cons[-1])] = {"grid": 0, "storage": 1, "battery": 1, "production": 2}.get(ntl, 3)
                    continue
                rang[id(cons[-1])] = {"grid": 0, "storage": 1, "battery": 1,
                                      "production": 2}.get(ntl, 3)
                if ntl == "production":
                    prod_sum += abs(v)
                elif ntl in ("load", "group"):
                    hat_verbraucher = True
                    if v > 0:
                        cons_sum += abs(v)
        if cons:
            cons.sort(key=lambda n: (n["flow"] is None, -(n["w"] or 0)))   # aktiv zuerst, 0 W ans Ende
            # Anordnung wie die Loxone-App: das Panel setzt Knoten i im Uhrzeigersinn
            # ab oben -> Netz oben, dann Speicher, Erzeuger (rechts), danach Haus und
            # die uebrigen Verbraucher (links). Stabil: Rest bleibt wie oben sortiert.
            cons.sort(key=lambda n: rang.get(id(n), 3))
            nodes = cons
            prod_total = prod_sum or (abs(pv) if pv else 0.0)
            # gemessene Verbraucher-Knoten, sonst die Bilanz
            cons_total = cons_sum if hat_verbraucher else bilanz()
        else:
            nodes = agg_nodes()   # EM2 oder EFM ohne eigene Knoten
            prod_total = abs(pv) if pv else 0.0
            cons_total = bilanz()
        return {"control": uuid, "name": _clean(c.get("name")) or "Energiefluss",
                "nodes": nodes,
                "totals": {"prod": prod_total, "cons": cons_total, "grid": g or 0.0}}

    def _icon_ref(self, ic) -> dict:
        """Symbol-Referenz (Konfigurator) -> {icon}|{iconUrl}|{iconImg} fuers Panel."""
        s = ic.get("src") if isinstance(ic, dict) else None
        if s == "builtin" and ic.get("id"):
            return {"icon": ic["id"]}
        if s == "loxone" and ic.get("p"):
            u = self._icon_url(ic["p"])
            return {"iconUrl": u} if u else {}
        if s == "loxlib" and ic.get("name"):
            return {"iconUrl": "/loxlib?n=" + quote(str(ic["name"]))}
        if s == "google" and ic.get("name"):
            return {"iconUrl": "/gicon?name=" + quote(str(ic["name"]))}
        if s == "custom" and ic.get("file"):
            return {"iconImg": "/uicon?f=" + quote(str(ic["file"]))}
        return {}

    def _tab_meta(self, tab_keys, prof: dict | None = None) -> dict:
        """Label + Symbol je Tab. Eigene Symbole (tabIcons) gehen vor; sonst Raum-/
        Kategorie-Symbol aus Loxone, die Standard-Tabs kennt das Frontend selbst."""
        meta = {}
        own = ((prof or {}).get("tabIcons") or {})
        for t in tab_keys or []:
            meta.update(self._tab_meta_one(t, prof))
            if t in own:
                ref = self._icon_ref(own[t])
                if ref:
                    m = meta.setdefault(t, {"label": self._tab_title(t, prof) if _is_layout_tab(t) else ""})
                    m.pop("iconUrl", None)
                    m.update(ref)
        return meta

    def _tab_meta_one(self, t, prof: dict | None) -> dict:
        """Standard-Label/-Symbol eines Tabs (freier Tab, Kategorie, Raum)."""
        if not isinstance(t, str):
            return {}
        if _FREE_TAB.match(t) or _MULTI_TAB.match(t):
            return {t: {"label": self._tab_title(t, prof), "iconUrl": ""}}
        if t.startswith("cat:"):
            cat = self.cats.get(t[4:], {})
            return {t: {"label": _clean(cat.get("name")) or "Kategorie",
                        "iconUrl": self._icon_url(cat.get("image")) or ""}}
        if t.startswith("room:"):
            room = self.rooms.get(t[5:], {})
            return {t: {"label": _clean(room.get("name")) or "Raum",
                        "iconUrl": self._icon_url(room.get("image")) or ""}}
        return {}

    def panel_dpms(self, pid: str | None):
        """Display-Abschaltzeit (Sek.) fuer ein Panel aus dem Profil (0=nie,
        None=nicht gesetzt -> Agent nutzt seinen kiosk.conf-Default). Wird dem
        Panel-Agenten in der Announce-Antwort mitgegeben (er fuehrt xset aus)."""
        ui = {**self.theme.get("ui", {}),
              **((self.panels.get(pid or "") or {}).get("ui") or {})}
        v = ui.get("dpmsOff")
        return max(0, min(3600, int(v))) if isinstance(v, (int, float)) else None

    def panel_night(self, pid: str | None) -> dict:
        """Nachtmodus je Panel: `dim` = Abdunklung in Prozent (0 = aus), `wake` =
        Sekunden, die eine Beruehrung wieder voll aufhellt (0 = nicht aufhellen).
        Wie panel_dpms(): Theme-Vorgabe, vom Panel-Profil ueberschreibbar."""
        ui = {**self.theme.get("ui", {}),
              **((self.panels.get(pid or "") or {}).get("ui") or {})}

        def _num(key, lo, hi, default):
            v = ui.get(key)
            return max(lo, min(hi, int(v))) if isinstance(v, (int, float)) else default

        return {"dim": _num("nightDim", 0, 90, 0), "wake": _num("nightWake", 0, 300, 20)}

    def night_control_options(self) -> list:
        """Bausteine, die als Nacht-Ausloeser taugen: alles mit einem `active`-State
        (Switch, InfoOnlyDigital, PresenceDetector ...). Damit laesst sich auch ein
        Loxone-Betriebsmodus nutzen, sobald er in der Visu auf so einem Baustein
        liegt — der Modus selbst steht nicht in der Struktur (s. ARCHITEKTUR.md)."""
        out = []
        # Loxone-Betriebsmodi der Anlage (Struktur `operatingModes`): Nacht, solange
        # der gewaehlte Modus laeuft. Ausloeser-Kennung "opmode:<Id>".
        for mid, mname in sorted((self.op_modes or {}).items(), key=lambda kv: str(kv[1]).lower()):
            nm = _clean(mname)
            if nm:
                out.append({"uuid": f"opmode:{mid}", "name": f"Betriebsmodus: {nm}",
                            "type": "", "room": "", "mode": True})
        # Nur Betriebsmodi anbieten (Nutzerwunsch). Ein frueher gewaehlter Baustein bleibt
        # sichtbar und gueltig, damit eine bestehende Einstellung nicht still verschwindet.
        cur = str((self.night_cfg or {}).get("control") or "") if isinstance(getattr(self, "night_cfg", None), dict) else ""
        if cur and not cur.startswith("opmode:") and cur in self.controls:
            c = self.controls[cur]
            out.append({"uuid": cur, "name": _clean(c.get("name")) + " (bisheriger Baustein)", "type": c.get("type"),
                        "room": _clean((self.rooms.get(c.get("room")) or {}).get("name"))})
        return out

    def _opmode_active(self, mid: str) -> bool | None:
        """Laeuft der Loxone-Betriebsmodus `mid` gerade? Quelle: globaler State
        `operatingMode` (Wert = Id des aktiven Modus). None, wenn nicht bekannt."""
        u = (self.global_states or {}).get("operatingMode")
        v = self.states.get(u) if isinstance(u, str) else None
        if isinstance(v, bool) or not isinstance(v, (int, float, str)) or v == "":
            return None
        # Mehrere gleichzeitig aktive Modi kommen ggf. als Liste ("1,6") - dann Mitgliedschaft
        teile = [t for t in re.split(r"[\s,;|]+", str(v).strip()) if t]
        try:
            return any(int(float(t)) == int(mid) for t in teile)
        except (TypeError, ValueError):
            return str(mid) in teile

    def _sun_minutes(self) -> tuple[int, int] | None:
        """Sonnenauf-/-untergang als Minuten seit Mitternacht (Ortszeit).

        Rangfolge: zuerst der MINISERVER (globalStates `sunrise`/`sunset` liefern
        genau dieses Format), sonst der Wetterdienst aus den Front-Daten ("HH:MM").
        None, wenn keine Quelle brauchbare Werte hat."""
        gs = self.global_states or {}
        ms = []
        for key in ("sunrise", "sunset"):
            u = gs.get(key)
            v = self.states.get(u) if isinstance(u, str) else None
            ms.append(int(v) if isinstance(v, (int, float)) and 0 <= v < 1440 else None)
        if ms[0] is not None and ms[1] is not None:
            return ms[0], ms[1]
        w = (self._front or {}).get("weather") or {}
        out = []
        for key in ("sunrise", "sunset"):
            hm = w.get(key)
            if not (isinstance(hm, str) and ":" in hm):
                return None
            h, _, m = hm.partition(":")
            try:
                out.append(int(h) * 60 + int(m))
            except ValueError:
                return None
        return out[0], out[1]

    def _night_now(self) -> bool:
        """Ist gerade Nacht?

        Rangfolge: ein in den Einstellungen gewaehlter Betriebsmodus ("opmode:<Id>",
        Nacht = Modus laeuft) oder Baustein (sein `active`-State = Nacht), sonst die Sonnenzeiten nach _sun_minutes() (Miniserver vor
        Wetterdienst), zuletzt NIGHT_FROM..NIGHT_TO. Ein gewaehlter, aber nicht
        (mehr) vorhandener Baustein faellt still auf die Sonnenzeiten zurueck."""
        u = (self.night_cfg or {}).get("control")
        if u and str(u).startswith("opmode:"):
            r = self._opmode_active(str(u)[7:])
            if r is not None and str(u)[7:] in (self.op_modes or {}):
                return r
        elif u:
            c = self.controls.get(u)
            if c:
                return bool(self._state(c, "active"))
        now = datetime.now()
        sun = self._sun_minutes()
        if sun:
            cur = now.hour * 60 + now.minute
            return cur >= sun[1] or cur < sun[0]
        hm = now.strftime("%H:%M")
        return hm >= NIGHT_FROM or hm < NIGHT_TO

    def panel_reload(self, pid: str | None):
        """Auto-Neustart-Intervall (Stunden) fuer ein Panel aus dem Profil
        (0/None = aus). Gegen Einfrieren; der Agent startet Chromium periodisch
        neu. Wird in der Announce-Antwort mitgegeben."""
        ui = {**self.theme.get("ui", {}),
              **((self.panels.get(pid or "") or {}).get("ui") or {})}
        v = ui.get("reloadHours")
        return max(0, min(168, float(v))) if isinstance(v, (int, float)) else None

    def _has_agent(self, name: str) -> bool:
        """True, wenn zu einer Geraetekennung (?device=) ein Panel-Agent bekannt
        ist, der sich in den letzten 10 Minuten gemeldet hat. Dann schaltet der
        Agent das Display und startet Chromium neu; die Visu haelt sich mit
        eigener Abschaltung und eigenem Reload zurueck."""
        if not name:
            return False
        now = time.time()
        return any(a.get("name") == name and (now - a.get("ts", 0)) < 600
                   for a in self.agents.values())

    def device_list(self) -> dict:
        """Alle bekannten Anzeigegeraete, zusammengefuehrt ueber den Namen:
        Panel-Agenten (Announce), verbundene Browser (?device=) und die in
        panels.json konfigurierten Geraete (Betriebsmodus-Automatik). Browser
        ohne Kennung stehen getrennt unter `anonymous` (nach IP) und koennen
        aus den Einstellungen benannt werden (`/api/device/name`)."""
        now = time.time()
        devs: dict[str, dict] = {}

        def entry(name: str) -> dict:
            return devs.setdefault(name, {
                "name": name, "agent": None, "connections": 0, "online": False,
                "profile": "", "kiosk": "", "ip": "", "lastSeen": 0.0, "configured": False})

        for a in self.agents.values():
            if (now - a["ts"]) >= 600:
                continue
            e = entry(a["name"])
            e["agent"] = {"ip": a["ip"], "port": a["port"], "kiosk": a["kiosk"],
                          "panel": a["panel"], "online": (now - a["ts"]) < 60}
            e["ip"] = a["ip"]
            e["lastSeen"] = max(e["lastSeen"], a["ts"])
            e["online"] = e["online"] or e["agent"]["online"]
        anonymous = []
        for ws, info in list(self.conn_info.items()):
            prof = (self.conn_prof.get(ws) or {}).get("id", "")
            if not info.get("dev"):
                anonymous.append({"ip": info.get("ip", ""), "profile": prof,
                                  "kiosk": info.get("kiosk", ""), "since": info.get("ts", 0)})
                continue
            e = entry(info["dev"])
            e["connections"] += 1
            e["online"] = True
            e["profile"] = prof
            e["kiosk"] = info.get("kiosk") or e["kiosk"]
            e["ip"] = e["ip"] or info.get("ip", "")
            e["lastSeen"] = max(e["lastSeen"], info.get("ts", 0))
        for name in self.devices:
            entry(name)["configured"] = True
        for name, t in list(self._dev_gone.items()):
            if name in devs and not devs[name]["online"]:
                devs[name]["lastSeen"] = max(devs[name]["lastSeen"], t)
        for e in devs.values():
            e["detected"] = self.device_summary(e["name"])
            cfg = self.devices.get(e["name"]) if isinstance(self.devices.get(e["name"]), dict) else {}
            model = cfg.get("model") or ""
            fully = bool(cfg.get("fully")) or e["kiosk"] == "fully"
            e["model"] = model
            e["type"] = "agent" if e["agent"] else ("fully" if fully else "browser")
            # Aktionen je Geraetetyp: Android -> adb; Fully nur wenn angegeben
            os_ = (DEVICE_MODELS.get(model) or {}).get("os")
            e["caps"] = ([c for c, ok in (("kioskrestart", os_ == "android" and fully),
                                          ("fullyinstall", os_ == "android"),
                                          ("brightness", os_ == "android"),
                                          ("reboot", os_ == "android")) if ok])
            if e["agent"] and not e["profile"]:
                e["profile"] = e["agent"]["panel"]
        anonymous.sort(key=lambda a: a["ip"])
        return {"devices": sorted(devs.values(), key=lambda e: e["name"].lower()),
                "anonymous": anonymous, "profiles": sorted(self.panels)}

    async def display_drivers(self, on: bool, device: str = "", panel: str = "") -> list:
        """Display ueber die HTTP-Schnittstelle der Kiosk-App schalten (Fully
        Kiosk Remote Admin, WallPanel). Betroffen sind Geraete mit `display`-
        Treiber in panels.json: bei `device` genau dieses, bei `panel` die, die
        das Profil gerade zeigen, sonst alle. Liefert je Geraet ein Ergebnis."""
        showing = {}
        for ws, info in list(self.conn_info.items()):
            if info.get("dev"):
                showing[info["dev"]] = (self.conn_prof.get(ws) or {}).get("id", "")
        out = []
        for name, cfg in self.devices.items():
            disp = cfg.get("display") if isinstance(cfg, dict) else None
            if not disp:
                continue
            if device and name != device:
                continue
            if panel and not device and showing.get(name) != panel:
                continue
            out.append(await self._drive_display(name, disp, on))
        return out

    async def _drive_display(self, name: str, disp: dict, on: bool) -> dict:
        sess = self._drv_session
        if sess is None or sess.closed:
            sess = self._drv_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=6))
        drv = disp.get("driver")
        res = {"device": name, "driver": drv, "on": on}
        pw = str(disp.get("password") or "")

        def von_gegenstelle(text: str) -> str:
            # Gibt die Gegenstelle die Anfrage wieder (Echo, Fehlerseite), stuende
            # das Kennwort im Klartext darin. Nur hier ersetzen: In selbst
            # gebildeten Meldungen ("Cannot connect to host h:port") verriete die
            # Ersetzung ueber den frei waehlbaren Port, ob er das Kennwort enthaelt.
            return text.replace(pw, "***") if pw else text
        try:
            if drv == "fully":
                # Fully Kiosk Browser, Remote Admin: GET /?cmd=screenOn|screenOff&password=...
                url = (f"http://{disp['host']}:{disp['port']}/?cmd="
                       f"{'screenOn' if on else 'screenOff'}&type=json"
                       f"&password={quote(str(disp.get('password') or ''), safe='')}")
                async with sess.get(url) as r:
                    txt = (await r.text())[:300]
                    ok = r.status == 200
                    try:
                        j = json.loads(txt)
                        if isinstance(j, dict) and str(j.get("status", "")).lower() == "error":
                            ok, txt = False, str(j.get("statustext") or txt)
                    except ValueError:
                        pass
            else:
                # WallPanel: POST /api/command {"wake": true|false}. false gibt nur
                # den Bildschirmschoner von WallPanel frei (eigene Abschaltzeit dort).
                url = f"http://{disp['host']}:{disp['port']}/api/command"
                async with sess.post(url, json={"wake": bool(on)}) as r:
                    txt = (await r.text())[:300]
                    ok = r.status == 200
            if not ok:
                res["error"] = f"HTTP {r.status}: {von_gegenstelle(txt)}".strip()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as err:
            # ValueError: Host, den die Namensaufloesung nicht annimmt
            ok = False
            # Ohne die Adresse: InvalidURL und ClientResponseError nennen sie
            # ganz, bei Fully samt Kennwort.
            if isinstance(err, aiohttp.InvalidURL):
                res["error"] = f"ungültige Adresse {disp['host']}:{disp['port']}"
            elif isinstance(err, aiohttp.ClientResponseError):
                res["error"] = f"HTTP {err.status}: {von_gegenstelle(err.message)}"
            else:
                res["error"] = str(err) or err.__class__.__name__
        res["ok"] = ok
        if not ok:
            # Das Kennwort so, wie es verschickt wurde: aus einem Echo der
            # Anfrage oder einer Meldung mit der ganzen Adresse. Ersetzt den
            # ganzen Wert, das Ergebnis haengt also nicht vom Kennwort ab.
            res["error"] = re.sub(r"password=[^&\s]*", "password=***", res["error"])
            log.warning("Display-Treiber %s (%s): %s", name, drv, res["error"])
        return res

    def _device_ip(self, device: str) -> str:
        """Letzte bekannte IP eines Geraets: offene Visu-Verbindung, sonst
        Display-Treiber oder Agent."""
        for info in self.conn_info.values():
            if info.get("dev") == device and info.get("ip"):
                return info["ip"]
        cfg = self.devices.get(device)
        disp = cfg.get("display") if isinstance(cfg, dict) else None
        if isinstance(disp, dict) and disp.get("host"):
            return str(disp["host"])
        for a in self.agents.values():
            if a.get("name") == device and a.get("ip"):
                return a["ip"]
        return ""

    def fully_source(self) -> dict:
        """Woher kommt die Fully-APK? Reihenfolge: eigene hochgeladene Datei >
        eigene Adresse (Download-Seite oder direkter .apk-Link) > offizielle
        Seite fully-kiosk.com. Dazu die zuletzt geladene Version."""
        cfg = _load_cfg().get("fully") or {}
        url = cfg.get("url") if isinstance(cfg, dict) else ""
        up = FULLY_DIR / FULLY_UPLOAD
        cached = sorted(FULLY_DIR.glob("Fully-Kiosk-Browser-v*.apk")) if FULLY_DIR.is_dir() else []
        return {
            "default": FULLY_PAGE,
            "url": url or "",
            "upload": ({"size": up.stat().st_size, "date": int(up.stat().st_mtime * 1000)} if up.is_file() else None),
            "cached": (cached[-1].name.replace("Fully-Kiosk-Browser-v", "").replace(".apk", "") if cached else ""),
            "mode": "upload" if up.is_file() else ("url" if url else "default"),
        }

    async def _fully_apk(self) -> tuple[Path | None, str, str]:
        """Fully-Kiosk-APK bereitstellen -> (Datei, Version, Quelle) bzw.
        (None, Fehlertext, Quelle). Offizielle Seite: der Download-Link traegt die
        Version im Namen (".../Fully-Kiosk-Browser-v1.61.3.apk"), genommen wird
        die hoechste. Geladene Dateien bleiben liegen, bis eine neuere erscheint."""
        src = self.fully_source()
        FULLY_DIR.mkdir(parents=True, exist_ok=True)
        if src["mode"] == "upload":
            return FULLY_DIR / FULLY_UPLOAD, "eigene Datei", "Eigene hochgeladene Datei"
        page = src["url"] or FULLY_PAGE
        hint = (" - unter Geräte → Fully-Quelle eine andere Adresse eintragen oder die APK hochladen")
        sess = self._drv_session
        if sess is None or sess.closed:
            sess = self._drv_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6))
        hdr = {"User-Agent": "Mozilla/5.0 LoxPanel"}
        if re.search(r"\.apk(\?.*)?$", page, re.I):   # direkter Link
            url = page
            m = re.search(r"v?(\d+(?:\.\d+){1,3})", page.rsplit("/", 1)[-1])
            ver = m.group(1) if m else "unbekannt"
        else:
            try:
                async with sess.get(page, timeout=aiohttp.ClientTimeout(total=20), headers=hdr) as r:
                    html = await r.text()
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
                return None, f"Download-Seite nicht erreichbar ({err}){hint}", page
            links = {}
            for m in _FULLY_APK_RE.finditer(html):
                links[tuple(int(x) for x in m.group(2).split("."))] = (m.group(1), m.group(2))
            if not links:
                return None, "Kein Fully-Download-Link auf der Seite gefunden (Seite geändert?)" + hint, page
            url, ver = links[max(links)]
        f = FULLY_DIR / f"Fully-Kiosk-Browser-v{ver}.apk"
        if ver != "unbekannt" and f.is_file() and f.stat().st_size > 1_000_000:
            return f, ver, url
        try:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=180), headers=hdr) as r:
                if r.status != 200:
                    return None, f"Download fehlgeschlagen (HTTP {r.status}){hint}", url
                data = await r.content.read(FULLY_MAX_BYTES + 1)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
            return None, f"Download fehlgeschlagen ({err}){hint}", url
        if len(data) > FULLY_MAX_BYTES or not data.startswith(b"PK"):
            return None, "Download ist keine gültige APK" + hint, url
        for old in FULLY_DIR.glob("Fully-Kiosk-Browser-v*.apk"):   # aeltere Versionen aufraeumen
            old.unlink(missing_ok=True)
        f.write_bytes(data)
        log.info("Fully Kiosk %s heruntergeladen von %s (%d KB)", ver, url, len(data) // 1024)
        return f, ver, url

    async def fully_install(self, device: str, ip: str = "") -> dict:
        """Fully Kiosk Browser per adb auf ein Android-Panel installieren bzw.
        aktualisieren. Voraussetzung wie beim Launcher: adb ueber WLAN am Panel
        aktiv und diesem Server erlaubt."""
        ip = ip or self._device_ip(device)
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except (ValueError, AttributeError):
            return {"ok": False, "error": "IP des Geraets unbekannt - Visu am Panel einmal öffnen"}
        if not shutil.which("adb"):
            return {"ok": False, "error": "adb fehlt im Container"}
        apk, ver, src = await self._fully_apk()
        if apk is None:
            return {"ok": False, "error": ver, "source": src}
        target = f"{ip}:5555"
        async with _adb_lock:
            code, out = await _adb("connect", target, timeout=15)
            if "connected" not in out or "failed" in out:
                return {"ok": False, "error": "Panel per adb nicht erreichbar - ADB über WLAN am Panel aktiv?"}
            code, out = await _adb("-s", target, "get-state", timeout=10)
            if out != "device":
                return {"ok": False, "error": "adb nicht freigegeben - am Panel \"USB-Debugging zulassen\" bestätigen"}
            # -g: App-Rechte (Kamera, Mikrofon, Speicher ...) gleich erteilen; alte
            # Android-Versionen (< 6) kennen -g nicht -> ohne wiederholen.
            code, out = await _adb("-s", target, "install", "-r", "-g", str(apk), timeout=240)
            if "Success" not in out and ("-g" in out or "Unknown option" in out or "unknown option" in out):
                code, out = await _adb("-s", target, "install", "-r", str(apk), timeout=240)
        ok = "Success" in out
        log.info("Fully Kiosk %s auf %s (%s): %s", ver, device or ip, target, "ok" if ok else out[-200:])
        return {"ok": ok, "version": ver, "source": src,
                **({} if ok else {"error": "Installation fehlgeschlagen: " + out[-200:]})}

    async def device_touch_sound(self, device: str, ip: str = "", on=None) -> dict:
        """Android-Tipp-Toene ("Toene bei Beruehrung", sound_effects_enabled) per
        adb lesen bzw. setzen. Sie klicken bei jedem Antippen eines Bedienelements."""
        ip = ip or self._device_ip(device)
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except (ValueError, AttributeError):
            return {"ok": False, "error": "IP des Geraets unbekannt - Visu am Panel einmal öffnen"}
        if not shutil.which("adb"):
            return {"ok": False, "error": "adb fehlt im Container"}
        target = f"{ip}:5555"
        async with _adb_lock:
            code, out = await _adb("connect", target, timeout=15)
            if "connected" not in out or "failed" in out:
                return {"ok": False, "error": "Panel per adb nicht erreichbar - ADB über WLAN am Panel aktiv?"}
            code, out = await _adb("-s", target, "get-state", timeout=10)
            if out != "device":
                return {"ok": False, "error": "adb nicht freigegeben - am Panel \"USB-Debugging zulassen\" bestätigen"}
            if on is not None:
                code, out = await _adb("-s", target, "shell", "settings", "put", "system",
                                       "sound_effects_enabled", "1" if on else "0", timeout=10)
                if code != 0:
                    return {"ok": False, "error": "Tipp-Töne nicht gesetzt: " + out[-200:]}
                log.info("Tipp-Toene %s (%s): %s", device or ip, target, "an" if on else "aus")
            code, out = await _adb("-s", target, "shell", "settings", "get", "system", "sound_effects_enabled", timeout=10)
        v = out.strip().splitlines()[-1] if out.strip() else ""
        return {"ok": True, "on": v != "0"}   # nicht gesetzt ("null") = Android-Standard an

    async def device_brightness(self, device: str, ip: str = "", value=None, auto=None) -> dict:
        """Display-Helligkeit eines Android-Panels per adb lesen bzw. setzen.
        auto=True: das Geraet regelt selbst (screen_brightness_mode 1).
        value (1-255): fester Wert - schaltet die Automatik ab, sonst
        ueberschreibt Android den Wert gleich wieder. Ohne beides: nur lesen.
        Antwort: {value, auto}."""
        ip = ip or self._device_ip(device)
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except (ValueError, AttributeError):
            return {"ok": False, "error": "IP des Geraets unbekannt - Visu am Panel einmal öffnen"}
        if not shutil.which("adb"):
            return {"ok": False, "error": "adb fehlt im Container"}
        target = f"{ip}:5555"
        async with _adb_lock:
            code, out = await _adb("connect", target, timeout=15)
            if "connected" not in out or "failed" in out:
                return {"ok": False, "error": "Panel per adb nicht erreichbar - ADB über WLAN am Panel aktiv?"}
            code, out = await _adb("-s", target, "get-state", timeout=10)
            if out != "device":
                return {"ok": False, "error": "adb nicht freigegeben - am Panel \"USB-Debugging zulassen\" bestätigen"}
            if auto is True:
                code, out = await _adb("-s", target, "shell", "settings", "put", "system", "screen_brightness_mode", "1", timeout=10)
                if code != 0:
                    return {"ok": False, "error": "Automatik nicht gesetzt: " + out[-200:]}
                log.info("Helligkeit %s (%s) auf automatisch gestellt", device or ip, target)
            elif value is not None:
                v = max(1, min(255, int(value)))
                await _adb("-s", target, "shell", "settings", "put", "system", "screen_brightness_mode", "0", timeout=10)
                code, out = await _adb("-s", target, "shell", "settings", "put", "system", "screen_brightness", str(v), timeout=10)
                if code != 0:
                    return {"ok": False, "error": "Helligkeit nicht gesetzt: " + out[-200:]}
                log.info("Helligkeit %s (%s) auf %d gesetzt", device or ip, target, v)
            code, out = await _adb("-s", target, "shell", "settings", "get", "system", "screen_brightness", timeout=10)
            _c, mode = await _adb("-s", target, "shell", "settings", "get", "system", "screen_brightness_mode", timeout=10)
        try:
            cur = int(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"ok": value is not None or auto is True,
                    "error": None if (value is not None or auto is True) else "Helligkeit nicht lesbar"}
        return {"ok": True, "value": cur, "auto": mode.strip().endswith("1")}

    async def kiosk_restart(self, device: str, action: str = "app", ip: str = "") -> dict:
        """Android-Panel per adb neu starten (ohne Fully-PLUS-Lizenz):
        action "app"    - Fully beenden und ueber den LoxPanel-Launcher (mit der
                          gespeicherten Panel-URL) neu starten,
        action "reboot" - ganzes Geraet neu starten (wenn das Display haengt).
        Voraussetzung: adb ueber WLAN am Panel aktiv und diesem Server erlaubt
        (einmalig bei der Einrichtung des Launchers bestaetigt)."""
        ip = ip or self._device_ip(device)
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except (ValueError, AttributeError):
            return {"ok": False, "error": "IP des Geraets unbekannt - Visu am Panel einmal öffnen"}
        model = ((self.devices.get(device) or {}) if isinstance(self.devices.get(device), dict) else {}).get("model")
        if action == "reboot" and (DEVICE_MODELS.get(model) or {}).get("shelly"):
            # Shelly Wall Display: eigene lokale Schnittstelle (Shelly-RPC) -
            # klappt ohne adb; sonst weiter unten per adb.
            try:
                sess = self._drv_session
                if sess is None or sess.closed:
                    sess = self._drv_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6))
                async with sess.get(f"http://{ip}/rpc/Shelly.Reboot") as r:
                    if r.status == 200:
                        log.info("Shelly %s (%s) per Shelly-RPC neu gestartet", device, ip)
                        return {"ok": True, "via": "shelly"}
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                pass
        if not shutil.which("adb"):
            return {"ok": False, "error": "adb fehlt im Container"}
        target = f"{ip}:5555"
        async with _adb_lock:
            code, out = await _adb("connect", target, timeout=15)
            if "connected" not in out or "failed" in out:
                return {"ok": False, "error": "Panel per adb nicht erreichbar - ADB über WLAN am Panel aktiv?"}
            code, out = await _adb("-s", target, "get-state", timeout=10)
            if out != "device":
                return {"ok": False, "error": "adb nicht freigegeben - am Panel \"USB-Debugging zulassen\" bestätigen"}
            if action == "reboot":
                code, out = await _adb("-s", target, "reboot", timeout=15)
                log.info("Geraet %s (%s) per adb neu gestartet: %s", device, target, out or code)
                return {"ok": code == 0, "via": "adb", **({} if code == 0 else {"error": out})}
            await _adb("-s", target, "shell", "am", "force-stop", "de.ozerov.fully", timeout=15)
            # Ueber den Launcher starten (oeffnet Fully mit der Panel-URL); fehlt er,
            # Fully direkt starten - es laedt dann seine eigene Start-URL.
            code, out = await _adb("-s", target, "shell", "am", "start", "-n", f"{LAUNCHER_PKG}/.Main", timeout=15)
            if code != 0 or "rror" in out:
                code, out = await _adb("-s", target, "shell", "monkey", "-p", "de.ozerov.fully",
                                       "-c", "android.intent.category.LAUNCHER", "1", timeout=15)
        ok = code == 0 and "rror" not in out
        log.info("Fully auf %s (%s) neu gestartet: %s", device, target, "ok" if ok else out)
        return {"ok": ok, "via": "adb", **({} if ok else {"error": out[-300:]})}

    async def launcher_version(self, device: str, ip: str = "") -> dict:
        """Installierte LoxPanel-Launcher-Version per adb lesen (nur lesend) und
        mit der im Update mitgelieferten vergleichen -> {ok, installed, bundled}.
        installed 0 = nicht installiert."""
        ip = ip or self._device_ip(device)
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except (ValueError, AttributeError):
            return {"ok": False, "error": "IP des Geraets unbekannt - Visu am Panel einmal öffnen"}
        if not shutil.which("adb"):
            return {"ok": False, "error": "adb fehlt im Container"}
        target = f"{ip}:5555"
        async with _adb_lock:
            code, out = await _adb("connect", target, timeout=15)
            if "connected" not in out or "failed" in out:
                return {"ok": False, "error": "Panel per adb nicht erreichbar"}
            code, out = await _adb("-s", target, "get-state", timeout=10)
            if out != "device":
                return {"ok": False, "error": "adb nicht freigegeben"}
            code, out = await _adb("-s", target, "shell", "dumpsys", "package", LAUNCHER_PKG, timeout=15)
        return {"ok": True, "installed": _launcher_ver_of(out) if code == 0 else 0,
                "bundled": _launcher_bundled_ver()}

    async def device_adblog(self, device: str, ip: str = "") -> dict:
        """Android-Geraet (Shelly, Tablet) per adb auslesen - NUR lesend: Sensoren (inkl.
        10 s Mitschnitt Naeherungssensor), Systemprotokoll, ANR-Eintraege ("isn't
        responding"), Speicher, CPU, Laufzeit. -> {ok, text|error}"""
        ip = ip or self._device_ip(device)
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except (ValueError, AttributeError):
            return {"ok": False, "error": "IP des Geräts unbekannt – Visu am Panel einmal öffnen"}
        if not shutil.which("adb"):
            return {"ok": False, "error": "adb fehlt im Container"}
        target = f"{ip}:5555"
        parts = [f"LoxPanel Geräte-Log · {device} ({ip}) · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Version {APP_VERSION}"]
        # Naeherungssensor 10 s mitschneiden (gleich zu Beginn - die Config bittet
        # dann um Annaeherung): Roh-Eingaben per getevent im Hintergrund, parallel
        # jede Sekunde die Proximity-Zeilen aus dumpsys sensorservice.
        prox = ("echo '--- Eingabegeraete mit Abstand/Proximity (getevent -pl) ---'; "
                "getevent -pl 2>&1 | grep -iE 'add device|name:|ABS_DISTANCE|prox'; "
                "f=/data/local/tmp/loxpanel_getevent.txt; getevent -lt > $f 2>&1 & p=$!; "
                "i=0; while [ $i -lt 10 ]; do echo \"--- dumpsys sensorservice, Sekunde $i ---\"; "
                "dumpsys sensorservice | grep -iE -A6 'prox' | head -n 40; sleep 1; i=$((i+1)); done; "
                "kill $p 2>/dev/null; echo '--- getevent -lt (10 s, ohne SYN_REPORT) ---'; "
                "grep -v SYN_REPORT $f | head -n 400; rm -f $f")
        steps = [
            ("Sensoren: Näherungssensor 10 s Mitschnitt (Hand annähern und wegnehmen)", [prox]),
            ("Sensoren (Liste + letzte Werte, dumpsys sensorservice)", ["dumpsys", "sensorservice"]),
            ("Laufzeit", ["uptime"]),
            ("Android", ["getprop", "ro.build.display.id"]),
            ("Speicher", ["cat", "/proc/meminfo"]),
            ("Speicher je App", ["dumpsys", "meminfo", "-c"]),
            ("Speicher Kiosk-Browser (Fully)", ["dumpsys", "meminfo", "de.ozerov.fully"]),
            # Wer spielt Ton ab (Tipp-Toene, Klingel)? Abspiel-Verlauf je App + Einstellung
            ("Tipp-Töne (Android-Einstellung)", ["settings", "get", "system", "sound_effects_enabled"]),
            ("Audio (Abspiel-Verlauf je App)", ["dumpsys", "audio"]),
            # Herstellereigene Schalter finden (z.B. Shelly-Tippton am Android-Schalter vorbei)
            ("Einstellungen system", ["settings", "list", "system"]),
            ("Einstellungen global", ["settings", "list", "global"]),
            ("Einstellungen secure", ["settings", "list", "secure"]),
            ("Systemeigenschaften", ["getprop"]),
            ("CPU", ["dumpsys", "cpuinfo"]),
            ("Prozesse (top)", ["top", "-b", "-n", "1", "-m", "25"]),
            ("ANR / Abstürze (dropbox)", ["dumpsys", "dropbox", "--print", "system_server_anr",
                                         "system_app_anr", "data_app_anr", "system_app_crash", "data_app_crash"]),
            ("Systemprotokoll (logcat, letzte 3000 Zeilen)", ["logcat", "-d", "-t", "3000", "-v", "time"]),
        ]
        async with _adb_lock:
            code, out = await _adb("connect", target, timeout=15)
            if "connected" not in out or "failed" in out:
                return {"ok": False, "error": "Panel per adb nicht erreichbar – ADB über WLAN am Panel aktiv?"}
            code, out = await _adb("-s", target, "get-state", timeout=10)
            if out != "device":
                return {"ok": False, "error": "adb nicht freigegeben – am Panel „USB-Debugging zulassen“ bestätigen"}
            for title, cmd in steps:
                code, out = await _adb("-s", target, "shell", *cmd, timeout=40)
                parts.append(f"\n===== {title} =====\n{out[-400000:] if out else '(leer)'}")
        log.info("Geräte-Log von %s (%s) geholt", device, ip)
        return {"ok": True, "text": "\n".join(parts)}

    async def _agent_start(self, agent: dict, profile: str) -> bool:
        """Startet den Kiosk eines Panel-Agenten mit einem Profil (Fernbefehl)."""
        url = f"http://{agent['ip']}:{agent['port']}/start"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json={"panel": profile},
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                    return r.status == 200
        except Exception as err:
            log.warning("Agent %s Start(%s) fehlgeschlagen: %s",
                        agent.get("name"), profile, err)
            return False

    async def switch_mode(self, mode: str) -> list:
        """Betriebsmodus-Wechsel (von Loxone via /api/mode): jedes Panel mit
        aktiver Automatik und einer Zuordnung fuer diesen Modus auf sein Profil
        umschalten. Zwei Wege je Panel (adressiert ueber seinen Namen):
        1. geraeteunabhaengig: offene Browser-Verbindung mit `?device=<name>`
           bekommt per WS ein `{t:'switch'}` -> laedt sich mit neuem Profil neu
           (funktioniert auf jedem Browser/Kiosk, kein Agent noetig);
        2. Fallback: Linux-Panel-Agent per Fernstart (`?device=` nicht gesetzt).
        """
        mode = (mode or "").strip()
        results: list = []
        if not mode:
            return results
        self.last_mode = mode   # merken -> frisch verbundene Geraete ziehen darauf nach
        now = time.time()
        by_name = {a["name"]: a for a in self.agents.values() if (now - a["ts"]) < 600}
        for name, cfg in self.devices.items():
            if not cfg.get("auto", True):
                continue
            profile = (cfg.get("modes") or {}).get(mode)
            if not profile:
                continue
            ws_targets = [ws for ws, dev in self.conn_dev.items() if dev == name]
            if ws_targets:
                sent = 0
                for ws in ws_targets:
                    if (self.conn_prof.get(ws) or {}).get("id") == profile:
                        sent += 1            # zeigt bereits das richtige Profil
                        continue
                    if await self._send_or_drop(ws, {"t": "switch", "panel": profile}):
                        sent += 1
                results.append({"panel": name, "profile": profile,
                                "ok": sent > 0, "via": "ws"})
                continue
            agent = by_name.get(name)
            if agent:
                ok = await self._agent_start(agent, profile)
                results.append({"panel": name, "profile": profile,
                                "ok": ok, "via": "agent"})
            else:
                results.append({"panel": name, "profile": profile,
                                "ok": False, "error": "Panel nicht online"})
        return results

    def _room_ok(self, uuid: str, prof: dict | None) -> bool:
        ar = prof.get("rooms") if prof else None
        if ar is None:
            return True
        return self.controls.get(uuid, {}).get("room") in ar

    def _cat_ok(self, uuid: str, prof: dict | None) -> bool:
        ac = prof.get("cats") if prof else None
        if ac is None:
            return True
        return self.controls.get(uuid, {}).get("cat") in ac

    def _shown(self, uuid: str, prof: dict | None) -> bool:
        """False, wenn diese Kachel auf dem Panel einzeln ausgeblendet wurde
        (zusaetzlich zum Raum-/Kategorie-Filter). Gilt panelweit."""
        return not (prof and uuid in prof.get("hide", ()))

    # ---- Config-Seite (Panel-Editor) ----
    def _panel_export(self, raw: dict) -> dict:
        """Rohes Profil aus der Datei -> UI-Form (rooms/cats als UUID-Listen,
        in Anzeige-Reihenfolge; leere Liste = alle)."""
        r = self._resolve_ids(raw.get("rooms"), self.rooms)
        c = self._resolve_ids(raw.get("cats"), self.cats)
        tabs = [t for t in (raw.get("tabs") or VALID_TABS) if _is_tab(t)]
        ui = {k: v for k, v in (raw.get("ui") or {}).items()
              if k in ("iconSize", "nameSize", "subSize", "font", "fontNum", "nudgeX",
                       "dpmsOff", "reloadHours", "nightDim", "nightWake",
                       "cols", "rows", "fill", "baseColor", "design",
                       "textColor", "bold", "lang", "player", "panes", "split", "phone", "bigValues",
                       "saverFcSize",
                       "motion", "contrast", "sceneLight", "iconAnim", "grid", "ambBg", "ambClock")}
        # Split-Pane je Tab: nur gueltige Tab-Kennung -> "weather"|"calendar".
        if isinstance(ui.get("panes"), dict):
            ui["panes"] = {str(k): v for k, v in ui["panes"].items()
                           if isinstance(k, str) and _is_tab(k) and (v in ("weather", "calendar") or (isinstance(v, str) and (v.startswith("player:") or v.startswith("energy:") or v.startswith("camera:") or v.startswith("chart:")) and len(v) > 7))}
            if not ui["panes"]:
                ui.pop("panes", None)
        else:
            ui.pop("panes", None)
        return {
            "title": raw.get("title") or "",
            "tabs": tabs or list(VALID_TABS),
            "rooms": [u for u in self.rooms_with if r and u in r],
            "cats": [u for u in self.cats_with if c and u in c],
            "ui": ui,
            "states": {k: v for k, v in (raw.get("states") or {}).items()
                       if k in ("active", "good", "warn", "crit")},
            "tiles": raw.get("tiles") if isinstance(raw.get("tiles"), dict) else {},
            "hide": [u for u in (raw.get("hide") or [])
                     if isinstance(u, str) and u in self.controls],
            # Eigene Favoriten (Tab "Favoriten"): frei gewaehlte Bausteine,
            # unabhaengig von Raum/Kategorie. None = nicht konfiguriert (Fallback
            # auf die Loxone-eigenen isFavorite-Bausteine), [] = bewusst leer.
            "favorites": ([u for u in raw.get("favorites") if isinstance(u, str) and u in self.controls]
                          if isinstance(raw.get("favorites"), list) else None),
            "alarmPop": {k: v for k, v in (raw.get("alarmPop") or {}).items()
                         if isinstance(v, bool) and k in self.controls},
            "alarmTone": bool(raw.get("alarmTone")),
            "tileOrder": {str(k): [u for u in v if isinstance(u, str) and u in self.controls]
                          for k, v in (raw.get("tileOrder") or {}).items()
                          if isinstance(k, str) and isinstance(v, list)},
            "saver": _sanitize_saver(raw.get("saver"), _grid((raw.get("ui") or {}).get("grid"))),
            "tabIcons": {k: ic for k, ic in ((k, _clean_icon(v)) for k, v in (raw.get("tabIcons") or {}).items()
                                             if _is_tab(k)) if ic},
            "layouts": {k: lay for k, lay in ((k, _sanitize_layout(v, _grid((raw.get("ui") or {}).get("grid")))) for k, v in
                                              (raw.get("layouts") or {}).items()
                                              if _is_tab(k) and _is_layout_tab(k)) if lay},
        }

    def _loxone_icons(self) -> list:
        """Alle im Struktur-Baum referenzierten Loxone-Icon-Pfade (für den Picker)."""
        paths = set()
        def add(c):
            di = (c.get("details") or {}).get("image")
            for v in ([di] if isinstance(di, str) else
                      [di.get("on"), di.get("off")] if isinstance(di, dict) else []) + [c.get("defaultIcon")]:
                if isinstance(v, str):
                    paths.add(v)
        for c in self.controls.values():
            add(c)
            for sc in (c.get("subControls") or {}).values():
                if isinstance(sc, dict):
                    add(sc)
        for table in (self.cats, self.rooms):
            for v in table.values():
                im = v.get("image")
                if isinstance(im, str):
                    paths.add(im)
        return sorted(p for p in paths if p.endswith(".svg") or p.endswith(".png"))

    @staticmethod
    def _sanitize_panels(panels: dict) -> dict:
        out: dict = {}
        for pid, p in panels.items():
            if not isinstance(pid, str) or not pid or pid.startswith("_") or not isinstance(p, dict):
                continue
            e: dict = {}
            if p.get("title"):
                e["title"] = str(p["title"])[:40]
            tabs = [t for t in (p.get("tabs") or []) if _is_tab(t)][:4]
            e["tabs"] = tabs or list(VALID_TABS)
            e["rooms"] = [str(x) for x in (p.get("rooms") or []) if isinstance(x, str)]
            e["cats"] = [str(x) for x in (p.get("cats") or []) if isinstance(x, str)]
            # Raum-Panel: welche Kategorien des Raums als untere Tabs dienen
            # (max 4). Leer/fehlt = automatisch (erste 4 im Raum).
            rc = [str(x) for x in (p.get("roomCats") or []) if isinstance(x, str)][:4]
            if rc:
                e["roomCats"] = rc
            hide = [str(x) for x in (p.get("hide") or []) if isinstance(x, str)]
            if hide:
                e["hide"] = hide           # einzeln ausgeblendete Kacheln (panelweit)
            # Eigene Favoriten: Reihenfolge = Auswahlreihenfolge, Duplikate raus.
            # isinstance-Pruefung (nicht "if fav:") haelt eine bewusst geleerte
            # Liste von "noch nie konfiguriert" auseinander (siehe _panel_export).
            if isinstance(p.get("favorites"), list):
                seen: set = set()
                fav = []
                for x in p["favorites"]:
                    if isinstance(x, str) and x not in seen:
                        seen.add(x)
                        fav.append(x)
                e["favorites"] = fav[:300]
            if isinstance(p.get("alarmPop"), dict):
                ap = {k: v for k, v in p["alarmPop"].items()
                      if isinstance(k, str) and _UUID_RE.match(k) and isinstance(v, bool)}
                if ap:
                    e["alarmPop"] = dict(list(ap.items())[:100])
            if p.get("alarmTone") is True:
                e["alarmTone"] = True
            # Kachel-Anordnung je Scope: Dict scope->Liste UUIDs, dedupliziert,
            # pro Scope gedeckelt. Nicht-String-Keys/Werte fallen raus.
            if isinstance(p.get("tileOrder"), dict):
                to = {}
                for k, v in p["tileOrder"].items():
                    if not isinstance(k, str) or not isinstance(v, list):
                        continue
                    seen2: set = set()
                    lst = []
                    for x in v:
                        if isinstance(x, str) and x not in seen2:
                            seen2.add(x); lst.append(x)
                    if lst:
                        to[k] = lst[:300]
                if to:
                    e["tileOrder"] = to
            dg = _grid((p.get("ui") or {}).get("grid"))    # Standardraster des Profils
            sv = _sanitize_saver(p.get("saver"), dg)
            if sv:
                e["saver"] = sv            # eigene Screensaver-Belegung
            if isinstance(p.get("tabIcons"), dict):
                ti = {k: ic for k, ic in ((k, _clean_icon(v)) for k, v in p["tabIcons"].items() if _is_tab(k)) if ic}
                if ti:
                    e["tabIcons"] = ti     # eigenes Symbol je Tab
            if isinstance(p.get("layouts"), dict):
                lays = {}
                for k, v in p["layouts"].items():
                    if _is_tab(k) and _is_layout_tab(k):
                        lay = _sanitize_layout(v, dg)
                        if lay:
                            lays[k] = lay
                if lays:
                    e["layouts"] = lays    # Kachel-Raster je Tab
            ui = p.get("ui") or {}
            # Groessen genauso klemmen wie der globale Pfad (_sanitize_theme_ui)
            # und wie die Nachbarfelder unten - sonst nimmt der Panel-Override
            # jeden Wert an, waehrend die globale Einstellung auf 8..80 begrenzt
            # ist.
            cui = {k: max(8, min(32 if k == "saverFcSize" else 80, int(ui[k])))
                   for k in ("iconSize", "nameSize", "subSize", "saverFcSize")
                   if isinstance(ui.get(k), (int, float))}
            if ui.get("tileShadow"):
                cui["tileShadow"] = str(ui["tileShadow"])[:200]
            if ui.get("font"):
                cui["font"] = str(ui["font"])[:120]
            if ui.get("fontNum"):
                cui["fontNum"] = str(ui["fontNum"])[:120]
            if isinstance(ui.get("nudgeX"), (int, float)):
                cui["nudgeX"] = max(-40, min(40, ui["nudgeX"]))  # horiz. Versatz px
            if isinstance(ui.get("dpmsOff"), (int, float)):
                cui["dpmsOff"] = max(0, min(3600, int(ui["dpmsOff"])))  # Display aus nach Sek.
            if isinstance(ui.get("reloadHours"), (int, float)):
                cui["reloadHours"] = max(0, min(168, float(ui["reloadHours"])))  # Auto-Neustart Std.
            if isinstance(ui.get("nightDim"), (int, float)):
                cui["nightDim"] = max(0, min(90, int(ui["nightDim"])))    # Nachts abdunkeln in %
            if isinstance(ui.get("nightWake"), (int, float)):
                cui["nightWake"] = max(0, min(300, int(ui["nightWake"])))  # Aufhellen bei Beruehrung, Sek.
            if ui.get("cols") in (2, 3):
                cui["cols"] = int(ui["cols"])   # Spalten: 2 oder 3
            if ui.get("rows") in (2, 3):
                cui["rows"] = int(ui["rows"])   # Zeilen: 2 oder 3 (2x3 / 3x3)
            if ui.get("fill"):
                cui["fill"] = True              # Visu fuellt grosse Screens (quadratische Kacheln)
            if ui.get("split") is False:
                cui["split"] = False            # Split-Screen aus (4"-Panel: nur Visu)
            if ui.get("phone") is True:
                cui["phone"] = True             # Handy: Flaechen untereinander, Tabs unten
            if ui.get("bigValues") in (True, "on", "off"):
                cui["bigValues"] = "on" if ui["bigValues"] in (True, "on") else "off"   # Werte gross: Panel-Override
            if isinstance(ui.get("player"), str) and ui.get("player"):
                cui["player"] = ui["player"]    # Split-Layout: AudioZone-UUID fuer den festen Player
            if isinstance(ui.get("panes"), dict):
                pn = {str(k): v for k, v in ui["panes"].items()
                      if isinstance(k, str) and _is_tab(k) and (v in ("weather", "calendar") or (isinstance(v, str) and (v.startswith("player:") or v.startswith("energy:") or v.startswith("camera:") or v.startswith("chart:")) and len(v) > 7))}
                if pn:
                    cui["panes"] = pn           # Split-Pane je Tab: Wetter/Kalender/Vollbreit
            if _color_ok(ui.get("textColor")):
                cui["textColor"] = ui["textColor"].strip()   # globale Schriftfarbe (Name)
            if _color_ok(ui.get("baseColor")):
                # Grundfarbe des Panel-Themes. Nur uebernehmen, wenn sich daraus
                # ueberhaupt ein tragfaehiger Satz bauen laesst - sonst stuende
                # eine Farbe in der Konfiguration, die das Panel ignoriert.
                _base = ui["baseColor"].strip()
                if theme_colors.derive(_base):
                    cui["baseColor"] = _base
            _dz = theme_colors.clean_design(ui.get("design"))
            if _dz:
                cui["design"] = _dz             # Design: Vorlage + eigene Farben
            if ui.get("bold"):
                cui["bold"] = True                            # Kachel-Namen fett
            if ui.get("motion") in ("off", "mid", "full"):
                cui["motion"] = ui["motion"]    # Animationsstufe NUR fuer dieses Panel (Override)
            if ui.get("contrast") in ("on", "off"):
                cui["contrast"] = ui["contrast"]  # Mehr Kontrast NUR fuer dieses Panel (Override)
            if ui.get("sceneLight") in ("on", "off"):
                cui["sceneLight"] = ui["sceneLight"]  # Szenen-Licht NUR fuer dieses Panel (Override)
            if ui.get("iconAnim") in ("on", "off"):
                cui["iconAnim"] = ui["iconAnim"]      # Animierte Symbole NUR fuer dieses Panel (Override)
            if ui.get("ambBg") in AMBIENT_BG_MODES:
                cui["ambBg"] = ui["ambBg"]              # Dashboard-Hintergrund (Verlauf oder eigenes Bild)
            if ui.get("ambClock") in AMBIENT_MODES:
                cui["ambClock"] = ui["ambClock"]        # Farbverlauf der Uhrzeit
            if ui.get("grid") in (2, "2"):
                cui["grid"] = 2                         # Standardraster 2x2 (Tabs + Dashboard)
            lang = _clean_lang(ui.get("lang"))
            if lang:
                cui["lang"] = lang                            # Panel-Sprache (Datum/Uhr, i18n)
            if cui:
                e["ui"] = cui
            st = p.get("states") or {}
            cst = {k: str(st[k]) for k in ("active", "good", "warn", "crit")
                   if isinstance(st.get(k), str)}
            if cst:
                e["states"] = cst
            tiles = p.get("tiles")
            if isinstance(tiles, dict):
                ct = {}
                for cu, ov in tiles.items():
                    if not isinstance(cu, str) or not isinstance(ov, dict):
                        continue
                    e2 = {}
                    for k in ("iconColor", "textColor", "bg", "border"):
                        if _color_ok(ov.get(k)):
                            e2[k] = ov[k].strip()
                    if ov.get("font"):
                        e2["font"] = str(ov["font"])[:120]
                    for bk in ("bold", "italic"):
                        if ov.get(bk) is True:
                            e2[bk] = True
                    icc = _clean_icon(ov.get("icon"))
                    if icc:
                        e2["icon"] = icc
                    if ov.get("big") in ("on", "off"):
                        e2["big"] = ov["big"]       # Werte gross: immer / nie (fehlt = Panel-Standard)
                    if ov.get("chart") in STAT_RANGES:
                        e2["chart"] = ov["chart"]   # Mini-Verlauf in der Kachel, Wert = Zeitraum
                        if ov.get("chartStyle") in STAT_TILE_STYLES and ov["chartStyle"] != "trend":
                            e2["chartStyle"] = ov["chartStyle"]   # Tagesmuster / Tagesspanne
                    if e2:
                        ct[cu] = e2
                if ct:
                    e["tiles"] = ct
            out[pid] = e
        return out

    @staticmethod
    def _panels_verworfen(roh: dict, sauber: dict, namen: dict | None = None) -> list[str]:
        """Was _sanitize_panels nicht uebernommen hat, als lesbare Pfade
        ("<Panel>: ui.cols", "<Panel>: tabs: foo"), damit der Konfigurator es
        meldet statt es still zu verlieren. Gemeldet wird nur, was einen Inhalt
        hatte: leere Werte (None, False, "", [], {}) nicht, begrenzte oder
        gekuerzte Werte (Groesse 100 -> 80, Titel auf 40 Zeichen) auch nicht -
        die kommen ja an. Standardwerte, die bewusst nicht gespeichert werden,
        stehen in PANEL_STANDARD. namen: UUID -> Bausteinname fuer lesbare
        Pfade (Kachel-Einstellungen stehen unter der UUID)."""
        namen = namen or {}

        def leer(v) -> bool:
            return v is None or v is False or (isinstance(v, str) and not v.strip()) \
                or (isinstance(v, (list, dict)) and not any(not leer(x) for x in
                                                            (v.values() if isinstance(v, dict) else v)))

        def standard(pfad: tuple, v) -> bool:
            for muster, wert in PANEL_STANDARD.items():
                if len(muster) == len(pfad) and all(m in ("*", p) for m, p in zip(muster, pfad)) \
                        and v == wert:
                    return True
            return False

        def kurz(xs: list) -> str:
            return ", ".join(str(x) for x in xs[:3]) + (f" … (+{len(xs) - 3})" if len(xs) > 3 else "")

        out: list[str] = []

        def vergleich(r, s, pfad: tuple, name: str):
            if isinstance(r, dict):
                for k, v in r.items():
                    if leer(v) or standard(pfad + (str(k),), v):
                        continue
                    p = pfad + (str(k),)
                    if isinstance(s, dict) and k in s:
                        vergleich(v, s[k], p, name)
                    elif isinstance(v, (dict, list)):
                        # ganz weggefallen (z. B. ui nur mit Unbekanntem): die
                        # einzelnen Angaben darin nennen
                        vergleich(v, {} if isinstance(v, dict) else [], p, name)
                    else:
                        out.append(f"{name}: {'.'.join(namen.get(x, x) for x in p)}")
            elif isinstance(r, list) and isinstance(s, list):
                werte = [x for x in r if not leer(x)]
                if all(isinstance(x, (str, int, float)) for x in werte):
                    fehlt = [x for x in werte if x not in s]
                    if fehlt:
                        out.append(f"{name}: {'.'.join(namen.get(x, x) for x in pfad)}: "
                                   f"{kurz([namen.get(x, x) for x in fehlt])}")
                elif len(s) < len(werte):
                    out.append(f"{name}: {'.'.join(namen.get(x, x) for x in pfad)}: "
                               f"{len(werte) - len(s)} von {len(werte)}")
                else:
                    for i, (x, y) in enumerate(zip(werte, s)):
                        vergleich(x, y, pfad + (str(i + 1),), name)

        for pid, p in (roh or {}).items():
            if leer(p):
                continue
            if pid not in sauber:
                out.append(f"Panel „{pid}“")
            else:
                titel = str(p.get("title") or "").strip() if isinstance(p, dict) else ""
                vergleich(p, sauber[pid], (), titel or pid)
        return out

    def _persist_panels_file(self, panels: dict, devices: dict) -> None:
        """Schreibt config/panels.json (Profile + Geraete-Automatik) in einem Rutsch."""
        doc = {"_comment": "Von der LoxPanel-Konfigurationsseite (/config bzw. "
                           "/settings) verwaltet. Jedes Panel oeffnet die Visu mit "
                           "?panel=<id>. rooms/cats leer = alle sichtbar. "
                           "`devices` bildet Betriebsmodus -> Profil je Panel ab.",
               "panels": panels}
        if devices:
            doc["devices"] = devices
        # Eine Generation Sicherung: die aktuelle (funktionierende) panels.json
        # vor dem Ueberschreiben nach panels.json.bak kopieren (best effort; ein
        # fehlgeschlagenes Backup darf das Speichern nicht blockieren).
        try:
            if PANELS_FILE.is_file():
                _atomic_write(PANELS_FILE.with_name(PANELS_FILE.name + ".bak"),
                              PANELS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:   # ValueError = UnicodeDecodeError bei kaputtem UTF-8
            log.warning("panels.json.bak nicht geschrieben: %s", err)
        _atomic_write(PANELS_FILE,
                      json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    def _write_panels(self, panels: dict) -> None:
        self._persist_panels_file(panels, self.devices)
        self.panels = load_panels()

    def _save_devinfo(self) -> None:
        try:
            _atomic_write(DEVINFO_FILE, json.dumps(self.devinfo, indent=1, ensure_ascii=False) + "\n")
        except OSError as err:
            log.warning("devinfo.json nicht geschrieben: %s", err)

    def devinfo_name(self, uid: str) -> str:
        """Gespeicherter Name zu einer Geraete-ID (falls schon erkannt)."""
        e = self.devinfo.get(uid) if uid else None
        return (e or {}).get("name", "") if isinstance(e, dict) else ""

    def device_detect(self, uid: str, dev: str, info: dict, ip: str) -> tuple[str, bool]:
        """Steckbrief eines Geraets verarbeiten. Liefert (Name, neu angelegt).
        Ohne Namen bekommt das Geraet einen Vorschlag (eindeutig gemacht); ist
        der Geraetetyp noch nicht gesetzt, wird er aus dem Steckbrief erkannt
        und mit seinen Vorgaben (Fully, Zoom ueber den Typ) eingetragen."""
        now = time.time()
        e = self.devinfo.get(uid) if isinstance(self.devinfo.get(uid), dict) else {}
        name = dev or e.get("name") or ""
        created = False
        if not name:
            # Uebernahme: genau ein schon angelegtes Geraet (z. B. frueher mit
            # ?device= benannt) ohne Steckbrief, gerade offline und vom selben Typ
            # -> das ist dieses Geraet; Name und Einstellungen bleiben.
            named = {v.get("name") for v in self.devinfo.values() if isinstance(v, dict)}
            online = {i.get("dev") for i in self.conn_info.values() if i.get("dev")}
            guess = guess_device_model(info)
            cand = [n for n, c in self.devices.items() if isinstance(c, dict) and n not in named
                    and n not in online and guess != "other" and c.get("model") == guess]
            if len(cand) == 1:
                name = cand[0]
        if not name:
            base = device_auto_name(info)
            taken = set(self.devices) | {v.get("name") for v in self.devinfo.values() if isinstance(v, dict)}
            name, n = base, 2
            while name in taken:
                name, n = f"{base} {n}", n + 1
            created = True
        # "zuletzt gesehen" mind. taeglich speichern: sonst bliebe auf der Platte der
        # alte Stand und das Aufraeumen nach einem Neustart hielte aktive Geraete
        # fuer 90 Tage verschwunden und loeschte sie.
        changed = (e.get("name") != name or e.get("info") != info or e.get("ip") != ip
                   or now - (e.get("last") or 0) > 86400)
        self.devinfo[uid] = {"name": name, "info": info, "ip": ip,
                             "first": e.get("first") or now, "last": now}
        cfg = self.devices.get(name) if isinstance(self.devices.get(name), dict) else None
        if cfg is None or not cfg.get("model"):
            model = guess_device_model(info)
            ncfg = dict(cfg or {"auto": True, "modes": {}})
            ncfg["model"] = model
            if info.get("fully") and DEVICE_MODELS[model]["os"] == "android":
                ncfg["fully"] = True
            devs = dict(self.devices)
            devs[name] = ncfg
            try:
                self._write_devices(devs)
                log.info("Geraet erkannt: '%s' -> %s", name, model)
            except Exception as err:
                log.warning("Geraet '%s' nicht gespeichert: %s", name, err)
            created = created or cfg is None
        if changed or created:
            self._save_devinfo()
        return name, created

    async def device_rename(self, old: str, new: str) -> dict:
        """Geraet umbenennen: Einstellungen und Steckbriefe ziehen mit; verbundene
        Visu bekommt den neuen Namen (merkt ihn sich, verbindet neu)."""
        if not new or new == old:
            return {"ok": False, "error": "neuer Name fehlt"}
        if new in self.devices or any(isinstance(e, dict) and e.get("name") == new for e in self.devinfo.values()):
            return {"ok": False, "error": "Name schon vergeben"}
        devs = {(new if k == old else k): v for k, v in self.devices.items()}
        n_info = 0
        for e in self.devinfo.values():
            if isinstance(e, dict) and e.get("name") == old:
                e["name"] = new
                n_info += 1
        if old in self.devices:
            self._write_devices(devs)
        if n_info:
            self._save_devinfo()
        n = await _push(self, {"t": "setdevice", "name": new}, "", old)
        log.info("Geraet umbenannt: '%s' -> '%s' (%d verbunden)", old, new, n)
        return {"ok": old in devs or new in devs or n_info > 0 or n > 0, "online": n}

    async def device_delete(self, name: str) -> dict:
        """Geraet vergessen: Einstellungen und Steckbriefe. Ist es gerade
        verbunden, vergisst es seinen Namen und meldet sich neu an."""
        devs = {k: v for k, v in self.devices.items() if k != name}
        had = name in self.devices
        uids = [u for u, e in self.devinfo.items() if isinstance(e, dict) and e.get("name") == name]
        for u in uids:
            del self.devinfo[u]
        if had:
            self._write_devices(devs)
        if uids:
            self._save_devinfo()
        n = await _push(self, {"t": "forget"}, "", name)
        log.info("Geraet geloescht: '%s' (%d Steckbrief(e), %d verbunden)", name, len(uids), n)
        return {"ok": had or bool(uids) or n > 0, "online": n}

    def device_summary(self, name: str) -> dict | None:
        """Erkannte Eigenschaften eines Geraets fuer die Geraeteliste."""
        best = None
        for uid, e in self.devinfo.items():
            if isinstance(e, dict) and e.get("name") == name and (best is None or e.get("last", 0) > best[1].get("last", 0)):
                best = (uid, e)
        if not best:
            return None
        uid, e = best
        i = e.get("info") or {}
        osn, br = _ua_parts(i)
        f = i.get("fully") or {}
        hw = " ".join(x for x in (f.get("manuf"), f.get("model") or i.get("model")) if x)
        scr = ""
        if i.get("sw") and i.get("sh"):
            scr = f"{i['sw']}×{i['sh']}" + (f" @{i['dpr']:g}x" if i.get("dpr") and i["dpr"] != 1 else "")
        return {"uid": uid, "os": osn, "browser": br, "hw": hw, "screen": scr,
                "view": f"{i['vw']}×{i['vh']}" if i.get("vw") else "",
                "cores": i.get("cores"), "mem": i.get("mem"), "touch": bool(i.get("touch")),
                "mac": f.get("mac", ""), "pwa": bool(i.get("pwa")), "ip": e.get("ip", ""),
                "first": e.get("first"), "last": e.get("last"), "guess": guess_device_model(i)}

    def effective_scale(self, dev: str) -> str | float:
        """Wirksame Skalierung eines Geraets: eigene Einstellung, sonst die
        Vorgabe seines Geraetetyps (Tablet/iPad: auto), sonst aus."""
        d = self.devices.get(dev) if dev else None
        if not isinstance(d, dict):
            return "off"
        sc = _clean_scale(d.get("scale"))
        if sc is not None:
            return sc
        return (DEVICE_MODELS.get(d.get("model") or "") or {}).get("scale", "off")

    def _write_devices(self, devices: dict) -> None:
        # Erst schreiben, dann uebernehmen: scheitert das Schreiben, laeuft der
        # Server mit dem Stand der Datei weiter
        self._persist_panels_file(self.panels, devices)
        self.devices = devices

    @staticmethod
    def _devices_export(devices: dict) -> dict:
        """Geraete fuer den Konfigurator (/api/meta, Antwort von POST
        /api/devices): das Display-Kennwort nur als hasPass, wie Miniserver
        und Kamera in /api/settings. Leer zurueck heisst es "unveraendert"
        (api_save_devices)."""
        out = {}
        for name, e in devices.items():
            if isinstance(e, dict) and isinstance(e.get("display"), dict):
                disp = {k: v for k, v in e["display"].items() if str(k).lower() not in ("pass", "password")}
                e = {**e, "display": {**disp, "hasPass": bool(e["display"].get("password"))}}
            out[name] = e
        return out

    @staticmethod
    def _sanitize_devices(devices: dict, panel_ids: set) -> dict:
        """Geraete-Automatik validieren: Schluessel = Agent-Name; je Panel `auto`
        (bool) + `modes` = {Modusname -> Profil-Id}. Nur existierende Profile
        werden uebernommen; leere Geraete fallen weg."""
        out: dict = {}
        if not isinstance(devices, dict):
            return out
        for name, cfg in devices.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(cfg, dict):
                continue
            modes = {}
            for mode, prof in (cfg.get("modes") or {}).items():
                if not isinstance(mode, str) or not isinstance(prof, str):
                    continue
                mode = mode.strip()[:40]
                prof = prof.strip()
                if mode and prof and prof in panel_ids:
                    modes[mode] = prof
            display = App._sanitize_display(cfg.get("display"))
            model = cfg.get("model") if cfg.get("model") in DEVICE_MODELS else ""
            scale = _clean_scale(cfg.get("scale"))
            if not modes and not display and not model and scale is None:
                continue
            entry = {"auto": bool(cfg.get("auto", True)), "modes": modes}
            if display:
                entry["display"] = display
            if model:
                entry["model"] = model                 # Geraetetyp (s. DEVICE_MODELS)
                if DEVICE_MODELS[model]["os"] == "android" and cfg.get("fully"):
                    entry["fully"] = True              # Fully Kiosk laeuft darauf
                    if "nrestart" in cfg:              # Fully nachts neu starten (Vorgabe: Shelly an)
                        entry["nrestart"] = bool(cfg.get("nrestart"))
            if scale is not None:
                entry["scale"] = scale                 # Skalierung (sonst Vorgabe des Geraetetyps)
            out[name.strip()[:60]] = entry
        return out

    @staticmethod
    def _sanitize_display(d) -> dict | None:
        """Display-Treiber eines Geraets: {driver: fully|wallpanel, host, port,
        password}. Ohne gueltigen Treiber oder Host -> None."""
        if not isinstance(d, dict):
            return None
        drv = str(d.get("driver") or "").strip().lower()
        if drv not in DISPLAY_DRIVERS:
            return None
        host = str(d.get("host") or "").strip()[:100]
        if not host:
            return None
        try:
            port = int(d.get("port") or DISPLAY_DRIVERS[drv])
        except (TypeError, ValueError):
            port = DISPLAY_DRIVERS[drv]
        return {"driver": drv, "host": host, "port": max(1, min(65535, port)),
                "password": str(d.get("password") or "")[:100]}

    @staticmethod
    def _sanitize_theme_ui(ui: dict) -> dict:
        """Globale Darstellungs-ui (theme.json) validieren: nur bekannte Keys."""
        ui = ui or {}
        out: dict = {}
        for k in ("iconSize", "nameSize", "subSize", "saverFcSize"):
            if isinstance(ui.get(k), (int, float)):
                out[k] = max(8, min(32 if k == "saverFcSize" else 80, int(ui[k])))   # Wettervorschau: max. 32
        if ui.get("tileShadow"):
            out["tileShadow"] = str(ui["tileShadow"])[:200]
        if ui.get("font"):
            out["font"] = str(ui["font"])[:120]
        if ui.get("fontNum"):
            out["fontNum"] = str(ui["fontNum"])[:120]
        if _color_ok(ui.get("textColor")):
            out["textColor"] = ui["textColor"].strip()
        if _color_ok(ui.get("baseColor")) and theme_colors.derive(ui["baseColor"].strip()):
            out["baseColor"] = ui["baseColor"].strip()
        _dz = theme_colors.clean_design(ui.get("design"))
        if _dz:
            out["design"] = _dz
        if ui.get("bold"):
            out["bold"] = True
        lang = _clean_lang(ui.get("lang"))
        if lang:
            out["lang"] = lang
        # Wecker global aus (Ton + Aufwecken/Sprung zur Wecker-Ansicht). Default
        # an; nur bei explizitem False gespeichert (kompaktes JSON, wie bold).
        if ui.get("alarmsEnabled") is False:
            out["alarmsEnabled"] = False
        # Animationen global an/aus (ein Schalter fuer alle --anim-*-Dauern im
        # Panel). Default an; nur bei explizitem "off" gespeichert.
        if ui.get("motion") in ("off", "mid"):
            out["motion"] = ui["motion"]
        # Mehr Kontrast (Schatten an Kacheln/Knoepfen). Default aus.
        if ui.get("contrast") == "on":
            out["contrast"] = "on"
        if ui.get("sceneLight") == "on":
            out["sceneLight"] = "on"
        if ui.get("bigValues") in (True, "on"):
            out["bigValues"] = "on"       # Werte gross auf Wert-Kacheln, Standard aus
        # Animierte Symbole: Default an; nur explizites "off" speichern.
        if ui.get("iconAnim") == "off":
            out["iconAnim"] = "off"
        # Licht per Doppeltipp aus. Default an; nur explizites False speichern.
        if ui.get("dblTapOff") is False:
            out["dblTapOff"] = False
        return out

    @staticmethod
    def _sanitize_categories(cats) -> dict:
        """categories aus dem Config-Editor validieren. Wert = Farbe (nur Icon)
        oder {on,off} (Zustands-Ampel). Ungueltiges/leeres wird verworfen."""
        out: dict = {}
        if not isinstance(cats, dict):
            return out
        for k, v in cats.items():
            k = str(k).strip()
            if not k or k.startswith("_"):
                continue
            if isinstance(v, dict):
                e = {}
                if _color_ok(v.get("on")):
                    e["on"] = str(v["on"]).strip()
                if _color_ok(v.get("off")):
                    e["off"] = str(v["off"]).strip()
                if e:
                    out[k[:40]] = e
            elif _color_ok(v):
                out[k[:40]] = str(v).strip()
        return out

    def _write_theme(self, ui: dict, categories=None) -> None:
        """Globale Darstellung in theme.json schreiben (Darstellungs-Keys ersetzen,
        uebrige Theme-Inhalte wie states/tabs bleiben erhalten). categories wird,
        wenn uebergeben, komplett ersetzt (der _comment-Schluessel bleibt)."""
        base = Path(__file__).resolve().parent.parent / "config"
        f = base / "theme.json"
        src = f if f.is_file() else (base / "theme.example.json")   # Vorlage als Basis
        try:
            doc = json.loads(src.read_text(encoding="utf-8")) if src.is_file() else {}
        except ValueError:
            doc = {}
        cur = doc.get("ui") if isinstance(doc.get("ui"), dict) else {}
        for k in THEME_UI_KEYS:
            if k in ui:
                cur[k] = ui[k]
            else:
                cur.pop(k, None)
        doc["ui"] = cur
        if categories is not None:
            keep = {k: v for k, v in (doc.get("categories") or {}).items()
                    if str(k).startswith("_")}   # _comment behalten
            doc["categories"] = {**keep, **categories}
        _atomic_write(f, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        self.theme = load_theme()
        self._dirty = True   # verbundene Panels neu rendern lassen

    async def fetch_icon(self, path: str) -> tuple[bytes, str] | None:
        if path in self.icon_cache:
            hit = self.icon_cache.pop(path)       # neu einsortieren = zuletzt benutzt
            self.icon_cache[path] = hit
            return hit
        try:
            status, body, ctype = await self._ms_http(path, 6)
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError):
            return None
        if status != 200:
            return None
        ctype = ctype or "application/octet-stream"
        self.icon_cache[path] = (body, ctype)
        while len(self.icon_cache) > ICON_CACHE_MAX:
            self.icon_cache.pop(next(iter(self.icon_cache)))   # am laengsten unbenutzt
        return self.icon_cache[path]

    async def _stat_load(self, ua: str, ym: str) -> None:
        """Eine Statistik-Monatsdatei holen (/stats/<uuidAction>.<JJJJMM>.xml,
        Bearer-Token wie bei den Icons) und in stat_cache legen. 404 heisst:
        fuer diesen Monat gibt es keine Aufzeichnung (leere Liste). Andere
        Fehler legen None ab, dann wird erst nach STAT_RETRY erneut versucht.
        Danach neu rendern lassen, damit offene Detailseiten das Diagramm zeigen."""
        key = (ua, ym)
        rows: list | None = None
        try:
            status, body, _ = await self._ms_http(f"stats/{ua}.{ym}.xml", 20)
            if status == 404:
                rows = []
            elif status == 200:
                # Monatsdatei kann MB gross sein: im Hilfsthread zerlegen, Live-Updates laufen weiter
                rows = await asyncio.get_running_loop().run_in_executor(
                    None, _parse_stat_xml, body.decode("utf-8", "replace"))
            else:
                log.info("Statistik %s.%s: HTTP %s", ua, ym, status)
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as err:
            log.info("Statistik %s.%s nicht abrufbar: %s", ua, ym, err)
        finally:
            self.stat_pending.discard(key)
        self.stat_cache.pop(key, None)          # neu einsortieren = zuletzt benutzt
        self.stat_cache[key] = (time.monotonic(), datetime.now().strftime("%Y%m"), rows)
        while len(self.stat_cache) > STAT_CACHE_MAX or (
                len(self.stat_cache) > 1 and _rows_total(self.stat_cache.values(), 2) > STAT_ROWS_MAX):
            self.stat_cache.pop(next(iter(self.stat_cache)))
        self.stat_gen += 1
        self.stat_memo = {}
        self._dirty = True

    async def _stat2_load(self, key: tuple, ua: str, gid: str, out: str, span: int) -> None:
        """Verlauf eines statisticV2-Ausgangs holen: jdev/sps/getStatistic/<uuid>/raw/
        <vonUnixUtc>/<bisUnixUtc>/all/<gruppe>/<ausgang> (so baut ihn die Loxone-App,
        StatisticV2Ext.getStatisticRaw). Eine Stunde Vorlauf liefert den Stand vor
        dem ersten Balken. Leere Antwort oder JSON statt Binaerdaten heisst: keine
        Aufzeichnung (leere Liste); andere Fehler legen None ab."""
        rows: list | None = None
        now = int(time.time())
        path = f"jdev/sps/getStatistic/{ua}/raw/{now - span - 3600}/{now}/all/{quote(gid)}/{quote(out)}"
        try:
            async with self.stat2_sem:
                status, body, _ = await self._ms_http(path, 30)
            if status != 200:
                log.info("Statistik V2 %s: HTTP %s", path, status)
            elif not body:
                rows = []
            elif body[:1] == b"{":
                rows = []
                log.info("Statistik V2 %s: keine Daten (%s)", path, body[:160].decode("utf-8", "replace"))
            else:
                rows = await asyncio.get_running_loop().run_in_executor(None, _parse_stat2_bin, body)
                if rows is None:
                    log.info("Statistik V2 %s: unerwartete Antwort, %d Bytes", path, len(body))
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as err:
            log.info("Statistik V2 %s nicht abrufbar: %s", path, err)
        finally:
            self.stat_pending.discard(key)
        self.stat2_cache.pop(key, None)
        self.stat2_cache[key] = (time.monotonic(), rows)
        while len(self.stat2_cache) > STAT_CACHE_MAX or (
                len(self.stat2_cache) > 1 and _rows_total(self.stat2_cache.values(), 1) > STAT_ROWS_MAX):
            self.stat2_cache.pop(next(iter(self.stat2_cache)))
        self.stat_gen += 1
        self.stat_memo = {}
        self._dirty = True

    async def fetch_cover(self, url: str) -> tuple[bytes, str] | None:
        if not self.icon_session:
            return None
        # Nur Bilder, hoechstens 5 MB: /cover ist ein offener Proxy fuer
        # beliebige URLs (Senderlogos, iTunes, Audioserver). Ohne diese Grenze
        # liesse sich darueber jede Seite im Netz abrufen bzw. fremdes HTML
        # unter der Panel-Adresse ausliefern.
        try:
            # keine Weiterleitungen folgen: sonst liesse sich die Host-Pruefung (_cover_host_ok) umgehen
            async with self.icon_session.get(url, timeout=aiohttp.ClientTimeout(total=COVER_TIMEOUT),
                                             allow_redirects=False) as r:
                ctype = r.headers.get("Content-Type", "image/jpeg")
                if r.status != 200 or not ctype.lower().startswith("image/"):
                    return None
                if (r.content_length or 0) > _COVER_MAX_BYTES:
                    return None
                body = await r.content.read(_COVER_MAX_BYTES + 1)
                return None if len(body) > _COVER_MAX_BYTES else (body, ctype)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    # ---- Kachel fuer ein Control ----
    def _spans_rooms(self, uuids) -> bool:
        """True, wenn die Bausteine ueber mehr als einen bekannten Raum verteilt
        sind. Dann lohnt es sich, den Raum je Kachel zu zeigen (Kategorie Licht
        ueber mehrere Raeume). Bausteine ohne Raum (z.B. Zentral) zaehlen nicht."""
        rooms = {self.controls[u].get("room") for u in uuids
                 if u in self.controls and self.controls[u].get("room") in self.rooms}
        return len(rooms) > 1

    def _alarm_next_text(self, c: dict) -> str:
        """Naechste Weckzeit eines Weckers (AlarmClock) als Text. Loxone liefert
        `nextEntryTime` in Sekunden seit dem 1.1.2009 (lokale Wanduhr); 0/leer =
        kein aktiver Eintrag. Ausgabe z.B. 'Heute 06:30', 'Morgen 06:30',
        'Mo 06:30' oder '24.12. 06:30'."""
        v = self._state(c, "nextEntryTime")
        try:
            ts = int(float(v))
        except (TypeError, ValueError):
            return ""
        if ts <= 0:
            return ""
        # Wert als Wanduhr behandeln (TZ-neutral): 2009-Basis + Sekunden.
        dt = datetime(2009, 1, 1) + timedelta(seconds=ts)
        today = datetime.now().date()
        d = (dt.date() - today).days
        hm = dt.strftime("%H:%M")
        if d == 0:
            return "Heute " + hm
        if d == 1:
            return "Morgen " + hm
        if 2 <= d <= 6:
            return ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][dt.weekday()] + " " + hm
        return dt.strftime("%d.%m.") + " " + hm

    def _alarm_entries(self, c: dict) -> list[dict]:
        """Weckzeit-Eintraege eines Weckers aus dem State `entryList`. Loxone
        liefert ein JSON-Objekt {entryID: {name, isActive, alarmTime (Sek seit
        Mitternacht), modes:[...], daily, nightLight}} — ggf. als (prozentkodierter)
        String. Gibt [{name, hm, active, repeat}] sortiert nach Uhrzeit zurueck;
        [] wenn nichts parsebar (dann wird der Rohwert einmal geloggt)."""
        raw = self._state(c, "entryList")
        if raw in (None, ""):
            return []
        data = raw
        if isinstance(raw, str):
            txt = unquote(raw).strip()
            try:
                data = json.loads(txt)
            except Exception:
                _log_once_warn(("alarm", txt[:60]), "Wecker entryList nicht als JSON parsebar: %r", txt[:200])
                return []
        seq = data.values() if isinstance(data, dict) else data
        if not isinstance(seq, (list, tuple)) and not hasattr(seq, "__iter__"):
            return []
        out = []
        ids = list(data.keys()) if isinstance(data, dict) else list(range(len(seq)))
        for eid, e in zip(ids, seq):
            if not isinstance(e, dict):
                continue
            try:
                secs = int(float(e.get("alarmTime") or 0))
            except (TypeError, ValueError):
                secs = 0
            hm = "%02d:%02d" % ((secs // 3600) % 24, (secs % 3600) // 60)
            repeat = self._alarm_repeat(e)
            out.append({"id": str(eid), "name": _clean(e.get("name")) or "Weckzeit", "hm": hm,
                        "secs": secs, "modes": [str(m) for m in (e.get("modes") or [])],
                        "daily": bool(e.get("daily")),
                        "active": bool(e.get("isActive")), "repeat": repeat})
        out.sort(key=lambda x: (not x["active"], x["hm"]))
        return out

    _WD_ABBR = {"montag": "Mo", "dienstag": "Di", "mittwoch": "Mi", "donnerstag": "Do",
                "freitag": "Fr", "samstag": "Sa", "sonntag": "So"}

    def _alarm_repeat(self, e: dict) -> str:
        """Wiederholungs-Text eines Weckzeit-Eintrags. `daily` -> „Täglich"; sonst
        die `modes` (Betriebsart-IDs) ueber die globalen operatingModes zu Namen
        aufloesen — Wochentage werden auf Mo/Di/… gekuerzt. Fallback, wenn keine
        Namen ermittelbar: Anzahl der Betriebsarten."""
        if e.get("daily"):
            return "Täglich"
        modes = e.get("modes")
        if not isinstance(modes, list) or not modes:
            return ""
        op = self.op_modes
        names = []
        for m in modes:
            nm = _clean(op.get(str(m)))
            if not nm:
                continue
            names.append(self._WD_ABBR.get(nm.lower(), nm))
        if not names:
            return f"{len(modes)} Betriebsart" + ("" if len(modes) == 1 else "en")
        # Alle 7 Wochentage -> „Täglich" (kompakter)
        if len(names) == 7 and all(v in names for v in self._WD_ABBR.values()):
            return "Täglich"
        # Sonder-Betriebsarten (Feiertag, Urlaub …) und Wochentage getrennt
        # lesbar: "Feiertag, Urlaub · Di, Do, So"
        wd = [n for n in names if n in self._WD_ABBR.values()]
        other = [n for n in names if n not in wd]
        return " · ".join(x for x in (", ".join(other), ", ".join(wd)) if x)

    def _daytimer_mode(self, c: dict) -> str:
        """Aktiver Modus/Tag eines Daytimers als Name. `mode` (Zahl) wird ueber
        `modeList` aufgeloest, Format: '0:mode=0;name=\"Feiertag\",1:mode=3;
        name=\"Montag\",...' (Anfuehrungszeichen escaped)."""
        raw = str(self._state(c, "modeList") or "").replace('\\"', '"')
        modes = {int(m): n for m, n in re.findall(r'mode=(\d+);name="([^"]*)"', raw)}
        try:
            return modes.get(int(float(self._state(c, "mode"))), "")
        except (TypeError, ValueError):
            return ""

    def _daytimer_value(self, c: dict) -> str:
        """Aktueller Wert eines Daytimers als Text: 0/leer -> „Aus"; analog ->
        formatiert (details.format); digital -> „Ein"."""
        val = self._state(c, "value")
        if not val:
            return "Aus"
        det = c.get("details") or {}
        if det.get("analog"):
            return self._fmt_num(val, det.get("format") or "%.1f")
        return "Ein"

    @staticmethod
    def _color_parse(raw) -> tuple:
        """Loxone color-State parsen. RGB: 'hsv(h,s,v)' (h 0-360, s/v 0-100) ->
        ('rgb', h, s, v). Tunable White: 'temp(brightness,kelvin)' ->
        ('temp', brightness, kelvin, None). Sonst ('none', 0, 0, 0)."""
        s = str(raw or "")
        m = re.match(r"hsv\((\d+),(\d+),(\d+)\)", s, re.I)
        if m:
            return ("rgb", int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"temp\((\d+),(\d+)\)", s, re.I)
        if m:
            return ("temp", int(m.group(1)), int(m.group(2)), None)
        return ("none", 0, 0, 0)

    @staticmethod
    def _hsv_hex(h, s, v) -> str:
        """HSV (h 0-360, s/v 0-100) -> #rrggbb fuer die Farb-Vorschau."""
        import colorsys
        r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s / 100.0, v / 100.0)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))

    @classmethod
    def _icon_hex(cls, h, s, v) -> str:
        """Live-Farbe fuers Kachel-Piktogramm: wie _hsv_hex, aber mit
        Mindesthelligkeit (45 %..100 %), sonst verschwindet ein tief gedimmtes
        RGB-Licht (z.B. Nachtszene) auf dunklem Grund. Gleiche Idee wie
        _dim_yellow fuer Dimmer: dunkler bleibt dunkler, aber sichtbar."""
        return cls._hsv_hex(h, s, 45 + 0.55 * max(0, min(100, v)))

    def types_overview(self) -> dict:
        """Diagnose fuer /api/types: alle Bausteintypen der geladenen Anlage mit
        Anzahl, Beispielnamen, Unterstuetzungsstatus (full / partial / none),
        den State-Namen und details-Schluesseln je Typ, dazu die Liste der
        Controls, die als tote Kachel enden. Der Status wird nicht aus einer
        Liste geraten, sondern aus dem Rendering: `_control_item()` liefert
        fuer unterstuetzte Typen nav, cmd, controls oder sublabel."""
        types: dict[str, dict] = {}
        for uuid, c in self.controls.items():
            t = str(c.get("type") or "?")
            e = types.setdefault(t, {"type": t, "count": 0, "examples": [], "states": set(),
                                     "details": set(), "supported": False, "controls": []})
            e["count"] += 1
            name = _clean(c.get("name"))
            if name and len(e["examples"]) < 3:
                e["examples"].append(name)
            e["states"].update(k for k in (c.get("states") or {}) if isinstance(k, str))
            e["details"].update(k for k in (c.get("details") or {}) if isinstance(k, str))
            room = _clean((self.rooms.get(c.get("room")) or {}).get("name"))
            e["controls"].append({"uuid": uuid, "name": name, "room": room})
            if not e["supported"]:
                try:
                    it = self._control_item_build(uuid)   # ungeschuetzt: Ersatzkachel zaehlt nicht als Unterstuetzung
                except Exception as err:  # Diagnose darf nie an einem Baustein scheitern
                    log.warning("types_overview: %s (%s): %s", name, t, err)
                    it = {}
                if any(k in it for k in ("nav", "cmd", "controls", "sublabel")):
                    e["supported"] = True
        out, dead = [], []
        for t in sorted(types, key=str.lower):
            e = types[t]
            status = "none" if not e["supported"] else ("partial" if t in PARTIAL_TYPES else "full")
            if status == "none":
                dead.extend({**ctl, "type": t} for ctl in e["controls"])
            out.append({"type": t, "status": status, "count": e["count"], "examples": e["examples"],
                        "states": sorted(e["states"]), "details": sorted(e["details"])})
        counts = {s: sum(1 for e in out if e["status"] == s) for s in ("full", "partial", "none")}
        # Diagnose Energiefluss: rohe Knotenstruktur + aktuelle Werte je EFM/EM2.
        # Damit laesst sich die Rolle/Richtung je Knoten belegen (statt raten).
        energy = []
        for uuid, c in self.controls.items():
            if c.get("type") in ("EFM", "EnergyManager2"):
                det = c.get("details") or {}
                energy.append({
                    "uuid": uuid, "name": _clean(c.get("name")), "type": c.get("type"),
                    "actualFormat": det.get("actualFormat"), "storageFormat": det.get("storageFormat"),
                    "Ppwr": self._state(c, "Ppwr"), "Gpwr": self._state(c, "Gpwr"),
                    "Spwr": self._state(c, "Spwr"), "Ssoc": self._state(c, "Ssoc"),
                    "nodes": det.get("nodes"),
                    "actuals": {f"actual{i}": self._state(c, f"actual{i}") for i in range(6)},
                })
        # Diagnose globale States (Sonnenzeiten, aktive Betriebsmodi ...): Name,
        # UUID und aktueller Wert. Sonst nirgends sichtbar; Grundlage dafuer, die
        # Nacht-Erkennung an den Miniserver zu haengen statt an einen Wetterdienst.
        gstates = []
        for _n, _ref in (self.global_states or {}).items():
            if isinstance(_ref, str):
                gstates.append({"name": _n, "uuid": _ref, "value": self.states.get(_ref)})
            else:
                gstates.append({"name": _n, "raw": _ref})
        return {"connected": self.client is not None, "controls": len(self.controls),
                "typeCount": len(out), "typesByStatus": counts, "types": out,
                "energyDetails": energy,
                "globalStates": sorted(gstates, key=lambda g: g["name"]),
                "operatingModes": self.op_modes,
                "weatherServer": self._weather_diag(),
                "unsupportedControls": sorted(dead, key=lambda d: (d["room"], d["name"]))}

    def _weather_diag(self) -> dict:
        """Diagnose zum Loxone-Wetterserver: was die Anlage meldet und was davon
        ankommt. Sonst nirgends sichtbar — und die einzige verlaessliche Auskunft
        darueber, unter welchen Namen und in welchen Einheiten diese Anlage ihre
        Wetterwerte fuehrt."""
        cfg = self.weather_cfg or {}
        states = cfg.get("states") if isinstance(cfg.get("states"), dict) else {}
        eintraege = {rolle: len(self._lox_wx.get(u) or [])
                     for rolle, u in states.items() if isinstance(u, str)}
        akt = (self._lox_wx.get(states.get("actual")) or [None])[0]
        if isinstance(akt, dict):
            # NaN/Inf wuerde ungueltiges JSON ergeben — die Tabelle kann beides fuehren.
            akt = {k: (v if isinstance(v, int) or (isinstance(v, float) and math.isfinite(v)) else None)
                   for k, v in akt.items()}
        return {
            "vorhanden": bool(cfg),
            "quelle": self._wx_source,
            "states": states,
            "eintraege": eintraege,
            "aktuellerEintrag": akt,      # Rohwerte: zeigt Einheiten und Groessenordnung
            "wetterlagen": loxone_weather.weather_texts(cfg),
            "format": cfg.get("format"),
            "feldtypen": cfg.get("weatherFieldTypes"),
        }

    def _control_item(self, uuid: str, prof: dict | None = None,
                      show_room: bool = False) -> dict:
        """Kachel eines Bausteins - fehlertolerant: wirft der Aufbau (z.B. ein
        unerwarteter State-Wert nach einem Firmware-Update), faellt nur DIESE
        Kachel auf eine schlichte Namenskachel zurueck statt der ganzen Seite.
        Protokolliert wird je Baustein nur einmal (der Tick laeuft oft)."""
        try:
            return self._control_item_build(uuid, prof, show_room)
        except Exception:
            if uuid not in self._item_errors:
                self._item_errors.add(uuid)
                log.exception("Kachel fuer %s fehlgeschlagen - zeige Ersatzkachel", uuid)
            c = self.controls.get(uuid) or {}
            return {"id": uuid, "label": _clean(c.get("name")) or "?", "icon": "info", "on": False,
                    "nav": {"view": "control", "id": uuid}}

    def _control_item_build(self, uuid: str, prof: dict | None = None,
                            show_room: bool = False) -> dict:
        c = self.controls.get(uuid)
        if not c:
            return {"id": uuid, "label": "?", "icon": "info", "on": False}
        t = c.get("type")
        name = _clean(c.get("name"))
        it: dict = {"id": uuid, "label": name, "on": False, "icon": "info"}
        # Raum-Kennzeichnung: nur wenn die Ansicht mehrere Raeume umfasst (z.B.
        # Kategorie Licht ueber alle Raeume). Zentralbausteine haben keinen Raum.
        if show_room:
            rn = _clean((self.rooms.get(c.get("room")) or {}).get("name"))
            if rn:
                it["room"] = rn
        if c.get("isSecured"):
            it["secured"] = True
        iu = self._control_icon_url(c)
        if iu:
            it["iconUrl"] = iu
        cc = self._cat_color(c.get("cat"))
        if cc:
            it["color"] = cc
        if t == "LightControllerV2":
            r = LIGHT.render(self._with_uuid(uuid), self.states)
            it.update(on=r["on"], sublabel=r["label"], icon="bulb",
                      nav={"view": "control", "id": uuid})
            if r["on"]:
                # Glühbirne gelb, solange an - egal welche Szene. Hat der
                # Baustein eine Colorpicker-Subcontrol (RGBW-Ausgang), wird
                # stattdessen deren tatsaechliche Live-Farbe genutzt (gleiche
                # Farb-Infrastruktur wie bei einem eigenstaendigen ColorPickerV2).
                it["colorFixed"] = "#f2c14e"
                for sc in (c.get("subControls") or {}).values():
                    if sc.get("type") in ("Colorpicker", "ColorPickerV2"):
                        mode, ca, cb, cv = self._color_parse(self._state(sc, "color"))
                        if mode == "rgb" and cv > 0:
                            it["colorFixed"] = self._icon_hex(ca, cb, cv)
                        break
            # Horizontale </>-Mini-Buttons oben rechts zum Szenen-Durchschalten
            # (wie die Auf/Ab-Buttons bei Jalousien, nur seitlich statt
            # senkrecht) - ueberspringt die "Aus"-Stimmung beim Weiterschalten,
            # dafuer bleibt ja der Ein/Aus-Tap auf die Kachel selbst.
            _off = LIGHT._off_ids(self._with_uuid(uuid), self.states)
            moods = [m for m in LIGHT.moods(self._with_uuid(uuid), self.states)
                     if m.get("id") not in _off]
            if moods:
                active = LIGHT.active_moods(self._with_uuid(uuid), self.states)
                cur = next((i for i, m in enumerate(moods) if m.get("id") in active), None)
                pv = moods[-1 if cur is None else (cur - 1) % len(moods)]["id"]
                nx = moods[0 if cur is None else (cur + 1) % len(moods)]["id"]
                ua = c.get("uuidAction")
                it["prevnext"] = {"prev": {"cmd": {"uuid": ua, "cmd": f"changeTo/{pv}"}},
                                  "next": {"cmd": {"uuid": ua, "cmd": f"changeTo/{nx}"}}}
            # Doppeltipp auf die Kachel schaltet aus (nur solange an; global
            # abschaltbar). 778 ist die von Loxone reservierte Aus-Stimmung -
            # derselbe Befehl wie der Aus-Knopf der Loxone-App, unabhaengig
            # davon, wie die Szenen in der Anlage heissen.
            if r["on"] and self.theme.get("ui", {}).get("dblTapOff", True) and c.get("uuidAction"):
                it["dblOff"] = {"cmd": {"uuid": c.get("uuidAction"), "cmd": f"changeTo/{LIGHT.OFF_MOOD}"}}
        elif t == "Jalousie":
            r = JAL.render(self._with_uuid(uuid), self.states)
            # Fahrt auf der Kachel sichtbar machen: dieselben States, die die
            # Detailansicht schon liest (_view_control_inner). Ohne das steht die
            # Kachel waehrend einer halben Minute Fahrt reglos da.
            s = c.get("states") or {}
            up_move = bool(self.states.get(s.get("up")))
            down_move = bool(self.states.get(s.get("down")))
            # „fährt …" vor der Stellung las sich widerspruechlich: „▲ fährt …
            # 62% zu" wirkt, als sei sie beim Auffahren trotzdem zu. Beides
            # stimmt zwar - sie faehrt auf UND steht gerade auf 62 % geschlossen
            # -, nur stand nichts dazwischen, das die zwei Angaben trennt. Ein
            # Verb benennt die Richtung eindeutig (wie beim Tor, :3219), der
            # Trenner macht die Stellung als zweite Angabe kenntlich.
            sub = r["label"]
            if up_move:
                sub = "▲ öffnet · " + sub
            elif down_move:
                sub = "▼ schließt · " + sub
            # Mini-Buttons oben rechts (wie in der Loxone-App): bewusst per
            # CLICK statt pointerdown gebunden (siehe .updown im Client) -
            # anders als .tctrls, das schon beim Aufsetzen des Fingers
            # ausloest und dabei eine Wisch-Geste kapern wuerde. Ein 'click'
            # feuert nur, wenn kein Scroll/Wisch dazwischenkam - kein
            # Risiko mehr, die Jalousie beim Blättern aus Versehen loszufahren.
            # Gleiche "Tipp waehrend Fahrt = Stop"-Logik wie in der Detailansicht.
            it_updown = {"up": {"cmd": {"uuid": c.get("uuidAction"), "cmd": "Stop" if up_move else "Up"}},
                         "down": {"cmd": {"uuid": c.get("uuidAction"), "cmd": "Stop" if down_move else "Down"}}}
            it.update(on=r["on"], sublabel=sub, icon="blind",
                      nav={"view": "control", "id": uuid}, updown=it_updown)
            if up_move or down_move:
                it["anim"] = "up" if up_move else "down"   # Symbol wippt in Fahrtrichtung
            _p = _pos_pct(r.get("pct"))
            if _p is not None:
                # Dynamisches Piktogramm statt Positionsring (wie in der
                # Loxone-App): das Fenster im Icon faehrt entsprechend der
                # Stellung zu. 0 = offen, 100 = ganz geschlossen. Der Ring
                # entfiele hier doppelt, deshalb kein "pos" fuer Jalousien.
                it["blind"] = _p
        elif t == "Gate":
            pct = round((self._state(c, "position") or 0) * 100)
            it.update(on=pct > 0, icon="gate", nav={"view": "control", "id": uuid},
                      blind=(100 - (_pos_pct(pct) or 0)),   # Piktogramm faehrt zu, 100 = geschlossen
                      blindShape="gate",
                      sublabel=("Offen" if pct >= 100 else
                                ("Geschlossen" if pct <= 0 else f"{pct}% offen")))
        elif t in ("IRoomControllerV2", "IRoomController"):
            ta = self._state(c, "tempActual"); tt = self._state(c, "tempTarget")
            # heizt/kuehlt: V2 meldet es in prepareState, die alte Raumregelung
            # ueber ihre Ventile (siehe _irc1)
            prep = self._state(c, "prepareState") if t == "IRoomControllerV2" else self._irc1(c)["prep"]
            bits = self._irc_activity(prep, self._state(c, "openWindow"))
            sub = (f"{self._fmt_num(ta, '%.1f')}° → {self._fmt_num(tt, '%.1f')}°"
                   if ta is not None else "Heizung")
            if bits:
                sub += " · " + " · ".join(bits)
            it.update(icon="thermo", nav={"view": "control", "id": uuid},
                      on=bool(prep), sublabel=sub)
            if "heizt" in bits:
                it["anim"] = "heat"                       # Symbol flackert dezent
        elif t == "Intercom":
            ring = bool(self._state(c, "bell"))
            it.update(icon="cam", on=ring,
                      sublabel=("Es klingelt" if ring else "Türsprechanlage"),
                      nav={"view": "control", "id": uuid})
            if ring:
                it["tone"] = "crit"
                it["anim"] = "ring"                       # Symbol wackelt wie eine Glocke
        elif t in SWITCHY:
            on = bool(self._state(c, "active"))
            it.update(on=on, sublabel="Ein" if on else "Aus", icon="switch",
                      # Wie in der Loxone-App: Tap auf die Kachel oeffnet die
                      # Detailansicht (dort explizite Ein/Aus-Buttons); der
                      # eigentliche Schnellschalter ist der kleine Schieber
                      # oben rechts in der Kachel (toggle/.tswitch), der die
                      # Navigation NICHT ausloest (siehe panel.html: n.onclick
                      # prueft .tswitch zuerst, der Schalter selbst stoppt per
                      # pointerdown/preventDefault).
                      nav={"view": "control", "id": uuid},
                      toggle={"on": on, "cmd": {"uuid": c.get("uuidAction"), "cmd": "off" if on else "on"}})
        elif t == "TimedSwitch":
            # Treppenhaus-/Zeitschalter: kein 'active'-State, sondern
            # 'deactivationDelay' (>0 = laeuft noch N Sek, -1 = dauerhaft an,
            # 0 = aus). 'pulse' startet den Timer, 'off' schaltet aus.
            dd = self._state(c, "deactivationDelay")
            try:
                dd = float(dd if dd is not None else 0)
            except (TypeError, ValueError):
                dd = 0.0
            on = dd != 0
            if dd > 0:
                sub = "noch %d:%02d" % (int(dd) // 60, int(dd) % 60)
            elif dd < 0:
                sub = "Ein"
            else:
                sub = "Aus"
            it.update(on=on, sublabel=sub, icon="bulb",
                      nav={"view": "control", "id": uuid},
                      toggle={"on": on, "cmd": {"uuid": c.get("uuidAction"), "cmd": "off" if on else "pulse"}})
        elif t == "Daytimer":
            # Wochenschaltuhr: aktueller Wert + ob ein manueller Timer (override) laeuft.
            ov = bool(self._state(c, "override"))
            it.update(icon="info", on=bool(self._state(c, "value")),
                      nav={"view": "control", "id": uuid},
                      sublabel=self._daytimer_value(c) + (" · Timer läuft" if ov else ""))
        elif t in ("Dimmer", "EIBDimmer"):
            pos = self._state(c, "position") or 0
            it.update(icon="bulb", on=pos > 0, nav={"view": "control", "id": uuid},
                      sublabel=(f"{round(pos)} %" if pos > 0 else "Aus"))
            if pos > 0:
                it["colorFixed"] = _dim_yellow(pos)   # Gelbton nach Helligkeit abgestuft
        elif t in ("ValueSelector", "UpDownAnalog"):
            det = c.get("details") or {}
            it.update(icon="switch", nav={"view": "control", "id": uuid},
                      sublabel=self._fmt_num(self._state(c, "value"), det.get("format") or "%.1f"))
        elif t == "TextInput":
            it.update(icon="info", nav={"view": "control", "id": uuid},
                      sublabel=str(self._state(c, "text") or ""))
        elif t == "Fronius":
            prod = self._state(c, "prodCurr")
            it.update(icon="central", nav={"view": "control", "id": uuid},
                      sublabel=(self._fmt_num(prod, "%.2fkW") if prod is not None else "PV-Anlage"))
        elif t == "Window":
            pct = round((self._state(c, "position") or 0) * 100)
            it.update(icon="window", on=pct > 0, nav={"view": "control", "id": uuid},
                      # Eigenes Fenster-Piktogramm (Rahmen+Kreuz) statt des
                      # Jalousie-Lamellenstils - Kreuz verschwindet proportional
                      # beim Oeffnen. 100 = ganz zu (volles Kreuz), 0 = offen.
                      winpos=(100 - (_pos_pct(pct) or 0)),
                      sublabel=("Offen" if pct >= 100 else
                                ("Geschlossen" if pct <= 0 else f"{pct}% offen")))
        elif t == "Ventilation":
            spd = self._state(c, "speed") or 0
            it.update(icon="fan", on=spd > 0, nav={"view": "control", "id": uuid},
                      sublabel=(f"{round(spd)} %" if spd > 0 else "Aus"))
        elif t == "Webpage":
            det = c.get("details") or {}
            host = re.sub(r"^https?://", "", det.get("url") or "").split("/")[0]
            it.update(icon="info", nav={"view": "control", "id": uuid},
                      sublabel=(host or "Webseite"))
            img = det.get("image")
            if img and not it.get("iconUrl"):
                it["iconUrl"] = "/icon?p=" + quote(img)
        elif t == "UpDownDigital":
            # Auf/Ab-Taster (keine States) -> Detailseite mit Auf/Ab/Stop.
            it.update(icon="blind", nav={"view": "control", "id": uuid}, sublabel="Auf / Ab")
        elif t in ("Colorpicker", "ColorPickerV2"):
            mode, a, b, v = self._color_parse(self._state(c, "color"))
            bright = a if mode == "temp" else v
            on = bright > 0
            it.update(icon="bulb", on=on, nav={"view": "control", "id": uuid},
                      sublabel=(f"{bright} %" if on else "Aus"))
            if mode == "rgb" and on:
                it["colorFixed"] = self._icon_hex(a, b, v)   # Icon in aktueller Farbe
        elif t == "AudioZone":
            playing = self._state(c, "playState") == 2
            ua = c.get("uuidAction")
            it.update(on=playing, sublabel=(self._song(c) or ("Spielt" if playing else "Aus")),
                      icon="music", nav={"view": "control", "id": uuid},
                      controls=[
                          {"icon": "prev", "cmd": {"uuid": ua, "cmd": "queueminus"}},
                          {"icon": "pause" if playing else "play",
                           "cmd": {"uuid": ua, "cmd": "pause" if playing else "play"}},
                          {"icon": "next", "cmd": {"uuid": ua, "cmd": "queueplus"}},
                      ])
            if playing:
                it["colorFixed"] = "#e0a24d"        # Icon eingefaerbt, solange Wiedergabe laeuft
        elif t == "AudioZoneV2":
            # Audioserver Gen 2: wird ueber den Miniserver gesteuert (play/pause/
            # prev/next/volume) — nicht ueber das Gen-1-Audio-Backend (kein playerid).
            playing = self._state(c, "playState") == 2
            song = self._song(c)
            sm = self._sonn_for(c)          # Sonn liefert Titel/Status, wo Loxone leer ist
            if sm:
                playing = playing or bool(sm.get("playing"))
                song = song or sm.get("title") or ""
            ua = c.get("uuidAction")
            it.update(on=playing, sublabel=(song or ("Spielt" if playing else "Aus")),
                      icon="music", nav={"view": "control", "id": uuid},
                      controls=[
                          {"icon": "prev", "cmd": {"uuid": ua, "cmd": "prev"}},
                          {"icon": "pause" if playing else "play",
                           "cmd": {"uuid": ua, "cmd": "pause" if playing else "play"}},
                          {"icon": "next", "cmd": {"uuid": ua, "cmd": "next"}},
                      ])
            if playing:
                it["colorFixed"] = "#e0a24d"
        elif t == "Pushbutton":
            # Wie Switch/TimedSwitch: Tap auf die Kachel navigiert (Detail mit
            # explizitem "Ausloesen"-Button), der eigentliche Taster ist ein
            # runder Mini-Button oben rechts (siehe .tap im Client) - KEIN
            # Schieber wie bei Switch, da ein Taster keinen dauerhaften
            # Ein/Aus-Zustand hat, nur einen kurzen Impuls.
            it.update(icon="switch", sublabel="Taster",
                      nav={"view": "control", "id": uuid},
                      tap={"cmd": {"uuid": c.get("uuidAction"), "cmd": "pulse"}})
        elif t == "InfoOnlyDigital":
            on = bool(self._state(c, "active"))
            txt = (c.get("details") or {}).get("text") or {}
            lbl_on, lbl_off = str(txt.get("on") or ""), str(txt.get("off") or "")
            it.update(on=on, sublabel=(lbl_on if on else lbl_off) or ("Ein" if on else "Aus"))
            # Fenster-Piktogramm wie in der Loxone-App: erkannt am zugewiesenen
            # Icon (window-*.svg), NICHT am Bausteintyp - InfoOnlyDigital wird
            # fuer alles Moegliche verwendet. Ob "an" offen oder zu bedeutet,
            # ist je Anlage frei konfiguriert, deshalb an den in Loxone Config
            # hinterlegten Texten erkannt (ganze Woerter, keine Teilstrings wie
            # "zu" in "Zuluft"). Eindeutig nur, wenn genau eine Seite passt -
            # sonst bleibt es beim normalen Icon statt falsch zu raten.
            if "window" in (it.get("iconUrl") or "").lower():
                words = set(re.findall(r"\w+", (lbl_on if on else lbl_off).lower()))
                shut = bool(words & _WIN_CLOSED)
                open_ = bool(words & _WIN_OPEN)
                if shut != open_ and not (words & {"nicht", "not", "kein", "no"}):
                    it["winpos"] = 100 if shut else 0
        elif t == "Meter":
            det = c.get("details") or {}
            a = self._fmt_num(self._state(c, "actual"), det.get("actualFormat", "%.1f"))
            tot = self._fmt_num(self._state(c, "total"), det.get("totalFormat", "%.1f"))
            it["sublabel"] = " • ".join(x for x in (a, tot) if x)
        elif t == "Slider":
            det = c.get("details") or {}
            it.update(sublabel=self._fmt_num(self._state(c, "value"), det.get("format", "%.1f")),
                      nav={"view": "control", "id": uuid})
        elif t == "InfoOnlyAnalog":
            det = c.get("details") or {}
            it["sublabel"] = self._fmt_num(self._state(c, "value"), det.get("format", "%.1f"))
        elif t in ("TextState", "InfoOnlyText"):
            it["sublabel"] = str(self._state(c, "textAndIcon") or self._state(c, "text") or "")
        elif t == "SmokeAlarm":
            ok = (self._state(c, "level") or 0) == 0
            it.update(icon="alarm", sublabel=("Alles ok" if ok else "Alarm!"),
                      tone=("good" if ok else "crit"))
        elif t == "Radio":
            det = c.get("details") or {}
            outs = det.get("outputs") or {}
            aoi = int(self._state(c, "activeOutput") or 0)
            # Kein Ausgang aktiv: der Text, den Loxone dafuer vergibt (allOff,
            # etwa "Automatik"), wie in der Detailseite; ohne ihn ein Strich (LoxPanel #80).
            ruhe = _clean(det.get("allOff")) or "–"
            it.update(icon="switch", nav={"view": "control", "id": uuid},
                      sublabel=(outs.get(str(aoi)) or (ruhe if aoi == 0 else f"Ausgang {aoi}")))
        elif t == "LightController":
            scenes = self._lc_scenes(c)
            asc = int(self._state(c, "activeScene") or 0)
            it.update(icon="bulb", on=asc != 0, nav={"view": "control", "id": uuid},
                      sublabel=(scenes.get(asc) or ("Aus" if asc == 0 else f"Szene {asc}")))
            if asc != 0:
                it["colorFixed"] = "#f2c14e"
        elif t == "PresenceDetector":
            on = bool(self._state(c, "active"))
            itxt = _presence_de(self._text(c, "infoText"))
            it.update(icon="info", on=on,
                      sublabel=(itxt if itxt and itxt.lower() not in ("an", "aus")
                                else ("Anwesend" if on else "Abwesend")))
            if on:
                it["colorFixed"] = "#52b881"        # gruen, solange Anwesenheit erkannt
        elif t == "WindowMonitor":
            wo, wt = self._win_counts(c)
            it.update(icon="window", on=(wo + wt) > 0, nav={"view": "control", "id": uuid},
                      # Gleiches Fenster-Piktogramm wie beim einzelnen Fenster -
                      # Sammelmelder ueber mehrere Fenster, daher nur binaer
                      # (irgendeines offen -> kein Kreuz), keine Prozentangabe.
                      winpos=(0 if (wo + wt) else 100),
                      sublabel=" · ".join(x for x in (f"{wo} offen" if wo else "",
                                                      f"{wt} gekippt" if wt else "") if x) or "Alle geschlossen")
        elif t == "Alarm":
            armed = bool(self._state(c, "armed"))
            lvl = self._state(c, "level") or 0
            it.update(icon="alarm", on=armed, tone=("crit" if lvl else None),
                      nav={"view": "control", "id": uuid},
                      sublabel=("Alarm!" if lvl else ("Scharf" if armed else "Unscharf")))
        elif t == "AlarmClock":
            ringing = bool(self._state(c, "isAlarmActive"))
            nxt = self._alarm_next_text(c)
            has = bool(self._alarm_entries(c))
            rn = _clean((self.rooms.get(c.get("room")) or {}).get("name"))
            if rn:
                it["room"] = rn   # Raum auf der Kachel zeigen (mehrere Wecker unterscheidbar)
            if ringing:
                it["anim"] = "ring"
            it.update(icon="alarm", on=ringing, tone=("crit" if ringing else None),
                      nav={"view": "control", "id": uuid},
                      sublabel=("Weckt!" if ringing else
                                (nxt or ("Keine Weckzeit aktiv" if has else "Kein Wecker"))))
        elif t == "AcControl":
            modes = self._json_list_map(c, "operatingModes")
            tt = self._fmt_num(self._state(c, "targetTemperature"), "%.1f")
            it.update(icon="thermo", on=(self._state(c, "status") or 0) != 0,
                      nav={"view": "control", "id": uuid},
                      sublabel=(" · ".join(x for x in (modes.get(int(self._state(c, "mode") or 0)),
                                                       (tt + " °C" if tt else "")) if x) or "Klima"))
        elif t == "ClimateControllerUS":
            dh = self._state(c, "demandHeat") or 0
            dc = self._state(c, "demandCool") or 0
            it.update(icon="thermo", on=bool(dh or dc),
                      nav={"view": "control", "id": uuid},
                      sublabel=("Heizt" if dh else ("Kühlt" if dc else "Bereit")))
        elif t == "SystemScheme":
            # Kachel oeffnet die volle Schema-Ansicht (Hintergrundbild + Live-Werte).
            # Als Sublabel den Hauptbaustein (details.mainControl) zeigen, sonst Hinweis.
            main = self._resolve_control((c.get("details") or {}).get("mainControl"))
            sub = (self._scheme_value(main).get("text") if main else "") or "Anlagenschema"
            it.update(icon="central", sublabel=sub, nav={"view": "control", "id": uuid})
        elif t == "Hourcounter":
            it["sublabel"] = ("Wartung fällig" if self._state(c, "overdue")
                              else self._fmt_num(self._state(c, "total"), "%.0f h"))
        elif t == "Tracker":
            lines = self._tracker_lines(c)
            _, last = self._split_ts(lines[0]) if lines else (None, "")
            it.update(icon="list", nav={"view": "control", "id": uuid},
                      sublabel=(last or "Keine Einträge"))
        elif t == "EFM":
            # Energieflussmonitor: Ppwr Erzeugung, Gpwr Netz (+Bezug/-Einspeisung),
            # Spwr Speicher (+Entladen/-Laden), actual0..5 = Knoten aus details.nodes
            fmt = (c.get("details") or {}).get("actualFormat") or "%.2f kW"
            bits = []
            p = self._fmt_num(self._state(c, "Ppwr"), fmt) if self._state(c, "Ppwr") is not None else ""
            if p:
                bits.append("PV " + p)
            g = self._flow_text(self._state(c, "Gpwr"), fmt, "Bezug", "Einspeisung")
            if g:
                bits.append(g)
            it.update(icon="central", nav={"view": "control", "id": uuid},
                      sublabel=" · ".join(bits) or "Energiefluss")
        elif t == "EnergyManager2":
            bits = []
            p = self._fmt_num(self._state(c, "Ppwr"), "%.2f kW") if self._state(c, "Ppwr") is not None else ""
            if p:
                bits.append("PV " + p)
            soc = self._state(c, "Ssoc")
            if soc is not None and (c.get("details") or {}).get("HasSsoc", True):
                bits.append("Speicher " + self._fmt_num(soc, "%.0f") + " %")
            it.update(icon="central", nav={"view": "control", "id": uuid},
                      sublabel=" · ".join(bits) or "Energiemanager")
        elif t == "PvProductionForecast":
            bits = [f"{lbl} {self._fmt_num(v, '%.1f kWh')}"
                    for lbl, v in (("Heute", self._state(c, "today")), ("Morgen", self._state(c, "tomorrow")))
                    if v is not None]
            it.update(icon="central", nav={"view": "control", "id": uuid},
                      sublabel=" · ".join(bits) or "PV-Prognose")
        elif t == "Irrigation":
            act = bool(self._state(c, "active"))
            rain = bool(self._state(c, "rainActive"))
            sub = "Bewässert" if act else ("Regenpause" if rain else "Bereit")
            zone = self._irrigation_zone_name(c)
            if act and zone:
                sub += " · " + zone
            it.update(icon="info", on=act, nav={"view": "control", "id": uuid}, sublabel=sub)
        elif t == "MailBox":
            mail = bool(self._state(c, "mailReceived"))
            pk = bool(self._state(c, "packetReceived"))
            sub = " · ".join(x for x, f in (("Post da", mail), ("Paket da", pk)) if f) or "Leer"
            it.update(icon="info", on=(mail or pk), nav={"view": "control", "id": uuid}, sublabel=sub)
        elif t == "Sauna":
            act = bool(self._state(c, "active"))
            ta = self._state(c, "tempActual")
            sub = "Ein" if act else "Aus"
            if ta is not None:
                sub += f" · {self._fmt_num(ta, '%.0f')} °C"
            if act:
                tt = self._state(c, "tempTarget")
                if tt is not None:
                    sub += f" → {self._fmt_num(tt, '%.0f')} °C"
                md = self._state(c, "mode")
                if isinstance(md, (int, float)) and int(md) in SAUNA_MODES:
                    sub += f" · {SAUNA_MODES[int(md)]}"
            if (c.get("details") or {}).get("hasVaporizer") and self._state(c, "lessWater"):
                it["tone"] = "warn"
            if self._state(c, "error") or self._state(c, "saunaError"):
                it["tone"] = "crit"
            it.update(icon="thermo", on=act, nav={"view": "control", "id": uuid}, sublabel=sub)
        elif t == "SteakThermo":
            act = bool(self._state(c, "isActive"))
            temps = self._steak_temps(c)
            sub = " · ".join(f"{self._fmt_num(v, '%.0f')} °C" for _, v in temps[:2]) if temps else ("Aktiv" if act else "Aus")
            if self._state(c, "greenAlarmActive") or self._state(c, "yellowAlarmActive") or self._state(c, "timerAlarmActive"):
                it["tone"] = "good"
            it.update(icon="thermo", on=act, nav={"view": "control", "id": uuid}, sublabel=sub)
        elif (t or "").startswith("Central"):
            muuids = [m.get("uuid") for m in ((c.get("details") or {}).get("controls") or [])
                      if m.get("uuid") in self.controls]
            n = 0
            n2 = len(muuids)
            if t == "CentralLightController":
                n = sum(1 for mu in muuids if LIGHT.render(self._with_uuid(mu), self.states)["on"])
                it["sublabel"] = self._central_sum(t, n, n2)
            elif t == "CentralAudioZone":
                n = sum(1 for mu in muuids if self._state(self.controls[mu], "playState") == 2)
                it["sublabel"] = self._central_sum(t, n, n2)
            elif t in ("CentralGate", "CentralWindow"):
                n = sum(1 for mu in muuids if (self._state(self.controls[mu], "position") or 0) > 0)
                it["sublabel"] = f"{n} offen" if n else "Alle geschlossen"
            elif t == "CentralJalousie":
                k = sum(1 for mu in muuids if (self._state(self.controls[mu], "position") or 0) < 0.02)
                it["sublabel"] = self._central_sum(t, k, n2) or "Zentral"
            elif t == "CentralAlarm":
                k = sum(1 for mu in muuids if self._state(self.controls[mu], "armed"))
                it["sublabel"] = self._central_sum(t, k, n2)
            it.setdefault("sublabel", "Zentral")
            it.update(icon="central", on=(n > 0),
                      nav={"view": "group", "kind": "central", "id": uuid})
            if n and t in ("CentralGate", "CentralWindow"):
                it.update(count=n, countTone="hint")
            elif n and t in ("CentralLightController", "CentralAudioZone"):
                it["count"] = n
        # Status-Bausteine antippbar machen -> grosse Wertseite
        if t in STATUS_BIG and "nav" not in it and "cmd" not in it:
            it["nav"] = {"view": "control", "id": uuid}
        # Kategorie-Ampel: Bausteine mit an/aus-Zustand einer Kategorie mit
        # Zustandsfarben leuchten aktiv (on-Farbe) bzw. ok (off-Farbe). Analoge
        # Anzeigen, Zentralbausteine und Bausteine mit eigenem tone (Rauch/…)
        # bleiben unberuehrt.
        cs = self._cat_states(c.get("cat"))
        if cs and t not in _ANALOG and not (t or "").startswith("Central") and not it.get("tone"):
            rgb = _hex_rgb(cs.get("on") if it.get("on") else cs.get("off"))
            if rgb:
                st = it.setdefault("style", {})
                # Deckkraft folgt den Overlay-Reglern (--ov-fill/--ov-bord, Panel-
                # bzw. Pro-Kachel-Einstellung, inkl. Modus nur-Rahmen/nur-Fuellung)
                # statt fest .16/.55 -> "Hintergrund/Rahmen transparenter" wirkt
                # damit auch auf die Kategorie-Ampel-Kacheln. Fallback = altes
                # Aussehen, wenn kein Overlay konfiguriert ist.
                st.setdefault("bg", "rgba(%s,var(--ov-fill,.16))" % rgb)
                st.setdefault("border", "rgba(%s,var(--ov-bord,.55))" % rgb)
        return self._apply_big(self._apply_tile_style(it, uuid, prof), c, uuid, prof)

    def _apply_big(self, it: dict, c: dict, uuid: str, prof: dict | None) -> dict:
        """"Werte gross": reine Wert-Kachel bekommt it["big"] = {"v": Zahl, "u": Einheit}.
        Format, Skalierung und Einheit kommen aus Loxone (_fmt_num); hier wird der
        fertige Text nur an der Zahl getrennt. Panel-Schalter ui.bigValues, je Kachel
        tiles.<uuid>.big = "on"/"off" gewinnt. Keine Wertkachel (Text, Bedienung,
        Mini-Verlauf, kein Messwert) -> unveraendert."""
        if c.get("type") not in BIG_TYPES or it.get("spark") or it.get("toggle") or it.get("controls"):
            return it
        ov = ((prof.get("tiles") or {}).get(uuid) if prof else None) or {}
        mode = ov.get("big") if isinstance(ov, dict) else None
        if not (mode == "on" or (mode != "off" and prof and prof.get("bigValues"))):
            return it
        if c.get("type") == "Meter":
            det = c.get("details") or {}
            txt = self._fmt_num(self._state(c, "actual"), det.get("actualFormat", "%.1f"))
        else:
            txt = it.get("sublabel") or ""
        m = _BIGNUM_RE.match(txt)
        if m:
            it["big"] = {"v": m.group(1), "u": m.group(2)[:12]}
        return it

    def _apply_tile_style(self, it: dict, uuid: str, prof: dict | None) -> dict:
        """Pro-Kachel-Overrides (Farben/Icon/Schrift) aus dem Panel-Profil."""
        ov = (prof.get("tiles") if prof else {}).get(uuid) if prof else None
        if not isinstance(ov, dict):
            return it
        if ov.get("iconColor"):
            it["color"] = ov["iconColor"]           # Icon-Farbe (--ico)
            it["colorFixed"] = ov["iconColor"]      # gewinnt auch im Aktiv-Zustand
        style = dict(it.get("style") or {})         # Kategorie-Ampel als Basis, manuell ueberschreibt
        for src, dst in (("bg", "bg"), ("border", "border"),
                         ("textColor", "txt"), ("font", "font")):
            if ov.get(src):
                style[dst] = ov[src]
        if ov.get("bold"):
            style["weight"] = 700
        if ov.get("italic"):
            style["italic"] = True
        if style:
            it["style"] = style
        ic = ov.get("icon")
        if isinstance(ic, dict):
            s = ic.get("src")
            if s == "builtin" and ic.get("id"):
                it["icon"] = ic["id"]
                it.pop("iconUrl", None)
                it.pop("iconImg", None)
            elif s == "loxone" and ic.get("p"):
                u = self._icon_url(ic["p"])
                if u:
                    it["iconUrl"] = u
                    it.pop("iconImg", None)
            elif s == "loxlib" and ic.get("name"):
                it["iconUrl"] = "/loxlib?n=" + quote(str(ic["name"]))
                it.pop("iconImg", None)
            elif s == "google" and ic.get("name"):
                it["iconUrl"] = "/gicon?name=" + quote(str(ic["name"]))
                it.pop("iconImg", None)
            elif s == "custom" and ic.get("file"):
                it["iconImg"] = "/uicon?f=" + quote(str(ic["file"]))
                it.pop("iconUrl", None)
        # Mini-Verlauf in der Kachel (tiles.<uuid>.chart = Zeitraum), nur fuer
        # Bausteine mit Aufzeichnung. Ein Tipp oeffnet wie bisher die Detailseite.
        rng = ov.get("chart")
        c = self.controls.get(uuid) or {}
        if rng in STAT_RANGES and (c.get("statistic") or c.get("statisticV2")):
            style = ov.get("chartStyle") if ov.get("chartStyle") in STAT_TILE_STYLES else "trend"
            sp = self._stat_spark(c, rng, style)
            if sp:
                it["spark"] = sp
        return it

    # ---- Views ----
    def _view_tab(self, tab: str, prof: dict | None = None) -> dict:
        if _is_layout_tab(tab):
            # Kachel-Raster (2x2 oder 3x3 je Seite) wie das Dashboard: Kacheln und
            # Widgets. Raum-Tab: Raumname steht schon im Tab, nicht an jeder Kachel.
            cells = self._tab_layout(tab, prof)
            wd = self._widgets_data(cells, prof, show_room=not tab.startswith("room:"))
            g = _grid((((prof or {}).get("layouts") or {}).get(tab) or {}).get("grid"), (prof or {}).get("grid", 3))
            return {"t": "view", "layout": "cells", "grid": g, "title": self._tab_title(tab, prof), "tab": tab,
                    "route": {"view": "tab", "tab": tab}, "cells": cells, "wd": wd,
                    "items": list(wd["tiles"].values())}
        return {"t": "view", "title": "", "tab": tab, "route": {"view": "tab", "tab": tab}, "items": []}

    def _view_group(self, route: dict, prof: dict | None = None) -> dict:
        kind, gid = route.get("kind"), route.get("id")
        layout = None
        if kind == "cat":
            uuids = [u for u, c in self.controls.items()
                     if c.get("cat") == gid and self._room_ok(u, prof) and self._shown(u, prof)]
            uuids = _apply_order(uuids, ((prof.get("tileOrder") or {}) if prof else {}).get(f"cat:{gid}"))
            title = _clean(self.cats.get(gid, {}).get("name")); tab = "kategorien"
            sr = self._spans_rooms(uuids)
            return {"t": "view", "title": title, "tab": tab, "route": route,
                    "layout": layout,
                    "items": [self._control_item(u, prof, show_room=sr) for u in uuids]}
        elif kind == "room":
            uuids = [u for u, c in self.controls.items()
                     if c.get("room") == gid and self._cat_ok(u, prof) and self._shown(u, prof)]
            uuids = _apply_order(uuids, ((prof.get("tileOrder") or {}) if prof else {}).get(f"room:{gid}"))
            title = _clean(self.rooms.get(gid, {}).get("name")); tab = "raeume"
        elif kind == "central":
            c = self.controls.get(gid, {})
            members = (c.get("details") or {}).get("controls") or []
            uuids = [m.get("uuid") for m in members
                     if m.get("uuid") in self.controls and self._shown(m.get("uuid"), prof)]
            title = _clean(c.get("name")); tab = "zentral"
            cv = self._central_view(gid, c, uuids, prof, route)
            if cv:
                return cv
            if c.get("type") == "CentralAudioZone":
                layout = "list"
        else:
            uuids, title, tab = [], "", None
        return {"t": "view", "title": title, "tab": tab, "route": route,
                "layout": layout, "items": [self._control_item(u, prof) for u in uuids]}

    def _view_sources(self, uuid: str) -> dict:
        """Musikauswahl einer AudioZone: feste Rubriken (immer sichtbar, auch leer).

        'Favoriten' = die Zonen-Favoriten (roomfavs, vom Miniserver). 'Playlisten'
        ist vorerst ein Platzhalter (Bibliothek/Playlisten liegen im Audioserver
        und werden noch nicht abgefragt).
        """
        c = self.controls.get(uuid, {})
        ua = c.get("uuidAction")

        # Favoriten aus dem Audioserver-Event-Kanal (Port 7091) — fuer Gen1
        # (Musikserver) UND Gen2 (Audioserver/Sonn). Der Loxone-sourceList-State
        # ist bei vielen Setups leer, dies ist der zuverlaessige Weg. Der
        # Abspiel-Index (`play`) beruecksichtigt, dass Musikserver per `slot` und
        # Sonn per Item-`id` adressiert (siehe AudioEventClient._apply_favs).
        # Nur wenn der Kanal die Favoriten auch liefern darf: ein gekoppelter
        # Audioserver ohne geglueckte Anmeldung (oder unklare Kopplung) schickt keine (dieselbe Bedingung
        # wie beim Anfordern in prime_favs) -> dann die des Miniservers.
        _cl, _pid = self._audio_client_for(c) if c.get("type") in ("AudioZone", "AudioZoneV2") else (None, None)
        if _cl is not None and _pid is not None and (_cl.paired is False or _cl.authed):
            favs = _cl.favs.get(_pid, [])
            items = [{"label": f["name"],
                      "cmd": {"uuid": ua, "cmd": f"roomfav/play/{f.get('play', f['slot'])}"},
                      "cover": ("/cover?u=" + quote(f["cover"], safe="")) if f["cover"] else ""}
                     for f in favs if f.get("slot") is not None]
            body = ({"k": "favs", "wrap": True, "items": items} if items else
                    {"k": "status", "text": "noch keine – in der App/am Tablet anlegen"})
            return {"t": "view", "title": _clean(c.get("name")),
                    "route": {"view": "sources", "id": uuid},
                    "blocks": [{"k": "title", "text": _clean(c.get("name")), "sub": "Musikauswahl"},
                               {"k": "head", "text": "Favoriten"}, body]}

        favs = self._audio_favs(c)

        def strip(items):
            return {"k": "favs", "wrap": True, "items": [
                {"label": f["name"], "cmd": {"uuid": ua, "cmd": f"roomfav/play/{f['slot']}"},
                 "cover": ("/cover?u=" + quote(f["cover"], safe="")) if f["cover"] else ""}
                for f in items]}

        empty = {"k": "status", "text": "noch keine – im Tablet / der App anlegen"}
        blocks = [{"k": "title", "text": _clean(c.get("name")), "sub": "Musikauswahl"},
                  {"k": "head", "text": "Favoriten"},
                  strip(favs) if favs else dict(empty),
                  {"k": "head", "text": "Playlisten"},
                  dict(empty)]
        return {"t": "view", "title": _clean(c.get("name")),
                "route": {"view": "sources", "id": uuid}, "blocks": blocks}

    def _big_view(self, uuid: str, icon: str, big: str, sub: str = "", tone=None) -> dict:
        """Grosse 1/1-Wertseite fuer reine Status-Bausteine. Das Hero-Icon ist
        dasselbe wie auf der Kachel vorne: Loxone-eigenes Icon, falls vorhanden,
        sonst das Builtin-Icon (`icon`)."""
        c = self.controls.get(uuid, {})
        hero = {"k": "hero", "icon": icon}
        iu = self._control_icon_url(c)
        if iu:
            hero["iconUrl"] = iu
        blk = {"k": "big", "text": big}
        if tone:
            blk["tone"] = tone
        blocks = [hero, blk]
        if sub:
            blocks.append({"k": "status", "text": sub})
        return {"t": "view", "title": _clean(c.get("name")),
                "route": {"view": "control", "id": uuid}, "blocks": blocks}

    @staticmethod
    def _stat_months(t0: int, t1: int) -> list[str]:
        """Monatsschluessel JJJJMM, die das Fenster [t0, t1] (Wanduhr-Sekunden) beruehrt."""
        a = datetime(1970, 1, 1) + timedelta(seconds=t0)
        b = datetime(1970, 1, 1) + timedelta(seconds=t1)
        y, m, out = a.year, a.month, []
        while (y, m) <= (b.year, b.month):
            out.append(f"{y:04d}{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    @staticmethod
    def _stat_edges(rng: str, t1: int) -> list[int]:
        """Abschnittsgrenzen der Verbrauchsbalken: bei 24 h je volle Stunde, sonst
        je Tag ab Mitternacht. Der letzte Abschnitt laeuft bis jetzt."""
        if rng == "24h":
            step, n = 3600, 24
        else:
            step, n = 86400, STAT_RANGES[rng][1] // 86400
        start = t1 - t1 % step - (n - 1) * step
        return [start + k * step for k in range(n)] + [t1 + 1]

    def _stat_rows(self, ua: str, t0: int, t1: int) -> tuple[list, bool, bool]:
        """Zeilen im Fenster aus stat_cache, vorneweg der letzte Stand davor (falls
        bekannt). Fehlende oder noch wachsende Monate werden im Hintergrund
        nachgeladen. -> (zeilen, laedt_noch, abruffehler)"""
        allrows, loading, error = [], False, False
        now = time.monotonic()
        for ym in self._stat_months(t0, t1):
            key = (ua, ym)
            ent = self.stat_cache.get(key)
            if ent is None:
                want = True
            elif ent[2] is None:
                want = now - ent[0] >= STAT_RETRY
            else:
                want = ent[1] <= ym and now - ent[0] >= STAT_REFRESH
            if want and key not in self.stat_pending:
                self.stat_pending.add(key)
                self._spawn(self._stat_load(ua, ym))
            if ent is None:
                loading = True
            elif ent[2] is None:
                error = True
            else:
                allrows.extend(ent[2])
        allrows.sort(key=lambda r: r[0])
        before = [r for r in allrows if r[0] < t0]
        return ([before[-1]] if before else []) + [r for r in allrows if t0 <= r[0] <= t1], loading, error

    def _stat2_rows(self, ua: str, gid: str, out: str, rng: str, t0: int, t1: int) -> tuple[list, bool, bool]:
        """Wie _stat_rows, fuer einen statisticV2-Ausgang: Zeilen im Fenster, vorneweg
        der letzte Stand davor; fehlend oder aelter als STAT_REFRESH -> im
        Hintergrund neu holen. -> (zeilen, laedt_noch, abruffehler)"""
        key = (ua, gid, out, rng)
        ent = self.stat2_cache.get(key)
        age = time.monotonic() - ent[0] if ent else 0.0
        if ent is None or age >= (STAT_RETRY if ent[1] is None else STAT_REFRESH):
            if key not in self.stat_pending:
                self.stat_pending.add(key)
                self._spawn(self._stat2_load(key, ua, gid, out, STAT_RANGES[rng][1]))
        if ent is None:
            return [], True, False
        if ent[1] is None:
            return [], False, True
        before = [r for r in ent[1] if r[0] < t0]
        return ([before[-1]] if before else []) + [r for r in ent[1] if t0 <= r[0] <= t1], False, False

    @staticmethod
    def _stat_series_defs(c: dict) -> list:
        """Alle aufgezeichneten Reihen eines Bausteins als (name, art, stellen,
        einheit, quelle). `statistic`: je Ausgang, Art aus visuType, Quelle
        ("v1", index in der Monatsdatei). `statisticV2`: je Datenpunkt einer
        Gruppe, `accumulated` = Zaehlerstand, Quelle ("v2", gruppe, ausgang).
        Gleiche Titel in einer Gruppe (Netz: zweimal "Zaehlerstand") bekommen
        den Ausgangsnamen dazu."""
        defs = []
        for i, o in enumerate((c.get("statistic") or {}).get("outputs") or []):
            if isinstance(o, dict):
                dec, unit = _stat_fmt(o.get("format"))
                defs.append((_clean(o.get("name")) or f"Wert {i + 1}",
                             STAT_KIND.get(o.get("visuType"), "line"), dec, unit, ("v1", i)))
        for g in (c.get("statisticV2") or {}).get("groups") or []:
            if not isinstance(g, dict):
                continue
            dps = [d for d in (g.get("dataPoints") or []) if isinstance(d, dict) and d.get("output")]
            titles = [d.get("title") for d in dps]
            for d in dps:
                dec, unit = _stat_fmt(d.get("format"))
                name = _clean(d.get("title")) or d["output"]
                if titles.count(d.get("title")) > 1:
                    name = f"{name} · {d['output']}"
                defs.append((name, "counter" if g.get("accumulated") else "line", dec, unit,
                             ("v2", str(g.get("id")), str(d["output"]))))
        return defs

    def _stat_blocks(self, c: dict, rng: str) -> list:
        """Diagramm-Bloecke fuer einen Baustein mit `statistic` oder `statisticV2`.
        Reihen gleicher Art und Einheit teilen sich ein Diagramm (zwei Grillfuehler,
        Netz-Bezug und -Einspeisung), sonst je eines (Zaehler: Leistung als Linie,
        Verbrauch als Balken)."""
        defs = self._stat_series_defs(c)
        ua = c.get("uuidAction")
        if not (ua and defs):
            return []
        now = calendar.timegm(datetime.now().timetuple())
        t1 = now - now % 60                    # Fenster rueckt je Minute vor
        mkey = (ua, rng, t1, self.stat_gen)
        if mkey in self.stat_memo:
            return self.stat_memo[mkey]
        t0 = t1 - STAT_RANGES[rng][1]
        v1 = None                              # Monatsdateien: eine Abfrage fuer alle Ausgaenge
        groups: dict[tuple[str, str], list] = {}
        for d in defs:
            groups.setdefault((d[1], d[3]), []).append(d)
        blocks = []
        for kind, unit in groups:
            edges = self._stat_edges(rng, t1) if kind == "counter" else None
            series, any_rows, loading, error = [], False, False, False
            for name, _kind, dec, _unit, src in groups[(kind, unit)]:
                if src[0] == "v1":
                    if v1 is None:
                        v1 = self._stat_rows(ua, t0, t1)
                    rows, ld, er = v1
                    i = src[1]
                    pts = [(r[0], r[1][i]) for r in rows if i < len(r[1]) and r[1][i] is not None]
                else:
                    rows, ld, er = self._stat2_rows(ua, src[1], src[2], rng, t0, t1)
                    pts = [(r[0], r[1][0]) for r in rows if r[1] and r[1][0] is not None]
                any_rows, loading, error = any_rows or bool(rows), loading or ld, error or er
                if kind == "counter":
                    pts = _stat_bars(pts, edges)
                else:
                    if pts and pts[0][0] < t0:
                        pts[0] = (t0, pts[0][1])   # letzter Stand vor dem Fenster = Startwert
                    pts = _stat_thin(pts, t0, t1, STAT_MAX_POINTS, kind == "digital")
                series.append({"name": name, "dec": dec,
                               "pts": [[int(t), round(v, dec + 2)] for t, v in pts]})
            has = any_rows if kind == "counter" else any(s["pts"] for s in series)
            blk = {"k": "chart", "kind": kind, "unit": unit, "series": series,
                   "t0": edges[0] if edges else t0, "t1": t1,
                   "state": "ok" if has else ("loading" if loading else ("error" if error else "empty"))}
            if not blocks:                     # Zeitraum-Wahl nur am ersten Diagramm der Seite
                blk.update(range=rng, ranges=[[k, v[0]] for k, v in STAT_RANGES.items()])
            blocks.append(blk)
        if len(self.stat_memo) > 64:
            self.stat_memo = {}
        self.stat_memo[mkey] = blocks
        return blocks

    def chart_blocks(self, uuid: str, rng: str | None = None) -> dict | None:
        """Inhalt der Verlaufs-Pane im Split-Layout (panes "chart:<uuid>"): Name,
        aktueller Wert wie auf der Detailseite und die Diagramme aus
        _stat_blocks (dieselben Abrufe, Caches und Zustaende). None, wenn der
        Baustein fehlt oder nichts aufzeichnet."""
        c = self.controls.get(uuid)
        if not c or not (c.get("statistic") or c.get("statisticV2")):
            return None
        rng = rng if rng in STAT_RANGES else STAT_DEFAULT_RANGE
        v = self._view_control_inner(uuid)
        big = next((b.get("text") or "" for b in v.get("blocks") or [] if b.get("k") in ("big", "ist")), "")
        return {"control": uuid, "name": _clean(c.get("name")), "value": big,
                "range": rng, "blocks": self._stat_blocks(c, rng)}

    def _stat_primary(self, c: dict) -> tuple | None:
        """Die Reihe, die eine Kachel zeigt: die erste Linie, sonst die erste Reihe."""
        defs = self._stat_series_defs(c)
        return next((d for d in defs if d[1] == "line"), defs[0] if defs else None)

    def _stat_raw(self, c: dict, d: tuple, rng: str, t0: int, t1: int) -> tuple[list, bool, bool]:
        """Rohpunkte einer Reihe im Fenster, vorneweg der letzte Stand davor, aus
        denselben Caches wie die Diagramme. -> (punkte, laedt_noch, abruffehler)"""
        ua, src = c.get("uuidAction"), d[4]
        if src[0] == "v1":
            rows, ld, er = self._stat_rows(ua, t0, t1)
            i = src[1]
            return [(r[0], r[1][i]) for r in rows if i < len(r[1]) and r[1][i] is not None], ld, er
        rows, ld, er = self._stat2_rows(ua, src[1], src[2], rng, t0, t1)
        return [(r[0], r[1][0]) for r in rows if r[1] and r[1][0] is not None], ld, er

    @staticmethod
    def _stat_dur(sec: float) -> str:
        """Dauer als "3 h 20 min" bzw. "40 min"."""
        h, m = int(sec // 3600), int(round(sec % 3600 / 60))
        if m == 60:
            h, m = h + 1, 0
        return f"{h} h" + (f" {m} min" if m else "") if h else f"{m} min"

    def _stat_spark(self, c: dict, rng: str, style: str = "trend") -> dict | None:
        """Mini-Verlauf fuer eine Kachel (tiles.<uuid>.chart/.chartStyle).

        trend    Verlauf im gewaehlten Zeitraum: Linie mit Tiefst-/Hoechstwert,
                 Digitalwert als Stufen, Zaehlerstand als Verbrauchsbalken.
        pattern  Tagesmuster: 7 Tage x 24 Stunden, je Stunde der zeitgewichtete
                 Mittelwert (Digital: Ein-Anteil, Zaehler: Verbrauch der Stunde).
        span     Tagesspanne (nur Linien): je Tag Tiefst-, Hoechst- und Mittelwert.

        `badge` ist die kurze Angabe im Kopf der Kachel; die Visu zeigt sie nur an."""
        d = self._stat_primary(c)
        ua = c.get("uuidAction")
        if not (d and ua):
            return None
        name, kind, dec, unit, src = d
        if style == "span" and kind != "line":
            style = "trend"
        now = calendar.timegm(datetime.now().timetuple())
        t1 = now - now % 60
        mkey = ("spark", ua, rng, style, t1, self.stat_gen)
        if mkey in self.stat_memo:
            return self.stat_memo[mkey]
        fmt = f"%.{dec}f{unit}"
        out: dict | None = None
        if style == "trend":
            blocks = self._stat_blocks(c, rng)
            b = next((x for x in blocks if x.get("kind") == kind and x.get("unit") == unit), None)
            if b is None:
                return None
            se = next((x for x in b.get("series") or [] if x.get("name") == name), (b.get("series") or [{}])[0])
            full = [tuple(p) for p in se.get("pts") or []]
            out = {"style": "trend", "kind": kind, "state": b.get("state"), "t0": b.get("t0"),
                   "t1": b.get("t1"), "dec": dec}
            if kind == "counter":
                out["pts"] = [list(p) for p in full]
                if full:
                    out["badge"] = "Σ " + self._fmt_num(sum(v for _, v in full), fmt)
            else:
                out["pts"] = [[int(t), round(v, dec + 2)]
                              for t, v in _stat_thin(full, b["t0"], b["t1"], 48, kind == "digital")]
                if full and kind == "line":
                    lo, hi = min(full, key=lambda p: p[1]), max(full, key=lambda p: p[1])
                    out["lo"], out["hi"] = [int(lo[0]), lo[1]], [int(hi[0]), hi[1]]
                    ago = [v for t, v in full if t <= t1 - 86400]
                    if ago:
                        delta = full[-1][1] - ago[-1]
                        step = 10 ** -dec / 2
                        arrow = "▲" if delta >= step else ("▼" if delta <= -step else "=")
                        out["badge"] = f"{arrow} {self._fmt_num(abs(delta), fmt)} in 24 h"
                elif full:
                    t0 = b["t0"]
                    raw, _ld, _er = self._stat_raw(c, d, rng, t0, t1)
                    share = _stat_buckets(raw, [t0, t1], t1)[0]
                    if share is not None:
                        out["badge"] = "Ein " + self._stat_dur(share * (t1 - t0))
        else:
            start = t1 - t1 % 86400 - 6 * 86400        # Mitternacht vor 6 Tagen
            raw, loading, error = self._stat_raw(c, d, "7d", start, t1)
            days = [STAT_WEEKDAYS[((start // 86400) + i + 3) % 7] for i in range(7)]   # 1.1.1970 = Do
            state = "ok" if raw else ("loading" if loading else ("error" if error else "empty"))
            out = {"style": style, "kind": kind, "state": state, "dec": dec, "days": days}
            if style == "pattern":
                edges = [start + h * 3600 for h in range(7 * 24 + 1)]
                if kind == "counter":
                    cells = [None if a >= t1 else v for (a, v) in _stat_bars(raw, edges)]
                else:
                    cells = _stat_buckets(raw, edges, t1)
                out["cells"] = [None if v is None else round(v, dec + 2) for v in cells]
                vals = [v for v in cells if v is not None]
                if vals and kind == "counter":
                    out["badge"] = "7 Tage · Σ " + self._fmt_num(sum(vals), fmt)
                elif vals and kind == "line":
                    out["badge"] = "7 Tage · max " + self._fmt_num(max(vals), fmt)
                elif vals:
                    out["badge"] = "7 Tage"
            else:
                edges = [start + i * 86400 for i in range(8)]
                rngs = _stat_day_range(raw, edges, t1)
                avgs = _stat_buckets(raw, edges, t1)
                out["spans"] = [None if r is None else [round(r[0], dec + 2), round(r[1], dec + 2),
                                                        None if a is None else round(a, dec + 2)]
                                for r, a in zip(rngs, avgs)]
                if rngs[-1] is not None:
                    lo, hi = rngs[-1]
                    out["badge"] = "heute " + self._fmt_num(lo, f"%.{dec}f") + "–" + self._fmt_num(hi, fmt)
        if len(self.stat_memo) > 64:
            self.stat_memo = {}
        self.stat_memo[mkey] = out
        return out

    def _irrigation_zone_name(self, c: dict) -> str:
        """Name der aktuellen Bewaesserungszone (currentZone = Index oder Id
        in der zones-Liste), sonst leer."""
        cur = self._state(c, "currentZone")
        zones = self._named_items(self._json_state(c, "zones"))
        if cur in (None, "", 0, "0") and not zones:
            return ""
        try:
            idx = int(float(cur))
        except (TypeError, ValueError):
            idx = None
        for i, (label, z) in enumerate(zones):
            if idx is not None and (z.get("id") == idx or z.get("idx") == idx or i + 1 == idx):
                return label
        return f"Zone {cur}" if idx else ""

    def _steak_temps(self, c: dict) -> list[tuple[str, float]]:
        """Fuehler-Temperaturen des Grillthermometers aus currentTemperatures
        (Liste von Zahlen oder Objekten mit name/value)."""
        data = self._json_state(c, "currentTemperatures")
        out = []
        for label, e in self._named_items(data):
            v = e.get("value", e.get("temperature", e.get("temp")))
            try:
                out.append((label if not label.isdigit() else f"Fühler {label}", float(v)))
            except (TypeError, ValueError):
                continue
        return out

    # ---- Anlagenschema (SystemScheme) -----------------------------------
    def _resolve_control(self, uuid: str | None) -> dict | None:
        """Baustein zu einer UUID liefern – auch wenn es ein Subcontrol ist.
        self.controls enthaelt nur die Top-Level-Bausteine; die Referenzen im
        Anlagenschema zeigen teils auf Subcontrols (z.B. InfoOnly eines Oelkessels)."""
        if not uuid:
            return None
        c = self.controls.get(uuid)
        if c:
            return c
        for pc in self.controls.values():
            sub = (pc.get("subControls") or {}).get(uuid)
            if sub:
                return sub
        return None

    def _scheme_value(self, c: dict | None) -> dict:
        """Kompakter Anzeige-Wert eines im Schema referenzierten Bausteins:
        {text, on, tone}. Deckt die im Anlagenschema ueblichen Typen ab
        (Slider/InfoOnlyAnalog = Zahl, InfoOnlyDigital = Ein/Aus, TextState)."""
        if not c:
            return {"text": "", "on": False}
        t = c.get("type")
        det = c.get("details") or {}
        if t in ("Slider", "InfoOnlyAnalog", "Meter"):
            return {"text": self._fmt_num(self._state(c, "value") if t != "Meter"
                                          else self._state(c, "actual"),
                                          det.get("format", "%.1f")), "on": False}
        if t == "InfoOnlyDigital":
            on = bool(self._state(c, "active"))
            txt = det.get("text") or {}
            return {"text": (txt.get("on") if on else txt.get("off"))
                    or ("Ein" if on else "Aus"), "on": on}
        if t in ("TextState", "InfoOnlyText"):
            return {"text": str(self._state(c, "textAndIcon")
                               or self._state(c, "text") or ""), "on": False}
        # Fallback: erster vorhandener State als Text.
        for name in (c.get("states") or {}):
            v = self._state(c, name)
            if v not in (None, ""):
                return {"text": str(v), "on": False}
        return {"text": "", "on": False}

    def _view_scheme(self, uuid: str, c: dict, route: dict) -> dict:
        """Anlagenschema als Ansicht: Hintergrundbild vom Miniserver (ueber den
        /icon-Proxy) plus die Live-Werte der referenzierten Bausteine als Overlay
        an ihren Positionen. schemeSize ist das Original-Koordinatensystem, in dem
        pos/size angegeben sind – der Client skaliert es auf die Panelbreite."""
        det = c.get("details") or {}
        sz = det.get("schemeSize") or {}
        img = det.get("imagePath")
        # /icon liefert .png vom Miniserver (mit JWT); &v busted den Browser-Cache
        # bei geaenderter imageVersion. Hinweis: der Server-seitige icon_cache wird
        # per Pfad gehalten – aendert sich das Bild im Config, ggf. Server neu laden.
        src = None
        if img:
            src = "/icon?p=" + quote(img, safe="")
            if det.get("imageVersion"):
                src += "&v=" + str(det["imageVersion"])
        items = []
        for ref in (det.get("controlReferences") or []):
            rc = self._resolve_control(ref.get("uuidAction"))
            if not rc:
                continue
            val = self._scheme_value(rc)
            pos = ref.get("pos") or {}
            size = ref.get("size") or {}
            entry = {
                "x": pos.get("x", 0), "y": pos.get("y", 0),
                "w": size.get("width"), "h": size.get("height"),
                "text": (ref.get("text") or "") + val["text"],
                "on": val["on"],
            }
            # Bedienbare Referenzen (actionsVisible) sind antippbar -> Detailansicht
            # des Bausteins. Nur fuer Top-Level-Bausteine, die eine eigene View haben.
            ru = ref.get("uuidAction")
            if ref.get("actionsVisible") and ru in self.controls:
                entry["nav"] = {"view": "control", "id": ru}
            items.append(entry)
        return {"t": "view", "title": _clean(c.get("name")), "route": route,
                "layout": "scheme", "image": src,
                "sw": sz.get("width") or 1300, "sh": sz.get("height") or 866,
                "items": items}

    @staticmethod
    def _audio_view(v: dict, c: dict) -> dict:
        """Audio-Seiten nach dem Entwurf: Cover transparent im Hintergrund,
        Titel mittig, Lautstaerke als schmaler Balken rechts (+ ueber, - unter),
        unten Transport + klein "Quellen"."""
        if c.get("type") not in ("AudioZone", "AudioZoneV2") or not isinstance(v.get("blocks"), list):
            return v
        out, vol, more = [], None, None
        for b in v["blocks"]:
            k = b.get("k")
            if k == "cover":
                v["bgCover"] = b.get("src")
            elif k == "hero":
                continue
            elif k == "slider":
                vol = b
            elif k == "more":
                more = b.get("route")
            else:
                out.append(b)
        title = next((b for b in out if b.get("k") == "title"), None)
        rows = [b for b in out if b.get("k") == "row"]
        rest = [b for b in out if b.get("k") not in ("title", "row")]
        mid = {"k": "audiomid", "title": (title or {}).get("text", ""), "sub": (title or {}).get("sub", "")}
        if vol:
            mid["vol"] = {"value": vol.get("value", 0), "min": vol.get("min", 0), "max": vol.get("max", 100),
                          "cmd": vol.get("cmd")}
        if rows and more:
            rows[-1]["cells"] = rows[-1]["cells"] + [{"label": "Quellen", "icon": "list", "nav": more}]
        v["blocks"] = rest + [mid] + rows
        v["anchor"] = "bottom"
        return v

    def _alarm_edit_view(self, uuid: str, eid: str) -> dict:
        """Wecker-Eintrag bearbeiten: Uhrzeit (+/- ueber/unter Stunde und Minute),
        Wochentage, An/Aus, Speichern. Wochentage = Betriebsarten der Anlage
        (operatingModes) mit Wochentag-Namen."""
        c = self.controls.get(uuid, {})
        e = next((x for x in self._alarm_entries(c) if x["id"] == str(eid)), None)
        if not e:
            return self._view_control(uuid)
        order = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
        wd = {}
        for mid, nm in (self.op_modes or {}).items():
            n = str(nm).strip().lower()
            if n in order:
                wd[n] = str(mid)
        days = [{"k": self._WD_ABBR[n], "mode": wd.get(n, ""), "on": e["daily"] or (wd.get(n, "") in e["modes"])}
                for n in order]
        return {"t": "view", "title": e["name"], "anchor": "bottom",
                "route": {"view": "control", "id": uuid, "entry": str(eid)},
                "blocks": [{"k": "dhead", "room": _clean(c.get("name")), "name": e["name"]},
                           {"k": "alarmedit", "uuid": c.get("uuidAction"), "eid": str(eid), "name": e["name"],
                            "secs": e["secs"], "active": e["active"], "days": days,
                            "other": [m for m in e["modes"] if m not in wd.values()]}]}

    def _view_control(self, uuid: str, rng: str | None = None, chart: bool = False) -> dict:
        c = self.controls.get(uuid, {})
        if chart and (c.get("statistic") or c.get("statisticV2")):
            # Eigene Verlaufs-Seite (aus der Aktionsreihe der Detailseite geoeffnet)
            cb = self.chart_blocks(uuid, rng) or {}
            blocks = ([{"k": "status", "text": cb["value"]}] if cb.get("value") else []) + (cb.get("blocks") or [])
            return self._with_head({"t": "view", "title": _clean(c.get("name")),
                    "route": {"view": "control", "id": uuid, "chart": 1, "range": cb.get("range") or STAT_DEFAULT_RANGE},
                    "blocks": blocks}, c)
        v = self._audio_view(self._std_view(self._view_control_inner(uuid)), c)
        if c.get("isSecured"):
            v["secured"] = True   # Client fragt vor Befehlen die Visu-PIN ab
        # Verlaufs-Diagramme unter die Detailseite haengen, wenn der Baustein eine
        # Aufzeichnung hat. Nur bei Block-Seiten; die Route traegt dann den Zeitraum.
        if (c.get("statistic") or c.get("statisticV2")) and isinstance(v.get("blocks"), list):
            rng = rng if rng in STAT_RANGES else STAT_DEFAULT_RANGE
            charts = self._stat_blocks(c, rng)
            if charts:
                # Verlauf NIE unter dem Wert, sondern immer eine Ebene tiefer: Nebenaktion
                # rechts oben im Kopf (siehe _with_head), kein Knopf in der Aktionsreihe.
                v.setdefault("side", []).append({"icon": "chart", "label": "Verlauf",
                                                 "nav": {"view": "control", "id": uuid, "chart": 1}})
        # Verknuepfte Objekte (Loxone Config): Nebenaktion im Kopf, wie der
        # Verlauf eine Ebene tiefer -> Seite mit den Objekten als Kacheln
        if self._links_of(c) and isinstance(v.get("blocks"), list):
            v.setdefault("side", []).append({"icon": "link", "label": "Verknüpft",
                                             "nav": {"view": "links", "id": uuid}})
        return self._with_head(v, c)

    # Bloecke, die eine Seite zum "Spezialbaustein" machen (Bedienung/Medien)
    _SPECIAL_KINDS = {"dim", "scenes", "shade", "title", "alarmlist", "video", "favs",
                      "cover", "eflow", "slider", "chart", "web", "state", "audiomid",
                      "log", "kpis", "alarmedit", "ist", "sline"}

    # Symbole der Nebenaktionen (Knopf oeffnet eine Unterseite), von links nach rechts
    _SIDE_ORDER = ["list", "link", "chart"]
    _SIDE_LABEL = {"list": "Quellen", "link": "Verknüpft", "chart": "Verlauf"}

    def _with_head(self, v: dict, c: dict) -> dict:
        """Kopf jeder Detailseite: Raum + Bausteinname oben, kein Symbol-Kreis.
        Reine Anzeigen (nur Wert/Status, hoechstens der Verlaufs-Knopf) bekommen
        stattdessen ihr Piktogramm uebergross im Hintergrund (v["bgIcon"])."""
        blocks = v.get("blocks") if isinstance(v, dict) else None
        if not isinstance(blocks, list):
            v.pop("side", None)
            return v
        # Nebenaktionen (Verlauf, Verknuepft, Quellen = Knoepfe, die eine Unterseite
        # oeffnen) wandern aus den Aktionsreihen in den Kopf. Reihenfolge von links:
        # Quellen, Verknuepft, Verlauf; eine dadurch leere Reihe entfaellt.
        side = list(v.pop("side", None) or [])
        nb = []
        for b in blocks:
            if b.get("k") == "row":
                keep = []
                for cell in b.get("cells") or []:
                    if cell.get("nav") and cell.get("icon") in self._SIDE_LABEL:
                        side.append({"icon": cell["icon"], "label": cell.get("label") or self._SIDE_LABEL[cell["icon"]],
                                     "nav": cell["nav"]})
                    else:
                        keep.append(cell)
                if not keep:
                    continue
                b = {**b, "cells": keep}
            nb.append(b)
        blocks = nb
        side.sort(key=lambda x: self._SIDE_ORDER.index(x["icon"]))
        hero = next((b for b in blocks if b.get("k") == "hero"), None)
        blocks = [b for b in blocks if b.get("k") not in ("hero", "dhead")]
        # Seiten mit Eintragsliste (Szenen, Fenster, Zonen, Zentral-Mitglieder): der Zustand
        # steht EINZEILIG ("2 offen · 1 gekippt · 16 Fenster") statt als grosse Zahl, damit
        # die Liste Platz hat (Designsystem: Auswahl-/Sammelbausteine). Grosse Zahl bleibt
        # Seiten ohne Liste vorbehalten.
        if any(b.get("k") == "scenes" for b in blocks):
            nb2, i = [], 0
            while i < len(blocks):
                b = blocks[i]
                if b.get("k") == "big" and not b.get("line"):
                    b = {**b, "line": True, "small": False}
                    nx = blocks[i + 1] if i + 1 < len(blocks) else None
                    if nx and nx.get("k") == "status" and nx.get("text"):
                        b["extra"] = nx["text"]; i += 1
                nb2.append(b); i += 1
            blocks = nb2
        kinds = {b.get("k") for b in blocks}
        rows = [b for b in blocks if b.get("k") == "row"]
        simple = not (kinds & self._SPECIAL_KINDS) and all(
            all(cell.get("nav") for cell in (r.get("cells") or [])) for r in rows)
        if simple and hero:
            v["bgIcon"] = {k: hero[k] for k in ("icon", "iconUrl", "iconImg") if hero.get(k)}
        room = _clean((self.rooms.get(c.get("room")) or {}).get("name"))
        name = _clean(c.get("name"))
        # Raumzeile weglassen, wenn sie nichts sagt: gleich dem Namen ("OG Bad /
        # OG Bad") oder Loxone-Platzhalter "nicht zugeordnet"
        if room and (room.casefold() == (name or "").casefold() or room.casefold() in ("nicht zugeordnet", "unassigned")):
            room = ""
        dh = {"k": "dhead", "room": room, "name": name}
        if side:
            dh["acts"] = side
        blocks.insert(0, dh)
        v["blocks"] = blocks
        v["anchor"] = "bottom"   # Kopf immer oben, Wert mittig, Aktionsreihe unten
        return v

    # Kurze Beschriftungen fuer die Aktionsreihe (Platz auf 480 px).
    _ACT_SHORT = {"Einschalten": "Ein", "Ausschalten": "Aus", "Automatik": "Auto",
                  "Ganz Auf": "Ganz auf", "Ganz Ab": "Ganz ab"}

    @classmethod
    def _std_view(cls, v: dict) -> dict:
        """Mockup-Standards fuer JEDE Detailseite an einer Stelle durchsetzen,
        statt sie in jedem Baustein-Zweig einzeln nachzuziehen:
          * Zustandstext ("value") wird zur grossen Zahl/zum grossen Wort, wenn
            die Seite noch keinen grossen Wert hat.
          * Grosser Wert + Schieberegler -> Regler-Flaeche wie beim Dimmer
            (Ziehen stellt ein, grosse Zahl darin). Nicht bei Audio (Titel).
          * Knopf-Zeilen -> Aktionsreihe (runde Icon-Knoepfe, Text als Pille),
            lange Beschriftungen gekuerzt. Aufklapp- und Umbruch-Zeilen
            (Farbvorwahl, Wochentage) bleiben wie sie sind.
        Der Verlauf wandert dadurch automatisch auf eine eigene Seite (siehe
        _view_control)."""
        blocks = v.get("blocks") if isinstance(v, dict) else None
        if not isinstance(blocks, list):
            return v
        kinds = {b.get("k") for b in blocks}
        has_big = bool(kinds & {"big", "dim", "shade", "scenes", "state", "audiomid", "alarmedit", "log"})
        out = []
        for b in blocks:
            if b.get("k") == "value" and not has_big:
                b = {"k": "big", "text": b.get("text", "")}
                has_big = True
            elif b.get("k") == "astat" and not has_big:
                # Status-Wert (Wecker, Schaltuhr) ebenfalls gross, Zusatz darunter
                nb = {"k": "big", "text": b.get("text", "")}
                if b.get("tone"):
                    nb["tone"] = b["tone"]
                out.append(nb)
                has_big = True
                if b.get("sub"):
                    out.append({"k": "status", "text": b["sub"]})
                continue
            out.append(b)
        # grosser Wert + Schieberegler -> Regler-Flaeche
        if "title" not in kinds and "dim" not in kinds:
            bi = next((i for i, b in enumerate(out) if b.get("k") == "big"), None)
            si = next((i for i, b in enumerate(out) if b.get("k") == "slider"
                       and isinstance((b.get("cmd") or {}).get("tmpl"), str)), None)
            if bi is not None and si is not None:
                bt, sl = str(out[bi].get("text") or ""), out[si]
                m = re.match(r"^\s*[-−]?\d+(?:[.,]\d+)?(.*)$", bt)
                unit = m.group(1) if m else " %"
                try:
                    dim = {"k": "dim", "value": float(sl.get("value") or 0),
                           "min": float(sl.get("min") or 0), "max": float(sl.get("max") if sl.get("max") is not None else 100),
                           "step": float(sl.get("step") or 1), "unit": unit, "cmd": sl["cmd"]}
                    if dim["step"] >= 1:
                        dim.update(value=round(dim["value"]), min=round(dim["min"]), max=round(dim["max"]), step=round(dim["step"]))
                    out[bi] = dim
                    out = [b for i, b in enumerate(out) if i != si and b.get("k") != "hero"]
                    v["anchor"] = "bottom"
                except (TypeError, ValueError):
                    pass
        # Statuszeile, die nur den grossen Wert wiederholt, entfaellt
        bigt = {str(b.get("text") or "").strip().lower() for b in out if b.get("k") == "big"}
        out = [b for b in out if not (b.get("k") == "status" and str(b.get("text") or "").strip().lower() in bigt)]
        for b in out:
            # Umbruch-Zeilen mit bis zu 4 Knoepfen (z.B. Timer 15/30/60/90 min)
            # passen ebenfalls in die Aktionsreihe; laengere (Farbvorwahl) nicht.
            if b.get("k") == "row" and b.get("wrap") and len(b.get("cells") or []) <= 4:
                b.pop("wrap")
            if b.get("k") == "row" and not b.get("wrap") and not b.get("hidden") and not b.get("id"):
                b["act"] = True
                for c in b.get("cells") or []:
                    if c.get("label") in cls._ACT_SHORT:
                        c["label"] = cls._ACT_SHORT[c["label"]]
        v["blocks"] = out
        return v

    @staticmethod
    def _central_sum(t: str, n: int, total: int) -> str:
        """Zusammenfassung eines Zentralbausteins - gleiche Worte auf Kachel und Detail."""
        if t == "CentralLightController":
            return "Aus" if not n else ("1 Raum an" if n == 1 else f"{n} Räume an")
        if t == "CentralAudioZone":
            return f"{n} von {total} spielen" if n else "Aus"
        if t == "CentralJalousie":
            if not total:
                return ""
            return "Alle offen" if n >= total else ("Alle zu" if n == 0 else f"{n} von {total} offen")
        if t == "CentralAlarm":
            return f"{n} von {total} scharf" if total else "Keine Anlagen"
        return ""

    # Sammelaktionen der Zentralbausteine: je Mitglied ein bekannter Einzelbefehl
    _CENTRAL_ACT = {"lightoff": {"LightControllerV2": "changeTo/778"},
                    "up": {"Jalousie": "FullUp"}, "down": {"Jalousie": "FullDown"},
                    "shade": {"Jalousie": "shade"},
                    "arm": {"Alarm": "on"},
                    "pause": {"AudioZone": "pause", "AudioZoneV2": "pause"}}

    def _central_view(self, gid: str, c: dict, uuids: list, prof, route: dict) -> dict | None:
        """Zentralbaustein als Seite: Zusammenfassung gross, Mitglieder als
        Kacheln (antippen = Mitglied oeffnen), Sammelaktion(en) unten."""
        t = c.get("type")
        items, on = [], 0
        its = [self._control_item(u, prof, show_room=True) for u in uuids]
        rooms = [it.get("room") or "" for it in its]
        by_room = all(rooms) and len(set(rooms)) == len(rooms)   # Raum nur, wenn eindeutig
        for u, it in zip(uuids, its):
            lbl = (it.get("room") if by_room else it.get("label")) or it.get("label") or ""
            items.append({"id": u, "label": lbl, "sub": it.get("sublabel") or "", "on": bool(it.get("on")),
                          "icon": it.get("icon") or "info", "nav": {"view": "control", "id": u}})
            on += 1 if it.get("on") else 0
        # gleiche Beschriftung mehrfach -> mit Raum/Name der Zone unterscheiden
        # (nur was Loxone liefert; ohne Raum bleibt die Nummer der Zone)
        cnt = {}
        for x in items:
            cnt[x["label"]] = cnt.get(x["label"], 0) + 1
        for x, it in zip(items, its):
            if cnt[x["label"]] > 1:
                alt = [y for y in (it.get("room"), it.get("label")) if y and y != x["label"]]
                x["label"] = " · ".join(alt + [x["label"]]) if alt else x["label"]
        cells = []
        if t == "CentralLightController":
            summary = self._central_sum(t, on, len(uuids))
            cells = [{"label": "Alle aus", "cmd": {"uuid": gid, "cmd": "__central/lightoff"}}]
        elif t == "CentralJalousie":
            opn = sum(1 for u in uuids if (self._state(self.controls[u], "position") or 0) < 0.02)
            summary = self._central_sum(t, opn, len(uuids)) or "–"
            # Abweichler (die kleinere Gruppe) zuerst, nur Reihenfolge der Anzeige
            closed = len(uuids) - opn
            first_open = opn <= closed
            for x in items:
                x["_o"] = (self._state(self.controls[x["id"]], "position") or 0) < 0.02
            cells = [{"label": "Alle auf", "cmd": {"uuid": gid, "cmd": "__central/up"}},
                     {"label": "Beschatten", "cmd": {"uuid": gid, "cmd": "__central/shade"}},
                     {"label": "Alle zu", "cmd": {"uuid": gid, "cmd": "__central/down"}}]
        elif t == "CentralAlarm":
            summary = self._central_sum(t, on, len(uuids))
            cells = [{"label": "Alle scharf", "cmd": {"uuid": gid, "cmd": "__central/arm"}}]
        elif t == "CentralAudioZone":
            # normaler grosser Wert statt Riesen-Titel: "2 von 5" + kleine Zeile
            summary = self._central_sum(t, on, len(uuids))
            cells = [{"label": "Alle Pause", "cmd": {"uuid": gid, "cmd": "__central/pause"}}]
        else:
            return None
        if t == "CentralJalousie":
            items.sort(key=lambda x: x.get("_o") != first_open)
            for x in items:
                x.pop("_o", None)
        else:
            items.sort(key=lambda x: not x["on"])   # Aktive zuerst (passt zur Zusammenfassung oben)
        blocks = [{"k": "dhead", "room": "Zentral", "name": _clean(c.get("name"))},
                  {"k": "big", "text": summary},
                  {"k": "scenes", "items": items},
                  {"k": "row", "act": True, "cells": cells}]
        return {"t": "view", "title": _clean(c.get("name")), "tab": "zentral", "route": route,
                "anchor": "bottom", "blocks": blocks}

    async def _central_do(self, gid: str, action: str) -> None:
        c = self.controls.get(gid) or {}
        by_type = self._CENTRAL_ACT.get(action) or {}
        for m in ((c.get("details") or {}).get("controls") or []):
            mc = self.controls.get(m.get("uuid")) or {}
            cmd = by_type.get(mc.get("type"))
            if cmd and mc.get("uuidAction"):
                await self.command(mc["uuidAction"], cmd)

    # ---- Lichtszenen: Licht je Szene (lernend) --------------------------------
    # Loxone liefert nur die Live-Werte der Leuchten, nicht die gespeicherten
    # Werte jeder Szene. Deshalb: laeuft eine Szene 6 s unveraendert, wird ihr
    # Licht einmal gemessen und gemerkt. Bis dahin Schaetzung aus dem Namen.
    _SL_GUESS = ((("aus", "off"), 0, None),
                 (("nacht", "night", "schlaf", "orientier"), 10, "#ff9a5a"),
                 (("kino", "tv", "film", "fernseh"), 20, "#7a93ff"),
                 (("abend", "gemütlich", "gemuetlich", "relax", "essen", "dinner", "kerze", "lounge"), 40, "#ffb45e"),
                 (("morgen", "früh", "frueh", "aufsteh", "wach"), 60, "#ffd9a0"),
                 (("party", "disco", "farb", "bunt"), 80, "#c070ff"),
                 (("tag", "hell", "arbeit", "putz", "lesen", "voll", "kochen"), 100, "#fff4e0"))
    _SL_WARM = (255, 226, 176)          # Farbe fuer Leuchten ohne Farbinfo (warmweiss)

    @staticmethod
    def _kelvin_rgb(k: float) -> tuple:
        """Farbtemperatur (K) -> RGB (Naeherung nach Tanner Helland)."""
        t = max(1000.0, min(40000.0, float(k))) / 100.0
        r = 255.0 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
        g = (99.4708025861 * math.log(t) - 161.1195681661) if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
        b = 255.0 if t >= 66 else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
        return tuple(int(max(0, min(255, x))) for x in (r, g, b))

    def _lc_light_now(self, c: dict) -> dict | None:
        """Aktuelles Licht einer Lichtsteuerung aus ihren Leuchten:
        b = mittlere Helligkeit aller Leuchten (0-100), c = nach Helligkeit
        gewichtete Mischfarbe. None, wenn keine auswertbare Leuchte da ist."""
        import colorsys
        vals = []
        for sc in (c.get("subControls") or {}).values():
            t = sc.get("type")
            if t in ("Dimmer", "EIBDimmer"):
                try:
                    pos = float(self._state(sc, "position") or 0)
                    mx = float(self._state(sc, "max") or 100) or 100.0
                except (TypeError, ValueError):
                    continue
                vals.append((max(0.0, min(100.0, pos / mx * 100)), self._SL_WARM))
            elif t in ("Switch", "Pushbutton"):
                vals.append((100.0 if self._state(sc, "active") else 0.0, self._SL_WARM))
            elif t in ("Colorpicker", "ColorPickerV2"):
                mode, a, bb, v = self._color_parse(self._state(sc, "color"))
                if mode == "rgb":
                    r, g, b = colorsys.hsv_to_rgb((a % 360) / 360.0, bb / 100.0, 1.0)
                    vals.append((float(v), (int(r * 255), int(g * 255), int(b * 255))))
                elif mode == "temp":
                    vals.append((float(a), self._kelvin_rgb(bb)))
        if not vals:
            return None
        bright = sum(v for v, _ in vals) / len(vals)
        w = sum(v for v, _ in vals)
        if w <= 0:
            return {"b": 0, "c": None}
        rgb = [round(sum(v * col[i] for v, col in vals) / w) for i in range(3)]
        return {"b": round(bright), "c": "#%02x%02x%02x" % tuple(rgb)}

    def _scene_guess(self, name: str) -> dict | None:
        n = (name or "").strip().lower()
        for keys, b, col in self._SL_GUESS:
            if any(k in n for k in keys):
                return {"b": b, "c": col}
        return None

    def _scene_light_learn(self, now: float) -> None:
        for uuid, c in self.controls.items():
            if c.get("type") != "LightControllerV2" or not c.get("subControls"):
                continue
            cu = self._with_uuid(uuid)
            off = LIGHT._off_ids(cu, self.states)
            act = [m for m in LIGHT.active_moods(cu, self.states) if m not in off]
            if len(act) != 1:                    # aus oder mehrere Szenen gemischt
                self._sl_seen.pop(uuid, None)
                continue
            seen = self._sl_seen.get(uuid)
            if not seen or seen[0] != act[0]:
                self._sl_seen[uuid] = [act[0], now, False]
                continue
            if seen[2] or now - seen[1] < 6:     # einmal je Einschalten, nach 6 s
                continue
            seen[2] = True
            val = self._lc_light_now(c)
            if not val:
                continue
            store = self.scene_light.setdefault(uuid, {})
            if store.get(str(act[0])) != val:
                store[str(act[0])] = val
                self._sl_dirty = True
        if self._sl_dirty and now - self._sl_saved > 30:
            self._sl_dirty, self._sl_saved = False, now
            try:
                _atomic_write(SCENE_LIGHT_FILE, json.dumps(self.scene_light, ensure_ascii=False))
            except Exception:
                log.exception("Szenen-Licht nicht gespeichert")

    def _scene_light(self, uuid: str, c: dict, mood: dict, active: list, off: set) -> dict | None:
        """Licht einer Szene fuers Piktogramm: live (aktiv), gelernt, geschaetzt."""
        mid = mood.get("id")
        if mid in off:
            return {"b": 0, "c": None, "k": "live"}
        if mid in active and len([m for m in active if m not in off]) == 1:
            val = self._lc_light_now(c)
            if val:
                return {**val, "k": "live"}
        val = (self.scene_light.get(uuid) or {}).get(str(mid))
        if val:
            return {**val, "k": "learned"}
        g = self._scene_guess(mood.get("name"))
        return {**g, "k": "guess"} if g else None

    def _dim_subs(self, c: dict) -> list:
        """Dimmbare Leuchten (Dimmer) einer Lichtsteuerung."""
        return [sc for sc in (c.get("subControls") or {}).values()
                if sc.get("type") in ("Dimmer", "EIBDimmer") and sc.get("uuidAction")]

    async def _dim_all(self, ua: str, delta: int) -> None:
        """Alle Dimmer einer Lichtsteuerung gemeinsam heller/dunkler (Aktionsreihe
        der Lichtszenen). Ausgeschaltete Leuchten bleiben beim Dunklerstellen aus;
        beim Hellerstellen starten sie bei delta %."""
        c = next((x for x in self.controls.values() if x.get("uuidAction") == ua), None)
        if not c:
            return
        for sc in self._dim_subs(c):
            try:
                pos = float(self._state(sc, "position") or 0)
            except (TypeError, ValueError):
                pos = 0.0
            if pos <= 0 and delta < 0:
                continue
            new = max(0, min(100, round((pos + delta) / 10) * 10))
            await self.command(sc["uuidAction"], str(new))

    def _view_control_inner(self, uuid: str) -> dict:
        """Duenner Wrapper um _view_control_body: haengt die Kategoriefarbe
        (falls gesetzt) einmalig zentral an JEDE Detailansicht an, statt sie
        einzeln in jeden der vielen 'hero'-Bloecke unten einzutragen. Client
        faerbt damit den Icon-Kreis passend zur Kategorie (an die Loxone-TPD-
        Optik angelehnt: farbige Icon-Kreise statt neutralem Grau)."""
        r = self._view_control_body(uuid)
        cc = self._cat_color(self.controls.get(uuid, {}).get("cat"))
        if cc and isinstance(r, dict) and "blocks" in r:
            r["catColor"] = cc
        return r

    def _view_control_body(self, uuid: str) -> dict:
        c = self.controls.get(uuid, {})
        t = c.get("type")
        route = {"view": "control", "id": uuid}
        if t == "SystemScheme":
            return self._view_scheme(uuid, c, route)
        if t == "LightControllerV2":
            cu = self._with_uuid(uuid)
            active = LIGHT.active_moods(cu, self.states)
            _off = LIGHT._off_ids(cu, self.states)
            items = [{"id": f"{uuid}:{m.get('id')}", "label": m.get("name", str(m.get("id"))),
                      "on": m.get("id") in active, "icon": "mood",
                      "light": self._scene_light(uuid, c, m, active, _off),   # Szenen-Licht (Option am Panel)
                      "cmd": {"uuid": c.get("uuidAction"), "cmd": f"changeTo/{m.get('id')}"}}
                     for m in LIGHT.moods(cu, self.states)]
            r = LIGHT.render(cu, self.states)
            # Aktionsreihe nur mit dem, was der Baustein kann: "Aus" (es gibt eine
            # Aus-Szene) und heller/dunkler (es gibt dimmbare Leuchten; setzt alle
            # gemeinsam um 10 %, siehe command() "__dimall").
            off_ids = LIGHT._off_ids(cu, self.states)
            cells = []
            if any(m.get("id") in off_ids for m in LIGHT.moods(cu, self.states)) or 778 in off_ids:
                off_id = next((m.get("id") for m in LIGHT.moods(cu, self.states) if m.get("id") in off_ids), 778)
                cells.append({"icon": "power", "plain": True,
                              "cmd": {"uuid": c.get("uuidAction"), "cmd": f"changeTo/{off_id}"}})
            if self._dim_subs(c):
                cells += [{"icon": "minus", "cmd": {"uuid": c.get("uuidAction"), "cmd": "__dimall/-10"}},
                          {"icon": "plus", "cmd": {"uuid": c.get("uuidAction"), "cmd": "__dimall/10"}}]
            # Aus-Szene steht schon in der Aktionsreihe -> nicht doppelt als Kachel
            scenes = [i for i in items if not (cells and cells[0].get("icon") == "power"
                                               and i["cmd"]["cmd"] == cells[0]["cmd"]["cmd"])]
            # Detail-Schema fuer Auswahlbausteine: Zustand EINZEILIG ("An · Tag / viel Licht"),
            # damit die Szenenliste Platz hat. Aus-Stimmung steht nur im Aus-Knopf, nie in der Liste;
            # bei Licht aus nennt die Zeile ihren Namen (ausser er lautet selbst "Aus").
            extra = r["label"] if r["on"] else ""
            if not r["on"]:
                _an = next((str(m.get("name") or "") for m in LIGHT.moods(cu, self.states)
                            if m.get("id") in active and m.get("id") in _off), "")
                if _an and _an.strip().lower() != "aus":
                    extra = _an
            blocks = [{"k": "big", "text": "An" if r["on"] else "Aus", "tone": "", "line": True, "extra": extra}]
            blocks.append({"k": "scenes", "items": scenes})
            if cells:
                blocks.append({"k": "row", "act": True, "cells": cells})
            return {"t": "view", "title": _clean(c.get("name")), "subtitle": r["label"],
                    "route": route, "anchor": "bottom", "blocks": blocks}
        if t == "Radio":
            ua = c.get("uuidAction")
            det = c.get("details") or {}
            outs = det.get("outputs") or {}
            ao = int(self._state(c, "activeOutput") or 0)
            items = []
            if det.get("allOff"):
                items.append({"id": f"{uuid}:0", "label": det["allOff"], "on": ao == 0,
                              "icon": "stop", "cmd": {"uuid": ua, "cmd": "reset"}})
            for k in sorted(outs, key=lambda x: int(x)):
                items.append({"id": f"{uuid}:{k}", "label": outs[k], "on": ao == int(k),
                              "icon": "mood", "cmd": {"uuid": ua, "cmd": str(k)}})
            # Wie die Lichtszenen: grosse Auswahl-Kacheln 2x2, aktive dunkel.
            cur = next((i["label"] for i in items if i["on"]), "")
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom",
                    "blocks": ([{"k": "status", "text": cur}] if cur else []) + [{"k": "scenes", "items": items}]}
        if t == "LightController":
            ua = c.get("uuidAction")
            scenes = self._lc_scenes(c)
            asc = int(self._state(c, "activeScene") or 0)
            items = [{"id": f"{uuid}:0", "label": "Aus", "on": asc == 0, "icon": "stop",
                      "cmd": {"uuid": ua, "cmd": "0"}}]
            for sid in sorted(scenes):
                items.append({"id": f"{uuid}:{sid}", "label": scenes[sid], "on": asc == sid,
                              "icon": "mood", "cmd": {"uuid": ua, "cmd": str(sid)}})
            # Gleiches Detail-Schema wie LightControllerV2: Zustand gross, aktive
            # Szene klein, Szenen als Eintraege (Befehle unveraendert)
            cur = next((i["label"] for i in items if i["on"]), "")
            blocks = [{"k": "big", "text": "Aus" if asc == 0 else "An", "tone": ""}]
            if asc != 0 and cur:
                blocks.append({"k": "status", "text": "Szene: " + cur})
            blocks.append({"k": "scenes", "items": items})
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "WindowMonitor":
            windows = (c.get("details") or {}).get("windows") or []
            codes = [x for x in str(self._state(c, "windowStates") or "").split(",") if x != ""]

            def wtext(b):
                return ("offen" if b & 4 else "gekippt" if b & 2 else "offline" if b & 32
                        else "verriegelt" if b & 8 else "geschlossen" if b & 1 else "–")

            items = []
            for i, w in enumerate(windows):
                try:
                    b = int(float(codes[i])) if i < len(codes) else 0
                except (ValueError, TypeError):
                    b = 0
                ent = {"id": f"{uuid}:{i}", "icon": "blind", "on": bool(b & 6),
                       "label": _clean(w.get("name") or f"Fenster {i + 1}"),
                       "val": wtext(b), "_r": 0 if b & 4 else (1 if b & 2 else 2)}
                # Nur der Raum (Loxone: window.room = Raum-UUID), sonst der Einbauort
                ent["room"] = (_clean((self.rooms.get(w.get("room")) or {}).get("name")) if w.get("room") else "") \
                    or _clean(w.get("installPlace"))
                items.append(ent)
            # Offene zuerst, dann gekippte, dann der Rest (sonst Loxone-Reihenfolge)
            items.sort(key=lambda x: x.pop("_r"))
            # Detail-Schema: grosser Wert, Zeile darunter, Fenster als reine Anzeige-Zeilen
            n_open = sum(1 for x in items if x["val"] == "offen")
            n_tilt = sum(1 for x in items if x["val"] == "gekippt")
            big = f"{n_open} offen" if n_open else ("Alle geschlossen" if not n_tilt else f"{n_tilt} gekippt")
            sub = " · ".join(x for x in (f"{n_tilt} gekippt" if n_open and n_tilt else "",
                                          f"{len(items)} Fenster") if x)
            # val = Zustandswort rechts in der Zeile, vb = hervorgehoben (offen/gekippt)
            rows = [{"id": x["id"], "label": x["label"], "icon": "window", "on": x["on"],
                     "sub": x.get("room", ""), "val": x["val"], "vb": x["on"]} for x in items]
            blocks = [{"k": "big", "text": big}, {"k": "status", "text": sub}]
            if rows:
                blocks.append({"k": "scenes", "items": rows})
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "blocks": blocks}
        if t == "Jalousie":
            ua = c.get("uuidAction")
            cu = self._with_uuid(uuid)
            s = c.get("states") or {}
            up_move = bool(self.states.get(s.get("up")))
            down_move = bool(self.states.get(s.get("down")))
            moving = up_move or down_move
            pct = JAL.render(cu, self.states).get("pct")
            base = "–" if pct is None else ("Offen" if pct <= 0 else
                                            ("Geschlossen" if pct >= 100 else f"{pct}% geschlossen"))
            # Gleiche Formulierung wie auf der Kachel (_control_item), damit
            # Kachel und Detailansicht dasselbe sagen.
            val = ("▲ öffnet · " + base) if up_move else (("▼ schließt · " + base) if down_move else base)
            # Wie Original-Visu: kein Stop-Button. Tipp auf die Richtung waehrend der
            # Fahrt sendet Stop (haelt an); im Stand startet er die Fahrt.
            auf = {"label": "Auf", "on": up_move, "cmd": {"uuid": ua, "cmd": "Stop" if moving else "Up"}}
            ab = {"label": "Ab", "on": down_move, "cmd": {"uuid": ua, "cmd": "Stop" if moving else "Down"}}
            # Detail-Schema: grosse Stellung (Auf/Ab als runde Knoepfe daneben),
            # Loxone-Text darunter, Aktionspillen unten.
            blocks = [
                {"k": "shade", "pct": pct, "up": auf, "down": ab},
                {"k": "status", "text": " · ".join(x for x in (self._jal_status(cu), val) if x)},
                {"k": "row", "act": True, "cells": [
                    {"label": "Ganz auf", "cmd": {"uuid": ua, "cmd": "FullUp"}},
                    {"label": "Beschatten", "cmd": {"uuid": ua, "cmd": "shade"}},
                    {"label": "Ganz ab", "cmd": {"uuid": ua, "cmd": "FullDown"}},
                ]},
            ]
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "AudioZone":
            ua = c.get("uuidAction")
            playing = self._state(c, "playState") == 2
            title = self._song(c) or "Radio"
            sub = self._text(c, "artist") or self._text(c, "album")
            vol = int(self._state(c, "volume") or 0)
            cover = self._state(c, "cover")
            blocks = []
            if cover:
                blocks.append({"k": "cover", "src": "/cover?u=" + quote(str(cover), safe="")})
            blocks += [
                {"k": "title", "text": title, "sub": sub},
                {"k": "row", "cells": [
                    {"icon": "prev", "cmd": {"uuid": ua, "cmd": "queueminus"}},
                    {"icon": "pause" if playing else "play", "big": True,
                     "cmd": {"uuid": ua, "cmd": "pause" if playing else "play"}},
                    {"icon": "next", "cmd": {"uuid": ua, "cmd": "queueplus"}},
                ]},
                {"k": "slider", "icon": "vol", "value": vol, "min": 0, "max": 100,
                 "cmd": {"uuid": ua, "tmpl": "volume/{v}"}},
            ]
            # Quellen (Radio/Playlist/Spotify) immer auf Unterseite erreichbar
            # (Favoriten werden dort per prime_favs frisch angefordert).
            blocks.append({"k": "more", "route": {"view": "sources", "id": uuid}})
            # Bedienleiste (Transport + Lautstaerke) unten andocken; Cover/Titel
            # oben zentriert. Ohne laufende Musik rutscht so nichts nach oben.
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "AudioZoneV2":
            ua = c.get("uuidAction")
            playing = self._state(c, "playState") == 2
            title = self._song(c)
            sub = self._text(c, "artist") or self._text(c, "album")
            vol = int(self._state(c, "volume") or 0)
            cover = self._state(c, "cover")
            # Sonn/Audioserver4Home reicht Track-Metadaten NICHT ueber das
            # Loxone-Protokoll durch -> per Namensabgleich aus der Sonn-API
            # ergaenzen (nur wo Loxone leer ist).
            sm = self._sonn_for(c)
            if sm:
                playing = playing or bool(sm.get("playing"))
                title = title or sm.get("title") or ""
                sub = sub or sm.get("artist") or sm.get("album") or ""
                cover = cover or sm.get("cover")
                if not vol and sm.get("volume") is not None:
                    try:
                        vol = int(sm.get("volume"))
                    except (TypeError, ValueError):
                        pass
            # Dynamisches Song-Cover: Der Audioserver (Sonn) liefert bei Radio oft
            # nur das Sender-Logo. Laeuft ein echter Titel, das passende Album-
            # Cover (iTunes) nachschlagen und statt des Logos zeigen. Bei
            # Wortbeitraegen (kein Treffer) bleibt das Sender-Logo.
            art = (self._text(c, "artist") or (sm.get("artist") if sm else "") or "").strip()
            if playing and title and art:
                dyn = self._song_cover(art, title)
                if dyn:
                    blocks_cover_dyn = dyn
                    cover = None  # dyn ist bereits eine fertige /cover-URL
                else:
                    blocks_cover_dyn = None
            else:
                blocks_cover_dyn = None
            if not title:
                title = "Spielt" if playing else "Aus"
            blocks = []
            if blocks_cover_dyn:
                blocks.append({"k": "cover", "src": blocks_cover_dyn})
            elif cover:
                blocks.append({"k": "cover", "src": "/cover?u=" + quote(str(cover), safe="")})
            else:
                blocks.append({"k": "hero", "icon": "music"})
            blocks += [
                {"k": "title", "text": title, "sub": sub},
                {"k": "row", "cells": [
                    {"icon": "prev", "cmd": {"uuid": ua, "cmd": "prev"}},
                    {"icon": "pause" if playing else "play", "big": True,
                     "cmd": {"uuid": ua, "cmd": "pause" if playing else "play"}},
                    {"icon": "next", "cmd": {"uuid": ua, "cmd": "next"}},
                ]},
                {"k": "slider", "icon": "vol", "value": vol, "min": 0, "max": 100,
                 "cmd": {"uuid": ua, "tmpl": "volume/{v}"}},
            ]
            # 3-Punkte -> Quellen/Favoriten (Sonn via API, sonst Loxone-roomfav)
            blocks.append({"k": "more", "route": {"view": "sources", "id": uuid}})
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "Pushbutton":
            ua = c.get("uuidAction")
            hist = self.push_hist.get(uuid) or []
            blocks = []
            if hist:
                h0 = hist[0]
                # Grosser Wert = letzte Ausloesung, darunter Tag + Ergebnis
                # ("small": Hinweis an den Client fuer kleinere Schrift, wo unterstuetzt)
                blocks += [{"k": "big", "text": "Zuletzt ausgelöst", "small": True},
                           {"k": "status", "text": self._push_day(h0["ts"]) + " " + self._push_time(h0["ts"])
                            + ("" if h0.get("ok", True) else " · nicht erfolgreich")}]
                # Die letzten Ausloesungen als reine Anzeige-Zeilen (kein Befehl)
                blocks.append({"k": "scenes", "items": [{
                    "id": f"{uuid}:h{i}", "icon": "check" if h.get("ok", True) else "fail",
                    "label": self._push_day(h["ts"]) + " " + self._push_time(h["ts"]),
                    "sub": ("erfolgreich" if h.get("ok", True) else "nicht erfolgreich") + " · " + (h.get("src") or "Loxone"),
                    "on": not h.get("ok", True)} for i, h in enumerate(hist)]})
            else:
                blocks += [{"k": "state", "icon": "switch", "tone": "idle", "text": "Bereit",
                            "sub": "Noch keine Auslösung erfasst"}]
            blocks.append({"k": "row", "act": True, "cells": [{"label": "Auslösen", "cmd": {"uuid": ua, "cmd": "pulse"}}]})
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t in SWITCHY:
            ua = c.get("uuidAction")
            on = bool(self._state(c, "active"))
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": [
                {"k": "hero", "icon": "switch"},
                {"k": "big", "text": "Ein" if on else "Aus"},
                {"k": "row", "act": True, "cells": [
                    {"label": "Ein", "on": on, "cmd": {"uuid": ua, "cmd": "on"}},
                    {"label": "Aus", "on": not on, "cmd": {"uuid": ua, "cmd": "off"}},
                ]},
            ]}
        if t == "TimedSwitch":
            ua = c.get("uuidAction")
            dd = self._state(c, "deactivationDelay")
            try:
                dd = float(dd if dd is not None else 0)
            except (TypeError, ValueError):
                dd = 0.0
            on = dd != 0
            # Gross wie beim Schalter nur "Ein"/"Aus", die Restzeit darunter
            if dd > 0:
                sub = "läuft noch %d:%02d" % (int(dd) // 60, int(dd) % 60)
            elif dd < 0:
                sub = "dauerhaft eingeschaltet"
            else:
                sub = ""
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": [
                {"k": "hero", "icon": "bulb"},
                {"k": "big", "text": "Ein" if on else "Aus"},
                *([{"k": "status", "text": sub}] if sub else []),
                {"k": "row", "act": True, "cells": [
                    {"label": "Ein", "on": on, "cmd": {"uuid": ua, "cmd": "pulse"}},
                    {"label": "Aus", "on": not on, "cmd": {"uuid": ua, "cmd": "off"}},
                ]},
            ]}
        if t == "Gate":
            ua = c.get("uuidAction")
            pct = round((self._state(c, "position") or 0) * 100)
            active = self._state(c, "active") or 0
            moving = active != 0
            # Wie die Beschattung: oben oeffnen, Mitte Stellung (Fuellstand von
            # unten = offen), unten schliessen. Tippen waehrend der Fahrt stoppt.
            up = {"label": "Öffnen", "on": active > 0, "cmd": {"uuid": ua, "cmd": "stop" if moving else "open"}}
            dn = {"label": "Schließen", "on": active < 0, "cmd": {"uuid": ua, "cmd": "stop" if moving else "close"}}
            status = "öffnet …" if active > 0 else ("schließt …" if active < 0 else
                                                   ("Offen" if pct >= 100 else ("Geschlossen" if pct <= 0 else "Teilweise offen")))
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom", "blocks": [
                {"k": "shade", "pct": pct, "dir": "open", "up": up, "down": dn},
                {"k": "status", "text": status},
                {"k": "row", "act": True, "cells": [{"label": "Stopp", "cmd": {"uuid": ua, "cmd": "stop"}}]},
            ]}
        if t == "IRoomControllerV2":
            ua = c.get("uuidAction")
            ta = self._fmt_num(self._state(c, "tempActual"), "%.1f")
            tt = self._fmt_num(self._state(c, "tempTarget"), "%.1f")
            try:
                comfort = float(self._state(c, "comfortTemperature")
                                or self._state(c, "tempTarget") or 20)
            except (TypeError, ValueError):
                comfort = 20.0
            modes = self._irc_modes(c)
            am = self._state(c, "activeMode")
            try:
                am = int(am) if am is not None else None
            except (TypeError, ValueError):
                am = None
            art, manuell = self._irc_betriebsart(c)
            prep = self._state(c, "prepareState")
            kc = self._fmt_num(self._state(c, "comfortTemperature"), "%.1f")
            # Detail-Schema: Ist-Temperatur gross (Farbton heizt/kuehlt von Loxone)
            # mit -/+ (Komfort in 0,5er-Schritten), darunter eine Textzeile + Betriebsart-
            # Chip (_irc_top), Tagesplan als Zeitleiste (nur wenn Loxone ihn liefert),
            # unten die Modi als 1-h-Override.
            zustand = modes.get(am) if am is not None else ""
            blocks = self._irc_top(
                ta, prep, tt, kc, "Komfort", _kurz_modus(zustand), art, self._state(c, "openWindow"),
                {"uuid": ua, "cmd": f"setComfortTemperature/{comfort - 0.5:.1f}"},
                {"uuid": ua, "cmd": f"setComfortTemperature/{comfort + 0.5:.1f}"})
            plan = self._irc_schedule(c, modes)
            if plan and plan["segs"]:
                blocks.append({"k": "tline", **plan})
            # Betriebsmodi in EINER Zeile: Temperatur-Modi (Eco/Komfort) als
            # 1-h-Override + Automatik (zurueck zur Zeitschaltung). Namen aus MS
            # (details.timerModes). Gebaeudeschutz wird ausgelassen (aufgeraeumt).
            if modes:
                cells = [{"label": _kurz_modus(nm), "on": (mid == am),
                          "cmd": {"uuid": ua, "cmd": f"override/{mid}"}}
                         for mid, nm in sorted(modes.items())
                         if "schutz" not in (nm or "").lower()]
                cells.append({"label": "Auto",
                              "cmd": {"uuid": ua, "cmd": "stopOverride"}})
                blocks.append({"k": "row", "cells": cells})
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "IRoomController":
            # Alte Raumregelung (v1), Befehle laut Loxone-Strukturdoku:
            # settemp/<Nr>/<Wert>, starttimer/<Nr>/<Sekunden>, stoptimer.
            ua = c.get("uuidAction")
            z = self._irc1(c)
            art, manuell = self._irc_betriebsart(c)
            ta = self._fmt_num(self._state(c, "tempActual"), "%.1f")
            tt = self._fmt_num(self._state(c, "tempTarget"), "%.1f")
            # Detail-Schema wie beim V2 (kein Tagesplan: die alte Raumregelung
            # liefert keinen). Zustand = aktuelle Temperatur (Eco, Komfort ...),
            # bei manueller Betriebsart steht sie schon in der Betriebsart-Pille.
            zustand = z["name"] if z["name"] and not (manuell and z["ix"] == IRC1_MANUELL) else ""
            # -/+ verstellt Komfort der Periode (manuell: die manuelle
            # Temperatur) - nur mit bekanntem, absolutem Wert.
            minus = plus = None
            soll, soll_label = "", "Komfort"
            if z["stell"] is not None:
                ix, v = z["stell_ix"], z["stell"]
                soll = self._fmt_num(v, "%.1f")
                soll_label = "Manuell" if ix == IRC1_MANUELL else "Komfort"
                minus = {"uuid": ua, "cmd": f"settemp/{ix}/{v - 0.5:.1f}"}
                plus = {"uuid": ua, "cmd": f"settemp/{ix}/{v + 0.5:.1f}"}
            blocks = self._irc_top(ta, z["prep"], tt, soll, soll_label, zustand, art,
                                   self._state(c, "openWindow"), minus, plus)
            # Eco/Komfort fuer eine Stunde halten, Automatik beendet den Timer.
            blocks.append({"k": "row", "cells": [
                {"label": IRC1_TEMPS[IRC1_ECO], "on": z["ix"] == IRC1_ECO,
                 "cmd": {"uuid": ua, "cmd": f"starttimer/{IRC1_ECO}/{IRC1_TIMER_S}"}},
                {"label": "Komfort", "on": z["ix"] == z["komfort_ix"],
                 "cmd": {"uuid": ua, "cmd": f"starttimer/{z['komfort_ix']}/{IRC1_TIMER_S}"}},
                {"label": "Automatik", "cmd": {"uuid": ua, "cmd": "stoptimer"}},
            ]})
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "Intercom":
            ent = self.intercom_cfg.get(uuid)
            has_url = bool(ent.get("url") if isinstance(ent, dict) else ent)
            subs = c.get("subControls") or {}
            cells = [{"label": _clean(sc.get("name")),
                      "cmd": {"uuid": sc.get("uuidAction"), "cmd": "pulse"}}
                     for sc in subs.values()]
            # Livebild fuellt die Karte, Klingel-Hinweis im Bild; Tuer-Knoepfe
            # in der Aktionsreihe (einfacher Tipp).
            bell = bool(self._state(c, "bell"))
            blocks = [{"k": "video", "src": f"/mjpeg?id={quote(uuid)}", "bell": bell,
                       "reconnectH": self._cam_reconnect_h(uuid)}] if has_url else \
                     [{"k": "state", "icon": "cam", "tone": "crit" if bell else "idle",
                       "text": "Es klingelt" if bell else "Kein Video", "sub": "" if bell else "Video-URL unter System → Kameras eintragen"}]
            if cells:
                blocks.append({"k": "row", "act": True, "cells": cells[:4]})
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom", "blocks": blocks}
        if t == "Tracker":
            lines = self._tracker_lines(c)
            if not lines:
                # Hinweis statt Riesenschrift: dezente Zustandsflaeche
                return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom",
                        "blocks": [{"k": "state", "icon": "list", "tone": "idle", "text": "Keine Einträge",
                                    "sub": "Hier erscheinen die Meldungen des Bausteins"}]}
            rows = []
            for ln in lines:
                ts, txt = self._split_ts(ln)
                rows.append({"t": _short_ts(ts), "text": txt})
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom",
                    "blocks": [{"k": "log", "rows": rows}]}
        # --- Status-Bausteine: grosse 1/1-Wertseite ---
        if t == "Meter":
            det = c.get("details") or {}
            a = self._fmt_num(self._state(c, "actual"), det.get("actualFormat", "%.1f"))
            tot = self._fmt_num(self._state(c, "total"), det.get("totalFormat", "%.1f"))
            return self._big_view(uuid, "info", a or "–", (tot + " gesamt") if tot else "")
        if t == "Slider":
            ua = c.get("uuidAction")
            det = c.get("details") or {}
            fmt = det.get("format", "%.1f")

            def _f(key, dflt):
                try:
                    return float(det.get(key, dflt))
                except (TypeError, ValueError):
                    return float(dflt)

            def _n(x):   # ganzzahlig darstellen, wenn ohne Nachkommastelle
                return int(x) if float(x).is_integer() else x
            mn, mx = _f("min", 0), _f("max", 100)
            stp = _f("step", 1) or 1
            val = self._state(c, "value")
            try:
                cur = float(val)
            except (TypeError, ValueError):
                cur = mn
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "blocks": [
                {"k": "hero", "icon": "info"},
                {"k": "big", "text": self._fmt_num(val, fmt) or "–"},
                {"k": "slider", "icon": "vol", "value": _n(cur), "min": _n(mn),
                 "max": _n(mx), "step": _n(stp), "cmd": {"uuid": ua, "tmpl": "{v}"}},
            ]}
        if t == "InfoOnlyAnalog":
            det = c.get("details") or {}
            # Zahl mit Einheit gross; liefert Loxone zusaetzlich einen Text, steht der klein darunter
            return self._big_view(uuid, "info",
                                  self._fmt_num(self._state(c, "value"), det.get("format", "%.1f")) or "–",
                                  self._text(c, "textAndIcon") or self._text(c, "text"))
        if t in ("TextState", "InfoOnlyText"):
            return self._big_view(uuid, "info",
                                  str(self._state(c, "textAndIcon") or self._state(c, "text") or "–"))
        if t == "InfoOnlyDigital":
            on = bool(self._state(c, "active"))
            tx = (c.get("details") or {}).get("text") or {}
            return self._big_view(uuid, "info",
                                  (tx.get("on") if on else tx.get("off")) or ("Ein" if on else "Aus"))
        if t == "SmokeAlarm":
            ok = (self._state(c, "level") or 0) == 0
            if ok:
                return self._big_view(uuid, "alarm", "Kein Alarm", tone="good")
            ua = c.get("uuidAction")
            cause = self._text(c, "alarmCause")
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom", "blocks": [
                {"k": "state", "icon": "alarm", "tone": "crit", "text": "Alarm", "sub": cause or "Melder ausgelöst"},
                {"k": "row", "act": True, "cells": [
                    {"label": "Stumm", "cmd": {"uuid": ua, "cmd": "mute"}},
                    {"label": "Quittieren", "cmd": {"uuid": ua, "cmd": "confirm"}}]},
            ]}
        if t == "AalEmergency":
            stt = self._state(c, "status") or 0
            return self._big_view(uuid, "alarm", "Notruf ausgelöst" if stt else "Kein Notruf",
                                  tone=("crit" if stt else "good"))
        if t == "NfcCodeTouch":
            who = self._text(c, "lastuser") or self._text(c, "lasttag") or ""
            if not who:
                return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom",
                        "blocks": [{"k": "state", "icon": "info", "tone": "idle", "text": "Noch kein Zutritt",
                                    "sub": "Hier erscheint, wer zuletzt Zutritt hatte"}]}
            return self._big_view(uuid, "info", who, "Letzter Zutritt")
        if t == "PulseAt":
            stv = self._state(c, "startTime")
            try:
                sec = int(float(stv)) % 86400
                nxt = "%02d:%02d" % (sec // 3600, (sec % 3600) // 60)
            except (TypeError, ValueError):
                nxt = "–"
            return self._big_view(uuid, "info", nxt, "Nächster Impuls" + ("" if self._state(c, "isActive") else " · inaktiv"))
        if t == "PresenceDetector":
            on = bool(self._state(c, "active"))
            itxt = self._text(c, "infoText")
            if itxt:
                itxt = _presence_de(itxt)
            # Zustand gross, der Loxone-Text (z. B. Luftqualitaet) klein darunter
            sub = itxt if (itxt and itxt.lower() not in ("an", "aus")) else ""
            return self._big_view(uuid, "info", "Anwesend" if on else "Abwesend", sub)
        if t == "Alarm":
            ua = c.get("uuidAction")
            armed = bool(self._state(c, "armed"))
            lvl = self._state(c, "level") or 0
            delay = self._state(c, "armedDelay") or 0
            if lvl:
                st = {"k": "state", "icon": "alarm", "tone": "crit", "text": "Alarm", "sub": "Alarm ausgelöst"}
                cells = [{"label": "Quittieren", "cmd": {"uuid": ua, "cmd": "quit"}},
                         {"label": "Unscharf", "cmd": {"uuid": ua, "cmd": "off"}}]
            else:
                st = {"k": "state", "icon": "shield", "tone": "good" if armed else "idle",
                      "text": "Scharf" if armed else ("Wird scharf" if delay else "Unscharf"),
                      "sub": "Alle Melder überwacht" if armed else ("Verzögerung läuft" if delay else "Bereit zum Scharfschalten")}
                # Aktueller Zustand dunkel hinterlegt (wie die Modi der Heizung)
                cells = [{"label": "Scharf", "on": armed, "cmd": {"uuid": ua, "cmd": "on"}},
                         {"label": "Verzögert", "on": bool(delay) and not armed, "cmd": {"uuid": ua, "cmd": "delayedon"}},
                         {"label": "Unscharf", "on": not armed and not delay, "cmd": {"uuid": ua, "cmd": "off"}}]
            # Kopf = Raum + Name (_with_head); der Zustand steht als grosser Wert, nicht als Titel
            big = {"k": "big", "text": st["text"]}
            if st["tone"] in ("good", "crit"):
                big["tone"] = st["tone"]
            blocks = [big] + ([{"k": "status", "text": st["sub"]}] if st.get("sub") else [])
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom",
                    "blocks": blocks + [{"k": "row", "act": True, "cells": cells}]}
        if t == "AlarmClock":
            ua = c.get("uuidAction")
            ringing = bool(self._state(c, "isAlarmActive"))
            nxt = self._alarm_next_text(c)
            entries = self._alarm_entries(c)
            if ringing:
                return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom", "blocks": [
                    {"k": "state", "icon": "alarm", "tone": "crit", "text": "Weckt", "sub": nxt or ""},
                    {"k": "row", "act": True, "cells": [
                        {"label": "Schlummern", "cmd": {"uuid": ua, "cmd": "snooze"}},
                        {"label": "Aus", "cmd": {"uuid": ua, "cmd": "dismiss"}}]}]}
            # Eintraege als Kacheln (wie Lichtszenen); Antippen oeffnet die Bearbeitung.
            # Hervorgehoben (on) ist nur der Eintrag, auf den der grosse Wert zeigt
            # (= naechste Weckzeit aus nextEntryTime); aktive, aber nicht naechste
            # Eintraege bleiben normal, deaktivierte tragen "aus" in der Zeile.
            nhm = nxt[-5:] if nxt else ""
            nxt_id = next((e["id"] for e in entries if e["active"] and e["hm"] == nhm), None)

            def _sub(e):
                bits = [e["name"], e["repeat"]] + ([] if e["active"] else ["aus"])
                return " · ".join(x for x in bits if x)
            items = [{"id": f"{uuid}:{e['id']}", "label": e["hm"], "sub": _sub(e),
                      "on": e["id"] == nxt_id, "icon": "alarm",
                      "nav": {"view": "control", "id": uuid, "entry": e["id"]}} for e in entries]
            # Ueberschrift passend zum Loxone-Zustand: ohne naechste Weckzeit "Wecker"
            blocks = [{"k": "big", "text": nxt or "Kein Wecker aktiv"},
                      {"k": "status", "text": "Nächster Wecker" if nxt else "Wecker"}]
            if items:
                blocks.append({"k": "scenes", "items": items})
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom", "blocks": blocks}
        if t == "Daytimer":
            ua = c.get("uuidAction")
            ov = bool(self._state(c, "override"))
            mode = self._daytimer_mode(c)
            sub = ("Timer läuft · " + mode) if (ov and mode) else ("Timer läuft" if ov else mode)
            hero = {"k": "hero", "icon": "info"}
            iu = self._control_icon_url(c)
            if iu:
                hero["iconUrl"] = iu
            blocks = [hero, {"k": "astat", "text": self._daytimer_value(c), "sub": sub}]
            # Laeuft ein manueller Timer (override), kann er beendet werden
            # (stopOverride). Sonst 4 feste Dauern zum Starten: startOverride/
            # {value}/{sekunden} — value=1 (einschalten) fuer die gewaehlte Zeit.
            if ov:
                blocks.append({"k": "row", "cells": [
                    {"label": "Timer beenden", "cmd": {"uuid": ua, "cmd": "stopOverride"}}]})
            else:
                blocks.append({"k": "row", "wrap": True, "cells": [
                    {"label": "15 min", "cmd": {"uuid": ua, "cmd": "startOverride/1/900"}},
                    {"label": "30 min", "cmd": {"uuid": ua, "cmd": "startOverride/1/1800"}},
                    {"label": "60 min", "cmd": {"uuid": ua, "cmd": "startOverride/1/3600"}},
                    {"label": "90 min", "cmd": {"uuid": ua, "cmd": "startOverride/1/5400"}},
                ]})
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t in ("Dimmer", "EIBDimmer"):
            ua = c.get("uuidAction")
            pos = self._state(c, "position") or 0
            mn = self._state(c, "min"); mx = self._state(c, "max"); stp = self._state(c, "step")
            mn = 0 if mn is None else mn
            mx = 100 if mx is None else mx
            stp = stp if isinstance(stp, (int, float)) and stp else 1
            # Karte = Regler (Mockup): fuellt sich von unten bis zur Helligkeit,
            # grosse Zahl, Ziehen stellt ein; - / + in 10er-Schritten.
            step10 = max(stp, 10)
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": [
                {"k": "dim", "value": round(pos), "min": round(mn), "max": round(mx), "step": stp,
                 "cmd": {"uuid": ua, "tmpl": "{v}"}},
                {"k": "row", "act": True, "cells": [
                    {"icon": "power", "plain": True, "cmd": {"uuid": ua, "cmd": "off"}},
                    {"icon": "minus", "cmd": {"uuid": ua, "cmd": str(max(mn, round(pos) - step10))}},
                    {"icon": "plus", "cmd": {"uuid": ua, "cmd": str(min(mx, round(pos) + step10))}},
                    {"label": f"{round(mx)} %", "cmd": {"uuid": ua, "cmd": "on"}}]},
            ]}
        if t == "ValueSelector":
            ua = c.get("uuidAction")
            det = c.get("details") or {}
            val = self._state(c, "value") or 0
            mn = self._state(c, "min"); mx = self._state(c, "max"); stp = self._state(c, "step")
            mn = 0 if mn is None else mn
            mx = 100 if mx is None else mx
            stp = stp if isinstance(stp, (int, float)) and stp else 1
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": [
                {"k": "hero", "icon": "switch"},
                {"k": "big", "text": self._fmt_num(val, det.get("format") or "%.1f")},
                {"k": "slider", "icon": "vol", "value": val, "min": mn,
                 "max": mx, "step": stp, "cmd": {"uuid": ua, "tmpl": "{v}"}},
            ]}
        if t == "Window":
            ua = c.get("uuidAction")
            pct = round((self._state(c, "position") or 0) * 100)
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": [
                {"k": "hero", "icon": "blind"},
                {"k": "big", "text": f"{pct}%"},
                {"k": "slider", "icon": "blind", "value": pct, "min": 0, "max": 100, "step": 1,
                 "cmd": {"uuid": ua, "tmpl": "moveToPosition/{v}"}},
                {"k": "row", "cells": [
                    {"label": "Zu", "cmd": {"uuid": ua, "cmd": "fullclose"}},
                    {"label": "Auf", "cmd": {"uuid": ua, "cmd": "fullopen"}}]},
            ]}
        if t == "Ventilation":
            det = c.get("details") or {}
            spd = self._state(c, "speed") or 0
            am = self._state(c, "activeMode")
            mode = next((_clean(m.get("name")) for m in (det.get("modes") or [])
                         if isinstance(m, dict) and str(m.get("id")) == str(am)), "")
            bits = [mode] if mode else []
            aq = self._state(c, "airQualityIndoor")
            if det.get("hasAirQuality") and aq is not None:
                bits.append(f"Luftqualität {self._fmt_num(aq, '%.0f ppm')}")
            hu = self._state(c, "humidityIndoor")
            if det.get("hasIndoorHumidity") and hu is not None:
                bits.append(f"Feuchte {self._fmt_num(hu, '%.0f %%')}")
            # Stufe wie beim Dimmer als Flaeche. Nur Anzeige: die Stell-Befehle
            # dieses Bausteins sind noch nicht an einer echten Anlage geprueft.
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "anchor": "bottom", "blocks": [
                *([{"k": "status", "text": " · ".join(bits)}] if bits else []),
                {"k": "dim", "value": round(spd), "min": 0, "max": 100, "step": 1, "unit": " %", "ro": True,
                 "cap": "Lüfterstufe", "cmd": {"uuid": c.get("uuidAction"), "tmpl": ""}},
            ]}
        if t == "UpDownAnalog":
            det = c.get("details") or {}
            return self._big_view(uuid, "switch",
                                  self._fmt_num(self._state(c, "value"), det.get("format", "%.1f")) or "–")
        if t == "TextInput":
            return self._big_view(uuid, "info", str(self._state(c, "text") or "–"))
        if t == "Fronius":
            prod = self._state(c, "prodCurr")
            rows = []
            for nm, lbl, unit in (("consCurr", "Verbrauch", "%.2fkW"),
                                  ("prodCurrDay", "Heute erzeugt", "%.1fkWh"),
                                  ("deliveryDay", "Heute eingespeist", "%.1fkWh")):
                v = self._state(c, nm)
                if v is not None:
                    rows.append({"l": lbl, "v": self._fmt_num(v, unit)})   # Kennzahl-Kachel
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "blocks": [
                {"k": "hero", "icon": "central"},
                {"k": "big", "text": (self._fmt_num(prod, "%.2fkW") if prod is not None else "–")},
                {"k": "status", "text": "Aktuelle Erzeugung"},
                *([{"k": "kpis", "items": rows[:3]}] if rows else []),
            ]}
        if t == "Webpage":
            det = c.get("details") or {}
            url = (det.get("urlHd") or det.get("url") or "").strip()
            if url and not re.match(r"^https?://", url):
                url = "http://" + url
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "blocks": [{"k": "web", "url": url}]}
        if t == "UpDownDigital":
            # Auf/Ab-Taster ohne States: gedrueckt halten = fahren (UpOn), loslassen
            # = stoppen (UpOff). Push&hold ist die sichere Taster-Semantik.
            ua = c.get("uuidAction")
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": [
                {"k": "hero", "icon": "blind"},
                {"k": "status", "text": "Zum Fahren gedrückt halten"},
                {"k": "row", "cells": [
                    {"icon": "up", "hold": True, "cmd": {"uuid": ua, "cmd": "UpOn"},
                     "release": {"uuid": ua, "cmd": "UpOff"}},
                    {"icon": "down", "hold": True, "cmd": {"uuid": ua, "cmd": "DownOn"},
                     "release": {"uuid": ua, "cmd": "DownOff"}}]},
            ]}
        if t in ("Colorpicker", "ColorPickerV2"):
            ua = c.get("uuidAction")
            mode, a, b, v = self._color_parse(self._state(c, "color"))
            if mode == "temp":
                bright, kelvin = a, b
                bset = bright or 100
                blocks = [
                    {"k": "hero", "icon": "bulb"},
                    {"k": "big", "text": f"{bright} %"},
                    {"k": "slider", "icon": "bulb", "value": bright, "min": 0, "max": 100,
                     "step": 1, "cmd": {"uuid": ua, "tmpl": "temp({v}," + str(kelvin or 4000) + ")"}},
                    {"k": "row", "wrap": True, "cells": [
                        {"label": nm, "cmd": {"uuid": ua, "cmd": f"temp({bset},{k})"}}
                        for nm, k in (("Warm", 2700), ("Neutral", 4000), ("Kalt", 6500))]},
                    {"k": "row", "cells": [
                        {"label": "Aus", "cmd": {"uuid": ua, "cmd": f"temp(0,{kelvin or 4000})"}}]},
                ]
            else:   # rgb (auch wenn noch kein Wert: als RGB behandeln)
                hue, sat, val = a, (b or 100), v
                bset = val or 100
                blocks = [
                    {"k": "hero", "icon": "bulb"},
                    {"k": "big", "text": f"{val} %"},
                    {"k": "slider", "icon": "bulb", "value": val, "min": 0, "max": 100,
                     "step": 1, "cmd": {"uuid": ua, "tmpl": f"hsv({hue},{sat}," + "{v})"}},
                    {"k": "row", "wrap": True, "cells": [
                        {"label": nm, "cmd": {"uuid": ua, "cmd": f"hsv({h},{s},{bset})"}}
                        for nm, h, s in (("Rot", 0, 100), ("Gelb", 55, 100), ("Grün", 120, 100),
                                         ("Türkis", 180, 100), ("Blau", 225, 100),
                                         ("Violett", 285, 100), ("Weiß", 0, 0))]},
                    {"k": "row", "cells": [
                        {"label": "Aus", "cmd": {"uuid": ua, "cmd": f"hsv({hue},{sat},0)"}}]},
                ]
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "AcControl":
            ua = c.get("uuidAction")
            # An die IRR-Detailseite angeglichen: grosse Ist-Temp oben, Status-
            # zeile, dann 2 Bedienzeilen. Modus/Fan klappen ihre Auswahl inline
            # auf (viele Optionen passen nicht in eine feste Zeile).
            modes = self._json_list_map(c, "operatingModes")   # {id: name}
            fans = self._json_list_map(c, "fanspeeds")          # {id: name}
            on = (self._state(c, "status") or 0) != 0
            def _as_int(v, d=0):
                try:
                    return int(float(v))
                except (TypeError, ValueError):
                    return d
            cur_mode = _as_int(self._state(c, "mode"))
            cur_fan = _as_int(self._state(c, "fan"))
            tgt = self._state(c, "targetTemperature")
            ist = self._state(c, "temperature")
            try:
                cur_t = float(tgt)
            except (TypeError, ValueError):
                cur_t = 22.0
            try:
                lo = float(self._state(c, "minTemp"))
            except (TypeError, ValueError):
                lo = 5.0
            try:
                hi = float(self._state(c, "maxTemp"))
            except (TypeError, ValueError):
                hi = 40.0
            dn = max(lo, cur_t - 0.5); up = min(hi, cur_t + 0.5)
            # grosse Anzeige = Ist-Temp (wie IRR); Fallback Soll, wenn kein Ist
            try:
                ist_ok = ist is not None and float(ist) > -50
            except (TypeError, ValueError):
                ist_ok = False
            big = (self._fmt_num(ist, "%.1f") + " °C") if ist_ok else \
                  ((self._fmt_num(tgt, "%.1f") + " °C") if tgt is not None else "–")
            sbits = []
            if tgt is not None:
                sbits.append(f"Soll {self._fmt_num(tgt, '%.1f')} °C")
            if cur_mode in modes:
                sbits.append(modes[cur_mode])
            sbits.append("Ein" if on else "Aus")
            status = " · ".join(x for x in sbits if x)
            # Zeile 2: Auto (Schnellzugriff Auto-Modus) + Modus/Fan-Aufklapper
            auto_id = next((mid for mid, nm in modes.items()
                            if (nm or "").strip().lower() == "auto"), None)
            row2 = []
            if auto_id is not None:
                row2.append({"label": modes[auto_id], "on": cur_mode == auto_id,
                             "cmd": {"uuid": ua, "cmd": f"setMode/{auto_id}"}})
            # Modus/Fan oeffnen ein Popup mit der Auswahl (statt Inline-Zeilen)
            if modes:
                row2.append({"label": "Modus", "menu": [
                    {"label": nm, "on": mid == cur_mode, "cmd": {"uuid": ua, "cmd": f"setMode/{mid}"}}
                    for mid, nm in sorted(modes.items())]})
            if fans:
                row2.append({"label": "Fan", "menu": [
                    {"label": nm, "on": fid == cur_fan, "cmd": {"uuid": ua, "cmd": f"setFan/{fid}"}}
                    for fid, nm in sorted(fans.items())]})
            blocks = [
                {"k": "big", "text": big},
                {"k": "status", "text": status},
                {"k": "row", "cells": [
                    {"label": "−", "cmd": {"uuid": ua, "cmd": f"setTarget/{dn:.1f}"}},
                    {"label": "Aus", "on": not on, "cmd": {"uuid": ua, "cmd": "off"}},
                    {"label": "Ein", "on": on, "cmd": {"uuid": ua, "cmd": "on"}},
                    {"label": "+", "cmd": {"uuid": ua, "cmd": f"setTarget/{up:.1f}"}},
                ]},
                {"k": "row", "cells": row2},
            ]
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "ClimateControllerUS":
            dh = self._state(c, "demandHeat") or 0
            dc = self._state(c, "demandCool") or 0
            big = "Heizt" if dh else ("Kühlt" if dc else "Bereit")
            # verwaltete AC-Einheiten + wie viele gerade Bedarf anmelden
            try:
                units = json.loads(self._state(c, "controls") or "[]")
            except (ValueError, TypeError):
                units = []
            active = sum(1 for u in units if isinstance(u, dict) and u.get("demand"))
            sbits = [f"{active}/{len(units)} Anlagen aktiv"] if units else []
            hum = self._state(c, "humidity") or 0
            if hum:
                sbits.append(f"Feuchte {self._fmt_num(hum, '%.0f')} %")
            out = self._state(c, "actualOutdoorTemp")
            try:
                if out is not None and float(out) > -100:
                    sbits.append(f"Außen {self._fmt_num(out, '%.1f')} °C")
            except (TypeError, ValueError):
                pass
            return self._big_view(uuid, "thermo", big, " · ".join(sbits),
                                  tone=("crit" if dc else None))
        if t == "Hourcounter":
            ov = self._state(c, "overdue")
            return self._big_view(uuid, "info", self._fmt_num(self._state(c, "total"), "%.0f h") or "–",
                                  "Wartung fällig" if ov else "", tone=("crit" if ov else None))
        if t == "EFM":
            det = c.get("details") or {}
            fmt = det.get("actualFormat") or "%.2f kW"
            p = self._state(c, "Ppwr")
            rows = []
            g = self._flow_text(self._state(c, "Gpwr"), fmt, "Netzbezug", "Einspeisung")
            if g:
                rows.append({"k": "status", "text": g})
            sp = self._flow_text(self._state(c, "Spwr"), det.get("storageFormat") or fmt,
                                 "Speicher entlädt", "Speicher lädt", "Speicher")
            if sp:
                rows.append({"k": "status", "text": sp})
            nodes = self._named_items(det.get("nodes"))
            vals = [(label, self._state(c, f"actual{i}")) for i, (label, _n) in enumerate(nodes[:6])]
            vals = [(label, v) for label, v in vals if v is not None]
            if vals:
                rows.append({"k": "head", "text": "Verbraucher und Quellen"})
                rows += [{"k": "status", "text": f"{label}: {self._fmt_num(v, fmt)}"} for label, v in vals]
            eb = self.energy_blocks(uuid)   # Radial auch beim Antippen (4"-Panel ohne Split)
            if eb:
                # Radial gross, darunter bis zu drei Kennzahlen als kleine Kacheln
                kp = []
                if p is not None:
                    kp.append({"l": "Erzeugung", "v": self._fmt_num(p, fmt)})
                gp = self._state(c, "Gpwr")
                if gp is not None:
                    kp.append({"l": "Netzbezug" if gp >= 0 else "Einspeisung", "v": self._fmt_num(abs(gp), fmt)})
                sc = self._state(c, "selfConsumption")
                if sc is not None:
                    # Loxone liefert ohne Erzeugung Unsinn (z.B. 90514) und je nach
                    # Version einen Anteil 0..1 statt Prozent -> plausibel machen
                    try:
                        scv = float(sc)
                    except (TypeError, ValueError):
                        scv = None
                    if scv is not None and 0 <= scv <= 1.0001 and scv != 0:
                        scv *= 100
                    ok = scv is not None and 0 <= scv <= 100 and (p is None or float(p or 0) > 0)
                    kp.append({"l": "Eigenverbrauch", "v": self._fmt_num(scv, "%.0f %%") if ok else "–"})
                blocks = [{"k": "eflow", "e": eb}] + ([{"k": "kpis", "items": kp[:3]}] if kp else [])
            else:
                blocks = [{"k": "hero", "icon": "central"},
                          {"k": "big", "text": (self._fmt_num(p, fmt) if p is not None else "–")},
                          {"k": "status", "text": "Aktuelle Erzeugung"}, *rows]
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "blocks": blocks}
        if t == "EnergyManager2":
            # Wie der Energieflussmonitor: Radial oben, darunter Kennzahlen als
            # kleine Kacheln (Netz, Speicher, Ladestand) und die Verbraucher.
            det = c.get("details") or {}
            p = self._state(c, "Ppwr")
            kp = []
            gv = self._state(c, "Gpwr")
            if gv is not None:
                kp.append({"l": "Netzbezug" if float(gv or 0) >= 0 else "Einspeisung",
                           "v": self._fmt_num(abs(float(gv or 0)), "%.2f kW")})
            if det.get("HasSpwr", True):
                sv = self._state(c, "Spwr")
                if sv is not None:
                    f = float(sv or 0)
                    kp.append({"l": "Speicher" if f == 0 else ("Speicher entlädt" if f > 0 else "Speicher lädt"),
                               "v": self._fmt_num(abs(f), "%.2f kW")})
            soc = self._state(c, "Ssoc")
            if soc is not None and det.get("HasSsoc", True):
                mn = self._state(c, "MinSoc")
                kp.append({"l": "Ladestand" + (f" · Reserve {self._fmt_num(mn, '%.0f')} %" if mn is not None else ""),
                           "v": self._fmt_num(soc, "%.0f %%")})
            lk = []
            for label, e in self._named_items(self._json_state(c, "loads")):
                st = e.get("status", e.get("state", e.get("active")))
                if isinstance(st, bool) or st in (0, 1, "0", "1"):
                    st = "Ein" if st in (True, 1, "1") else "Aus"
                lk.append({"l": label, "v": str(st) if st not in (None, "") else "–"})
            eb = self.energy_blocks(uuid)   # Radial auch beim Antippen (4"-Panel ohne Split)
            head = ([{"k": "eflow", "e": eb}] if eb else
                    [{"k": "big", "text": (self._fmt_num(p, "%.2f kW") if p is not None else "–")},
                     {"k": "status", "text": "Aktuelle Erzeugung"}])
            blocks = [*head] + ([{"k": "kpis", "items": kp[:3]}] if kp else []) + \
                     ([{"k": "kpis", "items": lk[:3]}] if lk else [])
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "blocks": blocks}
        if t == "PvProductionForecast":
            det = c.get("details") or {}
            today = self._state(c, "today")
            rows = []
            for nm, lbl in (("tomorrow", "Morgen"), ("period", "Aktueller Zeitraum"), ("after", "Danach")):
                v = self._state(c, nm)
                if v is not None:
                    rows.append({"k": "status", "text": f"{lbl}: {self._fmt_num(v, '%.1f kWh')}"})
            mp = det.get("maxPower")
            if mp is not None:
                rows.append({"k": "status", "text": f"Anlagenleistung {self._fmt_num(mp, '%.1f kW')}"})
            err = self._text(c, "errorInfo")
            if err:
                rows.append({"k": "status", "text": err})
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "blocks": [
                {"k": "hero", "icon": "central"},
                {"k": "big", "text": (self._fmt_num(today, "%.1f kWh") if today is not None else "–")},
                {"k": "status", "text": "Erwartete Erzeugung heute"},
                *rows,
            ]}
        if t == "Irrigation":
            ua = c.get("uuidAction")
            act = bool(self._state(c, "active"))
            rain = bool(self._state(c, "rainActive"))
            zone = self._irrigation_zone_name(c)
            # Aktive Zone gross, Zonen als Kacheln (laufende dunkel), Steuerung
            # unten. Befehle aus der Loxone-Structure-File-Doku: start, startForce
            # (Regen ignorieren), stop. Die Zonen sind reine Anzeige.
            big = (zone or "Bewässert") if act else ("Regenpause" if rain else "Bereit")
            bits = []
            ep = self._state(c, "expectedPrecipitation")
            if ep is not None:
                bits.append(f"{self._fmt_num(ep, '%.1f mm')} Regen erwartet")
            zones = self._named_items(self._json_state(c, "zones"))
            cur = self._state(c, "currentZone")
            items = []
            for i, (label, z) in enumerate(zones):
                # Zonennummer laut Structure File: "id" im zones-JSON, sonst Position
                try:
                    zid = int(z.get("id", i)) if isinstance(z, dict) else i
                except (TypeError, ValueError):
                    zid = i
                running = bool(act and ((cur is not None and int(cur) == zid) or label == zone))
                dur = z.get("duration") if isinstance(z, dict) else None
                sub = "läuft" if running else (f"{round(float(dur) / 60)} min" if isinstance(dur, (int, float)) and dur > 0 else "")
                # Reine Anzeige (wie in der Loxone-App): Name, Dauer und laufende Zone kommen
                # aus dem Baustein; gesteuert wird nur ueber Start / Erzwingen / Stopp.
                items.append({"id": f"{uuid}:{i}", "label": label, "on": running, "sub": sub, "icon": "drop"})
            blocks = [{"k": "big", "text": big}]
            if bits:
                blocks.append({"k": "status", "text": " · ".join(bits)})
            if items:
                blocks.append({"k": "scenes", "items": items})
            blocks.append({"k": "row", "act": True, "cells": [
                {"label": "Start", "on": act, "cmd": {"uuid": ua, "cmd": "start"}},
                {"label": "Erzwingen", "cmd": {"uuid": ua, "cmd": "startForce"}},
                {"label": "Stopp", "cmd": {"uuid": ua, "cmd": "stop"}},
            ]})
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "MailBox":
            mail = bool(self._state(c, "mailReceived"))
            pk = bool(self._state(c, "packetReceived"))
            big = "Post und Paket" if (mail and pk) else ("Post da" if mail else ("Paket da" if pk else "Leer"))
            return self._big_view(uuid, "info", big, "Postkasten", tone=("good" if (mail or pk) else None))
        if t == "Sauna":
            ua = c.get("uuidAction")
            det = c.get("details") or {}
            act = bool(self._state(c, "active"))
            ta = self._state(c, "tempActual")
            err = self._state(c, "error") or self._state(c, "saunaError")
            sbits = ["Ein" if act else "Aus"]
            md = self._state(c, "mode")
            if isinstance(md, (int, float)) and int(md) in SAUNA_MODES:
                sbits.append(SAUNA_MODES[int(md)])
            tt = self._state(c, "tempTarget")
            if tt is not None:
                sbits.append(f"Soll {self._fmt_num(tt, '%.0f')} °C")
            tb = self._state(c, "tempBench")
            if tb is not None:
                sbits.append(f"Bank {self._fmt_num(tb, '%.0f')} °C")
            hum = self._state(c, "humidityActual")
            if hum is not None and det.get("hasVaporizer"):
                fbit = f"Feuchte {self._fmt_num(hum, '%.0f')} %"
                ht = self._state(c, "humidityTarget")
                if isinstance(ht, (int, float)) and ht > 0:
                    fbit += f" → {self._fmt_num(ht, '%.0f')} %"
                sbits.append(fbit)
            rows = []
            if det.get("hasDoorSensor") and self._state(c, "doorClosed") == 0:
                rows.append({"k": "status", "text": "Tür offen"})
            if self._state(c, "ready"):
                rows.append({"k": "status", "text": "Betriebstemperatur erreicht"})
            if self._state(c, "fan"):
                rows.append({"k": "status", "text": "Lüftung läuft"})
            if self._state(c, "drying"):
                rows.append({"k": "status", "text": "Trocknung läuft"})
            if self._state(c, "timer"):
                rows.append({"k": "status", "text": "Timer läuft"})
            if det.get("hasVaporizer") and self._state(c, "lessWater"):
                rows.append({"k": "status", "text": "Wasser nachfüllen"})
            if err:
                rows.append({"k": "status", "text": "Störung"})
            # Steuerung. Befehle an der Anlage verifiziert (bin/sauna_probe.py):
            # Solltemperatur temp/<wert>, Betriebsart mode/<0..6>, Ein/Aus on/off.
            # Solltemperatur relativ (der Miniserver begrenzt auf die Sauna-Grenzen);
            # die Buttons rechnen bei jedem Rendering vom aktuellen Sollwert weiter.
            ctrl = []
            if tt is not None:
                base = int(round(tt))
                ctrl.append({"k": "row", "cells": [
                    {"label": "−5°", "cmd": {"uuid": ua, "cmd": f"temp/{base - 5}"}},
                    {"label": "−1°", "cmd": {"uuid": ua, "cmd": f"temp/{base - 1}"}},
                    {"label": "+1°", "cmd": {"uuid": ua, "cmd": f"temp/{base + 1}"}},
                    {"label": "+5°", "cmd": {"uuid": ua, "cmd": f"temp/{base + 5}"}},
                ]})
            # Betriebsart per Aufklapper (mode/<n>), aktive Art ist markiert.
            ctrl.append({"k": "row", "cells": [
                {"label": "Ein", "on": act, "cmd": {"uuid": ua, "cmd": "on"}},
                {"label": "Aus", "on": not act, "cmd": {"uuid": ua, "cmd": "off"}},
                {"label": "Programm", "menu": [
                    {"label": nm, "on": isinstance(md, (int, float)) and int(md) == n,
                     "cmd": {"uuid": ua, "cmd": f"mode/{n}"}}
                    for n, nm in SAUNA_MODES.items()]},
            ]})
            blocks = [
                {"k": "hero", "icon": "thermo"},
                {"k": "big", "text": (f"{self._fmt_num(ta, '%.0f')} °C" if ta is not None else "–"),
                 **({"tone": "crit"} if err else {})},
                {"k": "status", "text": " · ".join(sbits)},
                *rows,
                *ctrl,
            ]
            return {"t": "view", "title": _clean(c.get("name")), "route": route,
                    "anchor": "bottom", "blocks": blocks}
        if t == "SteakThermo":
            act = bool(self._state(c, "isActive"))
            temps = self._steak_temps(c)
            rows = [{"k": "status", "text": f"{label}: {self._fmt_num(v, '%.0f')} °C"} for label, v in temps]
            for nm, lbl in (("targetGreen", "Ziel grün"), ("targetYellow", "Ziel gelb")):
                v = self._state(c, nm)
                if v is not None:
                    rows.append({"k": "status", "text": f"{lbl}: {self._fmt_num(v, '%.0f')} °C"})
            al = self._text(c, "activeAlarmText")
            if al:
                rows.append({"k": "status", "text": al})
            if self._state(c, "timerAlarmActive") or self._state(c, "timerRemaining"):
                rows.append({"k": "status", "text": "Timer läuft"})
            bat = self._state(c, "batteryStateOfCharge")
            if bat is not None:
                rows.append({"k": "status", "text": f"Akku {self._fmt_num(bat, '%.0f')} %"})
            big = (f"{self._fmt_num(temps[0][1], '%.0f')} °C" if temps else ("Aktiv" if act else "Aus"))
            return {"t": "view", "title": _clean(c.get("name")), "route": route, "blocks": [
                {"k": "hero", "icon": "thermo"},
                {"k": "big", "text": big},
                {"k": "status", "text": "Grillthermometer" + ("" if act else " · aus")},
                *rows,
            ]}
        return {"t": "view", "title": _clean(c.get("name")), "route": route,
                "items": [self._control_item(uuid)]}

    def render(self, route: dict, prof: dict | None = None) -> dict:
        v = (route or {}).get("view", "tab")
        if v == "group":
            return self._view_group(route, prof)
        if v == "control":
            if route.get("entry") is not None:
                return self._alarm_edit_view(route.get("id"), route.get("entry"))
            return self._view_control(route.get("id"), route.get("range"), bool(route.get("chart")))
        if v == "sources":
            return self._view_sources(route.get("id"))
        if v == "links":
            return self._view_links(route.get("id"), prof)
        return self._view_tab(route.get("tab", "favoriten"), prof)

    def _links_of(self, c: dict) -> list:
        """In Loxone Config verknuepfte Objekte eines Bausteins (LoxAPP3 "links"),
        nur solche, die es in der Struktur gibt."""
        out = []
        for u in (c.get("links") or []):
            if isinstance(u, str) and u in self.controls and u not in out:
                out.append(u)
        return out

    def _view_links(self, uuid: str, prof: dict | None = None) -> dict:
        """Seite "Verknuepft": die verknuepften Objekte als normale Kacheln. Ein
        Tipp oeffnet deren Detailseite - auch wenn sie in keinem Tab liegen (wie
        die Status-Symbole der Statusleiste)."""
        c = self.controls.get(uuid) or {}
        links = self._links_of(c)
        return {"t": "view", "title": _clean(c.get("name")), "sub": "Verknüpft",
                "route": {"view": "links", "id": uuid},
                "items": [self._control_item(u, prof, show_room=True) for u in links]}

    async def audio_events_task(self) -> None:
        """Verwaltet je Audioserver (aus /mediaServer der Struktur) einen
        Gen-2-Event-Client (WS 7091). Startet neue Server, stoppt verschwundene;
        reagiert so auf Struktur-/Config-Aenderungen. `enabled` (audiometa) ist
        der Master-Schalter. Adressen kommen automatisch aus der Struktur —
        keine IP-Eingabe noetig."""
        while True:
            enabled = (self.audiometa_cfg or {}).get("enabled", True)
            off = set((self.audiometa_cfg or {}).get("off") or [])   # je Audioserver abgeschaltet
            want = set()
            if enabled:
                for hp in self.mediaservers.values():
                    host = (hp or "").split(":")[0].strip()
                    if host and host not in off:
                        want.add(host)
            for host in want:
                if host not in self.audio_clients:
                    am = self.audiometa_cfg or {}
                    cl = AudioEventClient(host, 7091, user=self.user,
                                          token_provider=lambda: self.jwt,
                                          neu_versuch_s=_audiometa_sekunden(
                                              am, "retry_interval", AudioEventClient.NEU_VERSUCH_S),
                                          pruef_zeitlimit_s=_audiometa_sekunden(
                                              am, "response_timeout", AudioEventClient.PRUEF_ZEITLIMIT_S))
                    self.audio_clients[host] = cl
                    self._spawn(self._run_audio_client(host, cl))
                    log.info("Audioserver-Event-Client gestartet: %s", host)
            for host in list(self.audio_clients):
                if host not in want:
                    cl = self.audio_clients.pop(host, None)
                    if cl:
                        await cl.close()
                        log.info("Audioserver-Event-Client gestoppt: %s", host)
            await asyncio.sleep(10)

    async def _run_audio_client(self, host: str, cl: AudioEventClient) -> None:
        try:
            await cl.run(self._mark_dirty)
        except Exception as err:
            log.debug("audio client %s: %s", host, err)
        finally:
            if self.audio_clients.get(host) is cl:
                self.audio_clients.pop(host, None)

    def _audio_server_info(self, hp: str) -> dict:
        """Ein erkannter Audioserver fuer die Config: Adresse, abgeschaltet?, Zustand."""
        host = (hp or "").split(":")[0].strip()
        off = host in set((self.audiometa_cfg or {}).get("off") or [])
        cl = self.audio_clients.get(host)
        if off or not (self.audiometa_cfg or {}).get("enabled", True):
            state = "aus"
        elif cl is None:
            state = "startet"
        elif getattr(cl, "_ws", None) is not None:
            state = "verbunden"
        else:
            state = "nicht erreichbar" + (f" ({cl.last_err})" if getattr(cl, "last_err", None) else "")
        return {"host": host, "addr": hp, "off": off, "state": state[:160]}

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _audio_client_for(self, c: dict):
        """(Event-Client, playerid) zur AudioZoneV2-Zone `c` — via
        details.server -> mediaServer-Host und details.playerid. (None, None),
        wenn kein passender Client laeuft."""
        det = c.get("details") or {}
        pid = det.get("playerid")
        hp = self.mediaservers.get(det.get("server"))
        if pid is None or not hp:
            return None, None
        host = hp.split(":")[0].strip()
        return self.audio_clients.get(host), pid

    def _sonn_for(self, c: dict) -> dict | None:
        """Now-Playing zur Zone `c` aus dem passenden Audioserver-Event-Client."""
        cl, pid = self._audio_client_for(c)
        return cl.now.get(pid) if cl else None

    def _detect_audio_host(self) -> str | None:
        """Audioserver-Host aus einer AudioZone-Cover/sourceList-URL ableiten.

        Loxone-Musik-Cover werden ueber den Audioserver-Proxy ausgeliefert
        (z.B. http://10.0.2.2:7092/...), die Host-IP ist also dort ablesbar.
        """
        for c in self.controls.values():
            if c.get("type") != "AudioZone":
                continue
            s = c.get("states") or {}
            for key in ("cover", "sourceList"):
                v = self.states.get(s.get(key))
                if isinstance(v, str):
                    m = re.search(r"https?://(\d{1,3}(?:\.\d{1,3}){3}):\d+/", v)
                    if m:
                        return m.group(1)
        return None

    def _audio_backend_for(self, uuid: str) -> AudioBackend | None:
        """Liefert das Steuer-Backend fuer eine AudioZone (uuidAction).

        Host-Reihenfolge: manuell konfiguriert (audio_cfg) -> mediaServer-Host
        aus der Struktur (steht IMMER fest, auch wenn nichts spielt) -> als
        letzter Ausweg aus einer Cover-URL abgeleitet. Pro Host ein Backend.
        """
        if self.audio is not None:               # explizit konfiguriert
            return self.audio
        host = self.audiohost_by_action.get(uuid) or self._detect_audio_host()
        if not host:
            return None
        be = self.audio_backends.get(host)
        if be is None:
            be = make_backend({"host": host, "port": self.audio_cfg.get("port", 7091)})
            if be is not None:
                self.audio_backends[host] = be
                log.info("Audioserver-Backend fuer %s", host)
        return be

    async def command(self, uuid: str, cmd: str, pin: str | None = None) -> str | None:
        """Fuehrt einen Befehl aus. Mit pin: gesicherter Befehl (Visu-Passwort)."""
        if not (self.client and uuid and cmd):
            return None
        # Nur echte Bausteinbefehle durchlassen: uuid im Loxone-Format, Befehl ohne
        # Pfad-Spruenge/Query - sonst liesse sich ueber die Panel-Verbindung jede
        # beliebige Miniserver-Adresse (z.B. dev/sys/reboot) mit unserem Token aufrufen.
        if not _UUID_CMD_RE.match(str(uuid)) or not _CMD_OK_RE.match(str(cmd)) or ".." in str(cmd):
            log.warning("Befehl abgelehnt (ungueltig): %r %r", str(uuid)[:60], str(cmd)[:60])
            return None
        if cmd.startswith("__central/"):
            await self._central_do(uuid, cmd.split("/", 1)[1])
            return "200"
        if cmd.startswith("__dimall/"):
            try:
                await self._dim_all(uuid, int(cmd.split("/", 1)[1]))
            except ValueError:
                pass
            return "200"
        try:
            if pin is not None:
                return await self._secured_command(uuid, cmd, pin)
            # AudioZone-Steuerung: Ein mit dem Miniserver GEKOPPELTER Loxone-
            # Audioserver lehnt Befehle auf Port 7091 OHNE Anmeldung ab
            # ("command not allowed when paired") und schliesst die Verbindung.
            # Transportbefehle (play/pause/next/prev/volume/{n}) laufen bei ihm
            # deshalb ueber den Miniserver (sps/io/{uuid}/{cmd}), wie in
            # audioserver_events.py dokumentiert. Nur ein NACHWEISLICH nicht
            # gekoppelter Audioserver (Nachbau Sonn/MS4H bzw. Musikserver Gen 1,
            # paired=False) nimmt Direktbefehle an -> dann direkt an Port 7091
            # (audio/{playerid}/{cmd}, schneller, und roomfav/play laeuft dort
            # ohne Anmeldung). Ist der Kopplungsstatus (noch) unbekannt
            # (Event-Client noch nicht gesondet, HTTP-Probe fehlgeschlagen oder
            # audiometa aus), wird sicher ueber den Miniserver geleitet. Ausnahme
            # roomfav/get: immer ueber den Miniserver, sie befuellt den
            # sourceList-State fuer die Anzeige.
            pid = self.playerid_by_action.get(uuid)
            host = self.audiohost_by_action.get(uuid)
            acl = self.audio_clients.get(host) if host else None
            # Direkt an den Audioserver nur bei positiv bekanntem Nachbau
            # (acl.paired is False). None (unbekannt) / kein Event-Client /
            # gekoppelt -> Miniserver.
            direct_ok = acl is not None and acl.paired is False
            # Raumfavorit abspielen: bei einem gekoppelten Audioserver ueber die
            # angemeldete Ereignis-Verbindung (der Direktkanal ohne Anmeldung
            # wuerde die Verbindung schliessen). Nachbauten (authed=False)
            # ueberspringen das und spielen unten direkt ab (direct_ok).
            if pid is not None and cmd.startswith("roomfav/play/"):
                if acl is not None and acl.authed:
                    ok = await acl.play_roomfav(pid, cmd.rsplit("/", 1)[-1])
                    return "200" if ok else None
            if pid is not None and not cmd.startswith("roomfav/get") and direct_ok:
                backend = self._audio_backend_for(uuid)
                if backend:
                    ok = await backend.command(pid, cmd)
                    return "200" if ok else None
                log.warning("AudioZone-Befehl ohne Audio-Backend (uuid=%s, cmd=%s)", uuid, cmd)
                return None
            # Miniserver: gekoppelte Zonen (Transport + roomfav-Fallback),
            # unbekannter Kopplungsstatus, roomfav/get und Nicht-Audio-Befehle.
            code, _ = await self._ms_jdev(f"sps/io/{uuid}/{cmd}")
            if code == "200":
                log.info("cmd %s/%s", uuid, cmd)
            else:
                log.warning("cmd %s/%s -> Code %s", uuid, cmd, code)
            return code
        except Exception as err:  # Befehl darf den Server nicht killen
            log.warning("cmd %s/%s fehlgeschlagen: %s", uuid, cmd, err or type(err).__name__)
            return None

    async def _secured_command(self, uuid: str, cmd: str, pin: str) -> str | None:
        """Loxone secured-command: getvisusalt -> Hash(visuPw:salt) -> HMAC(key) -> ios."""
        # PIN-Raten bremsen: nach 5 Fehlversuchen je Baustein wachsende Sperre (1-16 min)
        fails, until = self._pin_fail.get(uuid, (0, 0.0))
        if time.monotonic() < until:
            log.warning("PIN fuer %s gesperrt (zu viele Fehlversuche)", uuid)
            return "423"
        # Ein abgelaufenes Token faellt hier auf (und wird erneuert), nicht erst
        # beim ios-Aufruf: dort hiesse ein Fehler "Visu-Passwort falsch".
        _, val = await self._ms_jdev(f"sys/getvisusalt/{quote(self.user)}")
        val = val if isinstance(val, dict) else {}
        key, salt = val.get("key", ""), val.get("salt", "")
        alg = (val.get("hashAlg") or "SHA1").upper()
        digest = hashlib.sha256 if alg == "SHA256" else hashlib.sha1
        pwhash = digest(f"{pin}:{salt}".encode()).hexdigest().upper()
        h = hmac.new(bytes.fromhex(key), pwhash.encode(), digest).hexdigest()
        # Der Hash gilt nur einmal, und ein Fehler hier heisst meist falsches
        # Visu-Passwort -> nicht neu anmelden (das Token war eben noch gueltig).
        code, _ = await self._ms_jdev(f"sps/ios/{h}/{uuid}/{cmd}", renew=False)
        log.info("secured cmd %s/%s -> Code %s", uuid, cmd, code)
        if str(code) == "200":
            self._pin_fail.pop(uuid, None)
        else:
            fails += 1
            self._pin_fail[uuid] = (fails, time.monotonic() + (60 * 2 ** min(fails - 5, 4) if fails >= 5 else 0))
        return code

    def _on_value(self, uuid: str, value: object) -> None:
        self.states[uuid] = value
        self._diag_vals += 1
        self._dirty = True
        if uuid in self.bell_map:
            now = bool(value)
            if now != bool(self._bell_prev.get(uuid)):
                # Beide Flanken pushen (wie beim Wecker): 0->1 zeigt das Popup
                # und startet - falls fuer diese Intercom aktiviert - den Ton;
                # 1->0 (bell-Impuls am Miniserver endet) stoppt ihn wieder. Der
                # "sound"-Schalter kommt aus den Intercom-Einstellungen und
                # reist im Event mit, damit das Panel selbst nicht nachfragen
                # muss, ob es klingeln darf.
                cid = self.bell_map[uuid]
                ent = self.intercom_cfg.get(cid)
                snd = bool(ent.get("sound")) if isinstance(ent, dict) else False
                # Eigener Klingelton (falls hochgeladen) reist als fertige URL
                # mit, damit das Panel nicht extra nachfragen muss - leer =
                # generischer Wecker-Ton.
                sf = _sound_file_for(cid) if snd else None
                self._pending_ring.append({"id": cid, "on": now, "sound": snd,
                                           "soundUrl": (f"/api/sound?id={cid}" if sf else None)})
            self._bell_prev[uuid] = value
        if uuid in self.alarm_map:
            now = bool(value)
            if now != bool(self._alarm_prev.get(uuid)):
                # Beide Flanken pushen: 0->1 startet den Weckton, 1->0 (z.B. in
                # Loxone/App oder am Panel quittiert) stoppt ihn wieder. Global
                # abschaltbar (Settings -> Global -> Darstellung); dann wird gar
                # nichts erst eingereiht - kein Ton, kein Aufwecken, kein Sprung
                # zur Wecker-Ansicht. Die Wecker-Kacheln selbst bleiben davon
                # unberuehrt und ueberall normal bedienbar.
                if self.theme.get("ui", {}).get("alarmsEnabled", True):
                    self._pending_alarm.append({"id": self.alarm_map[uuid], "on": now})
            self._alarm_prev[uuid] = value
        if uuid in self.push_state and value and not self._bell_prev.get(("push", uuid)):
            # Taster meldet eine Ausloesung (0 -> 1). Kam sie gerade von einem Panel,
            # ist sie dort schon (mit Ergebnis) eingetragen -> nicht doppelt.
            cu = self.push_state[uuid]
            last = (self.push_hist.get(cu) or [{}])[0]
            if time.time() - float(last.get("ts") or 0) > 4:
                self.push_record(cu, True, "")
        if uuid in self.push_state:
            self._bell_prev[("push", uuid)] = bool(value)
        if uuid in self.sec_map:
            now = bool(value)
            if now != bool(self._sec_prev.get(uuid)):
                # Beide Flanken: an -> Vollbild auf den Panels, aus -> schliessen
                self._pending_sec.append({"id": self.sec_map[uuid], "on": now})
            self._sec_prev[uuid] = value

    @staticmethod
    def _push_time(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime("%H:%M")

    @staticmethod
    def _push_day(ts: float) -> str:
        d = datetime.fromtimestamp(ts).date(), date.today()
        return "heute" if d[0] == d[1] else ("gestern" if (d[1] - d[0]).days == 1 else d[0].strftime("%d.%m."))

    def push_uuid(self, uuid: str) -> str | None:
        """Taster-UUID zu einer Befehls-UUID (uuidAction oder Control-UUID)."""
        c = self.controls.get(uuid)
        if c and c.get("type") == "Pushbutton":
            return uuid
        for cu, cc in self.controls.items():
            if cc.get("type") == "Pushbutton" and cc.get("uuidAction") == uuid:
                return cu
        return None

    def push_record(self, cu: str, ok: bool, src: str) -> None:
        """Ausloesung eintragen (neueste zuerst, max. PUSHLOG_KEEP) und speichern."""
        lst = [{"ts": round(time.time(), 1), "ok": bool(ok), "src": (src or "")[:40]}] + (self.push_hist.get(cu) or [])
        self.push_hist[cu] = lst[:PUSHLOG_KEEP]
        self._dirty = True
        try:
            _atomic_write(PUSHLOG_FILE, json.dumps(self.push_hist, ensure_ascii=False))
        except OSError as err:
            log.debug("Taster-Historie nicht gespeichert: %s", err)

    def _on_weather(self, uuid: str, entries: list) -> None:
        """Wetter-Tabelle vom Miniserver uebernehmen (nur mit Wetterdienst).

        Die Front wird sofort neu gebaut, statt bis zum naechsten 15-Minuten-Takt
        zu warten: aus dem letzten Stand, mit neuem Wetter und OHNE neuen
        Kalenderabruf (siehe _front_nur_wetter()). Nur bei echter Aenderung,
        sonst baute jeder Wiederholungs-Push die Front umsonst neu."""
        if self._lox_wx.get(uuid) == entries:
            return
        self._lox_wx[uuid] = entries
        self._front_refresh.set()

    def _ms_sun_hhmm(self) -> tuple[str | None, str | None]:
        """Sonnenauf-/-untergang des Miniservers als "HH:MM".

        Quelle sind die globalen States (Minuten seit Mitternacht) — dieselbe,
        an der auch der Nachtmodus haengt. Ohne Werte (None, None)."""
        gs = self.global_states or {}
        out: list[str | None] = []
        for key in ("sunrise", "sunset"):
            u = gs.get(key)
            v = self.states.get(u) if isinstance(u, str) else None
            if isinstance(v, (int, float)) and 0 <= v < 1440:
                out.append(f"{int(v) // 60:02d}:{int(v) % 60:02d}")
            else:
                out.append(None)
        return out[0], out[1]

    def _loxone_weather(self) -> dict | None:
        """Wetter vom Loxone-Wetterserver aufbereitet — oder None, wenn die
        Anlage keinen hat bzw. die Daten nicht tragfaehig sind. Dann bleibt
        Open-Meteo zustaendig."""
        states = (self.weather_cfg or {}).get("states")
        if not isinstance(states, dict):
            return None
        actual = self._lox_wx.get(states.get("actual")) or []
        if not actual:
            return None
        forecast = self._lox_wx.get(states.get("forecast")) or []
        sr, ss = self._ms_sun_hhmm()
        fore = 4                                  # Widgets zeigen 1-4 Tage davon
        try:
            return loxone_weather.build(self.weather_cfg, actual, forecast,
                                        sunrise=sr, sunset=ss, fore_days=fore,
                                        lat=self.ms_lat, lon=self.ms_lon)
        except Exception:
            log.exception("Wetterserver: Aufbereitung fehlgeschlagen — Open-Meteo bleibt")
            return None

    async def stream_task(self) -> None:
        # Dauer-Loop: Erstverbindung + Reconnect zum Miniserver. Bricht NIEMALS
        # den HTTP-Server ab — auch wenn der Miniserver (noch) nicht erreichbar
        # oder das Passwort falsch ist (dann bleibt /settings bedienbar).
        # Wartezeit zwischen Versuchen waechst (MS_RETRY). Von vorn beginnt sie
        # erst, wenn eine Verbindung mindestens so lange hielt wie die laengste
        # Wartezeit - sonst liefe ein Miniserver, der sofort wieder trennt, in
        # eine Anmeldung alle paar Sekunden. Lehnt der Miniserver die Anmeldung
        # ab, gelten die deutlich laengeren MS_RETRY_AUTH (Schutz vor Sperre).
        retry, auth_retry, connected_at = 0, 0, None
        while True:
            try:
                if not self.host:
                    # Noch kein Miniserver konfiguriert -> auf /settings warten
                    # (kein Verbindungsversuch, kein Log-Spam).
                    await asyncio.sleep(5)
                    continue
                if self.client is None:
                    await self.start()          # Erstverbindung / nach hartem Reset
                elif self.ws is None:
                    # Reiner WS-Neuaufbau (z.B. nach Miniserver-Reboot durch eine
                    # Loxone-Config-Aenderung): Struktur mitziehen, damit neue/
                    # umbenannte Controls ohne LoxPanel-Neustart erscheinen. Fehler
                    # isoliert -> Reconnect scheitert nie an der Struktur.
                    try:
                        if await self._refresh_structure():
                            self._pending_reload = True   # Panels neu laden lassen
                            log.info("Loxone-Struktur geaendert -> uebernommen, Panels werden neu geladen")
                    except Exception:
                        log.exception("Struktur-Refresh beim Reconnect uebersprungen")
                    await self._connect_ws()    # WS neu (Settings-Reconnect / nach Abriss)
                connected_at = time.monotonic()
                auth_retry = 0                  # Anmeldung hat funktioniert
                self._retry_now.clear()
                self.ms_reason, self.ms_next_retry = "", 0.0
                self.ms_up, self.ms_up_since = True, time.time()
                ws = self.ws
                await ws.stream(self._on_value, self._on_weather)
                code = getattr(ws, "close_code", None)
                why = describe_close(code)
                raise ConnectionError(
                    "WS-Stream beendet"
                    + (f" (Close-Code {code}" + (f": {why}" if why else "") + ")" if code and code != 1000 else "")
                    + (" - Miniserver meldete Neustart/Update" if getattr(ws, "out_of_service", False) else ""))
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if self.ms_up:
                    self.ms_up, self.ms_down_since = False, time.time()
                if connected_at is not None and time.monotonic() - connected_at >= MS_RETRY[-1]:
                    retry = 0
                connected_at = None
                close_code = getattr(self.ws, "close_code", None) if self.ws else None
                oos = bool(getattr(self.ws, "out_of_service", False)) if self.ws else False
                try:
                    if self.ws:
                        await self.ws.close()
                except Exception:
                    pass
                self.ws = None
                rejected = _auth_rejected(err) or close_code in WS_CLOSE_NO_HAMMER
                try:
                    if self.client:
                        await self._reauth()    # Token erneuern, Client behalten
                except Exception as err2:
                    rejected = rejected or _auth_rejected(err2)
                    await self._close_conn()    # Client kaputt -> harter Reset (start() baut neu)
                if rejected:
                    wait = MS_RETRY_AUTH[min(auth_retry, len(MS_RETRY_AUTH) - 1)]
                    auth_retry += 1
                    log.warning("Miniserver lehnt die Anmeldung ab (%s) — naechster Versuch in %d min "
                                "(Schutz vor Konto-Sperre; Zugangsdaten unter Einstellungen pruefen, "
                                "neue Eingaben wirken sofort)", err, wait // 60)
                else:
                    wait = MS_RETRY[min(retry, len(MS_RETRY) - 1)]
                    retry += 1
                    log.warning("Miniserver nicht verbunden (%s) — neuer Versuch in %ss", err, wait)
                self.ms_reason = _ms_reason_code(rejected, close_code, oos)
                self.ms_next_retry = time.time() + wait
                # Pause, aber durch reconnect() (neue Zugangsdaten) jederzeit abbrechbar.
                try:
                    await asyncio.wait_for(self._retry_now.wait(), timeout=wait)
                except asyncio.TimeoutError:
                    pass
                # Signal verbrauchen: sonst bliebe es gesetzt und der naechste Fehlversuch
                # ginge ohne jede Pause im Kreis.
                self._retry_now.clear()

    async def _send_or_drop(self, ws, payload) -> bool:
        """Sendet an ein Panel; bei JEDEM Fehler ODER Haenger (Timeout) wird die
        Verbindung getrennt (nicht nur bei ConnectionError — aiohttp wirft bei
        sterbenden Sockets auch RuntimeError, oder send blockiert bei half-open).
        Das ws wird zusaetzlich geschlossen, damit das Panel den Abbruch bemerkt
        und sich neu verbindet (statt still ohne Live-Updates weiterzulaufen)."""
        if ws.closed:
            self.drop_conn(ws)
            return False
        lock = self._ws_locks.get(ws)
        if lock is None:
            lock = asyncio.Lock()
            if ws in self.conn_prof:                # nur fuer angemeldete Verbindungen merken (sonst Leck)
                self._ws_locks[ws] = lock

        async def _do():
            async with lock:
                await ws.send_json(payload)
        try:
            # Zeitlimit gilt fuer Warten auf die Sperre UND das Senden
            await asyncio.wait_for(_do(), timeout=5)
            return True
        except Exception as err:
            if ws in self.conn_route:
                log.info("Panel '%s' getrennt: Senden fehlgeschlagen (%s)",
                         self.conn_dev.get(ws) or (self.conn_info.get(ws) or {}).get("ip") or "?",
                         type(err).__name__ + (f": {err}" if str(err) else ""))
            self.drop_conn(ws)
            try:
                await ws.close()
            except Exception:
                pass
            return False

    async def _send_all(self, targets, payload) -> int:
        """An mehrere Panels GLEICHZEITIG senden: ein haengendes Panel (z. B.
        schlafendes WLAN) darf die anderen nicht ausbremsen - nacheinander mit je
        5 s Zeitlimit stauten sich sonst die Live-Werte im ganzen Haus."""
        targets = list(targets)
        if not targets:
            return 0
        res = await asyncio.gather(*(self._send_or_drop(ws, payload) for ws in targets))
        return sum(1 for r in res if r)

    async def ms_sysinfo(self) -> dict:
        """Systemwerte des Miniservers fuer die Startseite, hoechstens alle 30 s
        abgefragt: Firmware, CPU-Last, Tasks und die Antwortzeit (ms) der
        CPU-Abfrage. Fehlende Werte (aeltere/neuere Firmware) bleiben weg."""
        now = time.monotonic()
        if not self.ms_up or now - self._msinfo_t < 30:
            return self._msinfo if self.ms_up else {}
        self._msinfo_t = now

        async def one(path: str):
            t0 = time.monotonic()
            try:
                code, val = await self._ms_jdev(path, timeout=3, renew=False)
            except Exception:
                return None, None
            ms = round((time.monotonic() - t0) * 1000)
            return (str(val).strip() if code == "200" and val not in (None, "") else None), ms

        keys = (("cpu", "sys/cpu"), ("tasks", "sys/numtasks"), ("fw", "cfg/version"))
        res = await asyncio.gather(*(one(p) for _, p in keys))
        info = {k: v for (k, _), (v, _) in zip(keys, res) if v}
        if res[0][1] is not None and res[0][0]:
            info["rtt"] = res[0][1]
        self._msinfo = info
        return info

    def ms_ok(self, now: float | None = None) -> bool:
        """Miniserver fuer die Panels erreichbar? Kurze Abbrueche (Reconnect,
        Token-Erneuerung) bis MS_OFFLINE_GRACE zaehlen noch als erreichbar."""
        return self.ms_up or (now or time.time()) - self.ms_down_since < MS_OFFLINE_GRACE

    def _nrestart_on(self, name: str) -> bool:
        """Fully auf diesem Geraet nachts neu starten? Eigene Wahl, sonst Vorgabe
        des Geraetetyps (Shelly: ja - dort waechst der Speicher von Fully ueber Tage)."""
        cfg = self.devices.get(name) if isinstance(self.devices.get(name), dict) else {}
        mdl = DEVICE_MODELS.get(cfg.get("model") or "") or {}
        if mdl.get("os") != "android" or not cfg.get("fully"):
            return False
        return bool(cfg.get("nrestart", mdl.get("shelly", False)))

    async def _nightly_restarts(self) -> None:
        """Einmal je Nacht (NEULADEN_STUNDE): Fully per adb neu starten. Das Neuladen
        der Seite raeumt nur die Seite auf; der Speicher des Fully-Prozesses (inkl.
        Grafik) wird erst durch einen Neustart der App frei. Nacheinander, adb ist
        ohnehin gesperrt; die Seite schaltet das Display danach wieder selbst ab."""
        for name in [n for n in self.devices if self._nrestart_on(n)]:
            try:
                r = await self.kiosk_restart(name, "app")
                log.info("Nächtlicher Neustart von Fully auf %s: %s", name,
                         "ok" if r.get("ok") else r.get("error", "Fehler"))
            except Exception as e:                # ein Geraet darf die anderen nicht aufhalten
                log.warning("Nächtlicher Neustart %s fehlgeschlagen: %s", name, e)

    async def _broadcast_tick(self) -> None:
        now = time.time()
        lt = time.localtime(now)
        if lt.tm_hour == NEULADEN_STUNDE and lt.tm_min >= 5 and self._nr_day != lt.tm_yday:
            self._nr_day = lt.tm_yday          # 3:05 - nach dem Neuladen der Seiten um 3:00
            self._spawn(self._nightly_restarts())
        if self.diag and now >= self._diag_next:
            self._diag_stats(now)
        ok = self.ms_ok(now)
        if ok != self.ms_sent:
            self.ms_sent = ok
            if not ok:
                log.warning("Miniserver seit %ds nicht erreichbar -> Panels melden", int(now - self.ms_down_since))
            await self._send_all(self.conn_route, {"t": "ms", "ok": ok, "since": int(self.ms_down_since * 1000)})
        if now >= self._sl_next:
            self._sl_next = now + 3
            self._scene_light_learn(now)
        while self._pending_ring:
            ev = self._pending_ring.pop(0)
            log.info("Klingel → %s: %s%s", "an" if ev["on"] else "aus", ev["id"],
                     (" (eigener Ton: %s)" % ev["soundUrl"]) if ev.get("soundUrl")
                     else (" (Standardton)" if ev.get("sound") else ""))
            if ev["on"]:
                self._spawn(self.display_drivers(True))   # Kiosk-Apps ueber HTTP wecken
            await self._send_all(self.conn_route, {"t": "ring", "id": ev["id"],
                                                   "on": ev["on"], "sound": ev.get("sound", False),
                                                   "soundUrl": ev.get("soundUrl")})
        while self._pending_alarm:
            ev = self._pending_alarm.pop(0)
            log.info("Wecker %s → %s", "an" if ev["on"] else "aus", ev["id"])
            if ev["on"]:
                self._spawn(self.display_drivers(True))
            await self._send_all(self.conn_route, {"t": "alarm", "id": ev["id"], "on": ev["on"]})
        while self._pending_sec:
            ev = self._pending_sec.pop(0)
            msg = self.sec_alarm_msg(ev["id"], ev["on"])
            targets = [ws for ws, p in list(self.conn_prof.items()) if self.sec_alarm_wanted(p, ev["id"])]
            log.info("Sicherheits-Alarm %s → %s (%d Panels)", "an" if ev["on"] else "aus", ev["id"], len(targets))
            if ev["on"] and targets:
                self._spawn(self.display_drivers(True))
            # Ton je Panel (Profil -> Alarm-Vollbild -> "Ton am Panel"), alle gleichzeitig
            await asyncio.gather(*(self._send_or_drop(ws, {**msg, "sound": bool((self.conn_prof.get(ws) or {}).get("alarmTone"))})
                                   for ws in targets))
        if self._front_dirty:
            # Front (Kalender/Wetter) an alle Panels. Neu verbundene bekommen den
            # aktuellen Stand ausserdem direkt beim Verbinden (ws_handler).
            self._front_dirty = False
            if self._front is not None:
                # Meist hat sich nur das Wetter bewegt (Miniserver-Push, z.B. Wind):
                # dann nur das Wetter schicken statt erneut aller Termine (~14 KB).
                prev, cur = self._front_sent, self._front
                if prev and {k: v for k, v in prev.items() if k != "weather"} == \
                        {k: v for k, v in cur.items() if k != "weather"}:
                    out = {"t": "front", "part": "weather", "weather": cur.get("weather")}
                else:
                    out = cur
                self._front_sent = cur
                await self._send_all(self.conn_route, out)
        if self._pending_reload:
            # Loxone-Struktur hat sich geaendert (Config) -> Panels neu laden, damit
            # neue/umbenannte Controls erscheinen. Nur bei echter Aenderung gesetzt.
            self._pending_reload = False
            await self._send_all(self.conn_route, {"t": "reload"})
        night = self._night_now()
        if night != self._night_on:
            # Nur beim Wechsel senden — die Panels halten den Zustand selbst.
            self._night_on = night
            log.info("Nachtmodus %s", "an" if night else "aus")
            await self._send_all(self.conn_route, {"t": "night", "on": night})
        if self._dirty and self.conn_route:
            self._dirty = False
            # Gleiche Ansicht (Route + Profil) nur EINMAL je Takt aufbauen, auch wenn
            # mehrere Panels sie zeigen - das Rendern ist der teuerste Teil des Takts.
            self._tick_memo = {}
            # Jedes Panel einzeln und GLEICHZEITIG beliefern (siehe _send_all):
            # ein haengendes Panel verzoegert nur sich selbst, nicht das ganze Haus.
            await asyncio.gather(*(self._push_conn(ws, route) for ws, route in list(self.conn_route.items())))

    async def _push_conn(self, ws, route) -> None:
        """Aktuelle Ansicht (plus Panes, Dashboard) an EIN Panel - nur was sich
        seit der letzten Zustellung an dieses Panel geaendert hat."""
        if ws not in self.conn_route:             # inzwischen getrennt
            return
        prof = self.conn_prof.get(ws)
        memo = self._tick_memo
        t0 = time.perf_counter()
        try:
            # Profil-Id statt Objekt: jede Verbindung haelt ihr eigenes (inhaltsgleiches) Profil-dict
            rk = ("view", json.dumps(route, sort_keys=True, default=str), (prof or {}).get("id"))
            msg = memo.get(rk)
            if msg is None:
                msg = memo[rk] = self.render(route, prof)
                dt = time.perf_counter() - t0          # Diagnose: Renderzeit je Minute
                self._rt_sum += dt
                self._rt_n += 1
                self._rt_max = max(self._rt_max, dt)
        except Exception:
            # EINE fehlerhafte Kachel/Route darf NIEMALS die Live-Update-
            # Schleife killen. Fehler loggen, diese Verbindung ueberspringen.
            _log_exc_limited(("render", str(route)), "render() fehlgeschlagen (route=%s) — uebersprungen", route)
            return
        # Split-Layout: Player-Pane des aktiven Tabs mitrendern (Zone kommt
        # vom Client via setplayer -> conn_player). Fehler isolieren.
        player_msg = None
        _zone = self.conn_player.get(ws)
        if _zone:
            try:
                pb = self.player_blocks(_zone)
                player_msg = {"t": "player", "blocks": pb} if pb is not None else None
            except Exception:
                _log_exc_limited(("player", str(_zone)), "player_blocks fehlgeschlagen (%s)", _zone)
        # Split-Layout: Energiefluss-Pane des aktiven Tabs mitrendern (Kachel
        # kommt vom Client via setenergy -> conn_energy). Fehler isolieren.
        energy_msg = None
        _euid = self.conn_energy.get(ws)
        if _euid:
            try:
                eb = self.energy_blocks(_euid)
                energy_msg = {"t": "energy", **eb} if eb is not None else None
            except Exception:
                _log_exc_limited(("energy", str(_euid)), "energy_blocks fehlgeschlagen (%s)", _euid)
        # Split-Layout: Verlaufs-Pane (chart:<uuid>) des aktiven Tabs
        # mitrendern (kommt vom Client via setchart -> conn_chart).
        chart_msg = None
        _chart = self.conn_chart.get(ws)
        if _chart:
            try:
                cb = self.chart_blocks(*_chart)
                chart_msg = {"t": "chart", **cb} if cb is not None else None
            except Exception:
                _log_exc_limited(("chart", str(_chart)), "chart_blocks fehlgeschlagen (%s)", _chart)
        # Split-Layout: Kamera-Pane (Intercom-Vollansicht) des aktiven Tabs
        # mitrendern (kommt vom Client via setcamera -> conn_camera).
        camera_msg = None
        _cuid = self.conn_camera.get(ws)
        if _cuid:
            try:
                ib = self.intercom_blocks(_cuid)
                camera_msg = {"t": "camera", "blocks": ib} if ib is not None else None
            except Exception:
                _log_exc_limited(("camera", str(_cuid)), "intercom_blocks fehlgeschlagen (%s)", _cuid)
        saver_msg = None
        try:
            sk = ("saver", (prof or {}).get("id"))
            saver_msg = memo.get(sk)
            if saver_msg is None:
                saver_msg = memo[sk] = self.saver_data(prof or {})
        except Exception:
            _log_exc_limited(("saver", str(None)), "saver_data fehlgeschlagen")
        # Nur senden, was sich seit der letzten Zustellung an DIESE
        # Verbindung geaendert hat. Der Tick laeuft, sobald sich
        # irgendein Wert im Haus bewegt — meist betrifft das die
        # Ansicht dieses Panels gar nicht, und das Panel wuerde
        # dieselbe Ansicht erneut bekommen und komplett neu zeichnen.
        if self.conn_route.get(ws) is not route:
            return       # Panel hat inzwischen navigiert - die neue Ansicht kam schon per nav
        last = self._last_sent.setdefault(ws, {})
        if msg != last.get("view"):
            if not await self._send_or_drop(ws, msg):
                return
            last["view"] = msg
        if player_msg is not None and player_msg != last.get("player"):
            if not await self._send_or_drop(ws, player_msg):
                return
            last["player"] = player_msg
        if energy_msg is not None and energy_msg != last.get("energy"):
            if not await self._send_or_drop(ws, energy_msg):
                return
            last["energy"] = energy_msg
        if saver_msg is not None and saver_msg != last.get("saver"):
            if not await self._send_or_drop(ws, saver_msg):
                return
            last["saver"] = saver_msg
        if chart_msg is not None and chart_msg != last.get("chart"):
            if await self._send_or_drop(ws, chart_msg):
                last["chart"] = chart_msg
            else:
                self._last_sent.pop(ws, None)
                return
        if camera_msg is not None and camera_msg != last.get("camera"):
            if await self._send_or_drop(ws, camera_msg):
                last["camera"] = camera_msg

    def _diag_stats(self, now: float) -> None:
        """Diagnose: eine Zeile je Minute - Miniserver-Zustand, Werte/Minute,
        Alter der letzten Miniserver-Nachricht und die verbundenen Panels."""
        first = not self._diag_next
        self._diag_next = now + 60
        rx = getattr(self.ws, "_last_rx", 0) if self.ws else 0
        age = f"{time.monotonic() - rx:.0f}s" if rx else "-"
        panels = ", ".join(f"{self.conn_dev.get(w) or (self.conn_info.get(w) or {}).get('ip') or '?'}"
                           f"[{(r or {}).get('view')}:{(r or {}).get('tab') or (r or {}).get('id') or ''}]"
                           for w, r in list(self.conn_route.items())) or "keine"
        # Server selbst: Speicher (RSS) und CPU-Anteil seit der letzten Zeile - zeigt, ob
        # der Dienst ueber Tage waechst oder den LoxBerry belastet.
        cpu_now, wall_now = time.process_time(), time.monotonic()
        cpu_pct = (100.0 * (cpu_now - self._diag_cpu[0]) / max(1e-6, wall_now - self._diag_cpu[1])
                   if self._diag_cpu else 0.0)
        self._diag_cpu = (cpu_now, wall_now)
        log.info("Diagnose: Miniserver %s, letzte Nachricht vor %s, %s Werte/min, %d States, "
                 "Render %d× / %.0f ms (max %.0f ms), Server %s MB / %.1f %% CPU, Panels: %s",
                 "verbunden" if self.ms_up else "GETRENNT", age,
                 "?" if first else self._diag_vals, len(self.states),
                 self._rt_n, self._rt_sum * 1000, self._rt_max * 1000,
                 _rss_mb(), cpu_pct, panels)
        self._rt_sum, self._rt_n, self._rt_max = 0.0, 0, 0.0
        self._diag_vals = 0

    async def broadcaster(self) -> None:
        # Diese Schleife darf NIEMALS sterben — sonst bekommen ALLE Panels keine
        # Live-Updates mehr (Symptom: Aktion wird ausgefuehrt, aber erst nach
        # Weg-/Zurueck-Navigieren angezeigt). Der ganze Tick ist deshalb gekapselt.
        while True:
            await asyncio.sleep(0.3)
            try:
                await self._broadcast_tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("broadcaster-Tick fehlgeschlagen — Schleife laeuft weiter")

    def _front_payload(self, data: dict) -> dict:
        return {"t": "front", "weather": data.get("weather"),
                "events": data.get("events") or [], "holidays": data.get("holidays") or {},
                "calName": data.get("calName") or "Family",
                # Legende der Kalender (Name + Farbe, ohne die Abo-URLs) und
                # die Anzeigeoptionen, die das Panel dafuer braucht.
                "cals": data.get("cals") or [],
                "calColors": bool(data.get("colors", True)),
                "svEvents": data.get("sv_events") or 3}

    def _front_cached_events(self, events: list) -> list:
        """Gespeicherte Termine auf HEUTE umschreiben.

        Der gespeicherte Stand kann von gestern sein — dauert der Aussetzer
        ueber Mitternacht, zeigt sein "Heute" auf den Vortag und laengst
        vergangene Tage stehen noch in der Liste. Beides hier richtigstellen,
        statt einen falschen Tag aufs Panel zu schicken.
        """
        heute = date.today()
        raus = []
        for e in events:
            try:
                d = date.fromisoformat(e.get("date") or "")
            except (ValueError, TypeError):
                continue
            if d < heute:
                continue
            label = front_info.day_label(d, heute)
            raus.append(e if e.get("day") == label else dict(e, day=label))
        return raus

    def _front_wetter(self, data: dict, wx: dict | None) -> None:
        """Wetter vom Loxone-Wetterserver einsetzen (Vorrang vor Open-Meteo) und
        die tatsaechlich verwendete Quelle fuer die Diagnose festhalten."""
        if wx is not None:
            data["weather"] = wx
            data["meta"]["wx_configured"] = True
            data["meta"]["wx_error"] = None
        data["meta"]["wx_source"] = "miniserver" if wx is not None else "open-meteo"
        self._wx_source = data["meta"]["wx_source"]

    def _front_nur_wetter(self, wx: dict | None) -> dict | None:
        """Front aus dem letzten Stand neu bauen, nur mit frischem Wetter.

        So reagiert die Front auf einen Wetter-Push des Miniservers, ohne
        Kalender und Open-Meteo erneut abzufragen. Wie oft der Miniserver
        schickt, bestimmt er selbst. Hing daran ein Kalenderabruf, fragte
        LoxPanel iCloud Durchgang an Durchgang an, und iCloud sperrte das Abo
        mit 503 und Retry-After. Der letzte Stand ist schon durch _front_keep()
        gelaufen; ein zweiter Durchgang wuerde die Uhrzeit des letzten guten
        Kalenderstands verfaelschen.
        """
        if self._front_last is None:
            return None
        data = copy.deepcopy(self._front_last)
        # Liefert der Wetterserver gerade nichts Brauchbares, bleibt der letzte
        # Stand samt seiner Quelle stehen; Open-Meteo kommt im naechsten Takt.
        if wx is not None:
            self._front_wetter(data, wx)
        self._front_meta = data.get("meta", {})
        return self._front_payload(data)

    def _front_keep(self, data: dict) -> dict:
        """Bei einem fehlgeschlagenen Abruf den letzten guten Stand behalten.

        Ohne das loescht ein einzelner Aussetzer die Anzeige: `load_front()`
        faengt den Fehler ab und liefert eine LEERE Liste zurueck, der
        Diff-Vergleich sieht darin eine echte Aenderung und schickt sie los -
        der Kalender ist am Panel bis zu 15 Minuten weg, nur weil iCloud einmal
        503 gesagt hat. Der alte Stand ist in dem Fall die bessere Auskunft als
        gar keiner; die Einstellungsseite nennt den Fehler weiterhin und sagt
        jetzt dazu, von wann die gezeigten Daten sind.

        Die Termine werden JE KALENDER ueberbrueckt: bei mehreren Abos ist die
        Liste auch dann gefuellt, wenn eine Quelle ausfaellt — ein gemeinsamer
        Stand wuerde genau dann ueberschrieben und die Termine der ausgefallenen
        Quelle verschwinden lassen.
        """
        meta = data.get("meta") or {}

        quellen = meta.get("cal_sources") or []
        if quellen:
            frisch: dict = {}
            for e in data.get("events") or []:
                frisch.setdefault(e.get("ck") or "", []).append(e)
            zusammen, stale = [], None
            for q in quellen:
                k = q.get("key") or ""
                gut = self._front_good_cal.get(k)
                if q.get("error") and not frisch.get(k) and gut:
                    zusammen.extend(self._front_cached_events(gut["events"]))
                    q["stale"] = gut["zeit"]
                    stale = gut["zeit"]
                else:
                    ev = frisch.get(k, [])
                    zusammen.extend(ev)
                    if not q.get("error"):
                        self._front_good_cal[k] = {"events": ev, "zeit": time.strftime("%H:%M")}
            # Quellen einzeln sortiert -> zusammengefuehrt neu ordnen.
            zusammen.sort(key=front_info.event_sort_key)
            data["events"] = zusammen
            meta["cal_count"] = len(zusammen)
            if stale:
                meta["events_stale"] = stale
        # Entfernte Kalender nicht ewig im Speicher mitschleppen.
        aktuell = {q.get("key") for q in quellen}
        for k in list(self._front_good_cal):
            if k not in aktuell:
                del self._front_good_cal[k]

        for fehler, feld in (("hol_error", "holidays"),
                             ("wx_error", "weather")):
            if meta.get(fehler) and not data.get(feld) and self._front_good.get(feld):
                data[feld] = self._front_good[feld]
                meta[f"{feld}_stale"] = self._front_good.get("_zeit")
            elif not meta.get(fehler) and data.get(feld):
                self._front_good[feld] = data[feld]
                self._front_good["_zeit"] = time.strftime("%H:%M")
        return data

    async def front_task(self) -> None:
        """Kalender + Wetter periodisch laden und an die Panels schicken. Laeuft nur
        aktiv, wenn mindestens ein iCal-Abo ODER Koordinaten gesetzt sind.

        _front_refresh weckt die Schleife vorzeitig. Nach dem Speichern holt sie
        alles neu; bei neuem Wetter vom Miniserver tauscht sie nur das Wetter und
        laesst den Kalender bis zum naechsten Takt in Ruhe."""
        # Grenze je Host: mehrere Abos liegen oft beim selben Anbieter (iCloud,
        # Google). Acht gleichzeitige Verbindungen dorthin sehen nach einem
        # Ansturm aus — genau das beantwortet iCloud gern mit 503.
        self._front_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit_per_host=3))
        try:
            while True:
                cfg = dict(self.calendar_cfg or {})
                # Koordinaten automatisch vom Miniserver, wenn keine in der Config.
                if cfg.get("lat") in (None, "") and self.ms_lat is not None:
                    cfg["lat"], cfg["lon"] = self.ms_lat, self.ms_lon
                # Wetter vom Miniserver hat Vorrang; Open-Meteo bleibt Rueckfall
                # fuer Anlagen ohne Loxone-Wetterdienst. Liefert der Wetterserver
                # Wetter, braucht es weder Koordinaten noch einen zweiten Abruf.
                cfg["fore_days"] = 4                 # Vorschau-Tage waehlt jedes Wetter-Widget selbst (max. 4)
                try:
                    wx = self._loxone_weather() if cfg.get("weather_ms", True) is not False else None
                    configured = bool(front_info.calendar_sources(cfg)) or wx is not None or (
                        cfg.get("lat") not in (None, "") and cfg.get("lon") not in (None, ""))
                except Exception:
                    # Ungewoehnliche Wetterdaten duerfen Kalender/Wetter nicht bis zum
                    # Neustart lahmlegen: diesen Durchgang auslassen, spaeter neu.
                    _log_exc_limited(("front", "cfg"), "front_task: Wetter/Quellen nicht lesbar")
                    wx, configured = None, False
                    await asyncio.sleep(30)
                    continue
                if configured:
                    try:
                        if time.monotonic() < self._front_cal_due:
                            # Geweckt vom Wetter-Push, der Kalender ist noch nicht
                            # wieder faellig: nur das Wetter tauschen.
                            payload = self._front_nur_wetter(wx)
                        else:
                            # Vor dem Abruf vormerken: auch ein unerwarteter Fehler
                            # darf keinen Abruf nach dem anderen nach sich ziehen.
                            self._front_cal_due = time.monotonic() + FRONT_INTERVAL
                            data = await front_info.load_front(self._front_session, cfg,
                                                               skip_weather=wx is not None)
                            self._front_wetter(data, wx)
                            data = self._front_keep(data)   # Aussetzer loescht nichts
                            self._front_last = copy.deepcopy(data)
                            self._front_meta = data.get("meta", {})
                            payload = self._front_payload(data)
                    except Exception:
                        log.exception("front_task: Laden fehlgeschlagen")
                        payload = None
                else:
                    self._front_meta = {}
                    self._wx_source = "open-meteo"
                    payload = {"t": "front", "weather": None, "events": [],
                               "holidays": {}, "cals": [], "calColors": True,
                               "svEvents": 3,
                               "calName": (cfg.get("name") or "Family")}
                # Nur bei echter Aenderung senden (spart Broadcasts bei gleichem Stand).
                if payload is not None:
                    key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                    if key != self._front_key:
                        self._front = payload
                        self._front_key = key
                        self._front_dirty = True
                # Bis der Kalender wieder faellig ist (hoechstens FRONT_INTERVAL) ODER
                # bis ein Speichern oder neues Wetter vom Miniserver weckt. Nach einem
                # Wetter-Push nur die RESTzeit warten, sonst schoebe jeder Push den
                # naechsten Kalenderabruf weiter hinaus.
                warte = FRONT_INTERVAL
                if configured:
                    warte = min(FRONT_INTERVAL, max(1.0, self._front_cal_due - time.monotonic()))
                try:
                    await asyncio.wait_for(self._front_refresh.wait(), timeout=warte)
                except asyncio.TimeoutError:
                    pass
                self._front_refresh.clear()
        finally:
            if self._front_session is not None:
                await self._front_session.close()
                self._front_session = None

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()
        if self.icon_session:
            await self.icon_session.close()
        if self.client:
            await self.client.close()
        if self.audio:
            await self.audio.close()
        for be in list(self.audio_backends.values()):
            await be.close()
        self.audio_backends.clear()
        for cl in list(self.audio_clients.values()):
            await cl.close()
        self.audio_clients.clear()


# Panel-/Config-/Settings-HTML immer frisch ausliefern: der Kiosk-Chromium
# cachte die Seite sonst heuristisch und zeigte nach einem Update die alte
# Version (aufklappende Auswahl etc. griff nicht) bis der Profil-Cache geleert
# wurde. no-cache erzwingt Revalidierung -> Updates greifen sofort.
_NOCACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _web_file(path: Path, ctype: str) -> web.Response:
    """Eine der Oberflaechen-Dateien ausliefern. Fehlt sie (kaputtes Image,
    falsch gemountetes Volume), gibt es einen 404 mit Dateinamen statt eines
    Stacktrace als 500."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        log.error("%s nicht lesbar: %s", path, err)
        return web.Response(status=404, text=f"{path.name} fehlt im LoxPanel-Image")
    return web.Response(text=text, content_type=ctype, headers=_NOCACHE)


async def index(request: web.Request) -> web.Response:
    return _web_file(HTML, "text/html")


# Update-Pruefung fuer die Config-Anzeige: dieselbe release.cfg, die LoxBerrys
# Auto-Update liest (plugin.cfg -> RELEASECFG). Installiert wird weiter nur ueber
# die LoxBerry-Pluginverwaltung - hier nur der Hinweis.
RELEASE_CFG_URL = ("https://raw.githubusercontent.com/actionhero-zz/loxohnepanel/"
                   "claude/festive-sagan-avv9if/release.cfg")
_UPD_CACHE: dict = {"ts": 0.0, "latest": ""}


def _ver_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])


async def update_handler(request: web.Request) -> web.Response:
    """{current, latest, newer}: neuere Version im Repo? Ergebnis 5 min gepuffert
    (die Config fragt bei jedem Seitenwechsel - GitHub nicht bei jedem Klick)."""
    now = time.time()
    if now - _UPD_CACHE["ts"] > 300 or (request.query.get("force") and now - _UPD_CACHE["ts"] > 30):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as sess:
                async with sess.get(RELEASE_CFG_URL, headers={"Cache-Control": "no-cache"}) as r:
                    txt = await r.text() if r.status == 200 else ""
            m = re.search(r"^VERSION=([0-9.]+)", txt, re.M)
            _UPD_CACHE.update(ts=now, latest=m.group(1) if m else _UPD_CACHE["latest"])
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            _UPD_CACHE["ts"] = now - 240           # Fehler: in einer Minute erneut
    latest = _UPD_CACHE["latest"]
    return web.json_response({"current": APP_VERSION, "latest": latest,
                              "newer": bool(latest) and _ver_tuple(latest) > _ver_tuple(APP_VERSION)},
                             headers=_NOCACHE)


async def version_handler(request: web.Request) -> web.Response:
    """Welcher Code-Stand laeuft TATSAECHLICH im Container - unabhaengig davon,
    was die LoxBerry-Pluginverwaltung als installierte Version anzeigt (die
    kennt nur plugin.cfg, nicht den Docker-Build). Einfachster Weg, ein
    haengendes Docker-Build-Cache-Problem von einem echten Code-Bug zu
    unterscheiden: Browser -> /api/version, kein Werkzeug noetig."""
    # Commit und Installationszeit stempelt preroot.sh bei der Installation in
    # bin/version.json (aus dem GitHub-ZIP); ohne die Datei nur die Version.
    out = {"version": APP_VERSION, "commit": "", "built": ""}
    try:
        vj = json.loads((Path(__file__).resolve().parent / "version.json").read_text())
        out["commit"] = str(vj.get("commit") or "")[:40]
        out["built"] = str(vj.get("built") or "")[:32]
    except (OSError, ValueError, AttributeError):
        pass
    return web.json_response(out, headers=_NOCACHE)


async def config_index(request: web.Request) -> web.Response:
    return _web_file(CONFIG_HTML, "text/html")


async def i18n_js(request: web.Request) -> web.Response:
    """Gemeinsamer Uebersetzungs-Katalog fuer /settings und /config."""
    return _web_file(I18N_JS, "application/javascript")


async def api_meta(request: web.Request) -> web.Response:
    """Alle Räume/Kategorien der Anlage + aktuelle Profile (für den Editor)."""
    app: App = request.app["app"]
    rooms = [{"uuid": ru, "name": _clean(app.rooms[ru].get("name", ""))} for ru in app.rooms_with]
    cats = [{"uuid": cu, "name": _clean(app.cats[cu].get("name", "")),
             "color": app.cats[cu].get("color")}         # Loxone-Voreinstellungsfarbe der Kategorie
            for cu in app.cats_with]
    panels = {pid: app._panel_export(raw) for pid, raw in app.panels.items()}
    controls = []
    for u, c in app.controls.items():
        if not c.get("name"):
            continue
        room = c.get("room")
        controls.append({
            "uuid": u, "name": _clean(c.get("name")), "type": c.get("type"),
            "room": room,
            "roomName": _clean((app.rooms.get(room) or {}).get("name", "")) if room else "",
            "cat": c.get("cat"),
            # Zentralbausteine: Mitglieder (fuer "Bausteine ausblenden" im Editor)
            **({"members": [m.get("uuid") for m in ((c.get("details") or {}).get("controls") or [])
                            if m.get("uuid") in app.controls]}
               if (c.get("type") or "").startswith("Central") else {}),
            "iconUrl": app._control_icon_url(c),
            # Statusbaustein: aktueller Text der aktiven Zeile (nur Anzeige im Editor)
            **({"stext": str(app._state(c, "textAndIcon") or app._state(c, "text") or "")[:120]}
               if c.get("type") in ("TextState", "InfoOnlyText") else {}),
            # Zeichnet der Baustein auf? Dann bietet der Konfigurator ihn fuer
            # die Verlaufs-Pane und den Mini-Verlauf in der Kachel an.
            "stat": bool(c.get("statistic") or c.get("statisticV2")),
            # Art der Reihe, die die Kachel zeigt (line/digital/counter): die
            # Tagesspanne gibt es nur fuer Linien.
            "statKind": (app._stat_primary(c) or (None, None))[1],
        })
    return web.json_response({
        "rooms": rooms, "cats": cats, "controls": controls,
        # Zeitraeume der Verlaufs-Diagramme (Schluessel, Anzeige) fuer die Auswahl
        # "Verlauf in der Kachel" — eine Quelle mit der Visu (STAT_RANGES).
        "statRanges": [[k, v[0]] for k, v in STAT_RANGES.items()],
        # Design-Vorlagen (Farbwaehler im Konfigurator): eine Quelle mit dem Server.
        "designPresets": theme_colors.DESIGN_PRESETS,
        "deviceModels": [{"key": k, **v} for k, v in DEVICE_MODELS.items()],
        "designKeys": list(theme_colors.DESIGN_KEYS),
        "icons": {"loxone": app._loxone_icons(), "loxlib": len(_loxlib_names()),
                  "ms": len(_msicons_names())},
        "tabs": [{"tab": "favoriten", "label": "Favoriten"},
                 {"tab": "zentral", "label": "Zentral"},
                 {"tab": "raeume", "label": "Räume"},
                 {"tab": "kategorien", "label": "Kategorien"}]
        + [{"tab": "cat:" + cu, "label": _clean(app.cats[cu].get("name", "")),
            "iconUrl": app._icon_url(app.cats[cu].get("image")), "cat": True}
           for cu in app.cats_with]
        + [{"tab": "room:" + ru, "label": _clean(app.rooms[ru].get("name", "")),
            "iconUrl": app._icon_url(app.rooms[ru].get("image")), "room": True}
           for ru in app.rooms_with],
        "panels": panels,
        "devices": App._devices_export(app.devices),
        "wsDevices": sorted({d for d in app.conn_dev.values() if d}),
        "theme": {"ui": {k: v for k, v in (app.theme.get("ui") or {}).items()
                         if k in THEME_UI_KEYS},
                  "categories": {k: v for k, v in (app.theme.get("categories") or {}).items()
                                 if not str(k).startswith("_")}},
    })


async def api_save_panels(request: web.Request) -> web.Response:
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    panels = data.get("panels")
    if not isinstance(panels, dict):
        return web.json_response({"ok": False, "error": "Feld 'panels' fehlt"}, status=400)
    clean = App._sanitize_panels(panels)
    # Was der Server nicht uebernimmt, meldet er (Konfigurator zeigt es an),
    # statt es still zu verlieren.
    weg = App._panels_verworfen(panels, clean,
                                {u: _clean(c.get("name")) or u for u, c in app.controls.items()})
    try:
        app._write_panels(clean)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    n = await _push(app, {"t": "reload"})   # offene Panels sofort neu laden
    log.info("panels.json gespeichert: %d Profile (%d Panels neu geladen)", len(clean), n)
    if weg:
        log.warning("panels.json: nicht übernommen: %s", "; ".join(weg))
    return web.json_response({"ok": True, "count": len(clean), "reloaded": n, "verworfen": weg})


async def api_save_theme(request: web.Request) -> web.Response:
    """Globale Darstellung (theme.json ui) speichern — gilt fuer alle Panels."""
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    ui = data.get("ui")
    if not isinstance(ui, dict):
        return web.json_response({"ok": False, "error": "Feld 'ui' fehlt"}, status=400)
    clean = App._sanitize_theme_ui(ui)
    cats = data.get("categories")
    clean_cats = App._sanitize_categories(cats) if isinstance(cats, dict) else None
    try:
        app._write_theme(clean, clean_cats)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    n = await _push(app, {"t": "reload"})   # offene Panels sofort neu laden
    log.info("theme.json (globale Darstellung%s) gespeichert (%d Panels neu geladen)",
             " + Kategorie-Farben" if clean_cats is not None else "", n)
    return web.json_response({"ok": True, "reloaded": n})


async def settings_index(request: web.Request) -> web.Response:
    return _web_file(SETTINGS_HTML, "text/html")


async def install_script(request: web.Request) -> web.Response:
    """Liefert das Panel-Installer-Skript (fuer 'curl ... | bash' vom Panel aus)."""
    try:
        txt = INSTALL_SH.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError:
        return web.Response(status=404, text="install-agent.sh nicht gefunden")
    return web.Response(text=txt, content_type="text/plain")


async def api_settings(request: web.Request) -> web.Response:
    app: App = request.app["app"]
    cfg = _load_cfg()
    ms = cfg.get("miniserver", {})
    ic = cfg.get("intercom", {})
    env_ms = bool(os.environ.get("LOXPANEL_MS_HOST"))

    def icv(uuid):
        e = ic.get(uuid) or {}
        if isinstance(e, str):
            e = {"url": e}
        return {"url": (e.get("url") or "").strip(), "user": e.get("user", ""),
                "hasPass": bool(e.get("pass")),
                # Ton am Panel bei Klingeln (generischer Wecker-Ton, oder eigener
                # Upload s.u.) - je Intercom einzeln abschaltbar. Default AUS:
                # bestehende Installationen sollen nach dem Update nicht
                # ploetzlich unaufgefordert piepen.
                "sound": bool(e.get("sound")),
                "reconnect": app._cam_reconnect_h(uuid),
                "crop": _clean_crop(e.get("crop")),
                # Eigener hochgeladener Klingelton (MP3/OGG/WAV/M4A/AAC) statt
                # des generischen Weckertons - nur der Vorhanden-Status, die
                # Datei selbst liefert /api/sound?id=<uuid>.
                "hasCustomSound": _sound_file_for(uuid) is not None}

    intercoms = [{"uuid": u, "name": _clean(c.get("name")), **icv(u)}
                 for u, c in app.controls.items() if c.get("type") == "Intercom"]
    cameras = [{"id": k, "name": str(e.get("name") or ""), "url": (e.get("url") or "").strip(),
                "user": e.get("user", ""), "hasPass": bool(e.get("pass")), "crop": _clean_crop(e.get("crop"))}
               for k, e in ic.items() if k.startswith("cam_") and isinstance(e, dict)]
    am = cfg.get("audiometa", {}) if isinstance(cfg.get("audiometa"), dict) else {}
    cal = cfg.get("calendar", {}) if isinstance(cfg.get("calendar"), dict) else {}
    return web.json_response({
        "miniserver": {
            "host": ms.get("host") or os.environ.get("LOXPANEL_MS_HOST", ""),
            "user": ms.get("user") or os.environ.get("LOXPANEL_MS_USER", ""),
            "port": ms.get("port", 443),
            "verify_tls": bool(ms.get("verify_tls", False)),
            "hasPass": bool(ms.get("pass")) or env_ms,
        },
        "intercoms": intercoms,
        "cameras": cameras,
        "audiometa": {"enabled": bool(am.get("enabled", True)),
                      "servers": [app._audio_server_info(hp) for hp in sorted(set(app.mediaservers.values()))]},
        "calendar": {
            # Quellen normalisiert (inkl. Migration einer alten einzelnen
            # ical_url), damit die Einstellungsseite genau das sieht, womit der
            # Server auch arbeitet.
            "sources": [{"name": q["name"], "url": q["url"], "color": q["color"],
                         "key": q["key"]}
                        for q in front_info.calendar_sources(cal)],
            "holiday_url": (cal.get("holiday_url") or "").strip(),
            "name": cal.get("name") or "Family",
            "colors": bool(cal.get("colors", True)),
            "sv_events": cal.get("sv_events", 3),
            "palette": front_info.CAL_COLORS,
            "max_sources": front_info.MAX_SOURCES,
            "lat": cal.get("lat"),
            "lon": cal.get("lon"),
            "days": cal.get("days", 14),
            "fore_days": cal.get("fore_days", 4),
            "weather_ms": cal.get("weather_ms", True) is not False,
            # Screensaver-Kamera ("Fenster zur Aussenwelt"): nur relevant/anzeigbar,
            # wenn kein iCal genutzt wird - die UI blendet das Feld sonst aus.
            "screensaverIntercom": cal.get("screensaverIntercom") or "",
            "status": app._front_meta,
            # Auto-Standort vom Miniserver (Fallback, wenn keine Koordinaten gesetzt)
            "ms_lat": app.ms_lat, "ms_lon": app.ms_lon, "ms_location": app.ms_location,
        },
        "night": {"control": (app.night_cfg or {}).get("control") or "",
                  "options": app.night_control_options()},
        "connected": app.client is not None,
        "nControls": len(app.controls),
        "cmdWatch": app.cmd_watch,
    })


async def api_msstatus(request: web.Request) -> web.Response:
    """Verbindung zum Miniserver fuer die Startseite: up = Stream laeuft,
    since = Beginn des aktuellen Zustands (ms), lastRx = Sekunden seit der
    letzten Nachricht des Miniservers (None ohne Stream)."""
    app: App = request.app["app"]
    rx = getattr(app.ws, "_last_rx", 0) if app.ws else 0
    return web.json_response({
        "configured": bool(app.host), "up": app.ms_up, "ok": app.ms_ok(),
        "since": int((app.ms_up_since if app.ms_up else app.ms_down_since) * 1000),
        "lastRx": round(time.monotonic() - rx, 1) if (app.ms_up and rx) else None,
        # Nur bei Trennung: Grund-Code + Sekunden bis zum naechsten Versuch (None = laeuft gerade)
        "reason": None if app.ms_up else (app.ms_reason or None),
        "retryIn": (max(0, int(app.ms_next_retry - time.time()))
                    if (not app.ms_up and app.ms_next_retry) else None),
        "sys": await app.ms_sysinfo(),
    }, headers=_NOCACHE)


async def api_types(request: web.Request) -> web.Response:
    """Diagnose: Bausteintypen der Anlage mit Unterstuetzungsstatus. JSON,
    mit ?format=text als lesbare Tabelle fuer den Browser."""
    app: App = request.app["app"]
    if not app.controls:
        data = {"connected": app.client is not None, "controls": 0, "typeCount": 0,
                "typesByStatus": {"full": 0, "partial": 0, "none": 0}, "types": [],
                "unsupportedControls": [],
                "hint": "Keine Struktur geladen. Miniserver unter /config verbinden."}
    else:
        data = app.types_overview()
    if request.query.get("format") == "text":
        lines = [f"LoxPanel Bausteintypen: {data['controls']} Controls, {data['typeCount']} Typen "
                 f"(voll {data['typesByStatus']['full']}, teilweise {data['typesByStatus']['partial']}, "
                 f"keine {data['typesByStatus']['none']})", ""]
        if data.get("hint"):
            lines.append(data["hint"])
        label = {"full": "voll", "partial": "teilw.", "none": "KEINE"}
        lines.append(f"{'Status':8} {'Anzahl':>6}  {'Typ':30} Beispiele")
        for e in data["types"]:
            lines.append(f"{label[e['status']]:8} {e['count']:6}  {e['type']:30} {', '.join(e['examples'])}")
        if data["unsupportedControls"]:
            lines += ["", "Nicht unterstuetzte Controls (tote Kacheln):"]
            lines += [f"  {d['room'] or '-':24} {d['name']:36} {d['type']}" for d in data["unsupportedControls"]]
        lines += ["", "States/Details je Typ:"]
        for e in data["types"]:
            lines.append(f"  {e['type']}: states={', '.join(e['states']) or '-'} | details={', '.join(e['details']) or '-'}")
        return web.Response(text="\n".join(lines) + "\n", content_type="text/plain", charset="utf-8")
    return web.json_response(data, dumps=lambda d: json.dumps(d, ensure_ascii=False, indent=2))


async def api_settings_ms(request: web.Request) -> web.Response:
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    host = str(data.get("host", "")).strip()
    if not host:
        return web.json_response({"ok": False, "error": "Host fehlt"}, status=400)
    cfg = _load_cfg()
    ms = dict(cfg.get("miniserver", {}))
    user = str(data.get("user", "")).strip()
    # Gespeichertes Passwort nur fuer DENSELBEN Host/Benutzer weiterverwenden.
    # Sonst koennte jeder im Netz den Host auf einen eigenen Rechner umstellen
    # und der Server meldete sich dort mit dem hinterlegten Passwort an.
    if (host, user) != (ms.get("host"), ms.get("user")):
        ms.pop("pass", None)
    ms["host"] = host
    ms["user"] = user
    try:
        ms["port"] = int(data.get("port") or 443)
    except (TypeError, ValueError):
        ms["port"] = 443
    ms["verify_tls"] = bool(data.get("verify_tls"))
    if data.get("pass"):                       # leer = altes Passwort behalten
        ms["pass"] = str(data["pass"])
    if not ms.get("pass"):
        return web.json_response({"ok": False, "error": "Passwort fehlt (bei geändertem Host/Benutzer bitte neu eingeben)"},
                                 status=400)
    cfg["miniserver"] = ms
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    try:
        n = await app.reconnect()
        log.info("Miniserver-Settings gespeichert, verbunden (%d Controls)", n)
        return web.json_response({"ok": True, "connected": True, "nControls": n})
    except Exception as err:
        return web.json_response({"ok": False, "error": f"Verbindung fehlgeschlagen: {err}"})


async def api_settings_cmdwatch(request: web.Request) -> web.Response:
    """Befehls-Monitoring (Zustellkontrolle) an/aus; wirkt sofort auf allen verbundenen Panels."""
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    on = bool(data.get("on"))
    cfg = _load_cfg()
    cfg["cmdwatch"] = {"on": on}
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    app.cmd_watch = on
    for ws in list(app.conn_route):
        await app._send_or_drop(ws, {"t": "cmdwatch", "on": on})
    log.info("Befehls-Monitoring %s", "an" if on else "aus")
    return web.json_response({"ok": True})


def _diag_info(app: "App") -> dict:
    files = _diag_files()
    return {"ok": True, "on": app.diag, "size": sum(f.stat().st_size for f in files),
            "max": DIAG_MAX * (DIAG_KEEP + 1)}


async def api_settings_diag(request: web.Request) -> web.Response:
    """Diagnose-Log: GET Zustand + Groesse, POST {on} an/aus (wirkt sofort, auch an den Panels)."""
    app: App = request.app["app"]
    if request.method == "POST":
        try:
            data = await request.json()
        except (ValueError, aiohttp.ContentTypeError):
            return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
        on = bool(data.get("on"))
        cfg = _load_cfg()
        cfg["diag"] = {"on": on}
        try:
            _write_cfg(cfg)
        except OSError as err:
            return web.json_response({"ok": False, "error": str(err)}, status=500)
        app.diag = on
        app._diag_next = 0.0
        _diag_apply(on)
        await app._send_all(app.conn_route, {"t": "diag", "on": on})
    return web.json_response(_diag_info(app))


async def api_settings_diag_download(request: web.Request) -> web.StreamResponse:
    """Alle Log-Dateien (aelteste zuerst) als eine Textdatei."""
    files = _diag_files()
    head = (f"LoxPanel Diagnose-Log · Version {APP_VERSION} · erstellt "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n").encode()
    body = head + b"".join(f.read_bytes() for f in files) if files else head + "(leer)\n".encode()
    name = f"loxpanel-diagnose-{datetime.now().strftime('%Y%m%d-%H%M')}.log"
    return web.Response(body=body, content_type="text/plain", charset="utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', **_NOCACHE})


async def api_settings_diag_clear(request: web.Request) -> web.Response:
    """Log-Dateien loeschen; laeuft das Log, beginnt es leer weiter."""
    app: App = request.app["app"]
    was = app.diag
    _diag_apply(False)
    for f in _diag_files():
        try:
            f.unlink()
        except OSError as err:
            log.warning("Diagnose-Log nicht geloescht (%s): %s", f.name, err)
    if was:
        _diag_apply(True)
    return web.json_response(_diag_info(app))


async def api_settings_night(request: web.Request) -> web.Response:
    """Nacht-Ausloeser: Baustein, dessen `active`-State den Nachtmodus schaltet.
    Leer = keiner, dann entscheiden die Sonnenzeiten."""
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    u = str(data.get("control") or "").strip()
    if u.startswith("opmode:"):
        if u[7:] not in app.op_modes:
            return web.json_response({"ok": False, "error": "Betriebsmodus nicht gefunden"}, status=400)
    elif u and u not in app.controls:
        return web.json_response({"ok": False, "error": "Baustein nicht gefunden"}, status=400)
    cfg = _load_cfg()
    night = dict(cfg.get("night", {}) if isinstance(cfg.get("night"), dict) else {})
    night["control"] = u
    cfg["night"] = night
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    app.night_cfg = _night_config()
    log.info("Nacht-Ausloeser gespeichert: %s", u or "(keiner -> Sonnenzeiten)")
    return web.json_response({"ok": True})


async def api_settings_audiometa(request: web.Request) -> web.Response:
    """Audioserver-Live-Daten (Gen-2-Event-Kanal) an/aus. Adressen werden
    automatisch aus der Struktur gelesen — es gibt nur den Master-Schalter."""
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    cfg = _load_cfg()
    am = dict(cfg.get("audiometa", {}) if isinstance(cfg.get("audiometa"), dict) else {})
    am["enabled"] = bool(data.get("enabled"))
    if isinstance(data.get("off"), list):        # je Audioserver abschalten (Hostnamen)
        am["off"] = sorted({str(h).strip()[:120] for h in data["off"] if str(h).strip()})
    cfg["audiometa"] = am
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    app.audiometa_cfg = _audiometa_config()
    # Bei Deaktivierung laufende Clients sofort schliessen; beim Aktivieren
    # startet der audio_events_task sie beim naechsten Durchlauf automatisch.
    for host, cl in list(app.audio_clients.items()):
        if not am["enabled"] or host in set(am.get("off") or []):
            await cl.close()
        app.audio_clients.clear()
    app._dirty = True
    log.info("Audioserver-Live-Daten %s", "aktiv" if am["enabled"] else "aus")
    return web.json_response({"ok": True})


async def api_settings_intercom(request: web.Request) -> web.Response:
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    items = data.get("intercoms") or {}
    if not isinstance(items, dict):
        return web.json_response({"ok": False, "error": "Feld 'intercoms' ungültig"}, status=400)
    cfg = _load_cfg()
    ic = dict(cfg.get("intercom", {}))
    for uuid, e in items.items():
        if not isinstance(e, dict):
            continue
        cur = ic.get(uuid)
        cur = dict(cur) if isinstance(cur, dict) else ({"url": cur} if isinstance(cur, str) else {})
        url, user = str(e.get("url", "")).strip(), str(e.get("user", "")).strip()
        # Passwort nur fuer dieselbe URL/denselben Benutzer behalten - sonst
        # ginge das gespeicherte Kamera-Passwort an eine neu eingetragene Adresse.
        if (url, user) != (cur.get("url"), cur.get("user", "")):
            cur.pop("pass", None)
        cur["url"], cur["user"] = url, user
        if e.get("pass"):
            cur["pass"] = str(e["pass"])
        cur["sound"] = bool(e.get("sound"))   # Ton bei Klingeln (generischer Wecker-Ton)
        if "crop" in e:
            cr = _clean_crop(e.get("crop"))
            if cr:
                cur["crop"] = cr                  # Bildausschnitt (Fokus/Zoom)
            else:
                cur.pop("crop", None)
        try:
            rc = int(e.get("reconnect") or 0)
        except (TypeError, ValueError):
            rc = 0
        cur["reconnect"] = rc if rc in CAM_RECONNECT_HOURS else 0   # Stream-Neuaufbau alle N h
        if cur.get("url"):
            ic[uuid] = cur
        else:
            ic.pop(uuid, None)
    # Eigene Kameras: Liste ersetzt die bisherigen cam_-Eintraege komplett
    cams = data.get("cameras")
    if isinstance(cams, list):
        keep = set()
        for e in cams[:16]:
            if not isinstance(e, dict):
                continue
            cid = str(e.get("id") or "")
            if not re.match(r"^cam_[a-z0-9]{4,16}$", cid):
                cid = "cam_" + os.urandom(4).hex()
            url, user = str(e.get("url", "")).strip(), str(e.get("user", "")).strip()
            if not url:
                continue
            cur = ic.get(cid) if isinstance(ic.get(cid), dict) else {}
            ent = {"name": str(e.get("name") or "Kamera").strip()[:40], "url": url, "user": user}
            cr = _clean_crop(e.get("crop")) if "crop" in e else _clean_crop(cur.get("crop"))
            if cr:
                ent["crop"] = cr                    # Bildausschnitt wie bei den Tuerstationen
            if e.get("pass"):
                ent["pass"] = str(e["pass"])
            elif cur.get("pass") and (url, user) == (cur.get("url"), cur.get("user", "")):
                ent["pass"] = cur["pass"]           # Passwort nur bei gleicher URL/gleichem Benutzer behalten
            ic[cid] = ent
            keep.add(cid)
        for k in [k for k in ic if k.startswith("cam_") and k not in keep]:
            ic.pop(k, None)
    cfg["intercom"] = ic
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    app.intercom_cfg = _intercom_config()
    log.info("Intercom-Settings gespeichert (%d Einträge)", len(ic))
    _cm = {"t": "camcrop", "map": app.cam_crops()}
    for _ws in list(app.conn_route):
        app._spawn(app._send_or_drop(_ws, _cm))     # Ausschnitt sofort an alle Panels
    return web.json_response({"ok": True})


async def api_settings_intercom_sound(request: web.Request) -> web.Response:
    """Eigenen Klingelton (Audiodatei) fuer eine Intercom hochladen. Ersetzt
    den generischen Wecker-Ton, solange 'Ton bei Klingeln' fuer sie aktiv ist
    (siehe api_settings_intercom). multipart/form-data: Feld 'id' (UUID) +
    Feld 'file' (Audiodatei, max. 5 MB, mp3/ogg/wav/m4a/aac)."""
    app: App = request.app["app"]
    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"ok": False, "error": "kein multipart/form-data"}, status=400)
    uuid, field = "", None
    async for part in reader:
        if part.name == "id":
            uuid = (await part.text()).strip()
        elif part.name == "file":
            field = part
            break   # Datei kommt als letztes Feld im Client - danach nicht weiterlesen
    if not uuid or uuid not in app.controls or app.controls[uuid].get("type") != "Intercom":
        return web.json_response({"ok": False, "error": "unbekannte Intercom"}, status=400)
    if field is None:
        return web.json_response({"ok": False, "error": "keine Datei übertragen"}, status=400)
    ctype = (field.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    ext = _SOUND_EXT_BY_MIME.get(ctype)
    if not ext:
        # Manche Browser schicken bei mp3/wav z.B. "application/octet-stream" -
        # dann anhand der Dateiendung des Original-Namens entscheiden.
        fname = (field.filename or "").lower()
        ext = next((e for e in _SOUND_MIME_BY_EXT if fname.endswith("." + e)), None)
    if not ext:
        return web.json_response(
            {"ok": False, "error": "nicht unterstütztes Format (mp3, ogg, wav, m4a, aac)"}, status=400)
    try:
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        for old in SOUNDS_DIR.glob(f"{uuid}.*"):   # vorherigen Upload dieser Intercom ersetzen
            old.unlink(missing_ok=True)
        dest = SOUNDS_DIR / f"{uuid}.{ext}"
        size = 0
        with open(dest, "wb") as f:
            while True:
                chunk = await field.read_chunk(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > _SOUND_MAX_BYTES:
                    f.close()
                    dest.unlink(missing_ok=True)
                    return web.json_response(
                        {"ok": False, "error": "Datei zu groß (max. 5 MB)"}, status=400)
                f.write(chunk)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    log.info("Eigener Klingelton gespeichert: %s (.%s, %d Bytes)", uuid, ext, size)
    return web.json_response({"ok": True})


async def api_settings_intercom_sound_delete(request: web.Request) -> web.Response:
    """Eigenen Klingelton wieder entfernen -> faellt auf den generischen
    Wecker-Ton zurueck (sofern 'Ton bei Klingeln' weiter aktiv ist)."""
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    uuid = str(data.get("id", "")).strip()
    p = _sound_file_for(uuid)
    if p:
        try:
            p.unlink()
        except OSError as err:
            return web.json_response({"ok": False, "error": str(err)}, status=500)
        log.info("Eigener Klingelton entfernt: %s", uuid)
    return web.json_response({"ok": True})


async def api_sound(request: web.Request) -> web.Response:
    """Liefert den hochgeladenen Klingelton einer Intercom aus (Panel-Client,
    <audio src="/api/sound?id=...">). 404, wenn keiner hinterlegt ist."""
    p = _sound_file_for(request.query.get("id", ""))
    if not p:
        return web.Response(status=404)
    try:
        body = p.read_bytes()
    except OSError:
        return web.Response(status=404)
    ctype = _SOUND_MIME_BY_EXT.get(p.suffix.lstrip("."), "application/octet-stream")
    return web.Response(body=body, content_type=ctype, headers={"Cache-Control": "no-cache"})


async def api_settings_weather(request: web.Request) -> web.Response:
    """Wetterquelle (System -> Miniserver): {ms: bool, lat, lon}. ms = Wetter vom
    Loxone-Wetterserver; sonst Open-Meteo mit den Koordinaten (leer = Standort
    des Miniservers)."""
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)

    def _coord(v, lim):
        if v in (None, ""):
            return None
        try:
            f = float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            return None
        return f if -lim <= f <= lim else None

    cfg = _load_cfg()
    cal = dict(cfg.get("calendar") or {}) if isinstance(cfg.get("calendar"), dict) else {}
    cal["weather_ms"] = bool(data.get("ms", True))
    lat, lon = _coord(data.get("lat"), 90.0), _coord(data.get("lon"), 180.0)
    cal["lat"] = lat if (lat is not None and lon is not None) else None
    cal["lon"] = lon if (lat is not None and lon is not None) else None
    cfg["calendar"] = cal
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    app.calendar_cfg = _calendar_config()
    app._front_refresh.set()
    log.info("Wetterquelle: %s", "Miniserver" if cal["weather_ms"] else "Open-Meteo")
    return web.json_response({"ok": True})


async def api_settings_calendar(request: web.Request) -> web.Response:
    """Kalender (iCal-Abos) + Wetter (Open-Meteo-Koordinaten) fuer die Front."""
    app: App = request.app["app"]
    try:
        data = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)

    def _coord(v, lim):
        # leer = nicht gesetzt; deutsches Komma erlauben; ausserhalb des Bereichs = ungueltig
        if v in (None, ""):
            return None
        try:
            f = float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            return None
        return f if -lim <= f <= lim else None

    def _int(v, default, lo, hi):
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return default

    cfg = _load_cfg()
    cal = dict(cfg.get("calendar", {}) if isinstance(cfg.get("calendar"), dict) else {})

    # Kalenderquellen NUR anfassen, wenn die Oberflaeche sie mitgeschickt hat.
    # Eine aeltere /config-Seite, die noch im Browser offen steht, kennt das
    # Feld nicht - ohne diese Pruefung loescht ihr "Speichern" saemtliche Abos.
    # Dasselbe gilt fuer die anderen neuen Felder weiter unten.
    roh = data.get("sources")
    if isinstance(roh, list):
        quellen, gesehen = [], set()
        for q in roh:
            if not isinstance(q, dict):
                continue
            url = front_info.normalize_ical_url(q.get("url"))
            # Doppelte URLs hier schon wegwerfen: calendar_sources() tut es
            # ohnehin, sonst stuenden sie in der Datei und die Oberflaeche
            # zeigte beim naechsten Laden weniger an, als gespeichert wurde.
            if not url or url in gesehen or len(quellen) >= front_info.MAX_SOURCES:
                continue
            gesehen.add(url)
            quellen.append({"name": str(q.get("name", "")).strip()[:40],
                            "url": url,
                            # Leer = spaeter die Vorschlagsfarbe der Position
                            "color": front_info.clean_color(q.get("color"), "")})
        cal["sources"] = quellen
        # Die alte Einzel-URL darf stehen bleiben, solange sie in der Liste
        # steht: calendar_sources() liest sie nur, wenn `sources` nichts
        # hergibt, ein Doppel-Kalender entsteht also nicht - und ein Downgrade
        # auf eine aeltere Version findet seinen Kalender noch vor. Erst wenn
        # der Benutzer sie aus der Liste genommen hat, verschwindet sie auch
        # hier, sonst kaeme sie beim Loeschen des letzten Abos zurueck.
        if front_info.normalize_ical_url(cal.get("ical_url")) not in gesehen:
            cal["ical_url"] = ""
    cal["holiday_url"] = str(data.get("holiday_url", "")).strip()
    cal["name"] = str(data.get("name", "")).strip() or "Family"
    if "colors" in data:
        cal["colors"] = bool(data.get("colors"))
    if "lat" in data or "lon" in data:       # Wetter steht jetzt unter System -> Miniserver
        lat, lon = _coord(data.get("lat"), 90.0), _coord(data.get("lon"), 180.0)
        # Nur ein vollstaendiges Koordinatenpaar speichern (halb gesetzt = kein Wetter).
        cal["lat"] = lat if (lat is not None and lon is not None) else None
        cal["lon"] = lon if (lat is not None and lon is not None) else None
    cal["days"] = _int(data.get("days"), 14, 1, 60)
    if "sv_events" in data:
        cal["sv_events"] = _int(data.get("sv_events"), 3, 1, 10)
    # Screensaver-Kamera ("Fenster zur Aussenwelt"): nur eine tatsaechliche
    # Intercom-UUID der Anlage akzeptieren, sonst leer (aus).
    sc = str(data.get("screensaverIntercom", "")).strip()
    cal["screensaverIntercom"] = sc if sc and app.controls.get(sc, {}).get("type") == "Intercom" else ""
    cfg["calendar"] = cal
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    app.calendar_cfg = _calendar_config()
    app._front_cal_due = 0.0   # Kalender sofort neu holen, nicht erst im naechsten Takt
    app._front_refresh.set()   # sofort neu laden und an die Panels schicken
    # screensaverIntercom ist Teil des einmaligen "theme"-Handshakes (nicht des
    # periodischen Front-Pushes) - offene Panels bekommen eine Aenderung sonst
    # erst nach der naechsten eigenen Neuverbindung mit. Reload wie bei den
    # anderen Einstellungsseiten (Panels/Darstellung).
    n = await _push(app, {"t": "reload"})
    log.info("Kalender/Wetter gespeichert (%d iCal-Abo(s), Wetter %s, Screensaver-Kamera %s; %d Panels neu geladen)",
             len(front_info.calendar_sources(cal)),
             "gesetzt" if cal.get("lat") is not None else "leer",
             "gesetzt" if cal["screensaverIntercom"] else "aus", n)
    return web.json_response({"ok": True, "reloaded": n})


# ---- Panel-Agenten (Fernstart der Displays) ----
async def api_agent_announce(request: web.Request) -> web.Response:
    """Panel-Agent meldet sich periodisch (Auto-Discovery)."""
    app: App = request.app["app"]
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        d = {}
    # IP/Port gehen spaeter in eine URL (api_agent_command) - deshalb streng
    # pruefen: nur echte IP-Adressen und gueltige Ports, sonst liesse sich per
    # Announce ein beliebiges Ziel eintragen, an das der Server Anfragen schickt.
    ip = str(d.get("ip") or "").strip() or (request.remote or "")
    try:
        ip = str(ipaddress.ip_address(ip))
        port = int(d.get("port") or 8130)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "ungueltige ip/port"}, status=400)
    if not 1 <= port <= 65535:
        return web.json_response({"ok": False, "error": "ungueltiger port"}, status=400)
    now = time.time()
    for k in [k for k, v in app.agents.items() if now - v["ts"] > 600]:
        del app.agents[k]   # verwaiste Eintraege aufraeumen (api_agents zeigt sie ohnehin nicht)
    app.agents[ip] = {"ip": ip, "name": str(d.get("name") or ip)[:60],
                      "panel": str(d.get("panel") or "")[:60], "port": port,
                      "kiosk": bool(d.get("kiosk")), "ts": now}
    # Panel-spezifische Geraeteeinstellungen an den Agenten zurueckgeben
    # (der wendet sie am Geraet an, z.B. Display-Abschaltung per xset).
    return web.json_response({"ok": True, "dpmsOff": app.panel_dpms(d.get("panel")),
                              "reloadHours": app.panel_reload(d.get("panel"))})


async def api_agents(request: web.Request) -> web.Response:
    app: App = request.app["app"]
    now = time.time()
    out = [{**a, "online": (now - a["ts"]) < 60}
           for a in app.agents.values() if (now - a["ts"]) < 600]
    out.sort(key=lambda a: a["name"])
    return web.json_response({"agents": out})


async def api_agent_command(request: web.Request) -> web.Response:
    """Leitet Start/Reload/Stop an den Panel-Agenten weiter."""
    app: App = request.app["app"]
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein JSON"}, status=400)
    ip = str(d.get("ip", ""))
    action = str(d.get("action", ""))
    a = app.agents.get(ip)
    if not a:
        return web.json_response({"ok": False, "error": "Panel nicht bekannt"}, status=404)
    if action not in ("start", "reload", "stop"):
        return web.json_response({"ok": False, "error": "unbekannte Aktion"}, status=400)
    host = f"[{a['ip']}]" if ":" in a["ip"] else a["ip"]   # IPv6 in URLs geklammert
    url = f"http://{host}:{a['port']}/{action}"
    payload = {"panel": str(d.get("panel") or "")} if action == "start" else {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as r:
                body = await r.text()
                log.info("Agent %s %s -> %s", ip, action, r.status)
                return web.json_response({"ok": r.status == 200, "status": r.status,
                                          "body": body[:200]})
    except Exception as err:
        return web.json_response({"ok": False, "error": str(err)})


async def api_mode(request: web.Request) -> web.Response:
    """Betriebsmodus-Wechsel von Loxone (virtueller Ausgang). Loxone schickt nur
    den Modusnamen, z.B.  GET /api/mode/gaeste  oder  /api/mode?name=gaeste .
    Die Zuordnung Modus -> Profil je Panel liegt in den Panel-Einstellungen."""
    app: App = request.app["app"]
    mode = request.match_info.get("mode", "")
    if not mode:
        mode = request.query.get("name") or request.query.get("mode") or ""
    if not mode and request.method == "POST":
        try:
            d = await request.json()
            mode = str(d.get("name") or d.get("mode") or "")
        except (ValueError, aiohttp.ContentTypeError):
            pass
    if not mode:
        return web.json_response({"ok": False, "error": "kein Modus angegeben"},
                                 status=400)
    results = await app.switch_mode(mode)
    log.info("Betriebsmodus '%s' -> %d Panel(s) umgeschaltet", mode, len(results))
    return web.json_response({"ok": True, "mode": mode, "switched": results})


async def api_save_devices(request: web.Request) -> web.Response:
    """Speichert die Betriebsmodus-Automatik je Panel (aus den Einstellungen)."""
    app: App = request.app["app"]
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein JSON"}, status=400)
    devices = App._sanitize_devices(d.get("devices") or {}, set(app.panels))
    # Leeres Display-Kennwort = unveraendert (/api/meta gibt es nicht heraus),
    # aber nur beim selben Ziel (Treiber und Host), sonst ginge das gespeicherte
    # an einen anderen Host. "verworfen": eines war da, das Ziel ist ein anderes.
    # Vor _write_devices, das app.devices ersetzt.
    verworfen = []
    for n, e in devices.items():
        disp = e.get("display") if isinstance(e, dict) else None
        alt = (app.devices.get(n) or {}).get("display") if isinstance(app.devices.get(n), dict) else None
        if not isinstance(disp, dict) or disp.get("password") or not isinstance(alt, dict) or not alt.get("password"):
            continue
        if alt.get("driver") == disp.get("driver") and alt.get("host") == disp.get("host"):
            disp["password"] = alt["password"]
        else:
            verworfen.append(n)
    old = {n: app.effective_scale(n) for n in set(app.devices) | set(devices)}
    try:
        app._write_devices(devices)
    except Exception as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    for n, sc in old.items():                      # Skalierung live nachziehen (ohne Neuladen)
        if app.effective_scale(n) != sc:
            await _push(app, {"t": "scale", "scale": app.effective_scale(n)}, "", n)
    return web.json_response({"ok": True, "devices": App._devices_export(devices),
                              "kennwortVerworfen": verworfen})


async def api_devices_get(request: web.Request) -> web.Response:
    """Alle Anzeigegeraete (Agent, Kiosk-App, Browser) mit Online-Status,
    Ansicht und Typ; Browser ohne Kennung getrennt nach IP."""
    app: App = request.app["app"]
    return web.json_response(app.device_list())


async def api_device_switch(request: web.Request) -> web.Response:
    """Ansicht eines Geraets wechseln: {device, panel}. Zuerst per WebSocket-
    Push (Browser laedt sich mit neuem Profil neu), sonst ueber den Agenten."""
    app: App = request.app["app"]
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein JSON"}, status=400)
    device = str(d.get("device") or "").strip()
    panel = str(d.get("panel") or "").strip()
    if not device:
        return web.json_response({"ok": False, "error": "device fehlt"}, status=400)
    if panel and panel not in app.panels:
        return web.json_response({"ok": False, "error": "unbekanntes Profil"}, status=400)
    n = await _push(app, {"t": "switch", "panel": panel}, "", device)
    if n:
        return web.json_response({"ok": True, "sent": n, "via": "ws"})
    now = time.time()
    agent = next((a for a in app.agents.values()
                  if a.get("name") == device and (now - a["ts"]) < 600), None)
    if agent:
        ok = await app._agent_start(agent, panel)
        return web.json_response({"ok": ok, "sent": 1 if ok else 0, "via": "agent"})
    return web.json_response({"ok": False, "sent": 0, "error": "Panel nicht online"})


async def api_device_name(request: web.Request) -> web.Response:
    """Gibt einem Browser ohne Kennung einen Geraetenamen: {ip, name}. Die
    Visu merkt sich den Namen (localStorage) und verbindet sich neu."""
    app: App = request.app["app"]
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein JSON"}, status=400)
    ip = str(d.get("ip") or "").strip()
    name = str(d.get("name") or "").strip()[:60]
    if not ip or not name:
        return web.json_response({"ok": False, "error": "ip und name noetig"}, status=400)
    n = 0
    for ws, info in list(app.conn_info.items()):
        if info.get("ip") != ip or info.get("dev"):
            continue
        if await app._send_or_drop(ws, {"t": "setdevice", "name": name}):
            n += 1
    return web.json_response({"ok": n > 0, "sent": n,
                              **({} if n else {"error": "kein Geraet ohne Kennung unter dieser IP"})})


async def api_msio(request: web.Request) -> web.Response:
    """Nur lesend: Zustand eines Ein-/Ausgangs des Miniservers ueber seinen Namen
    (`?name=` -> jdev/sps/io/<name>/state) bzw. die Liste der Ein-/Ausgaenge
    (`?list=in|out` -> jdev/sps/enumin|enumout). Fuer Bewegungs-/Praesenz-
    melder ohne Visualisierungs-Haken. Schaltet nichts - es gibt keinen Pfad
    fuer Werte, nur /state und die beiden Listen."""
    app: App = request.app["app"]
    lst = request.query.get("list", "")
    name = (request.query.get("name") or "").strip()
    if lst in ("in", "out"):
        path = "sps/enumin" if lst == "in" else "sps/enumout"
    elif name and len(name) <= 120 and "/" not in name:
        path = f"sps/io/{quote(name, safe='')}/state"
    else:
        return web.json_response({"ok": False, "error": "name= oder list=in|out"}, status=400)
    try:
        code, val = await app._ms_jdev(path, 8)
    except Exception as err:
        return web.json_response({"ok": False, "error": str(err)})
    return web.json_response({"ok": code == "200", "code": code, "path": path, "value": val})


async def api_device_rename(request: web.Request) -> web.Response:
    """Geraet umbenennen: {old, new}."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    old = str(d.get("old") or "").strip()[:60]
    new = str(d.get("new") or "").strip()[:60]
    if not old or not new:
        return web.json_response({"ok": False, "error": "alter und neuer Name noetig"}, status=400)
    return web.json_response(await app.device_rename(old, new))


async def api_panel_bg(request: web.Request) -> web.Response:
    """Dashboard-Hintergrundbild eines Panels: GET -> {url}; POST multipart (file)
    speichert (JPG/PNG/WebP, max. 12 MB); POST ?delete=1 entfernt es."""
    pid = str(request.query.get("panel") or "")
    if not re.match(r"^[a-z0-9_-]{1,40}$", pid):
        return web.json_response({"ok": False, "error": "panel fehlt"}, status=400)
    if request.method == "GET":
        return web.json_response({"ok": True, "url": bg_url(pid)})
    if request.query.get("delete"):
        for ext in _BG_TYPES:
            (BG_DIR / f"{pid}.{ext}").unlink(missing_ok=True)
        await _push(request.app["app"], {"t": "reload"}, pid)
        return web.json_response({"ok": True, "url": ""})
    try:
        reader = await request.multipart()
        part = None
        async for p in reader:
            if p.name == "file":
                part = p
                break
        if part is None:
            return web.json_response({"ok": False, "error": "keine Datei"}, status=400)
        data = await part.read(decode=False)
    except Exception:
        return web.json_response({"ok": False, "error": "Upload fehlgeschlagen"}, status=400)
    if len(data) > _BG_MAX_BYTES:
        return web.json_response({"ok": False, "error": "Bild zu groß (max. 12 MB)"}, status=400)
    ext = ("jpg" if data[:3] == b"\xff\xd8\xff" else "png" if data[:8] == b"\x89PNG\r\n\x1a\n"
           else "webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else "")
    if not ext:
        return web.json_response({"ok": False, "error": "nur JPG, PNG oder WebP"}, status=400)
    BG_DIR.mkdir(parents=True, exist_ok=True)
    for e in _BG_TYPES:
        (BG_DIR / f"{pid}.{e}").unlink(missing_ok=True)
    _atomic_bytes = BG_DIR / f".{pid}.tmp"
    _atomic_bytes.write_bytes(data)
    _atomic_bytes.replace(BG_DIR / f"{pid}.{ext}")
    await _push(request.app["app"], {"t": "reload"}, pid)   # Panels mit diesem Profil zeigen es sofort
    return web.json_response({"ok": True, "url": bg_url(pid)})


async def bg_handler(request: web.Request) -> web.Response:
    """Hintergrundbild ausliefern (URL traegt ?v=<Zeit>, daher lange cachebar)."""
    f = bg_file(request.match_info.get("pid", ""))
    if not f:
        raise web.HTTPNotFound()
    return web.Response(body=f.read_bytes(), content_type=_BG_TYPES[f.suffix[1:]],
                        headers={"Cache-Control": "max-age=2592000, immutable"})


async def api_device_delete(request: web.Request) -> web.Response:
    """Geraet loeschen: {name}."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    name = str(d.get("name") or "").strip()[:60]
    if not name:
        return web.json_response({"ok": False, "error": "name fehlt"}, status=400)
    return web.json_response(await app.device_delete(name))


async def api_tab_layout(request: web.Request) -> web.Response:
    """Tab-Editor: wirksame Belegung eines Tabs (gespeicherte Eintraege +
    Vorbefuellung aus Loxone, auto=True) fuer das mitgeschickte, evtl. noch
    ungespeicherte Profil. POST {panel, tab, profile}."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    tab = str(d.get("tab") or "")
    if not (_is_tab(tab) and _is_layout_tab(tab)):
        return web.json_response({"ok": False, "error": "kein Raster-Tab"}, status=400)
    raw = d.get("profile")
    raw = (App._sanitize_panels({"x": raw}).get("x") or {}) if isinstance(raw, dict) else None
    prof = app.resolve_profile(str(d.get("panel") or ""), raw)
    return web.json_response({"ok": True, "items": app._tab_layout(tab, prof)})


async def api_device_adblog(request: web.Request) -> web.Response:
    """Geraete-Log per adb als Textdatei: GET ?device=&ip= (nur lesend)."""
    app: App = request.app["app"]
    dev = str(request.query.get("device") or "").strip()
    if not dev:
        return web.json_response({"ok": False, "error": "device fehlt"}, status=400)
    res = await app.device_adblog(dev, str(request.query.get("ip") or ""))
    if not res.get("ok"):
        return web.json_response(res)
    name = "geraet-" + re.sub(r"[^A-Za-z0-9_-]+", "-", dev)[:40] + datetime.now().strftime("-%Y%m%d-%H%M") + ".log"
    return web.Response(text=res["text"], content_type="text/plain", charset="utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', **_NOCACHE})


async def api_kiosk_restart(request: web.Request) -> web.Response:
    """Panel per adb neu starten: POST {device, action: app|reboot, ip?}.
    app = Fully neu starten, reboot = Geraet neu starten."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    dev = str(d.get("device") or request.query.get("device") or "").strip()
    action = "reboot" if str(d.get("action") or request.query.get("action") or "") == "reboot" else "app"
    if not dev:
        return web.json_response({"ok": False, "error": "device fehlt"}, status=400)
    return web.json_response(await app.kiosk_restart(dev, action, str(d.get("ip") or "")))


async def api_kiosk_fully(request: web.Request) -> web.Response:
    """Fully Kiosk per adb installieren/aktualisieren: POST {device, ip?}."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    dev = str(d.get("device") or "").strip()
    return web.json_response(await app.fully_install(dev, str(d.get("ip") or "")))


async def api_kiosk_brightness(request: web.Request) -> web.Response:
    """Display-Helligkeit per adb: POST {device, ip?, value?} (value 1-255; ohne = nur lesen)."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    v = d.get("value")
    if v is not None:
        try:
            v = int(v)
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "ungültiger Wert"}, status=400)
    return web.json_response(await app.device_brightness(str(d.get("device") or "").strip(), str(d.get("ip") or ""), v,
                                                         True if d.get("auto") is True else None))


async def api_kiosk_touchsound(request: web.Request) -> web.Response:
    """Android-Tipp-Toene per adb: POST {device, ip?, on?} (ohne on = nur lesen)."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    on = d.get("on")
    return web.json_response(await app.device_touch_sound(str(d.get("device") or "").strip(), str(d.get("ip") or ""),
                                                          on if isinstance(on, bool) else None))


async def api_kiosk_fully_source(request: web.Request) -> web.Response:
    """GET: aktuelle Fully-Quelle. POST {url}: eigene Adresse setzen ("" = offizielle Seite)."""
    app: App = request.app["app"]
    if request.method == "POST":
        d = await _json_or_empty(request)
        url = str(d.get("url") or "").strip()
        if url and not re.match(r"^https?://[^\s]{4,500}$", url):
            return web.json_response({"ok": False, "error": "Adresse muss mit http:// oder https:// beginnen"}, status=400)
        cfg = _load_cfg()
        if url:
            cfg["fully"] = {"url": url}
        else:
            cfg.pop("fully", None)
        try:
            _write_cfg(cfg)
        except OSError as err:
            return web.json_response({"ok": False, "error": str(err)}, status=500)
    return web.json_response({"ok": True, **app.fully_source()})


async def api_kiosk_fully_upload(request: web.Request) -> web.Response:
    """Eigene Fully-APK hochladen (multipart, Feld 'file', max. 80 MB) bzw.
    mit ?delete=1 wieder entfernen. Die eigene Datei hat Vorrang vor jeder Adresse."""
    app: App = request.app["app"]
    dest = FULLY_DIR / FULLY_UPLOAD
    if request.query.get("delete"):
        dest.unlink(missing_ok=True)
        return web.json_response({"ok": True, **app.fully_source()})
    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"ok": False, "error": "kein multipart/form-data"}, status=400)
    field = None
    async for part in reader:
        if part.name == "file":
            field = part
            break
    if field is None:
        return web.json_response({"ok": False, "error": "keine Datei übertragen"}, status=400)
    FULLY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FULLY_DIR / (FULLY_UPLOAD + ".tmp")
    size, head = 0, b""
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = await field.read_chunk(262144)
                if not chunk:
                    break
                if not head:
                    head = chunk[:2]
                size += len(chunk)
                if size > FULLY_MAX_BYTES:
                    break
                f.write(chunk)
    except OSError as err:
        tmp.unlink(missing_ok=True)
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    if size > FULLY_MAX_BYTES or head != b"PK":
        tmp.unlink(missing_ok=True)
        return web.json_response({"ok": False, "error": "keine gültige APK (max. 80 MB)"}, status=400)
    tmp.replace(dest)
    log.info("Eigene Fully-APK hochgeladen (%d KB)", size // 1024)
    return web.json_response({"ok": True, **app.fully_source()})


async def api_display(request: web.Request) -> web.Response:
    """Display der Panels schalten: ?on=1|0, optional ?panel= / ?device=.
    Wirkt auf Geraete mit Kiosk-App (Fully Kiosk), die die Visu offen haben;
    Linux-Panels mit Agent regeln das Display selbst. Auch aus Loxone nutzbar."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    raw = d.get("on", request.query.get("on"))
    if isinstance(raw, bool):
        on = raw
    else:
        v = str(raw if raw is not None else "").strip().lower()
        if v in ("1", "true", "on", "an", "ein"):
            on = True
        elif v in ("0", "false", "off", "aus"):
            on = False
        else:
            return web.json_response({"ok": False, "error": "on=1|0 fehlt"}, status=400)
    panel, device = _push_filter(request, d)
    n = await _push(app, {"t": "display", "on": on}, panel, device)
    drivers = await app.display_drivers(on, device, panel)
    return web.json_response({"ok": True, "sent": n, "on": on, "drivers": drivers})


async def _push(app: "App", msg: dict, panel: str = "", device: str = "") -> int:
    """Push an offene Visu-Verbindungen (Server -> Browser). Optional gefiltert
    auf ein Panel-Profil (`panel`) oder ein Geraet (`device`, aus ?device=).
    Gibt die Anzahl erreichter Panels zurueck."""
    panel = (panel or "").strip()
    device = (device or "").strip()
    targets = [ws for ws in list(app.conn_prof)
               if (not panel or (app.conn_prof.get(ws) or {}).get("id") == panel)
               and (not device or app.conn_dev.get(ws) == device)]
    return await app._send_all(targets, msg)


def _push_filter(request: web.Request, d: dict) -> tuple:
    """panel/device-Filter aus Query ODER JSON lesen."""
    return (str(d.get("panel") or request.query.get("panel") or ""),
            str(d.get("device") or request.query.get("device") or ""))


async def _json_or_empty(request: web.Request) -> dict:
    if request.method == "POST":
        try:
            return await request.json()
        except (ValueError, aiohttp.ContentTypeError):
            return {}
    return {}


async def api_reload(request: web.Request) -> web.Response:
    """Laedt offene Panels neu (Server -> Browser). Optional ?panel= / ?device=.
    Auch aus Loxone per virtuellem Ausgang nutzbar."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    panel, device = _push_filter(request, d)
    n = await _push(app, {"t": "reload"}, panel, device)
    return web.json_response({"ok": True, "reloaded": n})


async def api_goto(request: web.Request) -> web.Response:
    """Schickt offene Panels auf eine Seite. ?control=<uuid> (Detailseite) ODER
    ?tab=<favoriten|zentral|raeume|kategorien>. Optional ?panel= / ?device=."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    control = str(d.get("control") or d.get("uuid") or request.query.get("control")
                  or request.query.get("uuid") or "").strip()
    tab = str(d.get("tab") or request.query.get("tab") or "").strip()
    if control:
        route = {"view": "control", "id": control}
    elif _is_tab(tab):
        route = {"view": "tab", "tab": tab}
    else:
        return web.json_response({"ok": False, "error": "control oder gueltiges tab noetig"},
                                 status=400)
    panel, device = _push_filter(request, d)
    n = await _push(app, {"t": "goto", "route": route}, panel, device)
    app._spawn(app.display_drivers(True, device, panel))   # Kiosk-Apps wecken
    return web.json_response({"ok": True, "route": route, "sent": n})


async def api_notify(request: web.Request) -> web.Response:
    """Blendet auf offenen Panels eine kurze Nachricht ein.
    ?text=... [&level=info|warn|crit] [&secs=5] [&panel=|&device=]."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    text = str(d.get("text") or request.query.get("text") or "").strip()[:200]
    if not text:
        return web.json_response({"ok": False, "error": "text fehlt"}, status=400)
    level = str(d.get("level") or request.query.get("level") or "info").strip()
    if level not in ("info", "warn", "crit"):
        level = "info"
    try:
        secs = int(float(d.get("secs") or request.query.get("secs") or 5))
    except (TypeError, ValueError):
        secs = 5
    secs = max(1, min(60, secs))
    panel, device = _push_filter(request, d)
    app._spawn(app.display_drivers(True, device, panel))   # Kiosk-Apps wecken
    n = await _push(app, {"t": "notify", "text": text, "level": level, "secs": secs},
                    panel, device)
    return web.json_response({"ok": True, "sent": n})


async def api_testtone(request: web.Request) -> web.Response:
    """Schickt einen kurzen Test-Weckton an die Panel-Browser (zum Pruefen der
    Audio-Ausgabe am Geraet, z.B. YC-41PM). Mit `panel` auf ein Profil begrenzt,
    sonst an alle offenen Visu-Verbindungen. Der Ton wird im Browser per Web
    Audio erzeugt (derselbe Weg wie der echte Weckton)."""
    app: App = request.app["app"]
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        d = {}
    target = str(d.get("panel") or "").strip()
    n = 0
    for ws, prof in list(app.conn_prof.items()):
        if target and (prof or {}).get("id") != target:
            continue
        if await app._send_or_drop(ws, {"t": "testtone"}):
            n += 1
    return web.json_response({"ok": True, "sent": n})


async def api_testring(request: web.Request) -> web.Response:
    """Schickt ein echtes Test-Klingel-Event an die Panel-Browser - Diagnose,
    ob ein hochgeladener Klingelton auf dem jeweiligen Geraet auch wirklich
    abspielt (manche Kiosk-Apps/WebViews auf schwacher Hardware wie dem Shelly
    Wall Display blockieren Autoplay fuer dynamisch erzeugte <audio>-Elemente
    strenger als fuer den synthetischen Weckton). Mit `panel` auf ein Profil
    begrenzt, sonst an alle offenen Visu-Verbindungen. Schickt nach 4s
    automatisch das Aus-Event hinterher, damit der Test nicht endlos klingelt."""
    app: App = request.app["app"]
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        d = {}
    uuid = str(d.get("id") or "").strip()
    if not uuid or uuid not in app.controls or app.controls[uuid].get("type") != "Intercom":
        return web.json_response({"ok": False, "error": "unbekannte Intercom"}, status=400)
    target = str(d.get("panel") or "").strip()
    # WICHTIG: denselben Weg wie der echte Klingel-Event-Pfad nehmen (_on_value)
    # - nicht "sound" fest auf True setzen. Sonst wuerde der Test selbst dann
    # Ton abspielen, wenn "Ton bei Klingeln" fuer diese Intercom (noch) gar
    # nicht gespeichert ist, und taeuscht eine funktionierende Konfiguration
    # nur vor.
    ent = app.intercom_cfg.get(uuid)
    snd = bool(ent.get("sound")) if isinstance(ent, dict) else False
    sf = _sound_file_for(uuid) if snd else None
    sound_url = f"/api/sound?id={uuid}" if sf else None

    async def _send(on: bool) -> int:
        n = 0
        for ws, prof in list(app.conn_prof.items()):
            if target and (prof or {}).get("id") != target:
                continue
            if await app._send_or_drop(ws, {"t": "ring", "id": uuid, "on": on,
                                            "sound": snd, "soundUrl": sound_url}):
                n += 1
        return n

    n = await _send(True)

    async def _stop_after():
        await asyncio.sleep(4)
        await _send(False)
    if n:
        app._spawn(_stop_after())
    return web.json_response({"ok": True, "sent": n, "sound": snd, "hasCustomSound": sf is not None})


_FONT_DIR = Path(__file__).resolve().parent.parent / "webfrontend" / "fonts"
_APPICON_DIR = Path(__file__).resolve().parent.parent / "webfrontend" / "appicons"


async def appicon_handler(request: web.Request) -> web.Response:
    """App-Symbol fuer "Zum Home-Bildschirm" (Handy-Web-App)."""
    size = request.match_info.get("size", "")
    if size not in ("256", "512"):
        return web.Response(status=404)
    f = _APPICON_DIR / f"icon_{size}.png"
    if not f.is_file():
        return web.Response(status=404)
    return web.Response(body=f.read_bytes(), content_type="image/png",
                        headers={"Cache-Control": "max-age=604800"})


async def manifest_handler(request: web.Request) -> web.Response:
    """Web-App-Manifest: Panel als App vom Home-Bildschirm starten (Vollbild,
    ohne Browserleiste). Startet mit dem Panel, aus dem es angelegt wurde."""
    app: App = request.app["app"]
    pid = str(request.query.get("panel") or "")
    if not re.match(r"^[a-z0-9_-]{1,40}$", pid):
        pid = ""
    dev = str(request.query.get("device") or "").strip()[:60]   # Geraetename bleibt in der Home-Bildschirm-App
    prof = app.panels.get(pid or "default") or {}
    name = _clean(prof.get("title") or "") or "LoxPanel"
    bg = "#0d0f1a"
    return web.json_response({
        "name": name, "short_name": name[:12],
        "start_url": "/" + ("?" + "&".join(x for x in (f"panel={quote(pid)}" if pid else "",
                                                        f"device={quote(dev)}" if dev else "") if x) if (pid or dev) else ""),
        "scope": "/",
        # "any": Wandtablets laufen quer, Handys hochkant - nicht festlegen
        "display": "standalone", "orientation": "any",
        "background_color": bg, "theme_color": bg,
        "icons": [{"src": "/appicon/256.png", "sizes": "256x256", "type": "image/png"},
                  {"src": "/appicon/512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
    }, content_type="application/manifest+json", headers=_NOCACHE)


# ---- Android-Panel einrichten (Shelly Wall Display u.a.) ----
_adb_lock = asyncio.Lock()   # adb-Server im Container nur einmal gleichzeitig benutzen


# Fehler in der Live-Schleife (alle 0,3 s je Panel) nur einmal je 5 min mit
# Traceback melden - eine dauerhaft kaputte Ansicht fuellte sonst das Log.
_EXC_SEEN: dict = {}
_WARN_SEEN: set = set()


def _log_once_warn(key, msg: str, *args) -> None:
    """Warnung je Schluessel nur einmal (Render laeuft ~3x/s je Panel)."""
    if key in _WARN_SEEN:
        return
    if len(_WARN_SEEN) > 1000:
        _WARN_SEEN.clear()
    _WARN_SEEN.add(key)
    log.warning(msg, *args)


# Loxone-UUID (ggf. mit Unterbaustein "/AI1"), Befehl nur aus harmlosen Zeichen
_UUID_CMD_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{16}(/[A-Za-z0-9_]+)?$")
_CMD_OK_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .,:;/+()=\-]*$")   # temp(..), hsv(..)


def _rss_mb() -> str:
    """Aktueller Speicher des Servers in MB (Linux /proc; sonst Hoechstwert)."""
    try:
        with open("/proc/self/status") as f:
            for ln in f:
                if ln.startswith("VmRSS:"):
                    return str(round(int(ln.split()[1]) / 1024))
    except OSError:
        pass
    try:
        import resource
        m = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return str(round(m / (1024 * 1024 if sys.platform == "darwin" else 1024)))
    except Exception:
        return "?"


def _presence_de(txt: str) -> str:
    """Infotext des Praesenzmelders: Loxone liefert ihn teils englisch ("Off / Lock")
    -> eindeutschen (Kachel und Detailseite gleich)."""
    _de = {"on": "An", "off": "Aus", "lock": "Gesperrt", "locked": "Gesperrt",
           "presence": "Anwesend", "absence": "Abwesend", "active": "Aktiv"}
    return re.sub(r"[A-Za-z]+", lambda m: _de.get(m.group(0).lower(), m.group(0)), txt or "")


def _log_exc_limited(key, msg: str, *args) -> None:
    now = time.monotonic()
    if now - _EXC_SEEN.get(key, -1e9) >= 300:
        if len(_EXC_SEEN) > 500:
            _EXC_SEEN.clear()
        _EXC_SEEN[key] = now
        log.exception(msg + " (weitere gleiche Meldungen 5 min still)", *args)
    else:
        log.debug(msg, *args, exc_info=True)


async def _adb(*args: str, timeout: float = 30) -> tuple[int, str]:
    """adb im Container ausfuehren -> (Returncode, Ausgabe). HOME zeigt auf das
    Config-Volume, dort legt adb seinen Schluessel (~/.android/adbkey) ab."""
    ADB_HOME.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HOME": str(ADB_HOME)}
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", *args, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    except OSError as e:
        return 127, f"adb nicht startbar: {e}"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"Zeitueberschreitung nach {timeout:.0f}s"
    except BaseException:
        # Aufrufer abgebrochen (Seite zu, Server stoppt): adb nicht verwaist zuruecklassen
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        raise
    return proc.returncode or 0, out.decode("utf-8", "replace").strip()


def _launcher_bundled_ver() -> int:
    """versionCode der mitgelieferten Launcher-APK (0 = unbekannt)."""
    try:
        return int(LAUNCHER_VERSION_FILE.read_text().strip())
    except (OSError, ValueError):
        return 0


def _launcher_ver_of(dumpsys: str) -> int:
    """versionCode aus "dumpsys package" (0 = nicht installiert)."""
    m = re.search(r"versionCode=(\d+)", dumpsys)
    return int(m.group(1)) if m else 0


async def api_panel_launcher_version(request: web.Request) -> web.Response:
    """Launcher-Version am Panel vs. Update: POST {device, ip?}."""
    app: App = request.app["app"]
    d = await _json_or_empty(request)
    return web.json_response(await app.launcher_version(str(d.get("device") or "").strip(), str(d.get("ip") or "")))


async def api_panel_launcher(request: web.Request) -> web.Response:
    """LoxPanel-Launcher per adb auf ein Android-Panel installieren und
    einrichten: {ip, port?, server, panel?, device?}. device "shelly" (Shelly
    Wall Display, Standard) setzt den Launcher als Startbildschirm - die
    Shelly-Oberflaeche hat kein App-Menue. device "android" (andere Tablets,
    Testing) laesst den Startbildschirm in Ruhe; dort erscheint die App normal
    im App-Menue. `server` ist die Adresse, unter der
    die Panels diesen Server erreichen (z.B. "192.168.1.10:8098") - die kennt
    nur der Aufrufer (LoxBerry-Seite), nicht der Container selbst.

    Schritte: verbinden -> installieren -> als Startbildschirm setzen -> URL
    eintragen (startet Fully). Antwort mit Protokoll je Schritt. Fully Kiosk
    selbst ist kommerziell und wird nicht mitgeliefert - fehlt es, gibt es
    einen Hinweis."""
    d = await _json_or_empty(request)
    try:
        ip = str(ipaddress.ip_address(str(d.get("ip") or "").strip()))
        port = int(d.get("port") or 5555)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "ungueltige Panel-IP/Port"}, status=400)
    server = str(d.get("server") or "").strip()
    panel = str(d.get("panel") or "").strip()
    device = str(d.get("device") or "shelly").strip()
    if device not in ("shelly", "android"):
        return web.json_response({"ok": False, "error": "unbekannter Geraetetyp"}, status=400)
    if not re.match(r"^[A-Za-z0-9.\-]{1,253}(:\d{1,5})?$", server):
        return web.json_response({"ok": False, "error": "Server-Adresse fehlt/ungueltig"}, status=400)
    if panel and not re.match(r"^[a-z0-9-]{1,60}$", panel):
        return web.json_response({"ok": False, "error": "ungueltige Profil-ID"}, status=400)
    if not 1 <= port <= 65535:
        return web.json_response({"ok": False, "error": "ungueltiger Port"}, status=400)
    if not shutil.which("adb"):
        return web.json_response({"ok": False, "error": "adb fehlt im Container (Image neu bauen)"})
    if not LAUNCHER_APK.is_file():
        return web.json_response({"ok": False, "error": "LoxPanel-Launcher.apk fehlt im Container"})

    target = f"{ip}:{port}"
    name = str(d.get("name") or "").strip()[:60]   # Geraetename -> erscheint unter Geraete
    q = ([f"panel={panel}"] if panel else []) + ([f"device={quote(name)}"] if name else [])
    url = f"http://{server}/" + ("?" + "&".join(q) if q else "")
    steps: list[dict] = []

    def step(name: str, code: int, out: str, ok: bool | None = None) -> bool:
        ok = (code == 0) if ok is None else ok
        steps.append({"step": name, "ok": ok, "out": out[-400:]})
        return ok

    async with _adb_lock:
        code, out = await _adb("connect", target, timeout=15)
        # "connected to" / "already connected" - sonst (z.B. "failed to connect") Abbruch.
        if not step("Verbinden", code, out, ok=("connected" in out and "failed" not in out)):
            return web.json_response({"ok": False, "steps": steps,
                                      "error": "Panel nicht erreichbar - ADB/Entwickleroptionen am Panel aktiv?"})
        code, out = await _adb("-s", target, "get-state", timeout=10)
        if not step("Freigabe", code, out, ok=(out == "device")):
            return web.json_response({"ok": False, "steps": steps,
                                      "error": "Am Panel \"USB-Debugging zulassen\" bestaetigen "
                                               "(\"Immer erlauben\" anhaken) und erneut klicken."})
        # Schon gleiche/neuere Version drauf? Dann Installieren ueberspringen.
        apk_ver = _launcher_bundled_ver()   # 0 = unbekannt -> immer installieren
        code, out = await _adb("-s", target, "shell", "dumpsys", "package", LAUNCHER_PKG, timeout=15)
        have_ver = _launcher_ver_of(out) if code == 0 else 0
        if apk_ver and have_ver >= apk_ver:
            step("Installieren", 0, f"Version {have_ver} schon installiert - uebersprungen")
        else:
            code, out = await _adb("-s", target, "install", "-r", str(LAUNCHER_APK), timeout=120)
            if not step("Installieren", code, out, ok=("Success" in out)):
                return web.json_response({"ok": False, "steps": steps, "error": "Installation fehlgeschlagen"})
        # Nutzungsstatistik erlauben: Launcher erkennt laufendes Fully und holt es
        # nur nach vorn statt neu zu laden. Fehlt das Recht, laedt er wie bisher.
        code, out = await _adb("-s", target, "shell", "appops", "set", LAUNCHER_PKG,
                               "GET_USAGE_STATS", "allow", timeout=10)
        step("Nutzungsstatistik", code, out or "erlaubt", ok=(code == 0 and "rror" not in out))
        # Fully Kiosk vorhanden? Nicht mitgeliefert (kommerziell) -> nur Hinweis.
        code, out = await _adb("-s", target, "shell", "pm", "path", "de.ozerov.fully", timeout=10)
        has_fully = "package:" in out
        step("Fully Kiosk", 0, "installiert" if has_fully
             else "fehlt - bitte von fully-kiosk.com installieren", ok=has_fully)
        if device == "shelly":
            # Startbildschirm: schlaegt auf alten Android-Versionen fehl - dann
            # waehlt man ihn beim ersten Druck auf Home ("Immer"). Kein Abbruch.
            code, out = await _adb("-s", target, "shell", "cmd", "package", "set-home-activity",
                                   f"{LAUNCHER_PKG}/.Home", timeout=15)
            step("Startbildschirm", code, out, ok=(code == 0 and "rror" not in out))
        # URL speichern (startet dabei Fully). adb shell setzt die Argumente zu
        # einer Kommandozeile zusammen -> URL fuer die Shell am Panel quoten.
        code, out = await _adb("-s", target, "shell",
                               f"am start -n {LAUNCHER_PKG}/.Main --es url {shlex.quote(url)}", timeout=15)
        if not step("URL eintragen", code, out, ok=(code == 0 and "rror" not in out)):
            return web.json_response({"ok": False, "steps": steps, "error": "URL konnte nicht gesetzt werden"})
    log.info("LoxPanel-Launcher auf %s eingerichtet (%s, URL %s)", target, device, url)
    return web.json_response({"ok": True, "steps": steps, "url": url, "fully": has_fully,
                              "version": max(apk_ver, have_ver)})


async def font_handler(request: web.Request) -> web.Response:
    """Self-gehostete Schriftdatei (Manrope, SIL OFL - frei redistributierbar)
    ausliefern. Kein CDN/Google Fonts: das Panel muss auch ohne Internet-
    zugang funktionieren (Kiosk-Geraet im lokalen Netz)."""
    name = request.match_info.get("name", "")
    if ".." in name or "/" in name or not name.endswith(".woff2"):
        return web.Response(status=400)
    f = _FONT_DIR / name
    if not f.is_file():
        return web.Response(status=404)
    return web.Response(body=f.read_bytes(), content_type="font/woff2",
                        headers={"Cache-Control": "max-age=2592000, immutable"})


# Icons vom Miniserver: nur Dateinamen bzw. EIN Ordner (IconsFilled/x.svg) und
# keine Befehls-/Datenpfade. Sonst liesse sich ueber /icon?p=jdev/sps/io/<uuid>/On.png
# mit dem Token des Servers jeder Miniserver-Befehl ausloesen (Sicherheits-Audit).
_ICON_PATH_RE = re.compile(r"^[A-Za-z0-9_\- ]+(/[A-Za-z0-9_\-. ]+)?\.(svg|png)$")
_ICON_DENY = {"jdev", "dev", "data", "stats", "sps", "audio", "admin", "upgrade", "update", "ws", "binstatisticdata"}


def _icon_path_ok(p: str) -> bool:
    return bool(p) and ".." not in p and bool(_ICON_PATH_RE.match(p)) \
        and p.split("/", 1)[0].lower() not in _ICON_DENY


async def icon_handler(request: web.Request) -> web.Response:
    app: App = request.app["app"]
    p = request.query.get("p", "")
    if not _icon_path_ok(p):
        return web.Response(status=400, text="bad icon")
    res = await app.fetch_icon(p)
    if not res:
        return web.Response(status=404)
    body, ctype = res
    if not (ctype.lower().startswith("image/") or ctype.lower().startswith("application/octet-stream")):
        return web.Response(status=404)
    return web.Response(body=body, content_type=ctype.split(";")[0],
                        headers={"Cache-Control": "max-age=86400"})


async def loxicons_handler(request: web.Request) -> web.Response:
    """Namen der Loxone-Bibliothek (fuer den Kachel-Editor, lazy geladen)."""
    return web.json_response({"icons": _loxlib_names(),
                              "ms": ["IconsFilled/" + n for n in _msicons_names()]})


async def loxlib_handler(request: web.Request) -> web.Response:
    """Ein SVG der Loxone-Bibliothek aus dem gemounteten Ordner ausliefern.
    Nur flache, validierte Dateinamen - kein Pfad-Ausbruch."""
    n = request.query.get("n", "")
    if not _LOXLIB_NAME.match(n) or ".." in n:
        return web.Response(status=400, text="bad")
    path = os.path.join(LOXLIB_DIR, n)
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(LOXLIB_DIR):
        return web.Response(status=400, text="bad")
    try:
        with open(path, "rb") as f:
            body = f.read()
    except OSError:
        return web.Response(status=404)
    return web.Response(body=body, content_type="image/svg+xml",
                        headers={"Cache-Control": "max-age=86400"})


def _cover_host_ok(u: str) -> bool:
    """Cover-Bilder kommen vom Audioserver (LAN) oder aus dem Internet - aber nie
    von localhost/Link-Local (z.B. Dienste auf dem LoxBerry selbst)."""
    try:
        host = (urlparse(u).hostname or "").lower()
    except ValueError:
        return False
    if not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True                                   # Name: wird normal aufgeloest
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast)


async def cover_handler(request: web.Request) -> web.Response:
    app: App = request.app["app"]
    u = request.query.get("u", "")
    if not (u.startswith("http://") or u.startswith("https://")) or not _cover_host_ok(u):
        return web.Response(status=400, text="bad cover")
    res = await app.fetch_cover(u)
    if not res:
        return web.Response(status=404)
    body, ctype = res
    return web.Response(body=body, content_type=ctype.split(";")[0],
                        headers={"Cache-Control": "max-age=60"})


class CamHub:
    """EINE Verbindung zur Kamera je Tuerstation, verteilt an beliebig viele
    Betrachter (Panels, Laptop, Klingel-Popup).

    Frueher beendete jede neue Anfrage den laufenden Stream derselben Kamera
    (viele Tuerstationen, u.a. DoorBird, erlauben nur wenige Betrachter). Schaute
    ein zweites Geraet das Dashboard an - z.B. morgens der Laptop -, riss das dem
    Wandpanel den Stream ab; dessen <img> zeigte dann das letzte Bild "haengend"
    weiter, ohne Fehler und damit ohne Neuaufbau.

    Jetzt: der Verteiler liest die Kamera einmal, zerlegt den MJPEG-Strom in
    Einzelbilder und schickt sie mit eigener Trennmarke an alle Betrachter.
    Bricht die Kamera ab (Neustart, WLAN, Timeout), baut er die Verbindung im
    Hintergrund neu auf - die Verbindung zum Browser bleibt dabei offen und das
    Bild laeuft danach einfach weiter. Ohne Betrachter wird die Kamera getrennt."""

    BOUNDARY = "loxpanelframe"
    RETRY_S = 3.0

    def __init__(self, uuid: str, url: str, auth):
        self.uuid, self.url, self.auth = uuid, url, auth
        self.subs: set[asyncio.Queue] = set()
        self.last: bytes | None = None          # letztes Bild -> neuer Betrachter sieht sofort etwas
        self.task: asyncio.Task | None = None
        self.ok = False                          # Kamera liefert gerade
        self._idle = None                         # Nachlauf-Timer ohne Betrachter

    def same(self, url: str, auth) -> bool:
        return self.url == url and self.auth == auth

    IDLE_KEEP_S = 60.0                           # nach dem letzten Betrachter noch so lange verbunden bleiben

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=3)
        if self.last:
            q.put_nowait(self.last)
        self.subs.add(q)
        if self._idle:            # schnell zurueckgeschaltet -> Verbindung bleibt
            self._idle.cancel()
            self._idle = None
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self._run())
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs.discard(q)
        if not self.subs and self.task and not self.task.done() and not self._idle:
            # Erst nach einer Weile ohne Betrachter trennen: beim Umschalten zwischen
            # Kameras (Pillen) ist die Verbindung dann sofort wieder da.
            self._idle = asyncio.get_running_loop().call_later(self.IDLE_KEEP_S, self._idle_stop)

    def _idle_stop(self) -> None:
        self._idle = None
        if not self.subs and self.task and not self.task.done():
            self.task.cancel()                   # keiner schaut mehr -> Kamera freigeben

    def stop(self) -> None:
        if self._idle:
            self._idle.cancel()
            self._idle = None
        if self.task and not self.task.done():
            self.task.cancel()

    def _push(self, frame: bytes) -> None:
        if not frame:
            return
        self.last = frame
        for q in list(self.subs):
            if q.full():                         # langsamer Betrachter: aeltestes Bild verwerfen
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(frame)

    async def _run(self) -> None:
        fails = 0                                # Fehlversuche in Folge -> wachsende Pause
        while self.subs or self._idle:
            sess = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30))
            try:
                async with sess.get(self.url, auth=self.auth) as up:
                    if up.status != 200:
                        raise aiohttp.ClientError(f"camera status {up.status}")
                    ct = up.headers.get("Content-Type", "")
                    m = re.search(r'boundary="?([^";]+)"?', ct)
                    mark = (b"--" + m.group(1).lstrip("-").encode()) if m else None
                    buf = b""
                    async for chunk in up.content.iter_any():
                        if not self.ok and fails:
                            log.info("Kamera %s liefert wieder", self.uuid[:8])
                        self.ok = True
                        fails = 0
                        buf += chunk
                        buf = self._frames(buf, mark)
                        if len(buf) > 8 * 1024 * 1024:   # Unsinn vom Geraet nicht unbegrenzt puffern
                            buf = b""
                    if buf and not mark:                  # Einzelbild statt Stream
                        self._push(buf)
            except asyncio.CancelledError:
                await sess.close()
                raise
            except Exception as e:                       # jeder Fehler -> neuer Versuch, nie still enden
                fails += 1
                # Einmal sichtbar, danach leise (Kamera offline -> sonst alle 3 s eine Zeile)
                (log.info if fails == 1 else log.debug)("Kamera %s: %s - neuer Versuch in %.0f s",
                                                        self.uuid[:8], e, self._wait(fails))
            finally:
                self.ok = False
                if not sess.closed:
                    await sess.close()
            if self.subs or self._idle:
                await asyncio.sleep(self._wait(fails))

    def _wait(self, fails: int) -> float:
        """Pause vor dem naechsten Versuch: 3 s, dann wachsend bis 30 s bei Dauerausfall."""
        return min(30.0, self.RETRY_S * 2 ** max(0, fails - 1))

    def _frames(self, buf: bytes, mark: bytes | None) -> bytes:
        """Vollstaendige JPEG-Bilder aus dem Puffer an die Betrachter, Rest zurueck."""
        if mark:
            while True:
                a = buf.find(mark)
                if a < 0:
                    return buf[-len(mark):] if len(buf) > len(mark) else buf
                b = buf.find(mark, a + len(mark))
                if b < 0:
                    return buf[a:]
                part = buf[a + len(mark):b]
                h = part.find(b"\r\n\r\n")
                body = part[h + 4:] if h >= 0 else part
                s0 = body.find(b"\xff\xd8")
                e0 = body.rfind(b"\xff\xd9")
                if s0 >= 0 and e0 > s0:
                    self._push(body[s0:e0 + 2])
                buf = buf[b:]
        # ohne Trennmarke: JPEG-Start/-Ende suchen
        while True:
            s0 = buf.find(b"\xff\xd8")
            if s0 < 0:
                return b""
            e0 = buf.find(b"\xff\xd9", s0 + 2)
            if e0 < 0:
                return buf[s0:]
            self._push(buf[s0:e0 + 2])
            buf = buf[e0 + 2:]


async def mjpeg_handler(request: web.Request) -> web.StreamResponse:
    """MJPEG der Tuerstation (mit Auth) an den Browser - ueber den CamHub, damit
    alle Betrachter dieselbe EINE Kamera-Verbindung teilen (siehe CamHub).

    Eigene ClientSession je Verteiler (nicht icon_session): mit dem SSL-Connector
    der icon_session liefert die Mobotix nur ein Einzelbild statt des Streams."""
    app: App = request.app["app"]
    uuid = request.query.get("id", "")
    ent = app.intercom_cfg.get(uuid)
    url = ent.get("url") if isinstance(ent, dict) else ent
    if not url:
        return web.Response(status=404)
    auth = None
    if isinstance(ent, dict) and ent.get("user"):
        auth = aiohttp.BasicAuth(ent.get("user", ""), ent.get("pass", ""))

    # Bildrate je Betrachter begrenzen (?fps=): das Dashboard-Widget braucht keine
    # 15 Bilder/s - schwache Panels (Shelly) muessten jedes Bild dekodieren.
    try:
        fps = max(0.0, min(30.0, float(request.query.get("fps", "0"))))
    except ValueError:
        fps = 0.0
    gap = 1.0 / fps if fps else 0.0

    hub = app._cam_hubs.get(uuid)
    if hub and not hub.same(url, auth):          # URL/Zugang geaendert -> neu
        hub.stop()
        hub = None
    if not hub:
        hub = app._cam_hubs[uuid] = CamHub(uuid, url, auth)
    q = hub.subscribe()

    # Erstes Bild abwarten: kommt binnen 12 s keins, Fehler melden (das Panel
    # versucht es dann nach 8 s erneut und zeigt "Kamera nicht erreichbar")
    try:
        first = await asyncio.wait_for(q.get(), timeout=12)
    except asyncio.TimeoutError:
        hub.unsubscribe(q)
        return web.Response(status=502, text="camera unreachable")

    # ?single=1: nur das aktuelle Einzelbild (schwache Panels holen so 1-2 Bilder/s,
    # statt einen Dauerstrom zu dekodieren - der Speicher des Browsers bleibt begrenzt).
    # Der Verteiler bleibt danach noch IDLE_KEEP_S verbunden, das naechste Bild ist frisch.
    if request.query.get("single"):
        hub.unsubscribe(q)
        while not q.empty():
            first = q.get_nowait()
        return web.Response(body=first, content_type="image/jpeg",
                            headers={"Cache-Control": "no-cache, no-store"})

    bnd = CamHub.BOUNDARY
    resp = web.StreamResponse(status=200, headers={
        "Content-Type": f"multipart/x-mixed-replace; boundary={bnd}",
        "Cache-Control": "no-cache, no-store"})
    try:
        await resp.prepare(request)
        frame = first
        while True:
            head = (f"--{bnd}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n").encode()
            # Timeout auf das Schreiben: liest ein eingefrorener Browser nicht mehr
            # mit, wird er abgehaengt statt die Verteilung aufzuhalten.
            await asyncio.wait_for(resp.write(head + frame + b"\r\n"), timeout=15)
            sent = time.monotonic()
            # Kommt lange kein Bild (Kamera still), regelmaessig pruefen, ob der
            # Browser noch da ist - sonst haelt ein verwaister Betrachter die Kamera ewig.
            while True:
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=20)
                    break
                except asyncio.TimeoutError:
                    if request.transport is None or request.transport.is_closing():
                        raise ConnectionError("Betrachter weg")
            if gap:
                # Bis zum naechsten erlaubten Zeitpunkt warten, dann das NEUESTE Bild nehmen
                wait = gap - (time.monotonic() - sent)
                if wait > 0:
                    await asyncio.sleep(wait)
                while not q.empty():
                    frame = q.get_nowait()
    except (aiohttp.ClientError, ConnectionError, asyncio.CancelledError, asyncio.TimeoutError):
        pass                                     # Betrachter weg (Seite zu, WLAN) - kein Fehler
    finally:
        hub.unsubscribe(q)
    return resp


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    app: App = request.app["app"]
    ws = web.WebSocketResponse(heartbeat=30)    # halb offene Verbindungen (WLAN weg) nach ~60 s erkennen
    await ws.prepare(request)
    dev = (request.query.get("device", "") or "").strip()[:60]
    uid = (request.query.get("uid", "") or "").strip()
    uid = uid if _UID_RE.match(uid) else ""
    if not dev and uid:
        dev = app.devinfo_name(uid)      # bekannt: Name ueber die Geraete-ID (IP egal)
    pid = request.query.get("panel", "")
    # Frisch verbundenes Geraet direkt auf den aktuell laufenden Betriebsmodus
    # setzen (statt der Start-Ansicht aus ?panel=), falls dafuer eine Zuordnung
    # existiert -> ohne Reload-Flackern gleich die richtige Visu.
    if dev and app.last_mode:
        cfg = app.devices.get(dev)
        if cfg and cfg.get("auto", True):
            mapped = (cfg.get("modes") or {}).get(app.last_mode)
            if mapped:
                pid = mapped
    prof = app.resolve_profile(pid)
    app.conn_prof[ws] = prof
    app.conn_dev[ws] = dev
    kiosk = request.query.get("kiosk", "")
    # Fully auch am Browser-Kennzeichen erkennen (ohne PLUS fehlt oft ?kiosk=fully)
    if not kiosk and "fully" in (request.headers.get("User-Agent") or "").lower():
        kiosk = "fully"
    app.conn_info[ws] = {"dev": dev, "kiosk": kiosk if kiosk == "fully" else "",
                         "ip": request.remote or "", "ts": time.time()}
    first_tab = prof["tabs"][0] if prof["tabs"] else "favoriten"
    app.conn_route[ws] = {"view": "tab", "tab": first_tab}
    log.info("Panel verbunden: '%s' (Tabs %s, Räume %s, Kategorien %s)", prof["id"],
             prof["tabs"], "alle" if prof["rooms"] is None else len(prof["rooms"]),
             "alle" if prof["cats"] is None else len(prof["cats"]))
    # Display-Einstellungen gehen auch an die Visu: ohne Agent (Android-Panel,
    # Tablet mit Kiosk-App) schaltet die Seite das Display selbst ab und laedt
    # sich periodisch neu. `agent` sagt ihr, ob ein Agent das uebernimmt.
    # Ab hier alles im try: bricht die Verbindung schon waehrend der ersten
    # Sendungen ab, raeumt finally die eben angelegten Eintraege trotzdem weg.
    try:
        await app._send_or_drop(ws, {"t": "theme", "vars": prof["vars"], "tabs": prof["tabs"],
                            "tabMeta": app._tab_meta(prof["tabs"], prof), "title": prof["title"],
                            "lang": prof["lang"], "fill": prof["fill"], "split": prof["split"],
                            "phone": prof.get("phone", False),
                            "scale": app.effective_scale(dev),
                            "wake": bool((DEVICE_MODELS.get(((app.devices.get(dev) or {}) if dev else {}).get("model") or "") or {}).get("wake")),
                            # Schwache Panels (Shelly, 2 GB): Kamera als Einzelbilder, keine Glas-Unschaerfe
                            "lite": bool((DEVICE_MODELS.get(((app.devices.get(dev) or {}) if dev else {}).get("model") or "") or {}).get("shelly")),
                            "panes": prof.get("panes") or {},
                            "dpmsOff": app.panel_dpms(prof["id"]),
                            "reloadHours": app.panel_reload(prof["id"]),
                            "reloadAt": NEULADEN_STUNDE,   # nachts neu laden, wenn reloadHours fehlt
                            "night": {**app.panel_night(prof["id"]), "on": app._night_on},
                            "screensaverCam": app._screensaver_cam(),
                            "camCrop": app.cam_crops(),
                            "motion": prof["motion"],
                            "contrast": prof["contrast"],
                            "sceneLight": prof["sceneLight"],
                            "iconAnim": prof["iconAnim"],
                            "saver": prof.get("saver"),
                            "ambBg": prof.get("ambBg", ""), "ambClock": prof.get("ambClock", ""),
                            "bgImg": bg_url(prof["id"]) if prof.get("ambBg") == "image" else "",
                            "agent": app._has_agent(dev),
                            # ?panel=<unbekannt>: Standard wird gezeigt, Panel meldet das sichtbar
                            "missing": pid if (pid and pid not in app.panels) else ""})
        _first = app.render(app.conn_route[ws], prof)
        await app._send_or_drop(ws, _first)
        app._last_sent.setdefault(ws, {})["view"] = _first
        # Player-Pane fordert der Client selbst an (setplayer), sobald ein Tab mit
        # Player-Pane aktiv ist — je Tab eine eigene Zone moeglich.
        # Kalender/Wetter fuer die Uhr-Startseite sofort mitschicken (falls schon geladen)
        if app._front is not None:
            await app._send_or_drop(ws, app._front)
        _sv = app.saver_data(prof)
        if _sv is not None:
            await app._send_or_drop(ws, _sv)
            app._last_sent.setdefault(ws, {})["saver"] = _sv
        await app._send_or_drop(ws, {"t": "ms", "ok": app.ms_ok(), "since": int(app.ms_down_since * 1000)})
        await app._send_or_drop(ws, {"t": "cmdwatch", "on": app.cmd_watch})
        await app._send_or_drop(ws, {"t": "diag", "on": app.diag})
        await app._send_or_drop(ws, {"t": "clock", **server_clock()})
        # Klingelt es gerade noch (bell-Impuls steht an), bekommt auch ein neu
        # bzw. wieder verbundenes Panel das Klingeln. Ein Panel, das waehrend des
        # Klingelns schlief, hat sonst das Ende verpasst und klingelt ewig weiter
        # (Panel raeumt beim Verbinden selbst auf, s. ws.onopen).
        for _bu, _cid in app.bell_map.items():
            if app.states.get(_bu):
                _ent = app.intercom_cfg.get(_cid)
                _snd = bool(_ent.get("sound")) if isinstance(_ent, dict) else False
                _sf = _sound_file_for(_cid) if _snd else None
                await app._send_or_drop(ws, {"t": "ring", "id": _cid, "on": True, "sound": _snd,
                                    "soundUrl": (f"/api/sound?id={_cid}" if _sf else None)})
        # Laeuft gerade ein Alarm, zeigt auch ein neu verbundenes Panel das Vollbild
        for _au in app.sec_alarms_active():
            if app.sec_alarm_wanted(prof, _au):
                await app._send_or_drop(ws, {**app.sec_alarm_msg(_au, True), "sound": bool(prof.get("alarmTone"))})
        cmd_q: asyncio.Queue = asyncio.Queue()
        cmd_task = None

        async def _cmd_worker() -> None:
            """Fuehrt die Befehle dieses Panels nacheinander aus und quittiert sie."""
            while True:
                data = await cmd_q.get()
                if data is None:                 # Panel getrennt: Rest abgearbeitet, Ende
                    return
                pin = data.get("pin")
                code = await app.command(str(data.get("uuid") or ""), str(data.get("cmd") or ""),
                                         None if pin is None else str(pin))
                pu = app.push_uuid(str(data.get("uuid") or "")) if data.get("cmd") == "pulse" else None
                if pu:                           # Taster: mit Ergebnis in die Historie
                    app.push_record(pu, code == "200", dev or "Panel")
                if data.get("id") is not None:
                    # Quittung fuer das Befehls-Monitoring des Panels
                    await app._send_or_drop(ws, {"t": "cmdack", "id": data.get("id"), "ok": code == "200"})
                if pin is not None:
                    await app._send_or_drop(ws, {"t": "cmdresult", "ok": code == "200"})
                elif code != "200" and data.get("uuid") and data.get("cmd"):
                    # Sichtbar machen statt still verschlucken (Details im Log)
                    await app._send_or_drop(ws, {"t": "notify", "level": "warn", "secs": 4, "text":
                                        "Befehl nicht ausgeführt – Miniserver antwortet nicht" if code is None
                                        else f"Befehl nicht ausgeführt (Miniserver meldet {code})"})

        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("t") == "nav" and isinstance(data.get("route"), dict):
                route = data["route"]
                app.conn_route[ws] = route
                try:
                    view_msg = app.render(route, app.conn_prof.get(ws, prof))
                except Exception:
                    # Detailseite wirft -> nicht die Verbindung abreissen lassen
                    # (sonst Reconnect-Loop). Fehler loggen, Hinweis anzeigen.
                    log.exception("render() (nav) fehlgeschlagen fuer route %s", route)
                    view_msg = {"t": "view", "title": "Fehler", "route": route,
                                "blocks": [{"k": "status", "text": "Diese Ansicht konnte nicht geladen werden."}]}
                await app._send_or_drop(ws, view_msg)
                # Auch die Navigation sendet am Tick vorbei — eintragen, sonst
                # schickt der naechste Tick dieselbe Ansicht ein zweites Mal.
                app._last_sent.setdefault(ws, {})["view"] = view_msg
                # Beim Oeffnen einer AudioZone / Musikauswahl die Zonen-Favoriten
                # aktiv anfordern; das frische Ergebnis wird per broadcaster
                # nachgereicht (roomfav/get befuellt den sourceList-State).
                if route.get("view") in ("control", "sources") and route.get("id"):
                    app._spawn(app.prime_favs(route["id"]))
            elif data.get("t") == "ping":
                # Lebenszeichen des Panels: es erkennt so eine tote Verbindung.
                # Dazu die Serverzeit, damit falsch gestellte Geraete richtig anzeigen.
                await app._send_or_drop(ws, {"t": "pong", "at": data.get("at"), **server_clock()})
            elif data.get("t") == "devinfo" and uid:
                # Steckbrief -> Geraet erkennen/anlegen. Neu benannt: Name an die
                # Visu, die verbindet sich damit neu (Zoom/Wach-Sperre greifen).
                info = _clean_devinfo(data.get("info"))
                name, _new = app.device_detect(uid, dev, info, request.remote or "")
                if name != dev:
                    await app._send_or_drop(ws, {"t": "setdevice", "name": name})
            elif data.get("t") == "clog":
                # Diagnose: Ereignis vom Panel (Verbindungsabbruch, JS-Fehler ...)
                if app.diag:
                    log.info("Panel '%s': %s", dev or request.remote or "?", str(data.get("msg") or "")[:500])
            elif data.get("t") == "idle":
                # Visu ohne Kiosk-JS meldet Leerlauf -> Display ueber Treiber aus
                if dev:
                    app._spawn(app.display_drivers(False, dev))
            elif data.get("t") == "cmd":
                # In die Befehls-Warteschlange dieses Panels: Befehle laufen der Reihe
                # nach (schnelle +/- Tipps bleiben in Ordnung), aber die Verbindung
                # bleibt waehrenddessen ansprechbar (Ping, Navigation).
                if cmd_task is None or cmd_task.done():
                    cmd_task = asyncio.create_task(_cmd_worker())
                cmd_q.put_nowait(data)
            elif data.get("t") == "setplayer":
                # Client meldet die AudioZone der aktiven Player-Pane (oder "" = keine).
                zone = str(data.get("zone") or "").strip()
                if zone:
                    app.conn_player[ws] = zone
                    try:
                        pb = app.player_blocks(zone)
                        if pb is not None:
                            _pm = {"t": "player", "blocks": pb}
                            await app._send_or_drop(ws, _pm)
                            app._last_sent.setdefault(ws, {})["player"] = _pm
                    except Exception:
                        log.exception("player_blocks (setplayer) fehlgeschlagen (%s)", zone)
                else:
                    app.conn_player.pop(ws, None)
            elif data.get("t") == "setenergy":
                # Client meldet die EFM/EnergyManager2-Kachel der aktiven
                # Energiefluss-Pane (oder "" = keine).
                euid = str(data.get("uuid") or "").strip()
                if euid:
                    app.conn_energy[ws] = euid
                    try:
                        eb = app.energy_blocks(euid)
                        if eb is not None:
                            _em = {"t": "energy", **eb}
                            await app._send_or_drop(ws, _em)
                            app._last_sent.setdefault(ws, {})["energy"] = _em
                    except Exception:
                        log.exception("energy_blocks (setenergy) fehlgeschlagen (%s)", euid)
                else:
                    app.conn_energy.pop(ws, None)
            elif data.get("t") == "setchart":
                # Client meldet den Baustein der aktiven Verlaufs-Pane und den
                # dort gewaehlten Zeitraum (oder uuid "" = keine Pane).
                cuid = str(data.get("uuid") or "").strip()
                rng = data.get("range") if data.get("range") in STAT_RANGES else STAT_DEFAULT_RANGE
                if cuid:
                    app.conn_chart[ws] = (cuid, rng)
                    try:
                        cb = app.chart_blocks(cuid, rng)
                        if cb is not None:
                            _cm = {"t": "chart", **cb}
                            await app._send_or_drop(ws, _cm)
                            app._last_sent.setdefault(ws, {})["chart"] = _cm
                    except Exception:
                        log.exception("chart_blocks (setchart) fehlgeschlagen (%s)", cuid)
                else:
                    app.conn_chart.pop(ws, None)
            elif data.get("t") == "setcamera":
                # Client meldet die Intercom-Kachel der aktiven Kamera-Pane
                # (oder "" = keine).
                cuid = str(data.get("uuid") or "").strip()
                if cuid:
                    app.conn_camera[ws] = cuid
                    try:
                        ib = app.intercom_blocks(cuid)
                        if ib is not None:
                            _cm = {"t": "camera", "blocks": ib}
                            await app._send_or_drop(ws, _cm)
                            app._last_sent.setdefault(ws, {})["camera"] = _cm   # wie player/energy: Tick nicht doppelt senden
                    except Exception:
                        log.exception("intercom_blocks (setcamera) fehlgeschlagen (%s)", cuid)
                else:
                    app.conn_camera.pop(ws, None)
    finally:
        # Schon angetippte Befehle noch ausfuehren, dann endet die Warteschlange
        if locals().get("cmd_task") is not None:
            cmd_q.put_nowait(None)
        if app.diag:
            log.info("Panel '%s' Verbindung beendet (Close-Code %s)", dev or request.remote or "?", ws.close_code)
        app.drop_conn(ws)
    return ws


async def on_startup(a: web.Application) -> None:
    # HTTP-Server startet SOFORT; die Miniserver-Verbindung baut stream_task im
    # Hintergrund auf (mit Retry) — so ist /settings auch ohne/mit falschen
    # Zugangsdaten erreichbar.
    app: App = a["app"]
    _diag_apply(app.diag)
    a["tasks"] = [asyncio.create_task(app.stream_task()),
                  asyncio.create_task(app.broadcaster()),
                  asyncio.create_task(app.audio_events_task()),
                  asyncio.create_task(app.front_task())]


# ---- Zugriffsschutz (optional) und Schutz vor fremden Webseiten ----
# Passwort (optional, Startseite der Konfiguration): schuetzt /config, /settings und
# die Einstellungs-APIs. Panels, Loxone-Befehle (/api/mode, /api/notify ...), Bilder
# und der WebSocket bleiben frei. Die LoxBerry-Plugin-Seite ruft die API ueber ein
# lokales Token (config/.cgi_token) auf.
_ADMIN_PAGES = ("/config", "/settings")
_ADMIN_API = ("/api/settings", "/api/panels", "/api/theme", "/api/devices", "/api/device/",
              "/api/kiosk/", "/api/panel/launcher", "/api/agent/command", "/api/agents",
              "/api/tablayout", "/api/meta", "/api/types", "/api/testtone", "/api/testring",
              "/api/loxicons", "/api/admin/password", "/api/msstatus", "/api/msio",
              "/api/panel/bg")
_ADMIN_TTL = 30 * 86400                     # Anmeldung haelt 30 Tage (bis Server-Neustart)
_ADMIN_SESSIONS: dict[str, float] = {}
CGI_TOKEN_FILE = _CFGDIR / ".cgi_token"


def _admin_hash() -> str:
    a = _load_cfg().get("admin")
    return a.get("hash", "") if isinstance(a, dict) else ""


def _pw_hash(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${dk.hex()}"


def _pw_ok(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), int(it))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), dk)


def _cgi_token() -> str:
    try:
        return CGI_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _ensure_cgi_token() -> None:
    if _cgi_token():
        return
    try:
        CGI_TOKEN_FILE.write_text(os.urandom(24).hex(), encoding="utf-8")
        os.chmod(CGI_TOKEN_FILE, 0o644)       # LoxBerry-Plugin-Seite (Benutzer loxberry) liest es
    except OSError as e:
        log.warning("CGI-Token nicht schreibbar: %s", e)


def _is_admin(request: web.Request) -> bool:
    if not _admin_hash():
        return True                           # kein Passwort gesetzt -> frei wie bisher
    tok = request.headers.get("X-LoxPanel-Token", "")
    if tok and hmac.compare_digest(tok, _cgi_token() or "-"):
        return True
    sid = request.cookies.get("lp_admin", "")
    exp = _ADMIN_SESSIONS.get(sid)
    return bool(exp and exp > time.time())


def _needs_admin(path: str) -> bool:
    return path in _ADMIN_PAGES or path.startswith(_ADMIN_API)


def _foreign_origin(request: web.Request) -> bool:
    """True, wenn ein Browser die Anfrage von einer FREMDEN Seite schickt (Origin
    passt nicht zur aufgerufenen Adresse). Ohne Origin (Miniserver, LoxBerry,
    Agent, curl) ist alles wie bisher erlaubt."""
    o = request.headers.get("Origin")
    if o is None:
        return False
    try:
        return urlparse(o).netloc.lower() != (request.host or "").lower()
    except ValueError:
        return True


_LOGIN_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LoxPanel – Anmeldung</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d0f1a;font-family:system-ui,sans-serif;color:#1f2440}
form{background:#fff;border-radius:22px;padding:28px 26px;width:min(340px,90vw);box-shadow:0 20px 50px rgba(0,0,0,.35)}
h1{font-size:20px;margin:0 0 4px}p{margin:0 0 18px;color:#5d6282;font-size:14px}
input{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:12px;border:1px solid #d8d6e8;font-size:16px}
button{margin-top:14px;width:100%;padding:12px;border:0;border-radius:999px;background:#1f2440;color:#fff;font-size:15px;font-weight:600;cursor:pointer}
.err{color:#c0392b;font-size:13px;min-height:18px;margin-top:8px}</style></head><body>
<form id="f"><h1>LoxPanel</h1><p>Die Konfiguration ist mit einem Passwort geschützt.</p>
<input type="password" id="pw" placeholder="Passwort" autocomplete="current-password" autofocus>
<button>Anmelden</button><div class="err" id="e"></div></form>
<script>document.getElementById('f').onsubmit=async e=>{e.preventDefault();
const r=await fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('pw').value})});
const j=await r.json().catch(()=>({}));if(j.ok)location.reload();else document.getElementById('e').textContent=j.error||'Anmeldung fehlgeschlagen';};</script>
</body></html>"""


@web.middleware
async def security_mw(request: web.Request, handler):
    path = request.path
    # Schreibende Anfragen und WebSocket nur von der eigenen Seite (Schutz vor CSRF)
    if (request.method not in ("GET", "HEAD", "OPTIONS") or path == "/ws") and _foreign_origin(request):
        return web.json_response({"ok": False, "error": "fremde Herkunft abgelehnt"}, status=403)
    # Schaltende GET-Routen (fuer Loxone-Aufrufe gedacht) nicht von fremden Webseiten
    # ausloesen lassen (<img src=...>): Browser melden das per Sec-Fetch-Site; der
    # Miniserver schickt diesen Kopf nicht und bleibt unberuehrt.
    if (request.headers.get("Sec-Fetch-Site") == "cross-site"
            and path.startswith(("/api/display", "/api/notify", "/api/mode", "/api/reload",
                                 "/api/goto", "/api/testtone", "/api/testring"))):
        return web.json_response({"ok": False, "error": "fremde Herkunft abgelehnt"}, status=403)
    if _needs_admin(path) and not _is_admin(request):
        if path in _ADMIN_PAGES:
            return web.Response(text=_LOGIN_HTML, content_type="text/html",
                                headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})
        return web.json_response({"ok": False, "error": "Anmeldung nötig", "login": True}, status=401)
    resp = await handler(request)
    if path in _ADMIN_PAGES:
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"       # Konfiguration nicht in fremde Rahmen
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


async def api_admin_status(request: web.Request) -> web.Response:
    return web.json_response({"enabled": bool(_admin_hash()), "authed": _is_admin(request)})


async def api_admin_login(request: web.Request) -> web.Response:
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        d = {}
    h = _admin_hash()
    if not h:
        return web.json_response({"ok": True})
    if not _pw_ok(str(d.get("password") or ""), h):
        await asyncio.sleep(1.0)                  # Raten bremsen
        return web.json_response({"ok": False, "error": "Passwort falsch"}, status=403)
    now = time.time()
    for k in [k for k, v in _ADMIN_SESSIONS.items() if v < now]:
        _ADMIN_SESSIONS.pop(k, None)
    sid = os.urandom(24).hex()
    _ADMIN_SESSIONS[sid] = now + _ADMIN_TTL
    resp = web.json_response({"ok": True})
    resp.set_cookie("lp_admin", sid, max_age=_ADMIN_TTL, httponly=True, samesite="Lax", path="/")
    return resp


async def api_admin_logout(request: web.Request) -> web.Response:
    _ADMIN_SESSIONS.pop(request.cookies.get("lp_admin", ""), None)
    resp = web.json_response({"ok": True})
    resp.del_cookie("lp_admin", path="/")
    return resp


async def api_admin_password(request: web.Request) -> web.Response:
    """Passwort setzen/aendern/entfernen: {current?, new}. new leer = Schutz aus.
    Ist schon eins gesetzt, muss current stimmen."""
    try:
        d = await request.json()
    except (ValueError, aiohttp.ContentTypeError):
        return web.json_response({"ok": False, "error": "kein gültiges JSON"}, status=400)
    cfg = _load_cfg()
    old = (cfg.get("admin") or {}).get("hash", "") if isinstance(cfg.get("admin"), dict) else ""
    if old and not _pw_ok(str(d.get("current") or ""), old):
        await asyncio.sleep(1.0)
        return web.json_response({"ok": False, "error": "Aktuelles Passwort falsch"}, status=403)
    new = str(d.get("new") or "")
    if new and len(new) < 6:
        return web.json_response({"ok": False, "error": "Mindestens 6 Zeichen"}, status=400)
    if new:
        cfg["admin"] = {"hash": _pw_hash(new)}
    else:
        cfg.pop("admin", None)
    try:
        _write_cfg(cfg)
    except OSError as err:
        return web.json_response({"ok": False, "error": str(err)}, status=500)
    _ADMIN_SESSIONS.clear()
    resp = web.json_response({"ok": True, "enabled": bool(new)})
    if new:                                     # gleich angemeldet bleiben
        sid = os.urandom(24).hex()
        _ADMIN_SESSIONS[sid] = time.time() + _ADMIN_TTL
        resp.set_cookie("lp_admin", sid, max_age=_ADMIN_TTL, httponly=True, samesite="Lax", path="/")
    log.info("Zugriffsschutz der Konfiguration %s", "gesetzt" if new else "entfernt")
    return resp


async def on_shutdown(a: web.Application) -> None:
    """Beim Stoppen (Update/Neustart) offene Dauerverbindungen sofort schliessen:
    Panel-WebSockets und Kamera-Streams. Sonst wartet der Server darauf, bis
    Docker ihn nach 10 s hart beendet. Die Panels verbinden sich danach selbst neu."""
    app: App = a["app"]
    for hub in list(app._cam_hubs.values()):
        hub.stop()
    for ws in list(app.conn_prof.keys()):
        with contextlib.suppress(Exception):
            await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message=b"server restart")


async def on_cleanup(a: web.Application) -> None:
    for t in a.get("tasks", []):
        t.cancel()
    sess = a["app"]._drv_session
    if sess is not None and not sess.closed:
        await sess.close()
    await a["app"].close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.environ.get("LOXPANEL_PORT", "8099")))
    args = p.parse_args()

    _ensure_cgi_token()
    a = web.Application(middlewares=[security_mw])
    a["app"] = App(_config(), _audio_config(), _audiometa_config())
    a.router.add_get("/", index)
    a.router.add_get("/api/version", version_handler)
    a.router.add_get("/api/update", update_handler)
    a.router.add_get("/config", config_index)
    a.router.add_get("/settings", settings_index)
    a.router.add_get("/i18n.js", i18n_js)
    a.router.add_get("/install-agent.sh", install_script)
    a.router.add_get("/api/meta", api_meta)
    a.router.add_post("/api/panels", api_save_panels)
    a.router.add_post("/api/theme", api_save_theme)
    a.router.add_get("/api/settings", api_settings)
    a.router.add_get("/api/msstatus", api_msstatus)
    a.router.add_get("/api/types", api_types)
    a.router.add_post("/api/settings/miniserver", api_settings_ms)
    a.router.add_post("/api/settings/cmdwatch", api_settings_cmdwatch)
    a.router.add_get("/api/settings/diag", api_settings_diag)
    a.router.add_post("/api/settings/diag", api_settings_diag)
    a.router.add_get("/api/settings/diag/download", api_settings_diag_download)
    a.router.add_post("/api/settings/diag/clear", api_settings_diag_clear)
    a.router.add_post("/api/settings/intercom", api_settings_intercom)
    a.router.add_post("/api/settings/intercom/sound", api_settings_intercom_sound)
    a.router.add_post("/api/settings/intercom/sound/delete", api_settings_intercom_sound_delete)
    a.router.add_get("/api/sound", api_sound)
    a.router.add_post("/api/settings/night", api_settings_night)
    a.router.add_post("/api/settings/audiometa", api_settings_audiometa)
    a.router.add_post("/api/settings/calendar", api_settings_calendar)
    a.router.add_post("/api/settings/weather", api_settings_weather)
    a.router.add_post("/api/agent/announce", api_agent_announce)
    a.router.add_get("/api/agents", api_agents)
    a.router.add_post("/api/agent/command", api_agent_command)
    a.router.add_post("/api/devices", api_save_devices)
    a.router.add_get("/api/devices", api_devices_get)
    a.router.add_post("/api/device/switch", api_device_switch)
    a.router.add_get("/api/device/adblog", api_device_adblog)
    a.router.add_post("/api/device/name", api_device_name)
    a.router.add_post("/api/device/delete", api_device_delete)
    a.router.add_route("*", "/api/panel/bg", api_panel_bg)
    a.router.add_get("/bg/{pid}", bg_handler)
    a.router.add_post("/api/device/rename", api_device_rename)
    a.router.add_get("/api/msio", api_msio)
    a.router.add_get("/api/display", api_display)
    a.router.add_post("/api/display", api_display)
    a.router.add_post("/api/kiosk/restart", api_kiosk_restart)
    a.router.add_post("/api/kiosk/fully", api_kiosk_fully)
    a.router.add_route("*", "/api/kiosk/fully/source", api_kiosk_fully_source)
    a.router.add_post("/api/kiosk/fully/upload", api_kiosk_fully_upload)
    a.router.add_post("/api/kiosk/brightness", api_kiosk_brightness)
    a.router.add_post("/api/kiosk/touchsound", api_kiosk_touchsound)
    a.router.add_post("/api/tablayout", api_tab_layout)
    a.router.add_get("/api/mode", api_mode)
    a.router.add_post("/api/mode", api_mode)
    a.router.add_get("/api/mode/{mode}", api_mode)
    a.router.add_post("/api/mode/{mode}", api_mode)
    a.router.add_post("/api/testtone", api_testtone)
    a.router.add_post("/api/testring", api_testring)
    a.router.add_get("/api/reload", api_reload)
    a.router.add_post("/api/reload", api_reload)
    a.router.add_get("/api/goto", api_goto)
    a.router.add_post("/api/goto", api_goto)
    a.router.add_get("/api/notify", api_notify)
    a.router.add_post("/api/notify", api_notify)
    a.router.add_post("/api/panel/launcher", api_panel_launcher)
    a.router.add_post("/api/panel/launcher/version", api_panel_launcher_version)
    a.router.add_get("/icon", icon_handler)
    a.router.add_get("/fonts/{name}", font_handler)
    a.router.add_get("/appicon/{size}.png", appicon_handler)
    a.router.add_get("/manifest.webmanifest", manifest_handler)
    a.router.add_get("/loxlib", loxlib_handler)
    a.router.add_get("/api/loxicons", loxicons_handler)
    a.router.add_get("/cover", cover_handler)
    a.router.add_get("/mjpeg", mjpeg_handler)
    a.router.add_get("/ws", ws_handler)
    a.router.add_get("/api/admin/status", api_admin_status)
    a.router.add_post("/api/admin/login", api_admin_login)
    a.router.add_post("/api/admin/logout", api_admin_logout)
    a.router.add_post("/api/admin/password", api_admin_password)
    a.on_startup.append(on_startup)
    a.on_shutdown.append(on_shutdown)
    a.on_cleanup.append(on_cleanup)
    # kurze Gnadenfrist fuer laufende Anfragen, dann beenden (Docker gibt 10 s)
    # Kein Zugriffsprotokoll: jede Anfrage (Symbole, Healthcheck, Geraete-Abfrage
    # alle 6 s) waere eine Logzeile - ueber 90 % des Logs, ohne Nutzen.
    web.run_app(a, host="0.0.0.0", port=args.port, shutdown_timeout=3, access_log=None)


if __name__ == "__main__":
    main()
