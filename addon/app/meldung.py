# -*- coding: utf-8 -*-
"""Morgenmeldung: welche Pferde hat der Rechner nicht erkannt?

Einmal am Morgen geht eine Benachrichtigung ans Hofbuero mit genau den Tieren,
die der Fuetterungsrechner selbst gemeldet hat ('in den letzten 12 Stunden bei
keiner Station erkannt' - Transponderfehler). Das ist derselbe Befund, der im
Dashboard unter 'Auffaellig' steht.

Warum die Einstellung hier liegt und nicht als HA-Automation:
Der Zeitplan der Abrufe wird schon im Add-on gepflegt. Stuende die Meldung
daneben in einer Automation, muesste man an zwei Stellen suchen, und ein
YAML-Fehler dort waere von der Oberflaeche aus nicht zu sehen. Also dieselbe
Bauart wie zeitplan.py: eine kleine Datei in /data, aenderbar im Ingress.

Zwei Eigenheiten, die aus dem Betrieb kommen:
  * **Nachholen statt verpassen.** Ausgeloest wird nicht auf die Minute genau,
    sondern 'ab dieser Uhrzeit, einmal am Tag'. Startet das Add-on gerade um
    07:00 neu, kaeme eine minutengenaue Meldung nie an.
  * **Stille bei Fehlanzeige.** Ist nichts zu melden, kommt normalerweise auch
    nichts - eine taegliche 'alles in Ordnung'-Meldung liest nach einer Woche
    niemand mehr. Wer die Bestaetigung will, schaltet sie ein.
"""
import json
import os
import time

from . import texte, zeitplan

DATA_DIR = "/data"
DATEI = os.path.join(DATA_DIR, "meldung.json")

# Empfaenger aus den Add-on-Einstellungen - derselbe Dienst, der auch die
# Freigabe-Anfragen bekommt. In der Oberflaeche ist er je Meldung ueberschreibbar.
STANDARD_ZIEL = os.environ.get("ABRUF_HOFBUERO_NOTIFY", "notify.mobile_app_iphone")

# Was soll gemeldet werden? Der Vorgabewert ist bewusst der engste: die
# gerechneten Rueckstaende betreffen an manchen Tagen das halbe Stallgebaeude
# und wuerden die Meldung wertlos machen.
UMFAENGE = {
    "transponder": "Nur nicht erkannte Tiere (Transponderfehler)",
    "alles": "Alles Auffaellige (auch Rueckstaende beim Futter)",
}

STANDARD = {
    "aktiv": True,
    "zeit": "07:00",
    "tage": list(range(7)),
    "umfang": "transponder",
    "ziel": "",              # leer = Dienst aus den Add-on-Einstellungen
    "auch_ohne_befund": False,
    "zuletzt": "",           # YYYY-MM-DD des letzten Versands (Tagessperre)
    "zuletzt_zeit": "",      # 17.08.2026 07:00 - nur zur Anzeige
    "zuletzt_titel": "",     # Betreff, der tatsaechlich rausging
    "zuletzt_anlass": "",    # 'plan' oder 'test'
}


def _normieren(roh):
    d = dict(STANDARD)
    roh = roh if isinstance(roh, dict) else {}
    d["aktiv"] = bool(roh.get("aktiv", STANDARD["aktiv"]))
    d["zeit"] = zeitplan.norm_zeit(roh.get("zeit")) or STANDARD["zeit"]
    try:
        tage = sorted({int(t) for t in roh.get("tage", STANDARD["tage"])
                       if 0 <= int(t) <= 6})
    except Exception:
        tage = []
    d["tage"] = tage or list(range(7))
    d["umfang"] = roh.get("umfang") if roh.get("umfang") in UMFAENGE else "transponder"
    d["ziel"] = str(roh.get("ziel") or "").strip()
    d["auch_ohne_befund"] = bool(roh.get("auch_ohne_befund", False))
    for feld in ("zuletzt", "zuletzt_zeit", "zuletzt_titel", "zuletzt_anlass"):
        d[feld] = str(roh.get(feld) or "")
    return d


