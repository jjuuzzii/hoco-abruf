# -*- coding: utf-8 -*-
"""Alle Nachrichtentexte des Bots - im Ingress aenderbar.

Die Standardtexte hier unten sind wortgleich mit dem, was der Bot bisher fest
im Code hatte. Wer nichts aendert, merkt vom Umbau nichts.

Geaenderte Texte liegen in /data/texte.json und ueberschreiben je Schluessel
den Standard. Ein leeres Feld im UI = Standard wieder verwenden.

Platzhalter stehen in geschweiften Klammern, z.B. {name}. Ein Tippfehler im
Platzhalter darf den Bot NICHT umbringen: unbekannte Namen bleiben einfach als
Text stehen, statt eine Ausnahme zu werfen (siehe _Sicher).

{stall} steht in jedem Text zur Verfuegung und traegt den Namen des Betriebs
aus den Add-on-Optionen. Ist keiner gesetzt, steht dort "HOCO-Abruf" - so
ergibt jeder Text auch bei frischer Installation einen ganzen Satz.
"""
import json
import os
import string
import threading

DATA_DIR = "/data"
DATEI = os.path.join(DATA_DIR, "texte.json")


def stall():
    """Name des Betriebs aus den Add-on-Optionen, sonst der Produktname."""
    return os.environ.get("STALL_NAME", "").strip() or "HOCO-Abruf"

