# -*- coding: utf-8 -*-
"""Aenderungswuensche der Einsteller - aufnehmen, verfolgen, abhaken.

Ein Einsteller kann auf seiner Pferdeseite beantragen, dass sich etwas aendert:
mehr Raufutter, weniger Kraftfutter, ein anderes Zeitfenster am Selektionstor.
Der Wunsch geht an die Website und liegt dort; dieses Modul holt die offenen
Wuensche und vergleicht sie bei jedem Lauf mit dem, was der Rechner **jetzt**
sagt.

**Geaendert wird nichts.** Der CSV-Auszug ist rein lesend, und das soll er
bleiben - an einem laufenden Fuetterungsrechner etwas zu verstellen, waere ein
ganz anderes Wagnis als ihn zu lesen. Eintragen muss weiterhin ein Mensch am
Panel. Was dieses Modul kann, ist der Soll-Ist-Vergleich: steht der gewuenschte
Wert inzwischen im Auszug, gilt der Wunsch als erledigt und der Einsteller
sieht das auf seiner Seite, ohne dass jemand etwas abhaken muss.

Moeglich ist das nur, weil die betroffenen Felder am 18.08.2026 einzeln gegen
Panel-Aufnahmen geprueft wurden (STAND.md, Abschnitt 2b).

Vergleichsgrundlage je Art - bewusst der ANSPRUCH, nicht das Geholte:

    rf   Tagesanspruch Raufutter in Minuten     (100034 / 801406)
    kf   Tagesanspruch Kraftfutter in kg        (100014 / 900061)
    min  Tagesanspruch Mineralfutter in Gramm   (100016 / 900061)
    sel  Zutrittsfenster am Selektionstor       (100035 / 803503+803501)
"""
import json
import urllib.parse
import urllib.request

from . import einheiten

# Die Website haengt hinter einer Firewall, die Anfragen ohne Browser-Kennung
# mit "error code: 1010" abweist - und zwar fuer JEDE Adresse, auch fuer solche,
# die es gar nicht gibt. Ein 403 heisst hier also nicht "Schluessel falsch".
# Am 18.08.2026 eine Viertelstunde gekostet, weil bot._web_post die Kennung
# mitschickt und dieses Modul zuerst nicht.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "Chrome/120.0 Safari/537.36")

ARTEN = {
    "rf":  ("Raufutter", "Min"),
    "kf":  ("Kraftfutter", "kg"),
    "min": ("Mineralfutter", "g"),
    "sel": ("Zeit am Selektionstor", ""),
    "tnr": ("Transpondernummer", ""),
}
# Wieviel Abweichung noch als "eingetragen" gilt. Kraftfutter steht in kg mit
# drei Nachkommastellen, deshalb dort feiner.
TOLERANZ = {"rf": 0.5, "kf": 0.0005, "min": 0.5}


def _log(msg):
    print("[wunsch] %s" % msg, flush=True)


def _zahl(text):
    return einheiten.zahl(str(text).split(" ")[0])


def laden(api, secret, zeit=20):
    """Offene Wuensche holen -> (liste, fehler).

    'fehler' ist "" bei Erfolg, sonst der Grund. Sonst sieht eine nicht
    erreichbare Website genauso aus wie 'nichts offen' - und man haelt einen
    Ausfall fuer Ruhe.
    """
    if not (api and secret):
        return [], "keine Website hinterlegt"
    url = api + "/wuensche?key=" + urllib.parse.quote(secret)
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=zeit) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        _log("Wuensche nicht abrufbar: %s" % e)
        return [], str(e)
    return (d.get("wuensche", []) if isinstance(d, dict) else []), ""


def ist_wert(pferd, art):
    """Was der Rechner jetzt sagt - als Text, so wie er angezeigt wird."""
    if art == "tnr":
        return pferd.get("transponder") or "unbekannt"
    if art == "sel":
        fenster = pferd.get("zutrittszeiten") or []
        return ", ".join("%s-%s" % (f.get("von"), f.get("bis")) for f in fenster) or "kein Fenster"
    block = pferd.get(art) or {}
    return block.get("anspruch_gesamt") or ""