class Meldung:
    """Einstellungen der Morgenmeldung, gesichert in /data/meldung.json."""

    def __init__(self):
        self.d = _normieren(self._lesen())

    # ---------------- Datei ----------------
    def _lesen(self):
        try:
            with open(DATEI, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def speichern(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATEI + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATEI)

    def __getitem__(self, k):
        return self.d[k]

    def get(self, k, default=None):
        return self.d.get(k, default)

    # ---------------- Aendern ----------------
    def setzen(self, felder):
        """Uebernimmt die Eingaben aus der Oberflaeche. Fehlertext oder None."""
        zeit = zeitplan.norm_zeit(felder.get("zeit"))
        if zeit is None:
            return "Keine gueltige Uhrzeit fuer die Morgenmeldung."
        ziel = str(felder.get("ziel") or "").strip()
        if ziel and not _dienst_gueltig(ziel):
            return ("'%s' ist kein Dienst. Erwartet wird etwas wie "
                    "'notify.mobile_app_iphone'." % ziel)
        neu = dict(self.d)
        neu.update(felder)
        neu["zeit"] = zeit
        neu["ziel"] = ziel
        self.d = _normieren(neu)
        self.speichern()
        return None

    # ---------------- Auswerten ----------------
    def faellig(self, jetzt=None):
        """Ist die Meldung heute dran und noch nicht raus?"""
        if not self.d["aktiv"]:
            return False
        jetzt = jetzt or time.localtime()
        if jetzt.tm_wday not in self.d["tage"]:
            return False
        if time.strftime("%H:%M", jetzt) < self.d["zeit"]:
            return False
        return self.d["zuletzt"] != time.strftime("%Y-%m-%d", jetzt)

    def erledigt(self, jetzt=None):
        """Merkt den Versand - sonst kaeme er jede Minute erneut."""
        self.d["zuletzt"] = time.strftime("%Y-%m-%d", jetzt or time.localtime())
        self.speichern()

    def versand_merken(self, titel, anlass="plan", jetzt=None):
        """Was ist wann tatsaechlich rausgegangen - fuer die Oberflaeche."""
        self.d["zuletzt_zeit"] = time.strftime("%d.%m.%Y %H:%M",
                                               jetzt or time.localtime())
        self.d["zuletzt_titel"] = str(titel or "")
        self.d["zuletzt_anlass"] = anlass
        self.speichern()

    def zuletzt_text(self):
        """'17.08.2026 07:00 (Test) - Aktivstall: 3 Tiere nicht erkannt'"""
        if not self.d["zuletzt_zeit"]:
            return ""
        art = " (Test)" if self.d["zuletzt_anlass"] == "test" else ""
        titel = (" - " + self.d["zuletzt_titel"]) if self.d["zuletzt_titel"] else ""
        return self.d["zuletzt_zeit"] + art + titel

    def naechste(self, jetzt=None):
        """'heute 07:00' / 'morgen 07:00' / '' - fuer die Oberflaeche."""
        if not self.d["aktiv"]:
            return ""
        jetzt = jetzt or time.localtime()
        heute = time.strftime("%Y-%m-%d", jetzt)
        offen_heute = (jetzt.tm_wday in self.d["tage"]
                       and self.d["zuletzt"] != heute)
        for versatz in range(8):
            wtag = (jetzt.tm_wday + versatz) % 7
            if wtag not in self.d["tage"]:
                continue
            if versatz == 0:
                if not offen_heute:
                    continue
                return "heute %s" % self.d["zeit"]
            if versatz == 1:
                return "morgen %s" % self.d["zeit"]
            return "%s %s" % (zeitplan.TAGE_KURZ[wtag], self.d["zeit"])
        return ""

    def beschreibung(self):
        tage = ("taeglich" if len(self.d["tage"]) == 7
                else " ".join(zeitplan.TAGE_KURZ[t] for t in self.d["tage"]))
        return "%s um %s" % (tage, self.d["zeit"])

    # ---------------- Inhalt ----------------
    def betroffene(self, pferde):
        """Die Tiere, die in diese Meldung gehoeren - schon bewertet."""
        if self.d["umfang"] == "alles":
            return [p for p in pferde if p.get("rueckstand")]
        return [p for p in pferde if p.get("rueckstand") == "transponder"]

    def nachricht(self, pferde, stand=""):
        """(titel, text) fuer die Benachrichtigung.

        Der Wortlaut steht in texte.py (Gruppe 'Meldung') und ist im Ingress
        aenderbar wie jede andere Vorlage - hier wird nur zusammengesetzt."""
        treffer = self.betroffene(pferde)
        stand = stand or "unbekannt"
        if not treffer:
            return (texte.T("melde_ok_titel"), texte.T("melde_ok_text", stand=stand))
        # Bei den nicht erkannten Tieren ist der Grund fuer alle derselbe - sie
        # stehen deshalb in einer Aufzaehlung, und der Satz dazu einmal
        # darunter. Bei 'alles' unterscheiden sich die Gruende, da braucht
        # jedes Tier seine eigene Zeile.
        if self.d["umfang"] == "alles":
            k_titel, k_zeile, k_text = ("melde_titel_alles", "melde_zeile_alles",
                                        "melde_text_alles")
            trenner = "\n"
        else:
            k_titel, k_zeile, k_text = "melde_titel", "melde_zeile", "melde_text"
            trenner = ", "
        zeilen = []
        for p in treffer:
            zeilen.append(texte.T(
                k_zeile, nr=p.get("nr", ""), name=p.get("name") or "",
                grund=(p.get("hinweis") or p.get("rueckstand_text") or "").strip()))
        anzahl = len(treffer)
        mehrzahl = "" if anzahl == 1 else "e"
        titel = texte.T(k_titel, anzahl=anzahl, mehrzahl=mehrzahl)
        return titel, texte.T(k_text, liste=trenner.join(zeilen), anzahl=anzahl,
                              mehrzahl=mehrzahl, stand=stand)


def _dienst_gueltig(ziel):
    teile = ziel.split(".")
    return len(teile) == 2 and all(t and t.replace("_", "").isalnum() for t in teile)
