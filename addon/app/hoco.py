# -*- coding: utf-8 -*-
"""Fuetterungsdaten aus dem CSV-Vollauszug des HOCO-Rechners lesen.

Der Fuetterungsrechner legt alle 30 Minuten einen vollstaendigen Auszug seiner
Datenbank auf seinem eigenen FTP-Server ab (`/export/HOCO_JJJJMMTT_HHMM.csv`,
anonymer Zugang, die letzten fuenf Dateien bleiben liegen). Damit ist der ganze
Weg ueber das Wasserbauer-Gateway - Panel abfahren, Bildschirm aufnehmen, vom
Modell ablesen lassen - fuer die Zahlen nicht mehr noetig.

Warum das mehr ist als eine Abkuerzung (am 18.08.2026 gegen den Archivlauf
08:58:10 geprueft, 50 Sekunden vor dem Auszug von 08:59):

  Raufutter geholt und Anspruch  28 von 28 Pferden exakt gleich
  Kraftfutter geholt und Anspruch 28 von 28 exakt gleich
  Torzeiten                      minutengenau (Temperino 18/18, Frodo 7/7)

Dazu faellt weg, was am Bildschirmweg dauernd Aerger machte: die Ein-Sitzungs-
Sperre am Panel, die von selbst wechselnde Sortierung der Selektionsliste, der
verschluckte Scroll, die Modellkosten - und die Lesefehler. In pferde.json
stand am 18.08. ein Pferd Nr. 28 'Blackjack', das es im Panel gar nicht gibt.

AUFBAU DER DATEI
Zeilenweise, Semikolon getrennt, cp1252. Drei Satzarten:

    COM;...                 Kommentar, wird uebersprungen
    DSC;<event>;<feld>;...  Spaltenkoepfe eines Blocks (Felder sind Zahlencodes)
    DTA;<event>;<wert>;...  eine Datenzeile dieses Blocks

Jede Zeile endet mit einem ueberzaehligen Semikolon - das letzte Feld ist leer
und wird abgeschnitten.

EINE FALLE, die schon einmal in die Irre gefuehrt hat: `801704` im
Besuchsprotokoll ist die PORT-Nummer, nicht die Stations-Kennung. Erst
Block 100031 bildet Port auf Station ab, dann gibt 100030 den Namen. Wer 100030
direkt auf 801704 anwendet, verschiebt alles um eine Stelle und haelt das
Selektionstor fuer den Fuetterungsrechner.
"""
import datetime
import ftplib
import io
import os
import re

from . import einheiten, pruefung, rueckstand

# --- FTP ------------------------------------------------------------------
# Erreichbar, seit die FritzBox einen WireGuard-Tunnel ins Wasserbauer-Netz
# haelt; der Home Assistant haengt am selben Router und braucht deshalb kein
# eigenes VPN. Der Rechner blockt ICMP - ein fehlgeschlagener Ping sagt nichts.
# Alles ueber Optionen einstellbar, damit ein anderer Betrieb nur die Adresse
# tauschen muss.
FTP_HOST = os.environ.get("HOCO_HOST", "").strip() or "172.16.1.49"
FTP_VERZEICHNIS = os.environ.get("HOCO_VERZEICHNIS", "").strip() or "/export"
FTP_BENUTZER = os.environ.get("HOCO_BENUTZER", "").strip() or "anonymous"
FTP_PASSWORT = os.environ.get("HOCO_PASSWORT", "").strip() or "anonymous@"

# Ab wann gilt der juengste Auszug als zu alt? Der Rechner schreibt alle 30
# Minuten; drei ausgelassene Male sind kein Zufall mehr, sondern eine Stoerung.
# Sie muss LAUT sein - stille alte Zahlen sind das Gefaehrlichste, was dieser
# Weg anrichten kann (siehe 'verschluckter Scroll' in STAND.md).
ALTER_WARNUNG_MIN = 95
DATEI_MUSTER = re.compile(r"^HOCO_(\d{8})_(\d{4})\.csv$")

# --- Bloecke und Felder ---------------------------------------------------
# Belegung am 18.08.2026 gegen pferde.json und archiv/2026-08.csv nachgewiesen,
# nicht aus einer Dokumentation uebernommen - es gibt keine.
TIERSTAMM = "100001"        # eine Zeile je Tier
NR, NAME, TRANSPONDER = "900070", "900045", "900056"

