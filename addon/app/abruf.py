# -*- coding: utf-8 -*-
"""Einen Datenabruf ausfuehren und alles ablegen, was danach kommt.

Es gibt nur noch einen Weg: den CSV-Vollauszug vom FTP des Fuetterungsrechners
(`hoco.py`). Der Bildschirmweg - Panel per Guacamole abfahren, aufnehmen, vom
Modell ablesen lassen - ist am 18.08.2026 ausgebaut worden, nachdem der Auszug
in fuenf Vergleichslaeufen bei geringem Zeitversatz **28 von 28** Pferden exakt
getroffen hat und die Ablesung umgekehrt Dinge lieferte, die es nicht gab
(ein erfundenes Pferd Nr. 28 samt Torzeiten).

Was mit ihm wegfiel: Guacamole-Zugang, Bildaufnahme, Modellanbindung und deren
Schluessel, Ziffernvorlagen, die Ein-Sitzungs-Sperre am Panel samt Pause-Knopf,
die Token-Abrechnung und die Umfaenge alles/ohne_min/schnell. Ein Auszug
enthaelt immer alles und kostet nichts - es gibt nichts mehr zu sparen.

Wer ihn zurueckholen muss, findet den vollstaendigen Stand in
`addon-sicherung-0.19.1-mit-ki/` (siehe STAND.md).
"""
import json
import os
import time

from . import archiv, hoco

SHARE_DIR = "/share/fuetterungsabruf"
PFERDE = os.path.join(SHARE_DIR, "pferde.json")


def _log(msg):
    print("[abruf] %s" % msg, flush=True)


def abrufen(scope="alles"):
    """Auszug holen, auswerten, ablegen. Rueckgabe ist der Klartext fuer die
    Oberflaeche.

    'scope' wird noch entgegengenommen, weil Zeitplan und Oberflaeche ihn
    mitgeben, aber nicht mehr ausgewertet: ein Auszug enthaelt immer alles.
    """
    try:
        ergebnis, name, alter = hoco.abrufen()
    except Exception as e:
        return "Fehler beim FTP-Abruf: %s" % e

    ergebnis["scope"] = "export"
    ergebnis["quelle"] = name

    os.makedirs(SHARE_DIR, exist_ok=True)
    with open(PFERDE, "w", encoding="utf-8") as f:
        json.dump(ergebnis, f, ensure_ascii=False, indent=2)

    try:
        n = archiv.schreiben(ergebnis)
        _log("Archiv: %d Zeilen angehaengt (%s)." % (n, os.path.basename(archiv.datei())))
    except Exception as e:
        _log("Archiv-Schreibfehler: %s" % e)

    # Tageshistorie: wie bisher nur die Laeufe vor dem 6-Uhr-Reset. Der letzte
    # davon gewinnt, weil jeder die Datei ueberschreibt - genauso hat es der
    # Bildschirmweg gemacht, und jede einzelne Messung steht ohnehin im Archiv.
    if time.localtime().tm_hour < 6:
        try:
            vdir = os.path.join(SHARE_DIR, "verlauf")
            os.makedirs(vdir, exist_ok=True)
            ziel = os.path.join(vdir, time.strftime("%Y-%m-%d") + ".json")
            with open(ziel, "w", encoding="utf-8") as f:
                json.dump(ergebnis, f, ensure_ascii=False, indent=2)
            _log("Tageshistorie gespeichert (%s)." % os.path.basename(ziel))
        except Exception as e:
            _log("Verlauf-Schnappschuss fehlgeschlagen: %s" % e)

    pferde = ergebnis.get("pferde", [])
    tore = sum(len(p.get("selektion") or []) for p in pferde)
    # Sitzt die Feldbelegung noch? Ein Befund gehoert in dieselbe Zeile wie
    # alles andere - er ist wichtiger als jede Futterzahl darin, denn wenn er
    # steht, sind die Futterzahlen moeglicherweise gar nicht die, fuer die wir
    # sie halten (siehe pruefung.py).
    befund = ergebnis.get("pruefung") or {}
    feldwarnung = ""
    if befund and not befund.get("ok"):
        feldwarnung = (" ACHTUNG Feldbelegung: %s – Einzelheiten im Protokoll."
                       % befund.get("kurz", "Befund"))
    warnung = ""
    if alter is not None and alter > hoco.ALTER_WARNUNG_MIN:
        warnung = (" ACHTUNG: Auszug ist %.0f Minuten alt – schreibt der Rechner noch?"
                   % alter)
    return ("OK – Auszug %s (%s), %d Pferde, %d Torzeiten.%s%s %s Stand %s."
            % (name,
               "%.0f Min alt" % alter if alter is not None else "Alter unbekannt",
               len(pferde), tore, warnung, feldwarnung,
               ergebnis.get("rueckstand_text", ""), ergebnis["stand"]))