# gruppe, titel, text, platzhalter {name: Beispielwert fuer die Vorschau}
STANDARD = {
    # ---------------- Anmeldung ----------------
    "anmelden_frage": {
        "gruppe": "Anmeldung", "titel": "Antwort auf /anmelden",
        "text": ("\U0001F434 *Anmeldung {stall}*\n\n"
                 "Welche(s) Pferd(e) moechtest du sehen?\n"
                 "Schick mir den *Namen* - bei mehreren mit Komma, z. B.:\n"
                 "_Pferd 1, Pferd 2_"),
        "platzhalter": {}},
    "pferd_nicht_gefunden": {
        "gruppe": "Anmeldung", "titel": "Pferdename nicht erkannt",
        "text": ("Hmm, das finde ich nicht in der Stallliste. \U0001F914\n"
                 "Bitte die Namen genau wie im Stall schreiben (bei mehreren mit Komma)."),
        "platzhalter": {}},
    "anmeldung_eingegangen": {
        "gruppe": "Anmeldung", "titel": "Anmeldung liegt beim Hofbuero",
        "text": ("Danke! \U0001F64C Deine Anmeldung fuer *{namen}* liegt jetzt beim "
                 "Hofbuero zur Freigabe.\nDu bekommst hier Bescheid mit deinem Link."),
        "platzhalter": {"namen": "Bella, Falko"}},
    "anmeldung_teilweise": {
        "gruppe": "Anmeldung", "titel": "Zusatz, wenn ein Name unklar war",
        "text": "\n\n(Nicht erkannt: {nicht} - bitte im Hofbuero melden.)",
        "platzhalter": {"nicht": "Schimmel"}},
    "freigegeben_kopf": {
        "gruppe": "Anmeldung", "titel": "Freigabe erteilt (Kopfzeile)",
        "text": "✅ Freigegeben! Hier deine persoenliche(n) Seite(n):",
        "platzhalter": {}},
    "freigegeben_fuss": {
        "gruppe": "Anmeldung", "titel": "Freigabe erteilt (Schlusszeile)",
        "text": "Mit */abruf* bekommst du sie jederzeit wieder.",
        "platzhalter": {}},
    "abgelehnt": {
        "gruppe": "Anmeldung", "titel": "Freigabe abgelehnt",
        "text": "Deine Anmeldung wurde nicht bestaetigt.\nBitte melde dich im Hofbuero.",
        "platzhalter": {}},
    "abgemeldet": {
        "gruppe": "Anmeldung", "titel": "Nach /abmelden",
        "text": ("Du bist abgemeldet - deine Verknuepfung wurde geloescht.\n"
                 "Mit */anmelden* kannst du dich jederzeit neu anmelden."),
        "platzhalter": {}},
    "war_nicht_angemeldet": {
        "gruppe": "Anmeldung", "titel": "/abmelden ohne Anmeldung",
        "text": "Du warst nicht angemeldet. Mit */anmelden* kannst du dich anmelden.",
        "platzhalter": {}},

    # ---------------- Abruf ----------------
    "kurz_kopf": {
        "gruppe": "Abruf", "titel": "Kopfzeile je Pferd",
        "text": "\U0001F434 *{name}*",
        "platzhalter": {"name": "Delana"}},
    "kurz_rf": {
        "gruppe": "Abruf", "titel": "Zeile Raufutter",
        "text": "Raufutter: {geholt} von {anspruch} – bis jetzt fällig {faellig} ({prozent} %)",
        "platzhalter": {"geholt": "93 Min", "anspruch": "360 Min", "faellig": "112 min",
                        "prozent": "83"}},
    "kurz_kf": {
        "gruppe": "Abruf", "titel": "Zeile Kraftfutter",
        "text": "Kraftfutter: {geholt} von {anspruch} – bis jetzt fällig {faellig} ({prozent} %)",
        "platzhalter": {"geholt": "0.528 kg", "anspruch": "1.000 kg", "faellig": "0.580 kg",
                        "prozent": "91"}},
    "kurz_min": {
        "gruppe": "Abruf", "titel": "Zeile Mineralfutter",
        "text": "Mineralfutter: {geholt} von {anspruch} – bis jetzt fällig {faellig} ({prozent} %)",
        "platzhalter": {"geholt": "15 g", "anspruch": "50 g", "faellig": "31 g",
                        "prozent": "48"}},
    "kurz_rueckstand": {
        "gruppe": "Abruf", "titel": "Hinweis, wenn etwas nicht geholt wurde",
        "text": "⚠️ {text}",
        "platzhalter": {"text": "Mineralfutter nicht geholt"}},
    "kurz_keine_zahlen": {
        "gruppe": "Abruf", "titel": "Wenn keine Zahlen vorliegen",
        "text": "(aktuell keine Zahlen)",
        "platzhalter": {}},
    "abruf_nicht_angemeldet": {
        "gruppe": "Abruf", "titel": "/abruf ohne Anmeldung",
        "text": ("Du bist noch nicht angemeldet.\n"
                 "Schick mir zuerst */anmelden*, dann deine Pferde."),
        "platzhalter": {}},
    "abruf_wartet": {
        "gruppe": "Abruf", "titel": "/abruf waehrend die Freigabe aussteht",
        "text": ("⏳ Deine Anmeldung liegt noch beim Hofbuero zur Freigabe. "
                 "Sobald sie bestaetigt ist, bekommst du deine Link(s)."),
        "platzhalter": {}},
    "hilfe": {
        "gruppe": "Abruf", "titel": "Antwort auf /hilfe",
        "text": ("\U0001F44B *{stall}*\n\n"
                 "• */anmelden* - deine Pferde hinterlegen (Freigabe durchs Hofbuero)\n"
                 "• */abruf* - Kurzstatus + Link je Pferd\n"
                 "• */abmelden* - Verknuepfung loeschen\n\n"
                 "Bei Fragen melde dich im Hofbuero."),
        "platzhalter": {}},

    "melde_titel": {
        "gruppe": "Meldung", "titel": "Betreff – nicht erkannt",
        "text": "Aktivstall: {anzahl} Tier{mehrzahl} nicht erkannt",
        "platzhalter": {"anzahl": "3", "mehrzahl": "e"}},
    "melde_zeile": {
        "gruppe": "Meldung", "titel": "Ein Pferd in der Aufzählung – nicht erkannt",
        "text": "{name} ({nr})",
        "platzhalter": {"nr": "26", "name": "Nilson",
                        "grund": "wurde in den letzten 12 Stunden bei keiner "
                                 "Station erkannt. Transponderfehler?"}},
    "melde_text": {
        "gruppe": "Meldung", "titel": "Rumpf – nicht erkannt",
        "text": ("{liste}\n\nSeit 12 Stunden an keiner Station erkannt "
                 "- bitte Transponder pruefen.\nStand der Daten: {stand}"),
        "platzhalter": {"liste": "Nilson (26), Lina (3), Wira (7)",
                        "anzahl": "3", "stand": "17.08.2026 05:31"}},
    "melde_titel_alles": {
        "gruppe": "Meldung", "titel": "Betreff – Umfang 'alles Auffällige'",
        "text": "Aktivstall: {anzahl} Tier{mehrzahl} auffaellig",
        "platzhalter": {"anzahl": "9", "mehrzahl": "e"}},
    "melde_zeile_alles": {
        "gruppe": "Meldung", "titel": "Eine Zeile je Pferd – Umfang 'alles'",
        "text": "{name} ({nr}): {grund}",
        "platzhalter": {"nr": "4", "name": "Pepsi",
                        "grund": "Kraftfutter im Rueckstand"}},
    "melde_text_alles": {
        "gruppe": "Meldung", "titel": "Rumpf – Umfang 'alles'",
        "text": "{liste}\n\nStand der Daten: {stand}",
        "platzhalter": {"liste": "Pepsi (4): Kraftfutter im Rueckstand",
                        "anzahl": "9", "stand": "17.08.2026 05:31"}},
    "melde_ok_titel": {
        "gruppe": "Meldung", "titel": "Betreff bei Fehlanzeige",
        "text": "Aktivstall: alle Tiere erkannt",
        "platzhalter": {}},
    "melde_ok_text": {
        "gruppe": "Meldung", "titel": "Text bei Fehlanzeige",
        "text": ("Der Fuetterungsrechner meldet heute kein Tier, das an keiner "
                 "Station war.\n\nStand der Daten: {stand}"),
        "platzhalter": {"stand": "17.08.2026 05:31"}},
}