# Je Futterart: Block, Feld fuer den Tagesanspruch, Feld fuer das Geholte.
# Mehrere Zeilen je Tier (eine je Futtersorte) - es wird summiert.
#
# ACHTUNG, teuer gelernt am 18.08.2026: In 100016 steht das Mineralfutter
# ZWEIMAL. `900060` ist der laufende Zyklus, `801615` der VORIGE. Anfangs stand
# hier 801615 - Tamira wurden 30 g angezeigt, waehrend das Panel 0 g zeigte
# (die 30 g waren die von gestern).
#
# Warum es nicht auffiel: Geprueft wurde gegen `verlauf/<tag>.json` (geschrieben
# um 05:32, also am ZYKLUSENDE) und gegen ein `pferde.json` mit scope=ohne_min,
# dessen Mineralzahlen ebenfalls vom Lauf davor stammten. Beide Male 28 von 28
# - der Test teilte den Irrtum des Codes. Wer hier etwas aendert, prueft gegen
# eine Ablesung MITTEN im laufenden Zyklus, nicht gegen einen Tagesabschluss.
#
# Merkhilfe: alle drei Arten benutzen dieselbe Form - `900061` Anspruch,
# `900060` geholt. Weicht eine davon ab, ist es vermutlich das falsche Feld.
# Viertes Feld: was JETZT noch offen ist. Damit ergibt sich der 'Anspruch
# bisherig' als geholt + offen - und zwar so, wie ihn das Panel zeigt, ohne
# ihn nachbauen zu muessen. Er ist naemlich NICHT einfach der anteilige
# Tagesanspruch: der Rechner deckelt ihn auf 'schon geholt + eine Mahlzeit'
# (Feld 'Max. RF pro Mahlzeit' in den Stammdaten). Tamira hat 300 Min am Tag,
# stand aber am 18.08. um 09:57 UND um 11:22 unveraendert bei 32 Min faellig -
# 2 geholt plus 30 je Mahlzeit. Geradlinig gerechnet waeren es 67 gewesen,
# also gut das Doppelte, und `rueckstand.py` urteilt genau darauf.
# Geprueft: RF 28/28 und KF 28/28 gegen den Archivlauf 50 Sekunden neben dem
# Auszug, Mineral 6/6 gegen eine Panel-Aufnahme im laufenden Zyklus.
FUTTER = {
    "rf":  ("100034", "801406", "900064", "900065"),   # Raufutter,  Minuten
    "kf":  ("100014", "900061", "900060", "900063"),   # Kraftfutter, kg
    "min": ("100016", "900061", "900060", "900063"),   # Mineral,    Gramm
}
BESUCHE = "100017"          # eine Zeile je Stationsbesuch
B_NR, B_PORT, B_ZEIT, B_ID = "900070", "801704", "801703", "801701"
B_DAUER = "801706"          # Aufenthaltsdauer in SEKUNDEN
MENGEN = "100037"           # was es bei diesem Besuch bekommen hat
M_BESUCH, M_KOMPONENTE, M_IST = "803701", "803702", "803704"
# Komponenten-Nummern -> Futterart. 1-4 Kraftfutter, 5-8 Mineral, 10-12
# Raufutter; 21 ist die Selektion selbst und traegt keine Menge.
KOMPONENTE = {"1": "kf", "2": "kf", "3": "kf", "4": "kf",
              "5": "min", "6": "min", "7": "min", "8": "min",
              "10": "rf", "11": "rf", "12": "rf"}
MELDUNGEN = "100019"        # was der Rechner selbst bemaengelt
M_NR, M_ART = "801903", "801902"
M_ZEIT = "801905"           # wann der Rechner es gemeldet hat
M_NICHT_ERKANNT = "6"
BETRIEB = "100011"          # Betriebsstammdaten
ZYKLUS_BEGINN = "801142"    # '06:00:00' - der taegliche Reset
PORTE = "100031"            # Port -> Stations-Kennung
P_STATION, P_PORT = "803001", "803101"
STATIONEN = "100030"        # Stations-Kennung -> Klartext
S_STATION, S_NAME = "803001", "803002"

SEL_ZEITEN = "100035"       # Zutrittszeiten je Tier und Selektionsbereich
SZ_BEREICH, SZ_NR, SZ_VON, SZ_BIS, SZ_EIN = "803502", "803504", "803503", "803501", "803505"

SEL_STATION = "Komp.Sel."   # das Selektionstor - Erkennung, Kraftfutter, Mineral
GRUPPE = "0"                # Tier-Nr. 0 ist die Gruppe 'alle Pferde', kein Tier


def _log(msg):
    print("[hoco] %s" % msg, flush=True)


# --------------------------------------------------------------------------
# Datei einlesen
# --------------------------------------------------------------------------
def bloecke_lesen(rohtext):
    """Rohtext -> {event: (spalten, [zeilen])}."""
    bloecke = {}
    for zeile in rohtext.splitlines():
        teile = zeile.split(";")
        if len(teile) < 3:
            continue
        if teile[0] == "DSC":
            bloecke[teile[1]] = (teile[2:-1], [])
        elif teile[0] == "DTA" and teile[1] in bloecke:
            bloecke[teile[1]][1].append(teile[2:-1])
    return bloecke


