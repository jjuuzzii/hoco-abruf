# -*- coding: utf-8 -*-
"""Prueft bei JEDEM Abruf, ob die Feldbelegung des Auszugs noch stimmt.

WARUM ES DAS GIBT
Kein einziges Feld dieses Auszugs ist dokumentiert. Jede Zuordnung in `hoco.py`
- welcher Block das Raufutter fuehrt, welches Feld das Geholte ist, welche
Komponenten-Nummer Kraftfutter bedeutet - wurde am 18.08.2026 durch Vergleich
erschlossen und gegen Panel-Aufnahmen belegt. Wasserbauer weiss nichts von uns.
Aendert eine neue Firmware eine Feldnummer, eine Komponenten-Nummer oder die
Spaltenreihenfolge, liest das Add-on **stillschweigend etwas anderes** und
liefert weiter Zahlen, die gueltig aussehen.

Dreimal ist genau das schon passiert, jedes Mal ohne Fehlermeldung: das
Mineralfutter stand einen Tag lang auf dem VORIGEN Zyklus (`801615` statt
`900060`); `801704` wurde fuer die Stations-Kennung gehalten, obwohl es die
Port-Nummer ist; und `803201` in der Stationskonfiguration ist **ebenfalls**
die Port-Nummer - deshalb wurde am 18.08. die Konfiguration von Raufe 12 fuer
die der Easy Station gehalten. Eine stille Abkuerzung ist gefaehrlicher als
eine laute Stoerung.

WIE GEPRUEFT WIRD - vier Ebenen, von grob nach fein

1. **Formatgedaechtnis.** Beim ersten Lauf wird die Kopfzeile jedes Blocks
   gemerkt (`/data/exportformat.json`). Danach faellt jede Aenderung auf:
   neuer Block, weggefallenes Feld, umsortierte Spalten. Das ist der Waechter
   fuer "Wasserbauer hat am Export etwas gedreht" - er braucht keine Annahme
   darueber, WAS sich aendern koennte.

2. **Kreuzprobe.** Der Rechner fuehrt seine Zahlen doppelt: als Tagessumme je
   Tier und Futterart (100034/100014/100016) und als Protokoll jedes einzelnen
   Besuchs mit den ausgegebenen Mengen (100017/100037). Beide muessen dasselbe
   ergeben. Am 18.08.2026 taten sie das ueber fuenf Auszuege hinweg **exakt**:
   28 von 28 Tieren, alle drei Futterarten, Abweichung null. Verschiebt sich
   eine Feldnummer, bricht das sofort - auch dann, wenn im falschen Feld
   plausible Zahlen stehen. Das faengt, was Ebene 1 nicht sehen kann: ein Feld,
   das bleibt, aber etwas anderes bedeutet.

3. **Schluessel im Klartext.** Zwei Stellen nennen ihre Bedeutung selbst -
   Block 100032 mit Namen wie `RF_ENABLE` und `HF_PORT_WEIGHT_CON_2`, die
   Sortenbloecke 100013/100015/100033 mit `Kraftfutter_1`, `Mineral_1`,
   `Raufutter_1`. Was im Klartext dasteht, laesst sich ohne Umweg pruefen.

4. **Groessenordnung.** Faengt den Fall, dass ein Feld auf ein anderes
   verrutscht, das zufaellig auch Zahlen fuehrt - Stueckzahlen, Sekunden,
   laufende Nummern.

Dieselbe Lehre wie ueberall hier: *ein Test, der die Annahme des Codes teilt,
prueft nichts.* Ebene 2 und 3 teilen sie nicht - sie kommen aus einer anderen
Ecke der Datei.
"""
import datetime
import json
import os

from . import einheiten

DATA_DIR = "/data"
FORMATDATEI = os.path.join(DATA_DIR, "exportformat.json")

