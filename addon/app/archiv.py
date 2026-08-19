# -*- coding: utf-8 -*-
"""Dauerhaftes Archiv aller Pferdedaten.

Bisher gab es nur zwei Staende: pferde.json (aktuell, wird ueberschrieben) und
verlauf/<datum>.json (ein Schnappschuss je Tag, nur vom Voll-Lauf). Damit war
weder nachvollziehbar, wann ein Pferd im Tagesverlauf wie viel geholt hat, noch
liess sich ein Zeitraum ausgeben.

Hier kommt nach JEDEM Abruf eine Zeile je Pferd dazu - Langform, eine Zeile
je Zeitpunkt und Pferd. Das laesst sich in Excel filtern und als Pivot
auswerten, ohne dass man die Spalten vorher kennen muss.

Abgelegt monatsweise unter /share/fuetterungsabruf/archiv/JJJJ-MM.csv. Bei
28 Pferden und vier Laeufen taeglich sind das rund 3.400 Zeilen im Monat -
wenige hundert Kilobyte im Jahr. Eine Datenbank waere hier Selbstzweck.

Trennzeichen ist das Semikolon (deutsches Excel), Zahlen bleiben so stehen,
wie das Panel sie anzeigt.
"""
import os
import re
import time

SHARE = "/share/fuetterungsabruf"
ORDNER = os.path.join(SHARE, "archiv")

# Neue Spalten kommen ANS ENDE, nie in die Mitte: die Monatsdatei wird
# fortgeschrieben, ihre Kopfzeile steht schon. Wuerde man mittendrin einfuegen,
# stuenden die alten Zeilen des laufenden Monats um Spalten verschoben da.
# Kuerzere Altzeilen fuellt lesen() beim Ausgeben rechts auf.
SPALTEN = [
    "zeitpunkt", "datum", "zeit", "umfang", "nr", "name",
    "rf_geholt", "rf_anspruch", "rf_prozent", "rf_bisherig_prozent",
    "kf_geholt", "kf_anspruch", "kf_prozent", "kf_bisherig_prozent",
    "selektionen", "selektion_zeiten", "hinweis",
    # ab 0.12.0
    "min_geholt", "min_anspruch", "min_prozent", "min_bisherig_prozent",
    "rueckstand", "rueckstand_text",
]


def _sauber(wert):
    """Semikolon und Zeilenumbrueche wuerden die Spalten zerreissen."""
    t = str(wert if wert is not None else "")
    return t.replace(";", ",").replace("\r", " ").replace("\n", " ").strip()


def _zeile(p, zeitpunkt, datum, zeit, umfang):
    rf = p.get("rf") or {}
    kf = p.get("kf") or {}
    mi = p.get("min") or {}
    sel = p.get("selektion") or []
    werte = [
        zeitpunkt, datum, zeit, umfang, p.get("nr"), p.get("name"),
        rf.get("fortschritt_gesamt"), rf.get("anspruch_gesamt"),
        rf.get("fortschritt_gesamt_prozent"), rf.get("fortschritt_bisherig_prozent"),
        kf.get("fortschritt_gesamt"), kf.get("anspruch_gesamt"),
        kf.get("fortschritt_gesamt_prozent"), kf.get("fortschritt_bisherig_prozent"),
        len(sel), ",".join(str(z) for z in sel), p.get("hinweis"),
        mi.get("fortschritt_gesamt"), mi.get("anspruch_gesamt"),
        mi.get("fortschritt_gesamt_prozent"), mi.get("fortschritt_bisherig_prozent"),
        p.get("rueckstand"), p.get("rueckstand_text"),
    ]
    return ";".join(_sauber(w) for w in werte)


def datei(monat=None):
    return os.path.join(ORDNER, "%s.csv" % (monat or time.strftime("%Y-%m")))