def tabelle(bloecke, event):
    """Einen Block als Liste von Zeilen-Woerterbuechern."""
    spalten, zeilen = bloecke.get(event, ([], []))
    return [dict(zip(spalten, z)) for z in zeilen]


def _zahl(text):
    """'0,792000' -> 0.792 ; '' -> 0.0  (deutsches Komma)."""
    return einheiten.zahl(str(text).replace(",", "."))


# --------------------------------------------------------------------------
# FTP
# --------------------------------------------------------------------------
def dateiliste(host=FTP_HOST, verzeichnis=FTP_VERZEICHNIS,
               benutzer=FTP_BENUTZER, passwort=FTP_PASSWORT, zeit=15):
    """Alle Auszuege im Verzeichnis, aelteste zuerst."""
    ftp = ftplib.FTP()
    try:
        ftp.connect(host, 21, timeout=zeit)
        ftp.login(benutzer, passwort)
        ftp.cwd(verzeichnis)
        return sorted(os.path.basename(n) for n in ftp.nlst()
                      if DATEI_MUSTER.match(os.path.basename(n)))
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def datei_holen(name, host=FTP_HOST, verzeichnis=FTP_VERZEICHNIS,
                benutzer=FTP_BENUTZER, passwort=FTP_PASSWORT, zeit=20):
    """Eine bestimmte Datei laden -> Rohtext."""
    ftp = ftplib.FTP()
    try:
        ftp.connect(host, 21, timeout=zeit)
        ftp.login(benutzer, passwort)
        ftp.cwd(verzeichnis)
        puffer = io.BytesIO()
        ftp.retrbinary("RETR " + name, puffer.write)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
    return puffer.getvalue().decode("cp1252", "replace")


def neueste_datei(host=FTP_HOST, verzeichnis=FTP_VERZEICHNIS,
                  benutzer=FTP_BENUTZER, passwort=FTP_PASSWORT, zeit=20):
    """Juengsten Auszug holen -> (dateiname, rohtext).

    Sortiert wird ueber den Namen, nicht ueber die FTP-Zeitstempel: im Namen
    steht die Ortszeit des Rechners, im Zeitstempel UTC. Beides zu mischen
    haette zur vollen Stunde die falsche Datei gewaehlt.
    """
    ftp = ftplib.FTP()
    try:
        ftp.connect(host, 21, timeout=zeit)
        ftp.login(benutzer, passwort)
        ftp.cwd(verzeichnis)
        namen = sorted(n for n in ftp.nlst() if DATEI_MUSTER.match(os.path.basename(n)))
        if not namen:
            raise RuntimeError("Kein HOCO-Auszug in %s" % verzeichnis)
        name = os.path.basename(namen[-1])
        puffer = io.BytesIO()
        ftp.retrbinary("RETR " + name, puffer.write)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
    return name, puffer.getvalue().decode("cp1252", "replace")


def neuester_name(host=FTP_HOST, verzeichnis=FTP_VERZEICHNIS,
                  benutzer=FTP_BENUTZER, passwort=FTP_PASSWORT, zeit=15):
    """Nur nachsehen, wie der juengste Auszug heisst - ohne ihn zu laden.

    Das ist die ganze Terminplanung: regelmaessig hier nachfragen und nur dann
    arbeiten, wenn ein anderer Name herauskommt. Ein LIST kostet nichts, der
    Rechner schreibt ohnehin nur alle 30 Minuten. Feste Abrufzeiten waren nur
    noetig, solange jeder Lauf das Panel belegte und Geld kostete.
    """
    ftp = ftplib.FTP()
    try:
        ftp.connect(host, 21, timeout=zeit)
        ftp.login(benutzer, passwort)
        ftp.cwd(verzeichnis)
        namen = sorted(os.path.basename(n) for n in ftp.nlst()
                       if DATEI_MUSTER.match(os.path.basename(n)))
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
    return namen[-1] if namen else ""


# Bloecke, ohne die ein Auszug unbrauchbar ist. Die Reihenfolge in der Datei
# ist fest, und 100017/100037 stehen GANZ HINTEN - fehlen sie, wurde die Datei
# beim Lesen noch geschrieben.
PFLICHT = (TIERSTAMM, "100034", "100014", "100016", STATIONEN, PORTE, BESUCHE, MENGEN)


