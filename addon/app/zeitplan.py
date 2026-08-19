# -*- coding: utf-8 -*-
"""Zeit-Helfer fuer die Morgenmeldung.

Frueher stand hier die ganze Abruf-Planung: beliebig viele Laeufe mit festen
Zeiten oder Takt, Wochentagen, Umfaengen und einer Pause-Funktion. Das war
noetig, solange jeder Abruf das Panel belegte (nur EINE Sitzung gleichzeitig)
und je Aufnahme Geld kostete - man musste genau ueberlegen, wann und wie oft
gelesen wird.

Seit 0.21.0 gibt es davon nichts mehr. Der Fuetterungsrechner legt alle 30
Minuten eine neue Datei auf seinen FTP; das Add-on sieht regelmaessig nach, ob
eine dazugekommen ist, und arbeitet nur dann (`bot._scheduler`). Nachsehen
kostet nichts, es gibt keine Sitzung zu belegen, und ein Auszug enthaelt immer
alles - es bleibt schlicht nichts zu planen.

Uebrig bleiben zwei Kleinigkeiten, die die Morgenmeldung braucht: sie hat
weiterhin eine feste Uhrzeit und Wochentage.
"""
import re

TAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def norm_zeit(s):
    """'7:5' -> None, '7:05' -> '07:05', '' -> ''."""
    s = (s or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        return None
    return "%02d:%02d" % (hh, mm)
