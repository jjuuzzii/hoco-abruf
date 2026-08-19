# -*- coding: utf-8 -*-
"""Fehlererkennung: welches Pferd hat sein Futter nicht geholt?

Drei Stufen, die schwerste zuerst:

  transponder  Der Rechner meldet es selbst, unter 'Uebersichten > Hinweise':
               'Pferd 26 (Nilson) wurde in den letzten 12 Stunden bei keiner
               Station erkannt. Transponderfehler?' Das ist der verlaesslichste
               Befund ueberhaupt - nur der Rechner sieht alle Stationen. Diese
               Meldung steht im Auszug (Block 100019) und wird von
               hoco.py bei jedem Abruf uebernommen.
  nichts       0 % geholt, obwohl etwas faellig war - Tier krank, Tor klemmt,
               Futter leer.
  wenig        unter SCHWELLE Prozent - im Auge behalten.

Die unteren beiden werden hier aus den ZAHLEN gerechnet. Das Panel faerbt zwar
auch Zeilen ein, aber worauf sich die Farbe genau bezieht, ist von aussen nicht
sicher zu erkennen (markierte Zeile? Warnung?). Gerechnet ist es erklaerbar:

  faellig    = 'Anspruch bisherig' (was das Tier bis jetzt haette holen sollen)
  geholt     = 'Fortschritt bisherig' in Prozent (der Balken in der Tabelle)

Zwei Faelle sind ausdruecklich KEIN Rueckstand:
  * kein Anspruch (Anspruch bisherig = 0) - da gibt es nichts zu holen,
  * kurz nach dem 6-Uhr-Reset. Dann ist erst ein Bruchteil des Tages faellig
    und ein Balken bei 0 % heisst schlicht 'das Tier war noch nicht da'.
    Gegenmittel: erst ab ANTEIL_MIN des Tagesanspruchs wird geurteilt - das
    ist einheitenfrei und gilt fuer Minuten, Kilogramm und Gramm gleich.

Gerechnet wird ausserdem nur ueber Rau- und Kraftfutter; Mineralfutter wird
angezeigt, aber nicht bewertet (Begruendung bei BEWERTET).
"""
from . import einheiten, ueberwachung

SCHWELLE = 50        # Prozent - darunter gilt es als Rueckstand
ANTEIL_MIN = 0.10    # erst ab 10 % Tagesanspruch wird ueberhaupt geurteilt

ARTEN = [("rf", "Raufutter"), ("kf", "Kraftfutter"), ("min", "Mineralfutter")]

# Mineralfutter wird NICHT bewertet - nur angezeigt.
#
# Es holt sich kaum ein Tier vollstaendig ab; die Portionen sind winzig, viele
# Pferde gehen tagelang nicht an die Station. Gemessen an 'Anspruch bisherig'
# stand damit fast der halbe Stall dauernd im Rueckstand - auf der Einsteller-
# Website wie im Dashboard. Eine Warnung, die jeden Tag bei jedem zweiten Pferd
# steht, liest nach einer Woche niemand mehr, und die echten Befunde gingen
# darin unter. Die Zahlen stehen weiterhin in jeder Tabelle und auf jeder
# Pferdeseite - nur eben ohne Urteil.
BEWERTET = ("rf", "kf")

# Reihenfolge der Schwere - wird zum Sortieren und zum Zusammenfassen genutzt.
STUFEN = ["transponder", "nichts", "wenig"]
STUFE_TEXT = {"transponder": "Nicht erkannt", "nichts": "Nicht geholt",
              "wenig": "Rueckstand"}


def _pruefe_art(werte):
    """Einen Futter-Block bewerten -> 'nichts' | 'wenig' | None."""
    if not isinstance(werte, dict):
        return None                      # nicht abgerufen - keine Aussage
    faellig = einheiten.zahl(werte.get("anspruch_bisherig"))
    if faellig <= 0:
        return None                      # nichts faellig
    gesamt = einheiten.zahl(werte.get("anspruch_gesamt"))
    if gesamt > 0 and faellig / gesamt < ANTEIL_MIN:
        return None                      # zu frueh am Tag fuer ein Urteil
    try:
        prozent = float(werte.get("fortschritt_bisherig_prozent") or 0)
    except (TypeError, ValueError):
        return None
    if prozent <= 0:
        return "nichts"
    if prozent < SCHWELLE:
        return "wenig"
    return None