def unvollstaendig(rohtext, bloecke):
    """Ist der Auszug abgeschnitten? Rueckgabe: Grund als Text, sonst "".

    Der Rechner klammert jeden Block: `COM; Begin Event: <n>;` ... `COM; End
    Event: <n>;`, und die Datei endet mit dem letzten End-Event. Wer liest,
    waehrend geschrieben wird, bekommt offene Klammern - daran ist es sicher zu
    erkennen, egal an welcher Stelle abgeschnitten wurde.

    Am 18.08.2026 passiert: der Auszug 15:29 kam mit 198 KB statt 1,5 MB. Das
    Ergebnis sah gueltig aus (28 Pferde), hatte aber **null** Torzeiten, weil
    das Besuchsprotokoll am Dateiende steht. Eine Pruefung nur auf vorhandene
    Bloecke reicht nicht: bei 90 % der Datei hatte der letzte Block schon
    begonnen und waere durchgerutscht.
    """
    anfang = rohtext.count("Begin Event:")
    ende = rohtext.count("End Event:")
    if anfang != ende or not anfang:
        return "%d Blockanfaenge, aber %d Blockenden" % (anfang, ende)
    if not rohtext.rstrip().endswith(";"):
        return "Datei endet mitten in einer Zeile"
    fehlt = [b for b in PFLICHT if not bloecke.get(b, ([], []))[1]]
    if fehlt:
        return "es fehlen die Bloecke " + ", ".join(fehlt)
    return ""


def datei_zeitpunkt(name):
    """'HOCO_20260818_1029.csv' -> datetime, sonst None."""
    m = DATEI_MUSTER.match(os.path.basename(name))
    if not m:
        return None
    return datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")


# --------------------------------------------------------------------------
# Auswerten
# --------------------------------------------------------------------------
def _zyklus_beginn(bloecke):
    """Uhrzeit des taeglichen Resets aus den Betriebsdaten, sonst 6 Uhr."""
    zeilen = tabelle(bloecke, BETRIEB)
    if zeilen:
        roh = (zeilen[0].get(ZYKLUS_BEGINN) or "").strip()
        m = re.match(r"^(\d{1,2}):(\d{2})", roh)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 6, 0


def _prozent(teil, ganz):
    """Anteil in Prozent, **bei 100 gedeckelt** - so zeigt es auch das Panel.

    Kein Anspruch = 100: es gibt nichts zu holen, also fehlt auch nichts.

    Der Deckel ist nicht kosmetisch. Gemessen am 'Soll bis jetzt' holt ein Tier
    regelmaessig mehr, als der Tag bisher hergibt - Mineralfutter kommt in einer
    einzigen Portion, oft schon am frueheren Morgen. Ungedeckelt stand bei
    Tamira '274 % vom Soll' (30 g geholt gegen 11 g faellig), im Archiv bis
    478 %. Das Panel hat hier immer 100 gezeigt, und mehr als 'erfuellt' gibt es
    auch nicht zu sagen. Aussagekraeftig ist nur, was FEHLT.
    """
    if ganz <= 0:
        return 100
    return min(100, int(round(100.0 * teil / ganz)))


def _stationsnamen(bloecke):
    """Port-Nummer -> Klartextname der Station.

    Zwei Tabellen, weil der HOCO zwei Nummernkreise fuehrt: das
    Besuchsprotokoll nennt den PORT, die Namensliste die Stations-Kennung.
    """
    namen = {r.get(S_STATION): r.get(S_NAME, "") for r in tabelle(bloecke, STATIONEN)}
    return {r.get(P_PORT): namen.get(r.get(P_STATION), "") for r in tabelle(bloecke, PORTE)}


def _torzeiten(bloecke, tag):
    """Erkennungen am Selektionstor je Tier fuer einen Kalendertag.

    Die Selektionsliste des Panels laeuft ueber den Kalendertag, nicht ueber
    den Fuetterungszyklus - das bleibt hier genauso. Mehrere Erkennungen in
    derselben Minute zaehlen als eine; das Panel zeigt sie auch nur einmal.
    """
    ports = _stationsnamen(bloecke)
    tor = {p for p, n in ports.items() if n == SEL_STATION}
    if not tor:
        _log("WARNUNG: keine Station '%s' gefunden - keine Torzeiten." % SEL_STATION)
        return {}
    je_tier = {}
    for b in tabelle(bloecke, BESUCHE):
        nr = b.get(B_NR)
        if nr == GRUPPE or b.get(B_PORT) not in tor:
            continue
        try:
            ts = datetime.datetime.strptime(b.get(B_ZEIT, ""), "%d.%m.%Y %H:%M:%S")
        except ValueError:
            continue
        if ts.date() != tag:
            continue
        je_tier.setdefault(nr, set()).add(ts.strftime("%H:%M"))
    return {nr: sorted(z) for nr, z in je_tier.items()}


