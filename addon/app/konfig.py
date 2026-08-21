# -*- coding: utf-8 -*-
"""Die Einstellungen des Add-ons - an einer Stelle, im Add-on selbst.

Bis 0.40.x standen sie in der Add-on-Konfiguration von Home Assistant und kamen
als Umgebungsvariablen an (run.sh). Das hiess: zwei Oberflaechen fuer dieselbe
Sache, und jede Aenderung brauchte einen Neustart - Umgebungsvariablen aendern
sich zur Laufzeit nicht.

Seit 0.41.0 liegen sie in /data/konfig.json. Die Ersteinrichtung im Panel
schreibt direkt hierher, und was dort gespeichert wird, gilt sofort.

Beim ersten Start nach dem Umstieg wird die Datei aus den bisherigen
Umgebungsvariablen erzeugt - niemand muss etwas neu eintragen.

Gelesen wird ueber `wert()`, nie ueber Modulkonstanten: eine Konstante haelt den
Stand vom Programmstart fest, und genau das soll hier nicht mehr passieren.
"""
import json
import os
import threading

DATA_DIR = "/data"
DATEI = os.path.join(DATA_DIR, "konfig.json")

# Kennung -> (Umgebungsvariable von frueher, Vorgabe)
#
# Die Umgebungsvariable dient nur noch der einmaligen Uebernahme und als
# Rueckfall, solange die Datei fehlt.
FELDER = {
    "stall_name":         ("STALL_NAME", ""),
    "hoco_host":          ("HOCO_HOST", ""),
    "hoco_verzeichnis":   ("HOCO_VERZEICHNIS", "/export"),
    "hoco_benutzer":      ("HOCO_BENUTZER", ""),
    "hoco_passwort":      ("HOCO_PASSWORT", ""),
    "hofbuero_notify":    ("ABRUF_HOFBUERO_NOTIFY", ""),
    "abruf_takt_minuten": ("ABRUF_TAKT_MINUTEN", "5"),
    "website_link":       ("WEBSITE_LINK", ""),
    "website_api":        ("WEBSITE_API", ""),
    "website_secret":     ("WEBSITE_SECRET", ""),
    "log_stufe":          ("ABRUF_LOG_STUFE", "info"),
}

_lock = threading.Lock()
_gemerkt = None


def _lesen():
    global _gemerkt
    if _gemerkt is not None:
        return _gemerkt
    try:
        with open(DATEI, encoding="utf-8") as f:
            d = json.load(f)
        _gemerkt = d if isinstance(d, dict) else {}
    except Exception:
        _gemerkt = {}
    return _gemerkt


def eigene_datei():
    """Steht die Konfiguration schon in /data - oder noch in der Umgebung?"""
    return os.path.exists(DATEI)


def alle():
    """Alle Einstellungen, Vorgaben eingesetzt."""
    d = _lesen()
    out = {}
    for kennung, (umgebung, vorgabe) in FELDER.items():
        gefunden = d.get(kennung)
        if gefunden is None or str(gefunden).strip() == "":
            # Solange die Datei fehlt oder ein Feld leer ist, gilt, was beim
            # Start in der Umgebung stand.
            gefunden = os.environ.get(umgebung, "").strip() or vorgabe
        out[kennung] = str(gefunden)
    return out


def wert(kennung, vorgabe=None):
    """Eine einzelne Einstellung - immer der aktuelle Stand."""
    gefunden = alle().get(kennung, "")
    if gefunden == "" and vorgabe is not None:
        return vorgabe
    return gefunden


def speichern(neue):
    """Uebernimmt geaenderte Werte und gibt den vollstaendigen Stand zurueck.

    Nur bekannte Kennungen werden geschrieben; ein Tippfehler im Formular legt
    also keine Karteileiche an.
    """
    global _gemerkt
    with _lock:
        d = dict(_lesen())
        for kennung, v in (neue or {}).items():
            if kennung in FELDER:
                d[kennung] = "" if v is None else str(v).strip()
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATEI + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATEI)
        _gemerkt = d
    return alle()


def uebernehmen_falls_noetig():
    """Erzeugt die Datei beim ersten Start aus den Umgebungsvariablen.

    Rueckgabe: die Anzahl uebernommener Werte, oder 0 - dann gab es nichts zu
    tun (Datei schon da oder Umgebung leer).
    """
    if eigene_datei():
        return 0
    aus_umgebung = {}
    for kennung, (umgebung, _vorgabe) in FELDER.items():
        vorhanden = os.environ.get(umgebung, "").strip()
        if vorhanden:
            aus_umgebung[kennung] = vorhanden
    if not aus_umgebung:
        return 0
    speichern(aus_umgebung)
    return len(aus_umgebung)


def fehlt():
    """Welche Angaben fehlen, damit ueberhaupt Daten geholt werden koennen."""
    d = alle()
    return [k for k in ("hoco_host", "hoco_verzeichnis", "hofbuero_notify")
            if not d.get(k)]
