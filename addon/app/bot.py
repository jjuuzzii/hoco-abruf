# -*- coding: utf-8 -*-
"""HOCO-Abruf – WhatsApp-Bot als Home-Assistant-Add-on.

Einsteller:
  /anmelden           -> Bot fragt: welche Pferde?
  <Name(n), Komma>    -> Anmeldung (1..n Pferde) geht zur FREIGABE ans Hofbuero
  (Hofbuero bestaetigt/lehnt per iPhone-Benachrichtigung ab)
  -> nach Freigabe schickt der Bot die persoenliche(n) Website-Link(s)
  /abruf              -> Bot schickt Kurzstatus + Link je Pferd
  /abmelden           -> Verknuepfung loeschen

Website (WP-Plugin): der Bot schiebt Schluessel (beim Start) und Tagesdaten
(nach jedem Abruf) automatisch an WEBSITE_API. Links = WEBSITE_LINK + Schluessel.
Schluessel je Pferd: /share/fuetterungsabruf/schluessel.json.
"""
import os
import re
import json
import time
import unicodedata
import difflib
import secrets
import string
import threading
from datetime import date, datetime, timedelta
import urllib.request
import urllib.parse

import websocket  # websocket-client

from . import abruf, hoco, meldung, rueckstand, web, texte, wunsch
from .texte import T

CORE_HTTP = "http://supervisor/core"
CORE_WS = "ws://supervisor/core/websocket"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HOFBUERO = meldung.STANDARD_ZIEL      # Dienst aus den Add-on-Einstellungen

# Website-Anbindung
WEBSITE_LINK = os.environ.get("WEBSITE_LINK", "").strip()      # z.B. https://perwein-hofgut.de/fuetterung/?k=
WEBSITE_API = os.environ.get("WEBSITE_API", "").strip()        # z.B. https://perwein-hofgut.de/wp-json/fuetterung/v1
WEBSITE_SECRET = os.environ.get("WEBSITE_SECRET", "").strip()
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


DATA_DIR = "/data"
STORE = os.path.join(DATA_DIR, "zuordnung.json")
SHARE_DIR = "/share/fuetterungsabruf"
PFERDE = os.path.join(SHARE_DIR, "pferde.json")
SCHLUESSEL = os.path.join(SHARE_DIR, "schluessel.json")

EVENTS = ["whatsapp_message_received", "mobile_app_notification_action"]
OK_PREFIX = "ABRUF_OK_"
NEIN_PREFIX = "ABRUF_NEIN_"

PANEL = {
    1: "Delana", 2: "Tamira", 3: "Lina", 4: "Pepsi", 5: "Fini", 6: "Fendi",
    7: "Wira", 8: "Fiora", 9: "Farina", 10: "Tiffy", 11: "Mina", 12: "Sisi",
    13: "Auryn", 14: "Lolo", 15: "Alvin", 16: "Temperino", 17: "Duque",
    18: "Leonhard", 19: "Frodo", 20: "Corazon", 21: "Dutsty", 22: "Diamant",
    23: "Szilaj", 24: "Hidalgo", 25: "Blackjack", 26: "Nilson", 27: "Timon",
    29: "Boca",
}


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").split())


def _nrs(eintrag):
    """Macht aus altem/neuem Eintrag eine Liste von Pferde-Nummern."""
    if isinstance(eintrag, list):
        out = []
        for e in eintrag:
            if isinstance(e, int):
                out.append(e)
            elif isinstance(e, dict) and "nr" in e:
                out.append(e["nr"])
            elif isinstance(e, str) and e.isdigit():
                out.append(int(e))
        return out
    if isinstance(eintrag, dict) and "nr" in eintrag:
        return [eintrag["nr"]]
    return []