# Die vollstaendige Feldkarte des Projekts - jedes Feld, auf das sich irgendein
# Modul verlaesst, mit dem Zweck dahinter. Wer hier etwas ergaenzt, ergaenzt
# zugleich die Ueberwachung. Reihenfolge wie in STAND.md Abschnitt 2b.
FELDKARTE = {
    "100001": ("Tierstamm", {
        "900070": "Pferdenummer", "900045": "Name", "900056": "Transponder",
        "800152": "Max KF pro Tag", "800139": "Max KF pro Mahlzeit",
        "800140": "Max Mineral pro Mahlzeit", "800158": "Max Mineral pro Intervall",
        "800147": "Intervalldauer", "800148": "Verdauzeit", "800159": "Zyklusdauer"}),
    "100034": ("Raufutter", {
        "900070": "Pferdenummer", "801406": "Anspruch je Zyklus",
        "900064": "geholt", "900065": "jetzt offen", "801419": "voriger Zyklus",
        "801420": "vorletzter Zyklus", "900067": "Sorte"}),
    "100014": ("Kraftfutter", {
        "900070": "Pferdenummer", "900061": "Anspruch je Zyklus",
        "900060": "geholt", "900063": "jetzt offen", "801415": "voriger Zyklus",
        "801416": "vorletzter Zyklus", "801405": "Menge kg",
        "801418": "bisher gefuettert", "900067": "Sorte"}),
    "100016": ("Mineralfutter", {
        "900070": "Pferdenummer", "900061": "Anspruch je Zyklus",
        "900060": "geholt", "900063": "jetzt offen", "801615": "voriger Zyklus",
        "801616": "vorletzter Zyklus", "900067": "Sorte"}),
    "100017": ("Besuchsprotokoll", {
        "900070": "Pferdenummer", "801701": "Besuchskennung", "801703": "Zeitpunkt",
        "801704": "PORT (nicht Station!)", "801706": "Dauer in Sekunden"}),
    "100037": ("Mengen je Besuch", {
        "803701": "Besuchskennung", "803702": "Komponente",
        "803703": "soll", "803704": "ist"}),
    "100030": ("Stationsnamen", {"803001": "Stations-Kennung", "803002": "Name"}),
    "100031": ("Port auf Station", {"803001": "Stations-Kennung", "803101": "Port"}),
    "100032": ("Stationskonfiguration", {
        "803201": "PORT (nicht Station!)", "803203": "Schluessel im Klartext",
        "803204": "Wert", "803206": "Text"}),
    "100019": ("Meldungen", {
        "801903": "Pferdenummer", "801902": "Art (6 = nicht erkannt)",
        "801905": "gemeldet am"}),
    "100011": ("Betriebsdaten", {"801142": "Zyklusbeginn"}),
    "100035": ("Zutrittszeiten Selektion", {
        "900070": "Pferdenummer", "803502": "Bereich", "803504": "Fensternummer",
        "803503": "von", "803501": "bis", "803505": "eingeschaltet"}),
    "100013": ("Kraftfuttersorten", {"801303": "Name", "900067": "Sorte"}),
    # Achtung: die Mineralsorten fuehren ihren Namen im 8015er-Kreis
    # (801503), nicht im 8013er wie Kraft- und Raufutter. Beim ersten Lauf
    # dieser Pruefung prompt aufgefallen - genau dafuer ist sie da.
    "100015": ("Mineralsorten", {"801503": "Name", "900067": "Sorte"}),
    "100033": ("Raufuttersorten", {"801303": "Name", "900067": "Sorte"}),
}

# Bloecke, die leer sein DUERFEN: keine Meldung, keine Zeitfenster.
DARF_LEER = ("100019", "100035")

# Klartext-Namen, die in den Sortenbloecken stehen muessen. Verschieben sich
# die Komponenten-Nummern, faellt es hier auf, bevor Futter falsch landet.
SORTEN = {"100013": "Kraftfutter", "100015": "Mineral", "100033": "Raufutter"}

# Grenzen, jenseits derer eine Zahl nicht aus dem Feld stammen kann, das wir zu
# lesen glauben. Grosszuegig - das soll Verrutschtes fangen, nicht ueber
# Fuetterung urteilen.
GRENZEN = {"rf": (0, 1440), "kf": (0, 20), "min": (0, 2000)}