def _heu_stationen(bloecke):
    """Welche Stationen geben wirklich Heu aus?

    Nicht jede Station, an der Komponente 10 ('Raufutter_1') gebucht wird, hat
    Heu. Die 'Easy St. 11' ist ein HayFusion, bei dem im Panel nur KF1 (33 g)
    und Min1 (15 g) eingerichtet sind - die Reiter 'Selektionstor' und
    'Schieber/Raufe' sind ausgegraut. Trotzdem steht dort bei jedem Besuch eine
    Komponente 10 mit **ist = 1**, unabhaengig davon, wie lange das Tier da war
    (Auryn 146 Sekunden -> 1). Das ist eine Marke, keine Fressminute.

    Erkannt wird das an der Station selbst: gibt sie auch Kraft- oder
    Mineralfutter aus, ist ihre Komponente 10 kein Heu. Der Heuschieber gibt
    ausschliesslich Komponente 10 aus - dort stimmt es (Szilaj: 418 Sekunden
    davor, 6 Minuten gutgeschrieben).
    """
    mengen = {}
    for r in tabelle(bloecke, MENGEN):
        mengen.setdefault(r.get(M_BESUCH), []).append(r)
    arten = {}
    for b in tabelle(bloecke, BESUCHE):
        for m in mengen.get(b.get(B_ID), []):
            art = KOMPONENTE.get(m.get(M_KOMPONENTE))
            if art:
                arten.setdefault(b.get(B_PORT), set()).add(art)
    return {port for port, a in arten.items() if a == {"rf"}}


def _zyklusfenster(bloecke, jetzt):
    """Anfang und Ende des laufenden Fuetterungszyklus -> (ab, bis).

    Alle Tagessummen des Rechners (`900060`, `900064`) laufen ueber diesen
    Zyklus, nicht ueber den Kalendertag. Was daneben angezeigt wird - die
    Besuchsliste, die abgezogenen Marken - muss denselben Ausschnitt nehmen,
    sonst widerspricht die Liste der Summe darueber. Genau das ist am
    18.08.2026 aufgefallen: Tamiras Karte sagte 4 Minuten Heu, die Liste
    darunter zeigte 34 - die Differenz war die Nacht vor dem 6-Uhr-Reset.
    """
    h, m = _zyklus_beginn(bloecke)
    ab = jetzt.replace(hour=h, minute=m, second=0, microsecond=0)
    if jetzt < ab:
        ab -= datetime.timedelta(days=1)
    return ab, ab + datetime.timedelta(days=1)


def _heu_marken(bloecke, ab, bis):
    """Schein-Minuten je Tier: Komponente 10 an einer Station ohne Heu.

    Die 'Easy St. 11' gibt **kein Heu** - im Panel sind dort nur KF1 (33 g) und
    Min1 (15 g) eingerichtet, die Reiter 'Selektionstor' und 'Schieber/Raufe'
    sind ausgegraut. Trotzdem bucht sie bei jedem Besuch eine Komponente 10
    mit `ist = 1`, unabhaengig von der Verweildauer (Auryn: zwanzig Besuche zu
    142-146 Sekunden, jedes Mal genau 1). Das ist eine Besuchsmarke, keine
    Fressminute.

    Der Rechner rechnet sie trotzdem in seine Tagessumme `900064` - am
    18.08.2026 nachgewiesen: gegen die Summe aus dem Besuchsprotokoll stimmten
    nur 18 von 28 Tieren, wenn man die Easy Station weglaesst, und **28 von
    28**, wenn man sie mitzaehlt. Das Panel zeigte fuer Temperino deshalb
    '8 Min' Raufutter, obwohl er den ganzen Zyklus ueber nicht ein einziges
    Mal am Heuschieber war; Auryns 57 Panel-Minuten waren 36 echte (eine
    Sitzung um 14:22, 2233 Sekunden) plus 19 Marken.

    Deshalb werden sie hier gezaehlt und in `auswerten` wieder abgezogen. Das
    ist die einzige Stelle, an der bewusst eine **andere** Zahl steht als am
    Panel - mit voller Absicht: gemeint ist die Frage des Einstellers 'wie
    lange hat mein Pferd Heu gefressen', und darauf antworten die Marken
    falsch.

    Einzeltier-Heu kommt ohnehin nur vom Heuschieber (Port 2): die Raufen 3-14
    bucht der Rechner ausschliesslich auf die Gruppe (Tier-Nr. 0).
    """
    heu = _heu_stationen(bloecke)
    mengen = {}
    for r in tabelle(bloecke, MENGEN):
        mengen.setdefault(r.get(M_BESUCH), []).append(r)
    je_tier = {}
    for b in tabelle(bloecke, BESUCHE):
        nr = b.get(B_NR)
        if nr == GRUPPE or b.get(B_PORT) in heu:
            continue
        try:
            ts = datetime.datetime.strptime(b.get(B_ZEIT, ""), "%d.%m.%Y %H:%M:%S")
        except ValueError:
            continue
        if not (ab <= ts < bis):
            continue
        for m in mengen.get(b.get(B_ID), []):
            if KOMPONENTE.get(m.get(M_KOMPONENTE)) == "rf":
                je_tier[nr] = je_tier.get(nr, 0.0) + _zahl(m.get(M_IST))
    return je_tier