class Bot:

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.lock = threading.Lock()
        self.store = self._laden()
        self.keys = self._keys_laden()
        self.mitarbeiter = self._mitarbeiter_laden()
        self.meldung = meldung.Meldung()
        self.wuensche = []     # offene Aenderungswuensche der Einsteller   # Morgenmeldung (ebenfalls im Ingress)
        self._seed_pferde()

    # ---------- Persistenz ----------
    def _laden(self):
        try:
            with open(STORE, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        d.setdefault("zuordnung", {})
        d.setdefault("wartet", {})
        d.setdefault("wunsch_gemeldet", {})  # id -> schon ans Hofbuero gemeldet
        d.setdefault("wunsch_gewarnt", {})   # id -> Ruecknahme-Warnung schon raus
        d.setdefault("offen", {})
        d.setdefault("namen", {})
        # Reste des Abos: der Dienst ist seit 18.08.2026 kostenlos, die Felder
        # werden nirgends mehr gelesen. Einmal wegraeumen, damit in der Datei
        # nichts steht, was jemanden auf eine falsche Faehrte fuehrt.
        for veraltet in ("bezahlt", "bezahlt_erinnert"):
            d.pop(veraltet, None)
        # Migration: Eintraege auf Listen von Nummern vereinheitlichen
        for schl in ("zuordnung", "offen"):
            for num in list(d[schl].keys()):
                d[schl][num] = _nrs(d[schl][num])
        return d

    def _speichern(self):
        tmp = STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.store, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STORE)

    def abmelden(self, nummer):
        """Vom Hofbuero ausgeloeste Abmeldung (Ingress).

        Rueckgabe: (war_angemeldet, [Pferdenamen, deren Link jetzt tot ist],
                    [Pferdenamen, die noch jemand anderem gehoeren]).

        Der Zugangsschluessel haengt am PFERD, nicht an der Person - zwei
        Einsteller eines Pferds benutzen denselben Link. Deshalb wird er nur
        geloescht, wenn nach dieser Abmeldung NIEMAND mehr auf dem Pferd steht.
        Waere es anders, spraenge beim Abmelden des einen dem anderen still der
        Zugang weg.

        Fuer den umgekehrten Fall - jemand soll den Zugang verlieren, obwohl
        das Pferd noch anderen gehoert - gibt es den Knopf 'Neuen Code
        erzeugen'. Das Hofbuero wird in der Oberflaeche darauf hingewiesen.
        """
        nummer = str(nummer)
        weg = self.store["zuordnung"].pop(nummer, None)
        self.store["offen"].pop(nummer, None)
        self.store["wartet"].pop(nummer, None)
        self._speichern()

        verwaist, geteilt = [], []
        for nr in _nrs(weg):
            if self.einsteller_von(nr):
                geteilt.append(PANEL.get(nr, str(nr)))
            elif self.zugang_entfernen(nr):
                verwaist.append(PANEL.get(nr, str(nr)))
        return bool(weg), verwaist, geteilt

    def _keys_laden(self):
        try:
            with open(SCHLUESSEL, encoding="utf-8") as f:
                d = json.load(f)
            return {int(k): v.get("schluessel", "") for k, v in d.get("pferde", {}).items()}
        except Exception as e:
            log("schluessel.json nicht gelesen: %s" % e)
            return {}

    def _mitarbeiter_laden(self):
        """Der Zugang fuer den Stallmitarbeiter - einer fuer alle Pferde.

        Er haengt nicht an einem Tier, sondern an der Aufgabe: Koppelzeiten
        nachsehen und offene Aenderungswuensche abarbeiten. Deshalb steht er
        neben `pferde` in derselben Datei und laeuft ueber denselben
        Push-Endpunkt `/keys` - die Website erkennt ihn am Wert 'mitarbeiter'
        statt an einer Pferdenummer. So gilt fuer ihn ohne Zusatzaufwand alles,
        was fuer die Pferdeschluessel schon gilt: erneuern, entfernen, pushen.
        """
        try:
            with open(SCHLUESSEL, encoding="utf-8") as f:
                vorhanden = (json.load(f).get("mitarbeiter") or "").strip()
        except Exception:
            vorhanden = ""
        if vorhanden:
            return vorhanden
        # Sofort festschreiben, nicht erst beim naechsten Speichern: sonst
        # erzeugt jeder Neustart einen anderen Code und der Link, den der
        # Mitarbeiter auf dem Handy hat, ist jedes Mal tot.
        code = self._code_erzeugen()
        try:
            try:
                with open(SCHLUESSEL, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                d = {}
            d["mitarbeiter"] = code
            tmp = SCHLUESSEL + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SCHLUESSEL)
            log("Mitarbeiter-Zugang neu angelegt und gesichert.")
        except Exception as e:
            log("Mitarbeiter-Zugang nicht gesichert: %s" % e)
        return code

    def mitarbeiter_code_neu(self):
        """Neuer Code fuer den Mitarbeiter; der alte Link wird ungueltig."""
        self.mitarbeiter = self._code_erzeugen()
        self._keys_speichern()
        return self.mitarbeiter

    def _seed_pferde(self):
        try:
            os.makedirs(SHARE_DIR, exist_ok=True)
        except Exception as e:
            log("Share-Ordner: %s" % e)

    # ---------- HA-Dienstaufruf ueber REST ----------
    def _post(self, domain, service, data):
        url = "%s/api/services/%s/%s" % (CORE_HTTP, domain, service)
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except Exception as e:
            log("Dienst %s/%s Fehler: %s" % (domain, service, e))
            return None

    def _senden(self, nummer, text):
        self._post("whatsapp", "send_message", {"target": str(nummer), "message": text})

    # ---------- Website-Push ----------
    def _web_post(self, pfad, payload):
        if not (WEBSITE_API and WEBSITE_SECRET):
            return None
        url = WEBSITE_API + pfad + "?key=" + urllib.parse.quote(WEBSITE_SECRET)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": BROWSER_UA})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status
        except Exception as e:
            log("Website-Push %s Fehler: %s" % (pfad, e))
            return None

    def keys_pushen(self):
        if not self.keys:
            return
        mapping = {schl: nr for nr, schl in self.keys.items() if schl}
        # Der Mitarbeiter-Zugang faehrt im selben Schluesselbund mit. Die
        # Website unterscheidet ihn am Wert: eine Zahl ist eine Pferdenummer,
        # 'mitarbeiter' ist die Stallseite.
        if getattr(self, "mitarbeiter", ""):
            mapping[self.mitarbeiter] = "mitarbeiter"
        st = self._web_post("/keys", mapping)
        if st:
            log("Schluessel an Website gepusht (%d)." % len(mapping))

    def daten_pushen(self):
        try:
            with open(PFERDE, encoding="utf-8") as f:
                daten = json.load(f)
        except Exception:
            return
        try:
            # Neu bewerten statt die Felder aus der Datei zu nehmen: eine gerade
            # gesetzte Ausnahme (ueberwachung.py) soll die Website sofort mit
            # dem naechsten Push erreichen, nicht erst nach dem naechsten Abruf.
            rueckstand.pruefe(daten.get("pferde", []))
        except Exception as e:
            log("Bewertung vor dem Push: %s" % e)
        verlauf = []
        vdir = os.path.join(SHARE_DIR, "verlauf")
        try:
            for fn in sorted([f for f in os.listdir(vdir) if f.endswith(".json")], reverse=True)[:14]:
                try:
                    with open(os.path.join(vdir, fn), encoding="utf-8") as f:
                        snap = json.load(f)
                    # Verlaufs-Tag: der Dateiname traegt das ENDE des Zyklus
                    # (den 6-Uhr-Reset am Morgen), gemeint ist aber der Tag, der
                    # davor gelaufen ist. Bis 0.32.0 stand die Zeile unter dem
                    # Enddatum - und damit standen auf derselben Pferdeseite
                    # unter '18.08.' zwei verschiedene Zahlen: im Verlauf der
                    # Zyklus, der an dem Morgen endete, im Reiter 'Heute' der,
                    # der an dem Morgen begann.
                    try:
                        tag = (datetime.strptime(fn[:-5], "%Y-%m-%d")
                               - timedelta(days=1))
                        snap["stand"] = tag.strftime("%d.%m.%Y")
                    except Exception:
                        pass
                    verlauf.append(snap)
                except Exception:
                    pass
        except Exception:
            pass
        payload = {"stand": daten.get("stand", ""), "pferde": daten.get("pferde", []), "verlauf": verlauf}
        st = self._web_post("/push", payload)
        if st:
            log("Tagesdaten an Website gepusht (%d Pferde)." % len(payload["pferde"]))

    def _link(self, nr):
        schl = self.keys.get(nr)
        return (WEBSITE_LINK + schl) if (schl and WEBSITE_LINK) else None

    def mitarbeiter_link(self):
        """Adresse der Stallseite - dieselbe Form wie eine Pferdeseite."""
        code = getattr(self, "mitarbeiter", "")
        return (WEBSITE_LINK + code) if (code and WEBSITE_LINK) else None

    # ---------- Namen & Codes (fuer das Ingress) ----------
    @staticmethod
    def nrs(eintrag):
        return _nrs(eintrag)

    def name_von(self, nr):
        try:
            return PANEL.get(int(nr), str(nr))
        except Exception:
            return str(nr)

    def kontakt_name(self, nummer):
        return self.store.get("namen", {}).get(str(nummer), "")

    def kontakt_setzen(self, nummer, name):
        self.store.setdefault("namen", {})[str(nummer)] = (name or "").strip()
        self._speichern()

    @staticmethod
    def _code_erzeugen():
        alpha = string.ascii_lowercase + string.digits
        return "".join(secrets.choice(alpha) for _ in range(10))

    def _keys_speichern(self):
        """schluessel.json auf den Stand von self.keys bringen.

        Bis 0.34.0 hat diese Funktion nur ERGAENZT. Ein entfernter Zugang blieb
        deshalb in der Datei stehen, wurde beim naechsten Start wieder geladen
        und beim naechsten Push wieder an die Website geschickt - der Link
        lebte weiter. Deshalb werden Eintraege, die es in self.keys nicht mehr
        gibt, jetzt ausdruecklich geloescht.
        """
        try:
            with open(SCHLUESSEL, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        d.setdefault("pferde", {})
        for nr, schl in self.keys.items():
            eintrag = d["pferde"].setdefault(str(nr), {})
            eintrag["schluessel"] = schl
            eintrag.setdefault("name", PANEL.get(nr, str(nr)))
        for weg in [k for k in d["pferde"] if int(k) not in self.keys]:
            d["pferde"].pop(weg, None)
        d["mitarbeiter"] = getattr(self, "mitarbeiter", "") or ""
        tmp = SCHLUESSEL + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SCHLUESSEL)

    def code_neu(self, nr):
        """Neuer Zufalls-Code fuer ein Pferd; alter Link wird damit ungueltig."""
        nr = int(nr)
        code = self._code_erzeugen()
        self.keys[nr] = code
        self._keys_speichern()
        return code

    def zugang_entfernen(self, nr):
        """Den Zugang eines Pferds loeschen - der Link ist danach tot.

        Wichtig ist die Reihenfolge dahinter: erst hier loeschen, dann
        `keys_pushen()`. Der Endpunkt `/keys` der Website ERSETZT die ganze
        Tabelle, ein Push ohne diesen Schluessel nimmt ihn dort also mit weg.
        Ohne den Push bliebe die Seite erreichbar, obwohl im Add-on nichts mehr
        davon steht - genau das war bis 0.34.0 der Fall.
        """
        nr = int(nr)
        if nr not in self.keys:
            return False
        self.keys.pop(nr, None)
        self._keys_speichern()
        log("Zugang fuer Pferd %s geloescht - Link ist ungueltig." % nr)
        return True

    def einsteller_von(self, nr, ausser=None):
        """Welche Nummern sind auf dieses Pferd angemeldet?

        Gebraucht an zwei Stellen: um beim Abmelden zu entscheiden, ob der
        Link noch jemandem gehoert, und um in den Tabellen anzuzeigen, dass ein
        Pferd MEHRERE Einsteller hat - bis 0.34.0 stand das nirgends.
        """
        nr = int(nr)
        raus = str(ausser) if ausser is not None else None
        return [n for n, e in self.store.get("zuordnung", {}).items()
                if str(n) != raus and nr in _nrs(e)]

    # ---------- Hofbuero-Benachrichtigung ----------
    def _hofbuero_freigabe(self, nummer, nrs):
        if "." in HOFBUERO:
            domain, service = HOFBUERO.split(".", 1)
        else:
            domain, service = "notify", HOFBUERO
        namen = ", ".join(PANEL.get(nr, str(nr)) for nr in nrs)
        self._post(domain, service, {
            "title": "HOCO-Abruf: Freigabe noetig",
            "message": "+%s moechte Zugriff auf: %s.\nBestaetigen?" % (nummer, namen),
            "data": {
                "tag": "abruf_%s" % nummer,
                "actions": [
                    {"action": OK_PREFIX + nummer, "title": "Bestaetigen"},
                    {"action": NEIN_PREFIX + nummer, "title": "Ablehnen"},
                ],
            },
        })

    def _benachrichtigen(self, ziel, titel, text, tag):
        """Eine Meldung aufs Telefon. ziel leer -> Dienst aus den Einstellungen."""
        dienst = (ziel or HOFBUERO).strip()
        if "." in dienst:
            domain, service = dienst.split(".", 1)
        else:
            domain, service = "notify", dienst
        return self._post(domain, service, {
            "title": titel,
            "message": text,
            # Gleicher 'tag' -> die Meldung von gestern wird auf dem Telefon
            # ersetzt statt gestapelt.
            "data": {"tag": tag},
        })

    # ---------- Morgenmeldung ----------
    # ---------- Aenderungswuensche der Einsteller ----------
    def wuensche_pruefen(self, melden=True):
        """Offene Wuensche gegen den aktuellen Stand halten.

        Laeuft nach jedem Abruf. Wurde ein Wunsch inzwischen am Panel
        eingetragen, wird er auf der Website abgehakt - der Einsteller sieht
        das ohne Zutun. Neue Wuensche werden EINMAL ans Hofbuero gemeldet;
        gemerkt wird das in /data, sonst kaeme die Meldung bei jedem Lauf.

        Geaendert wird am Fuetterungsrechner nichts (siehe wunsch.py).
        """
        offen_alle, fehler = wunsch.laden(WEBSITE_API, WEBSITE_SECRET)
        if fehler:
            raise RuntimeError(fehler)     # der Aufrufer soll es sagen koennen
        if not offen_alle:
            self.wuensche = []
            return []
        try:
            with open(PFERDE, encoding="utf-8") as f:
                pferde = json.load(f).get("pferde", [])
        except Exception:
            return []
        erledigt, offen, zurueck_warn, zurueck_still = wunsch.pruefen(offen_alle, pferde)
        for w in erledigt:
            if wunsch.abhaken(WEBSITE_API, WEBSITE_SECRET, w):
                log("Wunsch eingetragen: %s" % wunsch.text(w))
        # Zurueckgenommen und nichts passiert: einfach schliessen.
        for w in zurueck_still:
            wunsch.abhaken(WEBSITE_API, WEBSITE_SECRET, w, status="geschlossen")
        # Zurueckgenommen, aber schon eingetragen: das muss auffallen.
        for w in zurueck_warn:
            gemeldet = self.store.setdefault("wunsch_gewarnt", {})
            if w.get("id") in gemeldet:
                continue
            gemeldet[w["id"]] = w.get("zurueck", "")
            self._speichern()
            log("WARNUNG: " + wunsch.warntext(w))
            self._benachrichtigen(None, "Wunsch zurueckgenommen",
                                  wunsch.warntext(w), "wunsch")
            wunsch.abhaken(WEBSITE_API, WEBSITE_SECRET, w, status="geschlossen")
        self.wuensche = offen
        if melden and offen:
            gemeldet = self.store.setdefault("wunsch_gemeldet", {})
            neu = [w for w in offen if w.get("id") not in gemeldet]
            if neu:
                for w in neu:
                    gemeldet[w["id"]] = w.get("gestellt", "")
                self._speichern()
                self._benachrichtigen(
                    None, "Aenderungswunsch",
                    chr(10).join(wunsch.text(w) for w in neu)
                    + chr(10) + chr(10)
                    + "Eintragen am Fuetterungsrechner; danach hakt sich der "
                      "Wunsch von selbst ab.",
                    "wunsch")
        return offen

    def wunsch_ablehnen(self, wunsch_id, grund=""):
        """Einen Wunsch ablehnen. Bestaetigen geht NICHT von Hand.

        Das ist Absicht: 'eingetragen' darf nur dann dastehen, wenn der Wert
        wirklich im Auszug des Fuetterungsrechners steht. Ein Knopf zum
        Bestaetigen waere ein Knopf zum Behaupten - der Einsteller saehe
        'eingetragen', obwohl sich nichts geaendert hat, und niemand wuerde es
        je merken. Erledigt meldet deshalb ausschliesslich der Soll-Ist-
        Vergleich (wuensche_pruefen).

        Ablehnen dagegen ist eine Entscheidung, die nur ein Mensch treffen
        kann - dafuer gibt es den Knopf.
        """
        for w in (self.wuensche or []):
            if str(w.get("id")) == str(wunsch_id):
                if wunsch.abhaken(WEBSITE_API, WEBSITE_SECRET, w,
                                  status="abgelehnt", grund=grund):
                    self.wuensche = [x for x in self.wuensche if x is not w]
                    log("Wunsch abgelehnt (%s): %s" % (grund or "ohne Grund", wunsch.text(w)))
                    return True
                return False
        return False

    def morgenmeldung(self, anlass="plan"):
        """Die nicht erkannten Pferde ans Hofbuero. Gibt Klartext zurueck.

        Gelesen wird pferde.json vom letzten Abruf - die Meldung loest KEINEN
        eigenen Abruf aus. Am Panel ist nur eine Sitzung moeglich; ein Abruf
        zur Meldezeit wuerde mit dem Zeitplan kollidieren. Der Morgen-Lauf
        (05:30) hat die Zahlen ohnehin schon geholt."""
        try:
            with open(PFERDE, encoding="utf-8") as f:
                daten = json.load(f)
        except Exception as e:
            log("Morgenmeldung: pferde.json nicht gelesen (%s)" % e)
            return "keine Daten"
        pferde = daten.get("pferde", [])
        try:
            rueckstand.pruefe(pferde)      # aeltere Dateien haben die Felder nicht
        except Exception:
            pass
        m = self.meldung
        treffer = m.betroffene(pferde)
        if not treffer and not m.get("auch_ohne_befund") and anlass != "test":
            return "nichts zu melden"
        titel, text = m.nachricht(pferde, daten.get("stand", ""))
        ziel = m.get("ziel") or HOFBUERO
        if self._benachrichtigen(m.get("ziel"), titel, text, "abruf_morgenmeldung") is None:
            return "Dienst %s hat nicht angenommen - siehe Protokoll" % ziel
        m.versand_merken(titel, anlass)
        return "%s (%d Tier%s)" % (titel, len(treffer),
                                   "" if len(treffer) == 1 else "e")

    # ---------- Helfer ----------
    @staticmethod
    def _nummer(sender):
        return re.sub(r"\D", "", str(sender).split("@")[0])

    def _pferd_finden(self, text):
        t = text.strip()
        if t.isdigit() and int(t) in PANEL:
            n = int(t)
            return n, PANEL[n]
        nt = _norm(t)
        if not nt:
            return None
        for nr, name in PANEL.items():
            if _norm(name) == nt:
                return nr, name
        best = None
        best_q = 0.0
        for nr, name in PANEL.items():
            nn = _norm(name)
            if nn in nt.split() or nt in nn.split():
                return nr, name
            q = difflib.SequenceMatcher(None, nt, nn).ratio()
            if q > best_q:
                best_q = q
                best = (nr, name)
        if best and best_q >= 0.72:
            return best
        return None

    def _pferde_finden(self, text):
        """Mehrere Pferde aus 'Delana, Fiora und Farina' -> ([(nr,name)...], [nicht...])."""
        teile = re.split(r"[,\n;]+|\bund\b", text)
        gefunden = []
        nicht = []
        for t in teile:
            t = t.strip()
            if not t:
                continue
            tr = self._pferd_finden(t)
            if tr and tr[0] not in [g[0] for g in gefunden]:
                gefunden.append(tr)
            elif not tr:
                nicht.append(t)
        return gefunden, nicht

    # ---------- Event-Verteiler ----------
    def dispatch(self, event):
        et = event.get("event_type")
        data = event.get("data") or {}
        if et == "whatsapp_message_received":
            self.on_msg(data)
        elif et == "mobile_app_notification_action":
            self.on_action(data)

    def on_msg(self, data):
        try:
            sender = data.get("sender") or ""
            if "@g.us" in str(sender):
                return
            text = (data.get("content") or "").strip()
            if not text:
                return
            nummer = self._nummer(sender)
            if not nummer:
                return
            log("Nachricht von %s: %r" % (nummer, text))
            name = (data.get("notify_name") or data.get("pushName") or data.get("push_name")
                    or data.get("name") or "").strip()
            with self.lock:
                if name:
                    namen = self.store.setdefault("namen", {})
                    if namen.get(nummer) != name:
                        namen[nummer] = name
                        self._speichern()
                self._verarbeiten(nummer, text)
        except Exception as e:
            log("Fehler in on_msg: %s" % e)

    def _verarbeiten(self, nummer, text):
        roh = text.strip()
        ist_befehl = roh.startswith("/")
        befehl = _norm(roh).lstrip("/") if ist_befehl else ""

        if ist_befehl and befehl in ("anmelden", "start", "register"):
            self.store["wartet"][nummer] = int(time.time())
            self._speichern()
            self._senden(nummer, T("anmelden_frage"))
            return

        if ist_befehl and befehl in ("abruf", "futter", "fuetterung"):
            if nummer in self.store["zuordnung"] and self.store["zuordnung"][nummer]:
                bloecke = [self._kurz(nr) for nr in _nrs(self.store["zuordnung"][nummer])]
                self._senden(nummer, "\n\n".join(bloecke))
            elif nummer in self.store["offen"]:
                self._senden(nummer, T("abruf_wartet"))
            else:
                self._senden(nummer, T("abruf_nicht_angemeldet"))
            return

        if ist_befehl and befehl in ("hilfe", "help"):
            self._senden(nummer, self._hilfe())
            return

        if ist_befehl and befehl in ("abmelden", "abmeldung", "loeschen"):
            weg = self.store["zuordnung"].pop(nummer, None)
            self.store["offen"].pop(nummer, None)
            self.store["wartet"].pop(nummer, None)
            self._speichern()
            self._senden(nummer, T("abgemeldet") if weg else T("war_nicht_angemeldet"))
            return

        ts = self.store["wartet"].get(nummer)
        if ts and (int(time.time()) - int(ts) <= 600):
            gefunden, nicht = self._pferde_finden(roh)
            if not gefunden:
                self._senden(nummer, T("pferd_nicht_gefunden"))
                return
            nrs = [nr for nr, name in gefunden]
            namen = ", ".join(name for nr, name in gefunden)
            self.store["wartet"].pop(nummer, None)
            self.store["offen"][nummer] = nrs
            self._speichern()
            msg = T("anmeldung_eingegangen", namen=namen)
            if nicht:
                msg += T("anmeldung_teilweise", nicht=", ".join(nicht))
            self._senden(nummer, msg)
            self._hofbuero_freigabe(nummer, nrs)
            return

        # Sonst: normaler Chat -> schweigen. Abgelaufenen Wartezustand aufraeumen.
        if ts:
            self.store["wartet"].pop(nummer, None)
            self._speichern()
        return

    def _hilfe(self):
        return T("hilfe")

    # ---------- Freigabe durchs Hofbuero ----------
    def on_action(self, data):
        try:
            aktion = str(data.get("action", ""))
            if aktion.startswith(OK_PREFIX):
                with self.lock:
                    self._freigeben(aktion[len(OK_PREFIX):], True)
            elif aktion.startswith(NEIN_PREFIX):
                with self.lock:
                    self._freigeben(aktion[len(NEIN_PREFIX):], False)
        except Exception as e:
            log("Fehler in on_action: %s" % e)

    def _freigeben(self, nummer, ja):
        nrs = _nrs(self.store["offen"].pop(nummer, None))
        if not nrs:
            log("Freigabe fuer %s, aber kein offener Antrag." % nummer)
            return
        if ja:
            self.store["zuordnung"][nummer] = nrs
            self._speichern()
            namen = ", ".join(PANEL.get(nr, str(nr)) for nr in nrs)
            log("Freigegeben: %s -> %s" % (nummer, namen))
            z = [T("freigegeben_kopf"), ""]
            for nr in nrs:
                link = self._link(nr)
                z.append(T("kurz_kopf", name=PANEL.get(nr, str(nr))))
                z.append(link if link else "(Link folgt in Kuerze)")
                z.append("")
            z.append(T("freigegeben_fuss"))
            self._senden(nummer, "\n".join(z))
        else:
            self._speichern()
            log("Abgelehnt: %s" % nummer)
            self._senden(nummer, T("abgelehnt"))

    # ---------- Kurzstatus je Pferd (mit Link) ----------
    def _kurz(self, nr):
        name = PANEL.get(nr, str(nr))
        try:
            with open(PFERDE, encoding="utf-8") as f:
                daten = json.load(f)
            pferd = next((p for p in daten.get("pferde", []) if p.get("nr") == nr), None)
        except Exception:
            pferd = None
        z = [T("kurz_kopf", name=name)]
        if pferd:
            for feld, schluessel in (("rf", "kurz_rf"), ("kf", "kurz_kf"),
                                     ("min", "kurz_min")):
                werte = pferd.get(feld)
                if werte:
                    # 'prozent' misst am bis jetzt Faelligen, nicht am
                    # Tagesanspruch - deshalb steht 'faellig' jetzt mit in der
                    # Zeile. Vorher las sich '8 Min / 90 Min (24%)' so, als
                    # waeren 8 von 90 gleich 24 Prozent.
                    z.append(T(schluessel,
                               geholt=werte.get("fortschritt_gesamt", "?"),
                               anspruch=werte.get("anspruch_gesamt", "?"),
                               faellig=werte.get("anspruch_bisherig", "?"),
                               prozent=werte.get("fortschritt_bisherig_prozent", "?")))
            # Nur die schweren Faelle ansagen (Rechner-Hinweis oder gar nichts
            # geholt) - bei jedem kleinen Rueckstand zu warnen macht die
            # Nachricht stumpf.
            if (pferd.get("rueckstand") in ("transponder", "nichts")
                    and pferd.get("rueckstand_text")):
                z.append(T("kurz_rueckstand", text=pferd["rueckstand_text"]))
        else:
            z.append(T("kurz_keine_zahlen"))
        link = self._link(nr)
        if link:
            z.append(link)
        return "\n".join(z)