ZEITFORM = "%d.%m.%Y %H:%M:%S"


def _log(msg):
    print("[pruefung] %s" % msg, flush=True)


# --------------------------------------------------------------------------
# 1. Formatgedaechtnis
# --------------------------------------------------------------------------
def fingerabdruck(bloecke):
    """{block: [spalten]} - die Kopfzeilen, so wie sie heute dastehen."""
    return {block: list(spalten) for block, (spalten, _z) in sorted(bloecke.items())}


def _format_vergleich(bloecke):
    """Hat sich am Aufbau der Datei seit dem letzten Lauf etwas geaendert?"""
    jetzt = fingerabdruck(bloecke)
    try:
        with open(FORMATDATEI, encoding="utf-8") as f:
            frueher = json.load(f)
    except Exception:
        frueher = None

    befunde = []
    if frueher:
        neu = sorted(set(jetzt) - set(frueher))
        weg = sorted(set(frueher) - set(jetzt))
        if neu:
            befunde.append("neue Bloecke im Auszug: %s" % ", ".join(neu))
        if weg:
            befunde.append("Bloecke verschwunden: %s" % ", ".join(weg))
        for block in sorted(set(jetzt) & set(frueher)):
            alt, neu_sp = frueher[block], jetzt[block]
            if alt == neu_sp:
                continue
            dazu = [f for f in neu_sp if f not in alt]
            fort = [f for f in alt if f not in neu_sp]
            teile = []
            if dazu:
                teile.append("neu: " + ", ".join(dazu))
            if fort:
                teile.append("weg: " + ", ".join(fort))
            if not teile:
                teile.append("Spaltenreihenfolge geaendert")
            befunde.append("Block %s: %s" % (block, "; ".join(teile)))

    if jetzt != frueher:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(FORMATDATEI, "w", encoding="utf-8") as f:
                json.dump(jetzt, f, ensure_ascii=False, indent=1, sort_keys=True)
            if frueher is None:
                _log("Aufbau des Auszugs gemerkt (%d Bloecke) - ab jetzt faellt "
                     "jede Aenderung auf." % len(jetzt))
        except Exception as e:
            _log("Formatgedaechtnis nicht schreibbar: %s" % e)
    return befunde


# --------------------------------------------------------------------------
# 2. Struktur nach der Feldkarte
# --------------------------------------------------------------------------
def _struktur(bloecke):
    befunde = []
    for block, (zweck, felder) in sorted(FELDKARTE.items()):
        spalten, zeilen = bloecke.get(block, ([], []))
        if not spalten:
            befunde.append("Block %s (%s) fehlt ganz" % (block, zweck))
            continue
        fehlt = ["%s = %s" % (f, w) for f, w in sorted(felder.items()) if f not in spalten]
        if fehlt:
            befunde.append("Block %s (%s): %s nicht mehr in der Kopfzeile"
                           % (block, zweck, "; ".join(fehlt)))
        if not zeilen and block not in DARF_LEER:
            befunde.append("Block %s (%s) hat keine Zeilen" % (block, zweck))
    return befunde