def _besuche(bloecke, ab, bis, hoechstens=120):
    """Jeder Stationsbesuch eines Kalendertags, neueste zuerst.

    Das gab es am Panel nicht: dort stand nur die Tagessumme. Der Auszug
    protokolliert jeden Besuch mit Startzeit (`801703`), **Dauer in Sekunden**
    (`801706`) und der Menge, die das Tier dabei bekam - auch die Besuche, bei
    denen es **nichts** bekam, weil die Ration schon geholt war.

    Die Dauer ist nachgewiesen: bei 1503 Saetzen beginnt der naechste Besuch
    derselben Station auf die Sekunde genau am Ende des vorigen (Auryn
    14:11:05 + 146 s = 14:13:31). Solche unmittelbar anschliessenden Saetze
    werden hier zu **einem** Besuch zusammengefasst - sonst steht dieselbe
    Minute mehrfach in der Liste, was am 18.08.2026 als 'doppelte Daten'
    aufgefallen ist.

    Der Ausschnitt sind die **letzten 24 Stunden**, gerechnet ab jetzt - so
    gewuenscht am 19.08.2026. Er wandert also mit und haelt sich weder an den
    Kalendertag (bis 0.32.0) noch an den Fuetterungszyklus (0.33.0 bis 0.36.1).

    Damit zaehlt sich die Liste **nicht** mehr zu den Zahlen im Reiter 'Heute'
    zusammen, und das ist Absicht: 'Heute' gehoert zum Zyklus ab 6 Uhr, dieser
    Reiter zeigt durchgehend die letzten 24 Stunden - Besuchsliste und
    Verlaufstabelle also denselben Massstab.

    Das Datum steht bewusst NICHT dabei, obwohl das Fenster ueber Mitternacht
    zurueckreicht: die Liste ist nach Zeit sortiert und laeuft hoechstens einen
    Tag zurueck - wo der Sprung liegt, sieht man an der Reihenfolge. Am
    19.08.2026 ausprobiert und wieder entfernt, es war nur zusaetzliches
    Kleingedrucktes in einer ohnehin engen Zeile.
    """
    ports = _stationsnamen(bloecke)
    heu = _heu_stationen(bloecke)
    mengen = {}
    for r in tabelle(bloecke, MENGEN):
        mengen.setdefault(r.get(M_BESUCH), []).append(r)

    roh = {}
    for b in tabelle(bloecke, BESUCHE):
        nr = b.get(B_NR)
        if nr == GRUPPE:
            continue
        try:
            ts = datetime.datetime.strptime(b.get(B_ZEIT, ""), "%d.%m.%Y %H:%M:%S")
        except ValueError:
            continue
        if not (ab <= ts < bis):
            continue
        port = b.get(B_PORT)
        satz = {"ts": ts, "dauer": int(_zahl(b.get(B_DAUER)) or 0), "port": port}
        for m in mengen.get(b.get(B_ID), []):
            wert = _zahl(m.get(M_IST))
            if not wert:
                continue
            art = KOMPONENTE.get(m.get(M_KOMPONENTE))
            if art == "rf" and port not in heu:
                continue                      # Marke, kein Heu (siehe _heu_stationen)
            if art:
                satz[art] = satz.get(art, 0) + wert
        roh.setdefault(nr, []).append(satz)

    aus = {}
    for nr, liste in roh.items():
        liste.sort(key=lambda s: s["ts"])
        zusammen = []
        for s in liste:
            v = zusammen[-1] if zusammen else None
            anschluss = (v and v["port"] == s["port"]
                         and abs((s["ts"] - (v["ts"] + datetime.timedelta(seconds=v["dauer"])))
                                 .total_seconds()) <= 5)
            if anschluss:
                v["dauer"] += s["dauer"]
                for art in ("rf", "kf", "min"):
                    if s.get(art):
                        v[art] = v.get(art, 0) + s[art]
            else:
                zusammen.append(dict(s))
        fertig = []
        for s in zusammen[-hoechstens:]:
            e = {"zeit": s["ts"].strftime("%H:%M"), "station": ports.get(s["port"], "?")}
            if s["dauer"]:
                e["dauer"] = s["dauer"]
                e["bis"] = (s["ts"] + datetime.timedelta(seconds=s["dauer"])).strftime("%H:%M")
            for art in ("rf", "kf", "min"):
                if s.get(art):
                    e[art] = s[art]
            fertig.append(e)
        aus[nr] = list(reversed(fertig))       # neueste zuerst
    return aus


