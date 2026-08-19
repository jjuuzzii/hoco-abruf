# -*- coding: utf-8 -*-
"""Welche Pferde werden ueberwacht - und welche ausdruecklich nicht.

Nicht jedes Tier an der Nummer ist ein Fall fuers Hofbuero: eins hat gar
keinen Transponder, eins steht auf der Weide, eins ist verkauft und die Nummer
noch nicht geraeumt. Solche Tiere meldet der Fuetterungsrechner jede Nacht als
'nicht erkannt' - richtig gerechnet, aber kein Fehler. Wer sie nicht abstellen
kann, gewoehnt sich an die Meldung, und dann faellt der echte Fall nicht mehr auf.

Hier steht deshalb je Pferdenummer, ob es ueberwacht wird. Ausgenommene Tiere
bekommen kein Urteil - weder in der Morgenmeldung noch im Dashboard noch auf
der Einsteller-Website. Ihre Zahlen stehen weiterhin ueberall.

Absichtlich an der NUMMER festgemacht, nicht am Namen: die Nummer ist das, was
der Rechner fuehrt. Steht an einer Nummer spaeter ein anderes Pferd, muss die
Ausnahme neu gesetzt werden - genau richtig, denn das neue Tier ist ein neuer
Fall (dieselbe Regel gilt schon fuer die Zugangsschluessel).

**Ausnahmen enden von selbst.** Wurde ein Tier stillgestellt, WEIL der Rechner
es nicht erkannte, und taucht es wieder an einer Station auf, dann ist der
Grund weg - die Ausnahme faellt automatisch weg (siehe wieder_erkannt). Sonst
haette der Stall nach dem Transponderwechsel ein still ueberwachtes Loch, das
niemandem mehr auffaellt. Wer dagegen ein Tier vorsorglich stillstellt, das
gerade ganz normal erkannt wird (Weide ab morgen), behaelt seine Ausnahme, bis
er sie selbst aufhebt - dafuer merkt sich jeder Eintrag, ob er aus einer
laufenden Meldung heraus gesetzt wurde.
"""
import json
import os
import threading
import time

DATA_DIR = "/data"
DATEI = os.path.join(DATA_DIR, "ueberwachung.json")

_lock = threading.Lock()
_aus = {}          # nr (str) -> {"grund": str, "wegen_hinweis": bool}


def _log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def _eintrag(wert):
    """Macht aus alten wie neuen Formen einen vollstaendigen Eintrag."""
    if isinstance(wert, dict):
        return {"grund": str(wert.get("grund") or "")[:80],
                "wegen_hinweis": bool(wert.get("wegen_hinweis"))}
    # bis 0.15.0 stand hier nur der Grund als Zeichenkette
    return {"grund": str(wert or "")[:80], "wegen_hinweis": False}


def laden():
    global _aus
    try:
        with open(DATEI, encoding="utf-8") as f:
            d = json.load(f)
        roh = d.get("aus", {}) if isinstance(d, dict) else {}
        if isinstance(roh, list):        # aeltere/einfachere Form: nur Nummern
            roh = {str(nr): "" for nr in roh}
        _aus = {str(k): _eintrag(v) for k, v in roh.items()}
    except Exception:
        _aus = {}
    return _aus


def _speichern():
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATEI + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"aus": _aus}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATEI)


def ist_aus(nr):
    return str(nr) in _aus


def grund(nr):
    return _aus.get(str(nr), {}).get("grund", "")


def ausgenommene():
    """Alle ausgenommenen Nummern als sortierte Liste von Strings."""
    return sorted(_aus, key=lambda s: (len(s), s))


def setzen(nr, aus, grund_text="", wegen_hinweis=False):
    """Ueberwachung fuer eine Pferdenummer aus- oder wieder einschalten.

    wegen_hinweis: Das Tier wurde stillgestellt, waehrend der Rechner es als
    'nicht erkannt' meldete. Nur solche Ausnahmen enden von selbst wieder."""
    nr = str(nr).strip()
    if not nr:
        return
    with _lock:
        if aus:
            _aus[nr] = _eintrag({"grund": str(grund_text or "").strip(),
                                 "wegen_hinweis": wegen_hinweis})
        else:
            _aus.pop(nr, None)
        _speichern()


def wieder_erkannt(nr, name=""):
    """Der Rechner sieht das Tier wieder - eine Melde-Ausnahme endet hier.

    Gibt True zurueck, wenn dadurch etwas geaendert wurde."""
    nr = str(nr).strip()
    with _lock:
        eintrag = _aus.get(nr)
        if not eintrag or not eintrag.get("wegen_hinweis"):
            return False
        _aus.pop(nr, None)
        _speichern()
    _log("Ueberwachung: Nr. %s %s wird wieder erkannt - Ausnahme aufgehoben."
         % (nr, name or ""))
    return True


laden()