def _verbinden(bot):
    ws = websocket.create_connection(CORE_WS, timeout=30)
    try:
        json.loads(ws.recv())
        ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        res = json.loads(ws.recv())
        if res.get("type") != "auth_ok":
            raise RuntimeError("Auth fehlgeschlagen: %s" % res)
        mid = 1
        for et in EVENTS:
            ws.send(json.dumps({"id": mid, "type": "subscribe_events", "event_type": et}))
            mid += 1
        log("Verbunden & abonniert: %s" % ", ".join(EVENTS))
        ws.settimeout(None)
        while True:
            raw = ws.recv()
            if raw is None or raw == "":
                raise RuntimeError("WebSocket geschlossen")
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "event":
                try:
                    bot.dispatch(msg.get("event") or {})
                except Exception as e:
                    log("dispatch-Fehler: %s" % e)
    finally:
        try:
            ws.close()
        except Exception:
            pass


TAKT_S = max(60, int(os.environ.get("ABRUF_TAKT_MINUTEN") or 5) * 60)


def _scheduler(bot, run_abruf):
    """Regelmaessig nachsehen, ob eine neue Datei da ist - mehr Planung gibt es
    nicht mehr.

    Der Fuetterungsrechner legt alle 30 Minuten einen Auszug ab. Statt fester
    Abrufzeiten wird hier nur der DATEINAME abgefragt (ein FTP-LIST, kein
    Download); aendert er sich, wird gearbeitet. Zwei Vorteile gegenueber dem
    alten Zeitplan: es gibt keinen Lauf, der nichts Neues holt, und die Daten
    sind nie aelter als ein Takt plus der Schreibabstand des Rechners.

    Nach einem Neustart ist `zuletzt` leer - der erste Durchgang arbeitet also
    einmal, auch wenn die Datei schon bekannt war. Das ist gewollt: nach einem
    Neustart soll pferde.json frisch sein.
    """
    zuletzt = ""
    naechster_blick = 0.0
    while True:
        try:
            now = time.localtime()
            if time.time() >= naechster_blick:
                naechster_blick = time.time() + TAKT_S
                try:
                    name = hoco.neuester_name()
                except Exception as e:
                    log("FTP nicht erreichbar (%s) - naechster Versuch in %d Min."
                        % (e, TAKT_S // 60))
                    name = ""
                if name and name != zuletzt:
                    zuletzt = name
                    log("Neuer Auszug: %s" % name)
                    run_abruf("neu")
                else:
                    # Kein neuer Auszug - aber nach Wuenschen wird trotzdem
                    # gesehen. Sie kommen von der Website und haben mit dem
                    # Schreibtakt des Rechners nichts zu tun; sonst laege ein
                    # Wunsch bis zu einer halben Stunde unbemerkt herum.
                    try:
                        bot.wuensche_pruefen()
                    except Exception as e:
                        log("Wunsch-Pruefung: %s" % e)
            # Morgenmeldung: die nicht erkannten Tiere aufs Telefon. Zeit und
            # Tage stehen im Ingress unter 'Morgenmeldung'.
            if bot.meldung.faellig(now):
                bot.meldung.erledigt(now)
                try:
                    log("Morgenmeldung: %s" % bot.morgenmeldung("plan"))
                except Exception as e:
                    log("Morgenmeldung fehlgeschlagen: %s" % e)
        except Exception as e:
            log("Scheduler-Fehler: %s" % e)
        time.sleep(20)


def main():
    if not TOKEN:
        log("FEHLER: SUPERVISOR_TOKEN fehlt – ist homeassistant_api aktiv?")
        return
    bot = Bot()
    bot.keys_pushen()   # Schluessel beim Start an die Website
    status = {"laeuft": False, "letzter": None, "ergebnis": "noch nie"}
    abruf_lock = threading.Lock()

    def run_abruf(quelle="manuell", scope="voll"):
        with abruf_lock:
            if status["laeuft"]:
                return "laeuft bereits"
            status["laeuft"] = True
        log("Datenabruf (%s, '%s') …" % (quelle, scope))
        try:
            res = abruf.abrufen(scope)
        except Exception as e:
            res = "Fehler: %s" % e
        else:
            try:
                bot.daten_pushen()   # nach erfolgreichem Abruf an die Website
            except Exception as e:
                log("Daten-Push Fehler: %s" % e)
            try:
                bot.wuensche_pruefen()
            except Exception as e:
                log("Wunsch-Pruefung: %s" % e)
        status["ergebnis"] = res
        status["letzter"] = time.strftime("%d.%m.%Y %H:%M")
        status["laeuft"] = False
        log("Datenabruf fertig: %s" % res)
        return res

    port = int(os.environ.get("ABRUF_INGRESS_PORT", "8099"))
    try:
        threading.Thread(target=web.serve, args=(bot, run_abruf, status, port), daemon=True).start()
    except Exception as e:
        log("Weboberflaeche konnte nicht starten: %s" % e)

    threading.Thread(target=_scheduler, args=(bot, run_abruf), daemon=True).start()
    log("Nachsehen alle %d Minuten, ob ein neuer Auszug da ist (%s%s)."
        % (TAKT_S // 60, hoco.FTP_HOST, hoco.FTP_VERZEICHNIS))
    if bot.meldung.get("aktiv"):
        log("Morgenmeldung: %s, Umfang '%s', an %s"
            % (bot.meldung.beschreibung(), bot.meldung.get("umfang"),
               bot.meldung.get("ziel") or HOFBUERO))
    else:
        log("Morgenmeldung: aus")

    log("HOCO-Abruf gestartet. %d bestaetigt, %d offen. Website=%s" % (
        len(bot.store["zuordnung"]), len(bot.store["offen"]), "an" if WEBSITE_API else "aus"))
    while True:
        try:
            _verbinden(bot)
        except Exception as e:
            log("Verbindung weg (%s) – neuer Versuch in 5 s." % e)
            time.sleep(5)


if __name__ == "__main__":
    main()