def _zutrittszeiten(bloecke):
    """Zutrittszeiten am Selektionstor je Tier -> {nr: [{nr, von, bis, ein}]}.

    Panel: Pferdeverwaltung -> Selektionen. Fuenf Zeitfenster je Bereich, jedes
    einzeln ein- oder ausschaltbar. Am 18.08.2026 gegen Tamira geprueft
    (Zutrittszeit 1: 10:01 bis 10:00, Aus).

    Gebraucht fuer die Aenderungswuensche: nur so laesst sich sagen, ob eine
    gewuenschte Zeit am Rechner schon eingetragen ist.
    """
    aus = {}
    for r in tabelle(bloecke, SEL_ZEITEN):
        nr = r.get(NR)
        if nr is None or nr == GRUPPE:
            continue
        aus.setdefault(nr, []).append({
            "bereich": r.get(SZ_BEREICH, ""),
            "nr": r.get(SZ_NR, ""),
            "von": (r.get(SZ_VON) or "")[:5],
            "bis": (r.get(SZ_BIS) or "")[:5],
            "ein": r.get(SZ_EIN) == "1",
        })
    return {nr: sorted(liste, key=lambda e: (e["bereich"], e["nr"])) for nr, liste in aus.items()}


def _meldungen(bloecke, namen):
    """Was der Rechner selbst bemaengelt -> {nr: (text, seit)}.

    Das ist der verlaesslichste Befund ueberhaupt, weil nur der Rechner alle
    Stationen sieht (siehe rueckstand.py). Der Wortlaut ist derselbe wie auf
    der Hinweisseite des Panels, damit sich an den Texten nichts aendert.

    Dazu der **Zeitpunkt** (`801905`). Er steht seit jeher im Auszug, wurde
    aber nicht gelesen - und der Satz 'in den letzten 12 Stunden' stimmte
    dadurch nicht: die fuenf Meldungen vom 18.08.2026 waren alle vom 17.08.
    um 14:30 und standen seit ueber 29 Stunden unveraendert da. Der Rechner
    schreibt sie einmal und laesst sie liegen, bis das Tier wieder erkannt
    wird. Der Wortlaut bleibt trotzdem der des Panels (so steht er dort auch
    heute noch) - dazu kommt jetzt nur, seit wann er dort steht.
    """
    aus = {}
    for r in tabelle(bloecke, MELDUNGEN):
        if r.get(M_ART) != M_NICHT_ERKANNT:
            continue
        nr = r.get(M_NR)
        text = ("Pferd %s (%s) wurde in den letzten 12 Stunden bei keiner "
                "Station erkannt. Transponderfehler?" % (nr, namen.get(nr, "?")))
        aus[nr] = (text, (r.get(M_ZEIT) or "").strip())
    return aus


def auswerten(rohtext, jetzt=None, scope="ftp"):
    """Auszug -> derselbe Datensatz, den wasserbauer.abrufen() liefert.

    Bewusst formatgleich: Bot, Website und Archiv lesen weiter dieselben
    Felder, damit sich der Umstieg auf nichts auswirkt ausser auf die Herkunft
    der Zahlen.
    """
    jetzt = jetzt or datetime.datetime.now()
    bloecke = bloecke_lesen(rohtext)
    if TIERSTAMM not in bloecke:
        raise ValueError("Kein Tierstamm (Block %s) im Auszug" % TIERSTAMM)

    stamm = [r for r in tabelle(bloecke, TIERSTAMM) if r.get(NR) != GRUPPE]
    namen = {r[NR]: r.get(NAME, "") for r in stamm}
    ab, bis = _zyklusfenster(bloecke, jetzt)
    # Die Besuchsliste laeuft ueber die letzten 24 Stunden, die Futtersummen
    # ueber den Zyklus - zwei verschiedene Fragen, zwei verschiedene Fenster.
    besuch_ab = jetzt - datetime.timedelta(days=1)
    # Die Torzeiten bleiben beim KALENDERTAG: die Selektionsliste des Panels
    # laeuft so, und das Zeitband auf der Pferdeseite ist von 0 bis 24 Uhr
    # beschriftet. Nur die Futterzahlen und die Besuchsliste gehoeren zum
    # Zyklus.
    tore = _torzeiten(bloecke, jetzt.date())
    besuche = _besuche(bloecke, besuch_ab, jetzt)
    zutritt = _zutrittszeiten(bloecke)
    hinweise = _meldungen(bloecke, namen)
    stand = jetzt.strftime("%d.%m.%Y %H:%M")

    # Je Futterart und Tier summieren - es gibt mehrere Sorten (Kraftfutter_1..4,
    # Raufutter_1..3, Mineral_1..4), das Panel zeigt nur die Summe.
    summen = {}
    for art, (block, feld_anspruch, feld_geholt, feld_offen) in FUTTER.items():
        je_tier = {}
        for r in tabelle(bloecke, block):
            nr = r.get(NR)
            if nr is None or nr == GRUPPE:
                continue
            a, g, o = je_tier.get(nr, (0.0, 0.0, 0.0))
            je_tier[nr] = (a + _zahl(r.get(feld_anspruch)),
                           g + _zahl(r.get(feld_geholt)),
                           o + _zahl(r.get(feld_offen)))
        summen[art] = je_tier

    # NICHT abziehen. Am 18.08.2026 kurz versucht und sofort wieder verworfen:
    # die Minuten, die der Rechner an der Easy Station gutschreibt, sind echt -
    # Temperino hatte 8, Leonhard 6, und beide sollen sie sehen. Was hier
    # gezaehlt wird, dient nur der Anzeige (siehe _heu_marken).
    marken = _heu_marken(bloecke, ab, bis)

    liste = []
    for r in sorted(stamm, key=lambda x: int(x[NR] or 0)):
        nr = r[NR]
        text, seit = hinweise.get(nr, (None, ""))
        p = {"nr": int(nr), "name": r.get(NAME, ""),
             "transponder": r.get(TRANSPONDER, ""),
             "hinweis": text, "hinweis_seit": seit,
             "zuletzt_gesehen": stand}
        for art in ("rf", "kf", "min"):
            anspruch, geholt, offen = summen[art].get(nr, (0.0, 0.0, 0.0))
            bisherig = geholt + offen
            fmt = einheiten.EINHEIT[{"rf": "RF", "kf": "KF", "min": "MIN"}[art]]
            p[art] = {
                "anspruch_gesamt": fmt["gesamt"].format(anspruch),
                "fortschritt_gesamt": fmt["gesamt"].format(geholt),
                "fortschritt_gesamt_prozent": _prozent(geholt, anspruch),
                "anspruch_bisherig": fmt["bisherig"].format(bisherig),
                "fortschritt_bisherig_prozent": _prozent(geholt, bisherig),
            }
        if nr in tore:
            p["selektion"] = tore[nr]
        if nr in besuche:
            p["besuche"] = besuche[nr]
        # Nur die eingeschalteten Fenster - ausgeschaltete stehen mit 00:00 da
        # und wuerden die Anzeige nur zumuellen.
        an = [e for e in zutritt.get(nr, []) if e["ein"]]
        if an:
            p["zutrittszeiten"] = an
        liste.append(p)

    auffaellig = rueckstand.pruefe(liste)
    # Sitzt jedes Feld noch da, wo wir es vermuten? Keine Zeile dieses Auszugs
    # ist dokumentiert; aendert eine Firmware eine Feldnummer, liefert das
    # Add-on sonst weiter Zahlen, die gueltig aussehen. Siehe pruefung.py.
    befund = pruefung.pruefen(_MODUL, bloecke, liste, ab, bis)
    return {
        "stand": stand,
        "scope": scope,
        "anzahl_pferde": len(liste),
        "rueckstand_text": rueckstand.zusammenfassung(auffaellig),
        "rueckstand_anzahl": len(auffaellig),
        "pferde": liste,
        "selektion_datum": jetzt.strftime("%Y-%m-%d"),
        "pruefung": befund,
    }


