# -*- coding: utf-8 -*-
"""Zahlen und Einheiten, so wie der Fuetterungsrechner sie schreibt.

Der Rest von `ablesen.py` ist mit dem Bildschirmweg weggefallen (Anweisungen
ans Modell, Bildzuschnitt, Pruefung der Modellantworten). Diese beiden Dinge
werden weiter gebraucht: `zahl()` liest einen Wert aus einer formatierten
Angabe zurueck, `EINHEIT` schreibt ihn so, wie ihn Website, Bot und Archiv
seit jeher erwarten.

Die Schreibweisen stammen aus dem Panel und bleiben unveraendert - auch das
kleine 'min' beim bisherigen Anspruch. Wer sie anfasst, aendert stillschweigend
jede Pferdeseite und jede Archivzeile.
"""
import re

EINHEIT = {
    "RF": {"gesamt": "{:.0f} Min", "bisherig": "{:.0f} min"},
    "KF": {"gesamt": "{:.3f} kg", "bisherig": "{:.3f} kg"},
    "MIN": {"gesamt": "{:.0f} g", "bisherig": "{:.0f} g"},
}


def zahl(text):
    """'0.583' -> 0.583 ; '34 min' -> 34.0 ; '' -> 0.0"""
    treffer = re.search(r"[-+]?\d*[.,]?\d+", str(text).replace(" ", ""))
    return float(treffer.group().replace(",", ".")) if treffer else 0.0