GRUPPEN = ["Anmeldung", "Abruf", "Meldung"]

_lock = threading.Lock()
_eigene = {}


class _Sicher(string.Formatter):
    """Laesst unbekannte Platzhalter stehen, statt eine Ausnahme zu werfen."""

    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, "{%s}" % key)
        try:
            return args[key]
        except Exception:
            return "{%s}" % key

    def format_field(self, value, spec):
        try:
            return super().format_field(value, spec)
        except Exception:
            return str(value)


_form = _Sicher()


def laden():
    global _eigene
    try:
        with open(DATEI, encoding="utf-8") as f:
            d = json.load(f)
        _eigene = {k: v for k, v in d.items() if k in STANDARD and str(v).strip()}
    except Exception:
        _eigene = {}
    return _eigene


def speichern(neue):
    """Uebernimmt geaenderte Texte; leerer Text = zurueck zum Standard."""
    global _eigene
    with _lock:
        eigene = dict(_eigene)
        for k, v in neue.items():
            if k not in STANDARD:
                continue
            if str(v).strip():
                eigene[k] = v.replace("\r\n", "\n")
            else:
                eigene.pop(k, None)
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATEI + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(eigene, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATEI)
        _eigene = eigene
    return _eigene


def roh(schluessel):
    """Der aktuell gueltige Text - eigener, sonst Standard."""
    if schluessel in _eigene:
        return _eigene[schluessel]
    return STANDARD.get(schluessel, {}).get("text", "")


def ist_geaendert(schluessel):
    return schluessel in _eigene


def T(schluessel, **werte):
    """Fertiger Text mit eingesetzten Platzhaltern."""
    werte.setdefault("stall", stall())
    try:
        return _form.format(roh(schluessel), **werte)
    except Exception:
        return roh(schluessel)


def vorschau(schluessel, text=None):
    """Vorschau mit Beispielwerten - fuer die Weboberflaeche."""
    eintrag = STANDARD.get(schluessel, {})
    quelle = text if text is not None else roh(schluessel)
    beispiele = dict(eintrag.get("platzhalter", {}))
    beispiele.setdefault("stall", stall())
    try:
        return _form.format(quelle, **beispiele)
    except Exception:
        return quelle


laden()