def schreiben(ergebnis):
    """Haengt einen Abruf ans Archiv an. Gibt die Zahl der Zeilen zurueck."""
    jetzt = time.localtime()
    zeitpunkt = time.strftime("%Y-%m-%d %H:%M:%S", jetzt)
    datum = time.strftime("%Y-%m-%d", jetzt)
    zeit = time.strftime("%H:%M", jetzt)
    umfang = ergebnis.get("scope", "")

    os.makedirs(ORDNER, exist_ok=True)
    pfad = datei(time.strftime("%Y-%m", jetzt))
    neu = not os.path.exists(pfad)
    if not neu:
        _kopf_nachziehen(pfad)
    zeilen = 0
    with open(pfad, "a", encoding="utf-8", newline="") as f:
        if neu:
            f.write(";".join(SPALTEN) + "\n")
        for p in ergebnis.get("pferde", []):
            f.write(_zeile(p, zeitpunkt, datum, zeit, umfang) + "\n")
            zeilen += 1
    return zeilen


def _kopf_nachziehen(pfad):
    """Kopfzeile und alte Zeilen auf die heutige Spaltenzahl bringen.

    Die Kopfzeile wird nur beim Anlegen der Datei geschrieben. Kamen spaeter
    Spalten dazu - mit 0.12.0 die vier Mineral-Spalten und die beiden zum
    Rueckstand -, blieb sie stehen: in 2026-08.csv standen 17 Spaltennamen ueber
    23 Werten. Wer die Datei in einer Tabellenkalkulation oeffnet, bekommt sechs
    namenlose Spalten, und die aelteren Zeilen sind kuerzer als die neuen.

    Das wird hier einmalig geradegezogen: Kopfzeile ersetzen, kurze Zeilen mit
    Semikolons auffuellen. Passiert nur, wenn wirklich etwas fehlt - im
    Normalfall kostet es einen Blick auf die erste Zeile.
    """
    try:
        with open(pfad, encoding="utf-8", errors="replace", newline="") as f:
            alt = f.read().split("\n")
    except Exception:
        return
    if not alt or alt[0].rstrip("\r") == ";".join(SPALTEN):
        return
    soll = len(SPALTEN)
    neu = [";".join(SPALTEN)]
    for roh in alt[1:]:
        zeile = roh.rstrip("\r")
        if not zeile:
            neu.append("")
            continue
        fehlt = soll - 1 - zeile.count(";")
        neu.append(zeile + ";" * fehlt if fehlt > 0 else zeile)
    with open(pfad, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(neu))


def monate():
    """Vorhandene Archivmonate, neueste zuerst."""
    try:
        return sorted((f[:-4] for f in os.listdir(ORDNER)
                       if re.fullmatch(r"\d{4}-\d{2}\.csv", f)), reverse=True)
    except Exception:
        return []


def lesen(von="", bis=""):
    """Alle Archivzeilen im Zeitraum (JJJJ-MM-TT, beide Grenzen einschliesslich).

    Leere Grenze = offen. Gibt (kopfzeile, zeilen) zurueck."""
    zeilen = []
    for monat in sorted(monate()):
        # Monat ueberspringen, wenn er ganz ausserhalb liegt
        if von and monat < von[:7]:
            continue
        if bis and monat > bis[:7]:
            continue
        try:
            with open(datei(monat), encoding="utf-8") as f:
                for i, roh in enumerate(f):
                    roh = roh.rstrip("\n")
                    if not roh or (i == 0 and roh.startswith("zeitpunkt;")):
                        continue
                    datum = roh.split(";", 2)[1] if roh.count(";") >= 2 else ""
                    if von and datum < von:
                        continue
                    if bis and datum > bis:
                        continue
                    # Zeilen aus der Zeit vor neuen Spalten rechts auffuellen,
                    # damit der Export rechteckig bleibt.
                    fehlt = len(SPALTEN) - 1 - roh.count(";")
                    zeilen.append(roh + ";" * fehlt if fehlt > 0 else roh)
        except Exception:
            continue
    return ";".join(SPALTEN), zeilen


def als_csv(von="", bis=""):
    """Fertige CSV mit Byte-Marke, damit Excel UTF-8 erkennt."""
    kopf, zeilen = lesen(von, bis)
    return "﻿" + "\r\n".join([kopf] + zeilen) + "\r\n"


def umfang_text():
    """Kurzer Hinweis fuer die Oberflaeche: was liegt im Archiv."""
    m = monate()
    if not m:
        return "noch keine Aufzeichnungen"
    _kopf, zeilen = lesen()
    return "%d Messungen aus %d Monat%s (%s bis %s)" % (
        len(zeilen), len(m), "" if len(m) == 1 else "en", min(m), max(m))