def erfuellt(pferd, art, wunsch):
    """Ist der Wunsch am Rechner eingetragen?

    Bei den Futterarten wird gerechnet, nicht auf Zeichen verglichen: '0,3' und
    '0.300 kg' sind derselbe Wert. Beim Selektionsfenster genuegt, dass EIN
    eingeschaltetes Fenster passt - es gibt fuenf, und welches benutzt wird,
    entscheidet das Hofbuero.
    """
    if art == "tnr":
        # Der Chip wird am Panel neu eingetragen; verglichen wird auf die
        # Ziffer genau - eine Transpondernummer ist keine Naeherung.
        return str(pferd.get("transponder") or "").strip() == str(wunsch).strip()
    if art == "sel":
        gewuenscht = str(wunsch).replace(" ", "").replace("–", "-")
        for f in (pferd.get("zutrittszeiten") or []):
            if "%s-%s" % (f.get("von"), f.get("bis")) == gewuenscht:
                return True
        return False
    block = pferd.get(art) or {}
    ist = _zahl(block.get("anspruch_gesamt"))
    soll = einheiten.zahl(str(wunsch).replace(",", "."))
    return abs(ist - soll) <= TOLERANZ.get(art, 0.5)


def pruefen(wuensche, pferde):
    """Wuensche gegen den aktuellen Stand halten.

    Rueckgabe: (erledigt, offen, zurueck_gewarnt, zurueck_still)

      erledigt         war offen, steht jetzt am Rechner -> abhaken
      offen            noch nicht eingetragen
      zurueck_gewarnt  zurueckgenommen, ABER am Rechner schon eingetragen
      zurueck_still    zurueckgenommen, nichts passiert -> stillschweigend zu

    Der dritte Fall ist der unangenehme: der Einsteller hat es sich anders
    ueberlegt, im Hofbuero war es aber schon umgestellt. Dann steht am
    Fuetterungsrechner ein Wert, den niemand mehr wollte - und ohne Warnung
    faellt das keinem auf.
    """
    nach_nr = {str(p.get("nr")): p for p in pferde}
    erledigt, offen, zurueck_gewarnt, zurueck_still = [], [], [], []
    for w in wuensche:
        art = w.get("art")
        if art not in ARTEN:
            continue
        pferd = nach_nr.get(str(w.get("nr")))
        if not pferd:
            continue                      # Pferd steht nicht mehr im Rechner
        w = dict(w)
        w["ist"] = ist_wert(pferd, art)
        w["name"] = pferd.get("name") or w.get("name") or ""
        passt = erfuellt(pferd, art, w.get("wunsch"))
        if w.get("status") == "zurueckgenommen":
            (zurueck_gewarnt if passt else zurueck_still).append(w)
        else:
            (erledigt if passt else offen).append(w)
    return erledigt, offen, zurueck_gewarnt, zurueck_still


def warntext(w):
    """Der Fall 'zurueckgenommen, aber schon eingetragen' im Klartext."""
    titel, _e = ARTEN.get(w.get("art"), ("?", ""))
    return ("Nr. %s %s: %s war auf %s gewuenscht und ist am Rechner bereits so "
            "eingetragen - der Wunsch wurde aber am %s zurueckgenommen. "
            "Bitte pruefen, ob der alte Wert wiederhergestellt werden soll."
            % (w.get("nr"), w.get("name", ""), titel, w.get("wunsch"),
               w.get("zurueck", "?")))


def abhaken(api, secret, wunsch, status="erledigt", grund="", zeit=20):
    """Der Website den Endstand melden (erledigt / geschlossen)."""
    if not (api and secret):
        return False
    url = api + "/wunsch_status?key=" + urllib.parse.quote(secret)
    daten = json.dumps({"id": wunsch.get("id"), "status": status, "grund": grund,
                        "ist": wunsch.get("ist", "")}).encode("utf-8")
    req = urllib.request.Request(url, data=daten, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=zeit) as r:
            return r.status == 200
    except Exception as e:
        _log("Abhaken fehlgeschlagen: %s" % e)
        return False


def text(w):
    """Ein Wunsch als eine Zeile Klartext - fuer Meldung und Oberflaeche."""
    titel, einheit = ARTEN.get(w.get("art"), ("?", ""))
    soll = str(w.get("wunsch", ""))
    if einheit and not soll.endswith(einheit):
        soll = "%s %s" % (soll, einheit)
    return "Nr. %s %s: %s auf %s (jetzt %s)" % (
        w.get("nr"), w.get("name", ""), titel, soll, w.get("ist", "?"))