def abrufen(jetzt=None, **ftp_argumente):
    """Auszug holen, pruefen, auswerten -> (ergebnis, dateiname, alter_minuten).

    Geprueft wird auf Vollstaendigkeit: der Rechner schreibt die Datei in einem
    Zug, und wer im falschen Moment liest, bekommt die Haelfte. Ist der juengste
    Auszug unvollstaendig, wird der davor genommen - der ist fertig geschrieben
    und hoechstens 30 Minuten aelter. Lieber etwas aeltere vollstaendige Zahlen
    als frische halbe.
    """
    jetzt = jetzt or datetime.datetime.now()
    namen = dateiliste(**ftp_argumente)
    if not namen:
        raise RuntimeError("Kein HOCO-Auszug gefunden")
    letzter_fehler = None
    for name in reversed(namen[-2:]):          # juengster zuerst, dann der davor
        rohtext = datei_holen(name, **ftp_argumente)
        bloecke = bloecke_lesen(rohtext)
        grund = unvollstaendig(rohtext, bloecke)
        if grund:
            letzter_fehler = ("%s ist unvollstaendig (%d Zeichen, %s) - "
                              "vermutlich beim Schreiben gelesen."
                              % (name, len(rohtext), grund))
            _log("WARNUNG: " + letzter_fehler)
            continue
        geschrieben = datei_zeitpunkt(name)
        alter = (jetzt - geschrieben).total_seconds() / 60.0 if geschrieben else None
        _log("Auszug %s geholt (%d Zeichen, %s)"
             % (name, len(rohtext),
                "%.0f Min alt" % alter if alter is not None else "Alter unbekannt"))
        if alter is not None and alter > ALTER_WARNUNG_MIN:
            _log("WARNUNG: juengster Auszug ist %.0f Minuten alt - schreibt der "
                 "Rechner noch? Die Zahlen sind entsprechend alt." % alter)
        return auswerten(rohtext, jetzt=jetzt), name, alter
    raise RuntimeError(letzter_fehler or "Kein brauchbarer Auszug")


# pruefung.py braucht die Feldkarte dieses Moduls, darf es aber nicht
# importieren (Ringschluss). Deshalb wird es hereingereicht.
import sys as _sys                                            # noqa: E402
_MODUL = _sys.modules[__name__]