# --------------------------------------------------------------------------
# 3. Kreuzprobe: Tagessummen gegen Besuchsprotokoll
# --------------------------------------------------------------------------
def _kreuzprobe(hoco, bloecke, ab, bis):
    mengen = {}
    unbekannt = set()
    for r in hoco.tabelle(bloecke, hoco.MENGEN):
        mengen.setdefault(r.get(hoco.M_BESUCH), []).append(r)
        komp = r.get(hoco.M_KOMPONENTE)
        # 21 ist die Selektion selbst und traegt nie eine Menge.
        if komp not in hoco.KOMPONENTE and komp != "21" and hoco._zahl(r.get(hoco.M_IST)):
            unbekannt.add(komp)

    befunde = []
    if unbekannt:
        befunde.append("unbekannte Komponenten-Nummern mit Menge: %s - dieses "
                       "Futter wird derzeit NICHT gezaehlt"
                       % ", ".join(sorted(unbekannt, key=lambda x: (len(x), x))))

    aus_besuchen = {}
    lesbar = unlesbar = 0
    for b in hoco.tabelle(bloecke, hoco.BESUCHE):
        nr = b.get(hoco.B_NR)
        try:
            ts = datetime.datetime.strptime(b.get(hoco.B_ZEIT, ""), ZEITFORM)
            lesbar += 1
        except ValueError:
            unlesbar += 1
            continue
        if nr == hoco.GRUPPE or not (ab <= ts < bis):
            continue
        for m in mengen.get(b.get(hoco.B_ID), []):
            art = hoco.KOMPONENTE.get(m.get(hoco.M_KOMPONENTE))
            wert = hoco._zahl(m.get(hoco.M_IST))
            if art and wert:
                aus_besuchen.setdefault(nr, {})
                aus_besuchen[nr][art] = aus_besuchen[nr].get(art, 0.0) + wert
    if unlesbar and unlesbar > lesbar * 0.01:
        befunde.append("%d von %d Besuchszeitpunkten nicht als '%s' lesbar - "
                       "Datumsformat geaendert?" % (unlesbar, lesbar + unlesbar, ZEITFORM))

    for art, (block, _a, feld_geholt, _o) in sorted(hoco.FUTTER.items()):
        # Das Besuchsprotokoll fuehrt Kraftfutter in GRAMM, die Tagessumme in
        # Kilogramm. Wer das vergisst, sieht einen Faktor 1000 und haelt die
        # Zuordnung fuer kaputt.
        faktor = 1000.0 if art == "kf" else 1.0
        summe = {}
        for r in hoco.tabelle(bloecke, block):
            nr = r.get(hoco.NR)
            if nr is None or nr == hoco.GRUPPE:
                continue
            summe[nr] = summe.get(nr, 0.0) + hoco._zahl(r.get(feld_geholt))
        schief = []
        for nr, wert in sorted(summe.items(), key=lambda x: int(x[0] or 0)):
            gegen = aus_besuchen.get(nr, {}).get(art, 0.0)
            if abs(wert * faktor - gegen) > 0.5:
                schief.append("Nr %s (Summe %.1f, Protokoll %.1f)"
                              % (nr, wert * faktor, gegen))
        if schief:
            befunde.append("%s: %d von %d Tieren decken sich nicht mit dem "
                           "Besuchsprotokoll - %s"
                           % (art.upper(), len(schief), len(summe), ", ".join(schief[:3])))
    return befunde


# --------------------------------------------------------------------------
# 4. Klartext-Schluessel und Stationen
# --------------------------------------------------------------------------
def _klartext(hoco, bloecke):
    befunde = []
    for block, wortstamm in sorted(SORTEN.items()):
        feld = "801503" if block == "100015" else "801303"
        namen = [r.get(feld, "") for r in hoco.tabelle(bloecke, block)]
        if namen and not any(n.startswith(wortstamm) for n in namen):
            befunde.append("Block %s fuehrt keine Sorte mehr, die mit '%s' beginnt "
                           "(gefunden: %s)"
                           % (block, wortstamm, ", ".join(n for n in namen if n)[:80]))
    schluessel = {r.get("803203") for r in hoco.tabelle(bloecke, "100032")}
    if schluessel:
        for erwartet in ("RF_ENABLE", "HF_PORT_WEIGHT_CON_2"):
            if erwartet not in schluessel:
                befunde.append("Stationskonfiguration kennt '%s' nicht mehr" % erwartet)
    return befunde


