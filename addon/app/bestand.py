# -*- coding: utf-8 -*-
"""Haelt die Zuordnung Einsteller -> Pferd gueltig, wenn Nummern verrutschen.

Der Fuetterungsrechner nummeriert seine Pferde fortlaufend. Faellt eins aus dem
Bestand, ruecken die dahinter auf: aus Nr. 29 wird Nr. 28. Die Zuordnung im
Add-on haengt aber an genau dieser Nummer - und die Website findet danach zu
dem Zugangsschluessel kein Pferd mehr. Die Seite bleibt einfach leer, ohne
Fehlermeldung. Am 21.08.2026 ist das bei einem Pferd passiert und erst
aufgefallen, weil der Einsteller nachgefragt hat.

Deshalb wird nach jedem Abruf nachgesehen, ob die hinterlegten Nummern noch zu
den Namen passen, und stillschweigend nachgezogen. Der Zugangsschluessel wandert
dabei mit - Link und gedruckter Aufkleber bleiben gueltig.

Nachgezogen wird nur, wenn es zweifelsfrei ist. Ein falsch umgehaengtes Pferd
zeigte einem Einsteller die Zahlen eines fremden Tieres; das waere schlimmer als
eine leere Seite. Vier Bedingungen muessen zusammen erfuellt sein:

  1. Die bisherige Nummer steht nicht mehr im Auszug.
  2. Genau ein Pferd im Auszug traegt denselben Namen (Gross- und Kleinschreibung,
     Umlaute und Bindestriche werden dabei ignoriert).
  3. Diese Nummer ist noch an niemanden vergeben.
  4. Ist zu beiden ein Transponder bekannt, muss er uebereinstimmen.

Trifft etwas davon nicht zu, bleibt alles stehen und es wird protokolliert -
dann muss das Hofbuero hinsehen.
"""
import unicodedata


def _norm(text):
    """Namen vergleichbar machen: ohne Umlaute, Bindestriche, Gross-/Kleinschreibung."""
    roh = unicodedata.normalize("NFKD", str(text or ""))
    roh = roh.encode("ascii", "ignore").decode()
    return " ".join(roh.lower().replace("-", " ").split())


def namen_aus_auszug(daten):
    """{Nummer: Name} aus den zuletzt gelesenen Tagesdaten."""
    out = {}
    for p in (daten or {}).get("pferde", []) or []:
        try:
            out[int(p.get("nr"))] = str(p.get("name") or "").strip()
        except (TypeError, ValueError):
            continue
    return out


def _transponder(daten, nr):
    for p in (daten or {}).get("pferde", []) or []:
        try:
            if int(p.get("nr")) == int(nr):
                return str(p.get("transponder") or "").strip()
        except (TypeError, ValueError):
            continue
    return ""


def pruefen(daten, namen_bisher, belegte_nummern, transponder_bisher=None):
    """Sucht Nummern, die nachgezogen werden koennen.

    namen_bisher:        {Nummer: Name}, wie das Add-on sie bisher kennt
    belegte_nummern:     Nummern, die schon einem Einsteller gehoeren
    transponder_bisher:  {Nummer: Transponder} vom letzten Auszug, optional

    Ergebnis: (umzug, unklar)
      umzug  = {alte Nummer: (neue Nummer, Name)}
      unklar = [(alte Nummer, Name, Grund)]  - Faelle fuer das Hofbuero
    """
    aktuell = namen_aus_auszug(daten)
    if not aktuell:
        return {}, []          # ohne Auszug wird nichts entschieden

    nach_name = {}
    for nr, name in aktuell.items():
        nach_name.setdefault(_norm(name), []).append(nr)

    transponder_bisher = transponder_bisher or {}
    umzug, unklar = {}, []
    for alt, name in sorted(namen_bisher.items(), key=lambda x: int(x[0])):
        if alt in aktuell:
            continue                                   # Nummer stimmt noch
        kandidaten = nach_name.get(_norm(name), [])
        if not kandidaten:
            unklar.append((alt, name, "kein Pferd dieses Namens im Auszug"))
            continue
        if len(kandidaten) > 1:
            unklar.append((alt, name, "mehrere Pferde heissen so (%s)"
                           % ", ".join(str(k) for k in sorted(kandidaten))))
            continue
        neu = kandidaten[0]
        if neu in belegte_nummern:
            unklar.append((alt, name, "Nr. %d gehoert bereits jemandem" % neu))
            continue
        alt_tr = str(transponder_bisher.get(alt)
                     or transponder_bisher.get(str(alt)) or "")
        neu_tr = _transponder(daten, neu)
        if alt_tr and neu_tr and alt_tr != neu_tr:
            unklar.append((alt, name, "Transponder passt nicht (%s statt %s)"
                           % (neu_tr, alt_tr)))
            continue
        umzug[alt] = (neu, aktuell[neu])
    return umzug, unklar


def anwenden(umzug, keys, zuordnung):
    """Traegt den Umzug in Schluesselbund und Zuordnung ein.

    Beide werden an Ort und Stelle geaendert. Der Schluessel selbst bleibt, er
    haengt nur an einer anderen Nummer - deshalb bleiben Link und Aufkleber
    gueltig.
    """
    for alt, (neu, _name) in umzug.items():
        if alt in keys:
            keys[neu] = keys.pop(alt)
        for nummer, eintrag in list(zuordnung.items()):
            if not isinstance(eintrag, list):
                continue
            geaendert = False
            neue_liste = []
            for e in eintrag:
                try:
                    passt = int(e) == int(alt)
                except (TypeError, ValueError):
                    passt = False
                if passt:
                    neue_liste.append(neu if isinstance(e, int) else str(neu))
                    geaendert = True
                else:
                    neue_liste.append(e)
            if geaendert:
                zuordnung[nummer] = neue_liste
    return keys, zuordnung