def pruefe(pferde):
    """Setzt je Pferd die abgeleiteten Felder und gibt die Auffaelligen zurueck.

    Geschrieben werden je Pferd:
      <art>_rueckstand   'nichts' | 'wenig' | None   (rf_, kf_, min_)
      rueckstand         die schwerste Stufe des Tiers oder None
      rueckstand_text    fertiger Klartext fuer Oberflaeche und Nachricht
    """
    auffaellig = []
    for p in pferde:
        stufen, worte = [], []
        # Ausgenommene Tiere (kein Transponder, Weide, verkauft) bekommen gar
        # kein Urteil - siehe ueberwachung.py. Die Zahlen bleiben unberuehrt.
        # Wieder erkannt? Dann ist der Grund fuer eine Melde-Ausnahme weg und
        # sie endet hier von selbst (siehe ueberwachung.py). Vorsorglich
        # gesetzte Ausnahmen bleiben.
        if ueberwachung.ist_aus(p.get("nr")) and not p.get("hinweis"):
            ueberwachung.wieder_erkannt(p.get("nr"), p.get("name") or "")
        p["ueberwacht"] = not ueberwachung.ist_aus(p.get("nr"))
        if not p["ueberwacht"]:
            for feld, _titel in ARTEN:
                p[feld + "_bewertet"] = False
                p[feld + "_rueckstand"] = None
            p["rueckstand"] = None
            p["rueckstand_text"] = ""
            p["ueberwachung_grund"] = ueberwachung.grund(p.get("nr"))
            continue
        p.pop("ueberwachung_grund", None)
        # Der Rechner selbst hat immer recht - was er meldet, steht vorn.
        if p.get("hinweis"):
            stufen.append("transponder")
            worte.append(str(p["hinweis"]).strip())
        for feld, titel in ARTEN:
            # Das Merkmal '<art>_bewertet' braucht die Website: nur so kann sie
            # 'kein Befund' von 'wird gar nicht beurteilt' unterscheiden und die
            # Mineralfutter-Karte neutral statt gruen faerben.
            p[feld + "_bewertet"] = feld in BEWERTET
            stufe = _pruefe_art(p.get(feld)) if feld in BEWERTET else None
            p[feld + "_rueckstand"] = stufe
            if stufe:
                stufen.append(stufe)
                worte.append("%s %s" % (titel, "nicht geholt" if stufe == "nichts"
                                        else "im Rueckstand"))
        p["rueckstand"] = next((s for s in STUFEN if s in stufen), None)
        p["rueckstand_text"] = ", ".join(worte)
        if p["rueckstand"]:
            auffaellig.append(p)
    # Schwerste Stufe zuerst, innerhalb einer Stufe nach Pferdenummer.
    auffaellig.sort(key=lambda p: (STUFEN.index(p["rueckstand"]), p.get("nr") or 0))
    return auffaellig


def _namen(pferde, grenze=6):
    namen = [str(p.get("name") or p.get("nr")) for p in pferde]
    return ", ".join(namen[:grenze]) + (" u.a." if len(namen) > grenze else "")


def zusammenfassung(auffaellig):
    """Eine Zeile fuers Log und die Statusanzeige."""
    if not auffaellig:
        return "Kein Rueckstand - alle Tiere im Plan."
    teile = []
    tr = [p for p in auffaellig if p.get("rueckstand") == "transponder"]
    if tr:
        teile.append("%d nicht erkannt (%s)" % (len(tr), _namen(tr)))
    nichts = [p for p in auffaellig if p.get("rueckstand") == "nichts"]
    if nichts:
        teile.append("%d ohne Abholung (%s)" % (len(nichts), _namen(nichts)))
    wenig = [p for p in auffaellig if p.get("rueckstand") == "wenig"]
    if wenig:
        teile.append("%d im Rueckstand" % len(wenig))
    return "; ".join(teile)