def _stationen(hoco, bloecke):
    """Laesst sich das Selektionstor noch finden?

    Ueber zwei Tabellen, weil der Rechner zwei Nummernkreise fuehrt (Port und
    Stations-Kennung). Faellt eine weg oder heisst das Tor anders, gibt es keine
    Torzeiten mehr - und zwar lautlos.
    """
    befunde = []
    ports = hoco._stationsnamen(bloecke)
    if not ports:
        return ["Port-auf-Station-Zuordnung leer (Bloecke 100030/100031)"]
    tor = [p for p, n in ports.items() if n == hoco.SEL_STATION]
    if not tor:
        befunde.append("Keine Station '%s' mehr vorhanden - Torzeiten fallen aus "
                       "(vorhanden: %s)"
                       % (hoco.SEL_STATION, ", ".join(sorted(set(ports.values())))[:120]))
    elif len(tor) > 1:
        befunde.append("Station '%s' haengt an %d Ports (%s) - erwartet war einer"
                       % (hoco.SEL_STATION, len(tor), ", ".join(sorted(tor))))
    if not hoco._heu_stationen(bloecke):
        befunde.append("Keine reine Raufutter-Station mehr erkennbar - "
                       "Heu-Besuche wuerden aus der Liste verschwinden")
    return befunde


def _zyklus(hoco, bloecke):
    zeilen = hoco.tabelle(bloecke, hoco.BETRIEB)
    if not zeilen:
        return ["Betriebsdaten (100011) fehlen - Zyklusbeginn faellt auf 6 Uhr zurueck"]
    roh = (zeilen[0].get(hoco.ZYKLUS_BEGINN) or "").strip()
    if not roh or ":" not in roh:
        return ["Zyklusbeginn (801142) ist '%s' - nicht als Uhrzeit lesbar" % roh]
    return []


# --------------------------------------------------------------------------
# 5. Groessenordnung
# --------------------------------------------------------------------------
def _plausibel(pferde):
    befunde = []
    nummern = [p.get("nr") for p in pferde]
    doppelt = sorted({n for n in nummern if nummern.count(n) > 1})
    if doppelt:
        befunde.append("Pferdenummern doppelt vergeben: %s"
                       % ", ".join(str(n) for n in doppelt))
    ohne_namen = [p.get("nr") for p in pferde if not (p.get("name") or "").strip()]
    if ohne_namen:
        befunde.append("Tiere ohne Namen: %s" % ", ".join(str(n) for n in ohne_namen[:6]))
    for art, (unten, oben) in sorted(GRENZEN.items()):
        schlimm = []
        for p in pferde:
            for feld in ("anspruch_gesamt", "fortschritt_gesamt"):
                wert = einheiten.zahl((p.get(art) or {}).get(feld))
                if not (unten <= wert <= oben):
                    schlimm.append("Nr %s %s=%g" % (p.get("nr"), feld, wert))
        if schlimm:
            befunde.append("%s ausserhalb %g..%g: %s"
                           % (art.upper(), unten, oben, ", ".join(schlimm[:3])))
    return befunde


# --------------------------------------------------------------------------
def pruefen(hoco, bloecke, pferde, ab, bis):
    """Alle Ebenen -> {'ok': bool, 'befunde': [...], 'kurz': str}.

    `hoco` wird hereingereicht statt importiert, sonst importieren sich die
    beiden Module gegenseitig.
    """
    befunde = []
    befunde += _format_vergleich(bloecke)
    befunde += _struktur(bloecke)
    befunde += _zyklus(hoco, bloecke)
    befunde += _stationen(hoco, bloecke)
    befunde += _klartext(hoco, bloecke)
    befunde += _kreuzprobe(hoco, bloecke, ab, bis)
    befunde += _plausibel(pferde)

    if befunde:
        _log("ACHTUNG: die Feldbelegung des Auszugs stimmt nicht mehr - "
             "%d Befund%s:" % (len(befunde), "" if len(befunde) == 1 else "e"))
        for b in befunde:
            _log("   " + b)
        _log("   Bis das geklaert ist, koennen die Zahlen falsch sein, obwohl sie "
             "plausibel aussehen. Feldkarte: STAND.md Abschnitt 2b.")
        kurz = "%d Befund%s zur Feldbelegung" % (len(befunde),
                                                "" if len(befunde) == 1 else "e")
    else:
        kurz = "Feldbelegung bestaetigt (Kreuzprobe %d Tiere, 3 Futterarten)" % len(pferde)
    return {"ok": not befunde, "befunde": befunde, "kurz": kurz}
