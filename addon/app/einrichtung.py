# -*- coding: utf-8 -*-
"""Ersteinrichtung des HOCO-Abrufs.

Ein frisch installiertes Add-on weiss nichts: nicht, wo der Fuetterungsrechner
steht, nicht, wohin die Zahlen sollen, nicht, wer die Freigaben bekommt. Statt
den Betreiber zwischen Add-on-Optionen und Panel hin und her zu schicken,
fuehrt eine Ansicht im Panel durch alle Werte - und prueft jeden einzeln, bevor
er stehenbleibt.

Seit 0.41.0 ist das Panel der einzige Ort dafuer: Gespeichert wird in
/data/konfig.json (siehe konfig.py), und die Werte gelten sofort - kein
Neustart, keine zweite Oberflaeche in den Add-on-Optionen.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from . import hoco, konfig, wunsch

DATA_DIR = "/data"
DATEI = os.path.join(DATA_DIR, "einrichtung.json")

SUPERVISOR = "http://supervisor"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")   # nur noch fuer die WhatsApp-Probe

# Kennung, Beschriftung, Hilfetext, Pflichtfeld?, Folge wenn es fehlt
#
# Pflicht ist nur, was den Betrieb wirklich blockiert. Der Stallname gehoert
# nicht dazu: ohne ihn laeuft alles weiter, im Kopf der Pferdeseiten steht dann
# der Name der Website.
FELDER = [
    ("stall_name", "Name des Betriebs",
     "Steht im Kopf der Pferdeseiten, in den WhatsApp-Texten und hier unten "
     "links. Zum Beispiel „Aktivstall Musterhof“. Leer lassen geht "
     "auch - dann steht dort der Name der Website.", False,
     "steht im Kopf der Pferdeseiten der Name der Website"),
    ("hoco_host", "Adresse des Fütterungsrechners",
     "IP oder Name des HOCO-Rechners im Stallnetz. Er gibt seinen Auszug per "
     "FTP heraus - meist ohne Anmeldung.", True,
     "holt das Add-on keine Daten"),
    ("hoco_verzeichnis", "Verzeichnis des Auszugs",
     "Dort legt der Rechner seine CSV-Dateien ab. Üblich ist /export.", True,
     "findet das Add-on den Auszug nicht"),
    ("hoco_benutzer", "FTP-Benutzer",
     "Leer lassen, wenn der Rechner anonym herausgibt - das ist der Normalfall.",
     False, "meldet sich das Add-on anonym an"),
    ("hoco_passwort", "FTP-Kennwort", "Nur zusammen mit einem Benutzer.", False,
     "meldet sich das Add-on ohne Kennwort an"),
    ("hofbuero_notify", "Benachrichtigung ins Hofbüro",
     "Notify-Dienst für Freigaben und die Morgenmeldung, z. B. "
     "<code>notify.mobile_app_iphone</code>. Der Dienst muss in Home Assistant "
     "schon vorhanden sein.", True,
     "kommen keine Freigaben und keine Morgenmeldung an"),
    ("website_api", "Schnittstelle der Website",
     "Die Adresse aus der Einrichtung des Plugins, z. B. "
     "<code>https://beispielhof.de/wp-json/hoco/v1</code>. Leer lassen, wenn "
     "die Zahlen nur per WhatsApp gehen sollen.", False,
     "gehen die Zahlen nur per WhatsApp"),
    ("website_link", "Link-Basis der Pferdeseiten",
     "Ebenfalls aus dem Plugin, z. B. "
     "<code>https://beispielhof.de/fuetterung/?k=</code>.", False,
     "verschickt der Bot keine Links zur Pferdeseite"),
    ("website_secret", "Gemeinsames Geheimnis",
     "Der Wert, den die Einrichtung des Plugins anzeigt. Ohne ihn nimmt die "
     "Website keine Zahlen an.", False,
     "nimmt die Website keine Zahlen an"),
]

PFLICHT = [kennung for kennung, _t, _h, pflicht, _f in FELDER if pflicht]
FOLGE = {kennung: folge for kennung, _t, _h, _p, folge in FELDER}

# Kennung der Option -> Umgebungsvariable, unter der sie im laufenden Add-on
# ankommt. Nur fuer die Felder, die diese Ansicht prueft.
UMGEBUNG = {
    "stall_name": "STALL_NAME",
    "hoco_host": "HOCO_HOST",
    "hoco_verzeichnis": "HOCO_VERZEICHNIS",
    "hoco_benutzer": "HOCO_BENUTZER",
    "hoco_passwort": "HOCO_PASSWORT",
    "hofbuero_notify": "ABRUF_HOFBUERO_NOTIFY",
    "website_api": "WEBSITE_API",
    "website_link": "WEBSITE_LINK",
    "website_secret": "WEBSITE_SECRET",
}


# --------------------------------------------------------------- Speichern
def optionen():
    """Der aktuelle Stand aller Einstellungen."""
    return konfig.alle()


def schreibbar():
    """Kann gespeichert werden? -> (ja, Grund)

    Seit 0.41.0 schreibt das Add-on in eine eigene Datei unter /data. Das kann
    nur an einem vollen oder schreibgeschuetzten Datentraeger scheitern - der
    Supervisor ist dafuer nicht mehr noetig.
    """
    try:
        os.makedirs(konfig.DATA_DIR, exist_ok=True)
        probe = os.path.join(konfig.DATA_DIR, ".schreibprobe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True, ""
    except Exception as e:
        return False, str(e)


def speichern(werte):
    """Uebernimmt die Werte. Sie gelten sofort, ohne Neustart."""
    return konfig.speichern(werte)


# ------------------------------------------------------------------ Zustand
def zustand():
    try:
        with open(DATEI, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _zustand_schreiben(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATEI + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATEI)


def erledigt():
    return bool(zustand().get("erledigt"))


def abschliessen(ja=True):
    d = zustand()
    d["erledigt"] = bool(ja)
    d["stand"] = time.strftime("%d.%m.%Y %H:%M")
    _zustand_schreiben(d)
    return d


def laufende_werte():
    """Die Werte, mit denen das Add-on gerade arbeitet."""
    alle = konfig.alle()
    return {kennung: alle.get(kennung, "") for kennung in UMGEBUNG}


def fehlend():
    """Pflichtwerte, die noch leer sind."""
    werte = laufende_werte()
    return [k for k in PFLICHT if not werte.get(k)]


def noetig():
    """Soll die Ersteinrichtung von selbst aufgehen?

    Ja, solange sie nicht abgehakt ist UND noch ein Pflichtwert fehlt. Wer sie
    abgehakt hat, bekommt sie nicht wieder vor die Nase gesetzt - er findet sie
    weiterhin in der Seitenleiste.
    """
    return not erledigt() and bool(fehlend())


# --------------------------------------------------------------- Pruefungen
# Jede Pruefung gibt (ok, Text) zurueck. Der Text steht so in der Oberflaeche,
# er muss also auch im Fehlerfall etwas taugen: was war falsch und was hilft.

def pruefe_hoco(host, verzeichnis, benutzer="", passwort=""):
    if not host:
        return False, "Keine Adresse eingetragen."
    try:
        namen = hoco.dateiliste(host=host, verzeichnis=verzeichnis or "/",
                                benutzer=benutzer or "", passwort=passwort or "")
    except Exception as e:
        return False, ("Keine Verbindung: %s. Stimmt die Adresse, und ist der "
                       "Rechner aus dem Netz von Home Assistant erreichbar?" % e)
    if not namen:
        return False, ("Verbindung steht, aber in %s liegt keine Datei. Stimmt "
                       "das Verzeichnis?" % (verzeichnis or "/"))
    return True, ("Verbindung steht. %d Datei(en) im Verzeichnis, zuletzt: %s."
                  % (len(namen), sorted(namen)[-1]))


def pruefe_whatsapp():
    """Gibt es den Dienst, ueber den der Bot sendet?"""
    if not TOKEN:
        return False, "Kein Zugang zu Home Assistant (SUPERVISOR_TOKEN fehlt)."
    try:
        req = urllib.request.Request(
            SUPERVISOR + "/core/api/services",
            headers={"Authorization": "Bearer " + TOKEN})
        with urllib.request.urlopen(req, timeout=20) as r:
            dienste = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return False, "Home Assistant nicht erreichbar: %s" % e
    for d in dienste or []:
        if d.get("domain") == "whatsapp" and "send_message" in (d.get("services") or {}):
            return True, "Der Dienst <code>whatsapp.send_message</code> ist da."
    return False, ("Kein Dienst <code>whatsapp.send_message</code> gefunden. "
                   "Ohne WhatsApp-Integration laufen die Zahlen nur ueber die "
                   "Website - alles andere funktioniert weiter.")


def pruefe_notify(bot, dienst):
    if not dienst:
        return False, "Kein Dienst eingetragen."
    domain, _punkt, service = dienst.partition(".")
    if not service:
        domain, service = "notify", dienst
    status = bot._post(domain, service, {
        "title": "HOCO-Abruf",
        "message": "Testmeldung aus der Ersteinrichtung. Kommt sie an, "
                   "stimmt der Dienst."})
    if status and 200 <= status < 300:
        return True, ("Verschickt. Steht die Meldung auf dem Telefon, ist der "
                      "Dienst richtig.")
    return False, ("Home Assistant hat den Aufruf nicht angenommen. Gibt es "
                   "<code>%s.%s</code> wirklich? (Entwicklerwerkzeuge → "
                   "Aktionen)" % (domain, service))


def pruefe_website(api, secret):
    if not (api and secret):
        return False, ("Adresse oder Geheimnis fehlt. Beides zeigt die "
                       "Einrichtung des Plugins auf der Website an.")
    _liste, fehler = wunsch.laden(api, secret, zeit=15)
    if not fehler:
        return True, "Die Website antwortet und erkennt das Geheimnis."
    if "403" in fehler:
        return False, ("Die Website antwortet, weist das Geheimnis aber ab. Es "
                       "muss auf beiden Seiten dasselbe sein.")
    if "404" in fehler:
        return False, ("Unter dieser Adresse gibt es die Schnittstelle nicht. "
                       "Ist das Plugin aktiviert, und endet die Adresse auf "
                       "<code>/wp-json/hoco/v1</code>?")
    return False, "Keine Antwort: %s" % fehler
