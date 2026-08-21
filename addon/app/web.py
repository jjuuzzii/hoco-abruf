# -*- coding: utf-8 -*-
"""Ingress-Weboberflaeche des HOCO-Abrufs.

Fuenf Ansichten in einer Seite: Dashboard, Einsteller, Fuetterungsplaene,
WhatsApp-Vorlagen, Monitor. Gewechselt wird per JavaScript ohne Nachladen; der
aktive Tab steht in der Adresszeile, damit man nach dem Speichern eines
Formulars dort landet, wo man war.

Bewusst ohne Build-Schritt: Standardbibliothek, HTML per String-Bau, Stil und
Symbole in stil.py. Kein npm, keine externen Dateien - die Auslieferung bleibt
"Datei kopieren, Rebuild". Home Assistant erledigt die Anmeldung (Ingress);
die Seite selbst hat keine.
"""
import html
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import (archiv, einrichtung, hoco, meldung, rueckstand, stil, texte,
               ueberwachung, zeitplan)

SHARE = "/share/fuetterungsabruf"
PFERDE = os.path.join(SHARE, "pferde.json")
VERLAUF = os.path.join(SHARE, "verlauf")

ANSICHTEN = [
    ("view-einrichtung", "Ersteinrichtung", "start"),
    ("view-dashboard", "Dashboard", "dashboard"),
    ("view-einsteller", "Einsteller verwalten", "einsteller"),
    ("view-plaene", "Einstellungen", "plaene"),
    ("view-vorlagen", "WhatsApp-Vorlagen", "vorlagen"),
    ("view-monitor", "Fütterungs-Monitor", "monitor"),
]


_WUNSCH_TITEL = {"rf": "Raufutter", "kf": "Kraftfutter",
                 "min": "Mineralfutter", "sel": "Zeit am Selektionstor"}


def _lade(pfad, default):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _verlauf_dateien():
    try:
        return sorted([f for f in os.listdir(VERLAUF) if f.endswith(".json")], reverse=True)
    except Exception:
        return []


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _zahl(text):
    """'93 Min' -> 93.0 ; '0.583 kg' -> 0.583 ; None -> 0.0"""
    import re
    t = re.search(r"[-+]?\d*[.,]?\d+", str(text or "").replace(" ", ""))
    return float(t.group().replace(",", ".")) if t else 0.0


def _prozent(d):
    """Fortschritt in Prozent - bevorzugt den angezeigten Wert."""
    if not d:
        return 0
    p = d.get("fortschritt_gesamt_prozent")
    if isinstance(p, (int, float)):
        return max(0, min(100, int(p)))
    anspruch = _zahl(d.get("anspruch_gesamt"))
    if anspruch <= 0:
        return 0
    return max(0, min(100, int(100 * _zahl(d.get("fortschritt_gesamt")) / anspruch)))


def _balken(d, art):
    if not d:
        return "<span class=grau>&mdash;</span>"
    return ("<div class=progress-box><div class=progress-bar-bg>"
            "<div class='progress-fill %s' style='width:%d%%'></div></div>"
            "<div class=progress-meta><span>%s</span><span>von %s</span></div></div>"
            % (art, _prozent(d), _e(d.get("fortschritt_gesamt", "?")),
               _e(d.get("anspruch_gesamt", "?"))))




def _fmt(d):
    """Ist-Wert gross, Soll und Prozent klein darunter.

    Frueher stand alles in einer Zeile ('0.099 kg / 1.000 kg (33%)'). Bei acht
    Spalten und 28 Zeilen war die Tabelle damit breiter als jeder Bildschirm -
    man musste seitlich schieben, um den Status zu sehen. Zweizeilig passt sie.
    """
    if not d:
        return "&mdash;"
    return ("<span class=zell-ist>%s</span>"
            "<span class=zell-soll>von %s &middot; %s&nbsp;%%</span>"
            % (_e(d.get("fortschritt_gesamt", "?")),
               _e(d.get("anspruch_gesamt", "?")),
               _e(d.get("fortschritt_gesamt_prozent", "?"))))


def _pferde(d):
    """Pferdeliste aus pferde.json - Rueckstand hier nochmal rechnen.

    Der Abruf schreibt die Felder zwar mit, aber eine Datei aus einer aelteren
    Fassung hat sie nicht. Neu rechnen ist billiger als eine Fallunterscheidung
    an jeder Anzeigestelle."""
    liste = d.get("pferde", [])
    try:
        rueckstand.pruefe(liste)
    except Exception:
        pass
    return liste


def _urteil_moeglich(pferde):
    """Traegt schon mindestens ein Pferd den Stempel 'zuletzt_gesehen'?

    Der Stempel entsteht erst ab 0.13.0 beim Abruf. Ohne diese Abfrage saehe
    direkt nach dem Einspielen JEDES Pferd wie eine Karteileiche aus - der
    Monitor haette 29 Entfernen-Knoepfe angeboten. Solange kein einziger
    Stempel da ist, wird deshalb gar nicht geurteilt."""
    return any(p.get("zuletzt_gesehen") for p in pferde)


def _veraltet(p, stand, moeglich=True):
    """Stand dieses Pferd im letzten Abruf noch in einer Futtertabelle?

    Teil-Abrufe ergaenzen bewusst nur - ein Pferd, das der Rechner nicht mehr
    fuehrt, bliebe sonst ewig in pferde.json stehen (so wie Nr. 28 'Corazon',
    das am 16.08.2026 in keiner Tabelle mehr auftauchte)."""
    if not moeglich:
        return False
    return bool(stand) and p.get("zuletzt_gesehen") != stand


def _pferd_entfernen(nr):
    """Ein Pferd aus pferde.json loeschen. Das Archiv bleibt unberuehrt -
    dort steht die Aufzeichnung, und Geschichte wird nicht geloescht.

    Den Zugangsschluessel loescht der Aufrufer (siehe /pferd_weg): das Pferd
    ist weg, also darf auch sein Link nicht weiterleben. Bis 0.34.0 blieb er
    erreichbar - ein ausgezogenes Pferd hatte auf der Website eine Seite, die
    jeder mit dem alten QR-Aufkleber weiter aufrufen konnte."""
    d = _lade(PFERDE, None)
    if not d or "pferde" not in d:
        return False
    vorher = len(d["pferde"])
    d["pferde"] = [p for p in d["pferde"] if str(p.get("nr")) != str(nr)]
    if len(d["pferde"]) == vorher:
        return False
    d["anzahl_pferde"] = len(d["pferde"])
    with open(PFERDE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return True


def _zustand(p):
    """Status-Plakette fuer die Tabellen."""
    if p.get("ueberwacht") is False:
        return ("<span class='badge badge-neutral' title='%s'>Nicht &uuml;berwacht</span>"
                % _e(p.get("ueberwachung_grund") or "vom Hofb&uuml;ro ausgenommen"))
    stufe = p.get("rueckstand")
    titel = _e(p.get("rueckstand_text"))
    if stufe == "transponder":
        return ("<span class='badge badge-danger' title='%s'>Nicht erkannt</span>"
                % titel)
    if stufe == "nichts":
        return ("<span class='badge badge-danger' title='%s'>Nicht geholt</span>"
                % titel)
    if stufe == "wenig":
        return ("<span class='badge badge-warning' title='%s'>R&uuml;ckstand</span>"
                % titel)
    return "<span class='badge badge-success'>Aktiv</span>"


def _kurz_karte(pferde):
    """Die gerechneten Rueckstaende in einer Zeile - fuer den Blick aufs Dashboard.

    Die grosse Auffaellig-Karte zeigt bewusst nur, was der Rechner selbst
    meldet; gerechnete Rueckstaende haben sie frueher zugeschuettet. Auf dem
    Dashboard sollen sie trotzdem stehen, aber verdichtet: Zahl und Namen,
    Einzelheiten in der Tabelle.
    """
    ohne = [p for p in pferde if p.get("rueckstand") == "nichts"]
    wenig = [p for p in pferde if p.get("rueckstand") == "wenig"]
    if not (ohne or wenig):
        return ""
    def namen(liste, hoechstens=8):
        n = [_e(p.get("name") or p.get("nr")) for p in liste[:hoechstens]]
        rest = len(liste) - len(n)
        return ", ".join(n) + (" und %d weitere" % rest if rest > 0 else "")
    teile = ""
    if ohne:
        teile += ("<div class=wunsch-zeile><b>%d ohne Abholung</b> "
                  "<div class=grau>%s</div></div>" % (len(ohne), namen(ohne)))
    if wenig:
        teile += ("<div class=wunsch-zeile><b>%d im R&uuml;ckstand</b> "
                  "<div class=grau>%s</div></div>" % (len(wenig), namen(wenig)))
    return ("<div class=card style='margin-bottom:16px'>"
            "<div class=card-header-sm><span class=card-title>Futter nicht geholt"
            "</span>%s</div>%s"
            "<div class=grau style='margin-top:10px'>Gerechnet aus Anspruch und "
            "Geholtem. Einzelheiten im F&uuml;tterungs-Monitor.</div>"
            "<a class=card-link data-goto=view-monitor>Monitor &ouml;ffnen %s</a></div>"
            % (stil.icon("warnung"), teile, stil.icon("pfeil")))


def _rueckstand_karte(pferde):
    """Auffaellige Tiere ganz oben - das ist der Blick, der morgens zaehlt.

    Hier stehen NUR die Meldungen des Fuetterungsrechners selbst
    (Transponderfehler). Die gerechneten Rueckstaende bleiben aussen vor - sie
    haben zu viele Tiere in die Karte gespuelt und den Blick verstellt; in den
    Tabellen sind sie weiter an der Status-Plakette zu sehen.
    """
    if not pferde:
        return ""
    auffaellig = [p for p in pferde if p.get("rueckstand") == "transponder"]
    if not auffaellig:
        kopf = ("<div class='hinweis hinweis-ok' style='margin:20px 0'>%s<div>"
                "<b>Alle Tiere erkannt.</b> Der F&uuml;tterungsrechner meldet "
                "kein Tier, das an keiner Station war.</div></div>"
                % stil.icon("haken"))
        return kopf
    zeilen = ""
    for p in auffaellig:
        # Seit wann der Rechner das meldet, steht dahinter: die Meldung bleibt
        # stehen, bis das Tier wieder erkannt wird, und war am 18.08.2026 bei
        # allen fuenf Tieren ueber 29 Stunden alt. Ohne das Datum liest sich
        # jede Meldung wie eine von heute Nacht.
        hinweiszeile = ""
        if p.get("hinweis"):
            seit = (p.get("hinweis_seit") or "").strip()
            hinweiszeile = ("<div class=grau style='margin-top:4px'>%s%s</div>"
                            % (_e(p["hinweis"]),
                               _e(" (gemeldet %s)" % seit) if seit else ""))
        zeilen += ("<tr><td data-label='Nr.'>%s</td>"
                   "<td data-label='Pferd'><strong>%s</strong>%s</td>"
                   "<td data-label='Zustand'>%s</td>"
                   "<td data-label='Raufutter'>%s</td><td data-label='Kraftfutter'>%s</td>"
                   "<td data-label='Mineral'>%s</td><td style='text-align:right'>%s</td></tr>"
                   % (_e(p.get("nr")), _e(p.get("name")), hinweiszeile, _zustand(p),
                      _fehl(p, "rf"), _fehl(p, "kf"), _fehl(p, "min"),
                      _ausnahme_knopf(p, True)))
    return ("<div class=section-header style='margin-top:24px'>"
            "<h2>Auff&auml;llig &ndash; %d Tier%s</h2></div>"
            "<div class=table-container style='margin-bottom:8px'>"
            "<table class=styled-table><thead><tr><th>#</th><th>Pferd</th>"
            "<th>Status</th><th>Raufutter</th><th>Kraftfutter</th>"
            "<th>Mineralfutter</th><th></th></tr></thead><tbody>%s</tbody></table></div>"
            "<p class=grau style='margin:0 0 12px'><b>Nicht erkannt</b> meldet "
            "der F&uuml;tterungsrechner selbst (&Uuml;bersichten &rarr; "
            "Hinweise) &ndash; das Tier war an keiner Station, meist ein "
            "Transponderfehler. Gerechnete R&uuml;ckst&auml;nde stehen hier "
            "bewusst nicht; sie sind in der F&uuml;tterungs&uuml;bersicht an der "
            "Status-Plakette zu sehen.<br>Ein Tier ohne Transponder, auf der "
            "Weide oder verkauft ist kein Fehler &ndash; solche Nummern mit "
            "<b>Nicht &uuml;berwachen</b> stillstellen.</p>"
            % (len(auffaellig), "" if len(auffaellig) == 1 else "e", zeilen)
            )


def _ausnahme_knopf(p, aus, ansicht="view-dashboard"):
    """Knopf 'Nicht ueberwachen' bzw. 'Wieder ueberwachen' fuer ein Pferd."""
    # Kein Grundfeld mehr in der Tabelle: Knopf plus Eingabefeld waren gut
    # 260 Pixel je Zeile, und damit passte die Uebersicht auf keinen Bildschirm.
    # Der Grund laesst sich in der Karte 'Nicht ueberwacht' nachtragen, wo auch
    # steht, welche Nummern stillgestellt sind.
    return ("<form method=post action=ueberwachung style='display:inline-flex'>"
            "<input type=hidden name=ansicht value='%s'>"
            "<input type=hidden name=nr value='%s'>"
            "<input type=hidden name=aus value='%d'>"
            "<button class=btn style='white-space:nowrap;font-size:12px;padding:5px 9px' "
            "title='%s'>%s</button></form>"
            % (ansicht, _e(p.get("nr")), 1 if aus else 0,
               "Nicht mehr beurteilen" if aus else "Wieder beurteilen",
               "Aus" if aus else "Ein"))


def _ausnahmen_karte(pferde):
    """Die stillgestellten Nummern - sichtbar, damit sie niemand vergisst.

    Eine Ausnahme, die man nicht mehr sieht, ist eine Ausnahme, die irgendwann
    einen echten Fall verdeckt. Deshalb steht sie direkt unter der Karte."""
    aus = [p for p in pferde if p.get("ueberwacht") is False]
    if not aus:
        return ""
    zeilen = ""
    for p in aus:
        grund = (" &middot; <span class=grau>%s</span>"
                 % _e(p.get("ueberwachung_grund"))) if p.get("ueberwachung_grund") else ""
        zeilen += ("<tr><td data-label='Nr.'>%s</td>"
                   "<td data-label='Pferd'><strong>%s</strong>%s</td>"
                   "<td data-label='Grund merken'>"
                   "<form method=post action=ueberwachung style='display:flex;gap:6px'>"
                   "<input type=hidden name=ansicht value=view-monitor>"
                   "<input type=hidden name=nr value='%s'>"
                   "<input type=hidden name=aus value='1'>"
                   "<input name=grund class=input-text value='%s' placeholder='Grund' "
                   "style='flex:1;font-size:12px'>"
                   "<button class=btn style='font-size:12px'>Merken</button></form></td>"
                   "<td style='text-align:right'>%s</td></tr>"
                   % (_e(p.get("nr")), _e(p.get("name")), grund,
                      _e(p.get("nr")), _e(p.get("ueberwachung_grund") or ""),
                      _ausnahme_knopf(p, False)))
    return ("<div class=card style='margin-bottom:20px'>"
            "<div class=card-header-sm><span class=card-title>Nicht &uuml;berwacht "
            "&ndash; %d Tier%s</span>%s</div>"
            "<div class=grau style='margin:8px 0'>Diese Nummern werden nicht "
            "beurteilt: kein Eintrag unter &bdquo;Auff&auml;llig&ldquo;, keine "
            "Morgenmeldung, kein Urteil auf der Einsteller-Seite. Die Zahlen "
            "stehen weiterhin &uuml;berall.</div>"
            # Diese Tabelle steht direkt in der Karte, nicht in einem
            # `table-container`. Auf dem Handy bekommt jede Tabelle ein
            # Mindestmass (siehe stil.py) - ohne eigenen Schieberahmen wuerde
            # sie hier die ganze Seite breit machen statt in sich zu scrollen.
            "<div style='overflow-x:auto'>"
            "<table class=styled-table><tbody>%s</tbody></table></div></div>"
            % (len(aus), "" if len(aus) == 1 else "e", stil.icon("warnung"), zeilen))


def _meldung_karte(m):
    """Morgenmeldung einstellen - Zeit, Tage, Umfang, Empfaenger.

    Bewusst hier und nicht als Automation in Home Assistant: der Zeitplan
    der Abrufe wird auch hier gepflegt, und ein Fehler im YAML einer
    Automation waere von dieser Seite aus nicht zu sehen."""
    d = _lade(PFERDE, {})
    pferde = _pferde(d)
    jetzt_betroffen = len(m.betroffene(pferde))
    # Was ginge JETZT raus - wortgleich, mit den Daten des letzten Abrufs.
    # Ohne diese Vorschau muesste man den Testknopf druecken, um zu sehen,
    # was eine Aenderung an den Vorlagen bewirkt.
    betreff, rumpf = m.nachricht(pferde, d.get("stand", ""))
    vorschau = ("<div style='background:#f8fafc;border-radius:8px;padding:12px;"
                "margin-bottom:12px'>"
                "<div class=grau style='margin-bottom:6px'>So ginge die Meldung "
                "jetzt raus:</div>"
                "<div style='font-weight:700;margin-bottom:4px'>%s</div>"
                "<div style='white-space:pre-wrap'>%s</div></div>"
                % (_e(betreff), _e(rumpf)))
    zuletzt = m.zuletzt_text()
    zuletzt_zeile = (("<div class=grau style='margin-bottom:12px'>Zuletzt "
                      "gesendet: %s</div>" % _e(zuletzt)) if zuletzt else
                     "<div class=grau style='margin-bottom:12px'>Noch nie "
                     "gesendet.</div>")

    tage = ""
    for i, kurz in enumerate(zeitplan.TAGE_KURZ):
        tage += ("<label class=wahl><input type=checkbox name=tage value='%d'%s> %s</label>"
                 % (i, " checked" if i in m["tage"] else "", kurz))
    umfang = ""
    for schluessel, bez in meldung.UMFAENGE.items():
        umfang += ("<option value='%s'%s>%s</option>"
                   % (schluessel, " selected" if m["umfang"] == schluessel else "",
                      _e(bez)))
    naechste = m.naechste()
    zustand = ("<span class='badge badge-success'>Aktiv</span>" if m["aktiv"]
               else "<span class='badge badge-neutral'>Aus</span>")
    return (
        "<div class=card style='margin-bottom:16px'>"
        "<form method=post action=meldung>"
        "<input type=hidden name=ansicht value=view-plaene>"
        "<div class=card-header-sm><span class=card-title>Morgenmeldung</span>%s</div>"
        "<div class=grau style='margin:8px 0 12px'>Wer nachts an keiner Station "
        "war &ndash; morgens aufs Telefon. Gerade: <b>%d Tier%s</b>.</div>"
        "<div style='display:flex;gap:10px;align-items:center;flex-wrap:wrap;"
        "margin-bottom:12px'>"
        "<label class=wahl><input type=checkbox name=aktiv value=1%s> aktiv</label>%s"
        "um <input name=zeit class=input-text value='%s' style='width:80px'></div>"
        "<div style='margin-bottom:12px'>%s</div>"
        "<select name=umfang class=input-text style='width:100%%;margin-bottom:12px'>"
        "%s</select>"
        "<input name=ziel class=input-text value='%s' style='width:100%%;"
        "margin-bottom:8px' placeholder='%s (aus den Add-on-Einstellungen)'>"
        "<div class=grau style='margin-bottom:12px'>Benachrichtigungs-Dienst, "
        "z.B. <code>notify.mobile_app_iphone</code>. Leer lassen = der in den "
        "Add-on-Einstellungen hinterlegte.</div>"
        "<label class=wahl style='margin-bottom:12px'><input type=checkbox "
        "name=auch_ohne_befund value=1%s> auch melden, wenn nichts vorliegt "
        "(t&auml;gliche Entwarnung)</label>"
        "%s%s"
        "<div class=grau style='margin-bottom:12px'>%s%s</div>"
        "<button class='btn btn-primary'>%s Speichern</button> "
        "<button class=btn name=test value=1>%s Jetzt testen</button>"
        "</form></div>"
        % (stil.icon("uhr"), jetzt_betroffen,
           "" if jetzt_betroffen == 1 else "e",
           " checked" if m["aktiv"] else "", zustand, _e(m["zeit"]), tage,
           umfang, _e(m["ziel"]), _e(meldung.STANDARD_ZIEL),
           " checked" if m["auch_ohne_befund"] else "",
           vorschau, zuletzt_zeile,
           _e(m.beschreibung()),
           ("  &middot;  n&auml;chste Meldung: " + _e(naechste)) if naechste else "",
           stil.icon("speichern"), stil.icon("start")))


def _einsteller_zelle(wer):
    """Wer ist auf dieses Pferd angemeldet - alle, nicht nur der erste.

    Sind es mehrere, steht das ausdruecklich dabei: sie benutzen **denselben**
    Zugangslink (der Schluessel haengt am Pferd, nicht an der Person). Wer das
    nicht weiss, meldet einen ab und glaubt, dessen Zugang sei weg.
    """
    if not wer:
        return "<span class=grau>&mdash;</span>"
    if len(wer) == 1:
        return _e(wer[0])
    return ("%s<div class=grau style='font-size:12px'>%d Personen &middot; "
            "ein gemeinsamer Link</div>"
            % ("<br>".join("<span style='white-space:nowrap'>%s</span>" % _e(w)
                           for w in wer), len(wer)))


def _feldbefund(d):
    """Warnt, wenn die Feldbelegung des Auszugs nicht mehr bestaetigt ist.

    Steht ganz oben und in Rot, weil dieser Befund alle anderen entwertet: ist
    ein Feld verrutscht, sehen die Futterzahlen darunter weiter richtig aus.
    Solange nichts zu melden ist, steht hier NICHTS - eine taegliche
    Bestaetigung liest nach einer Woche niemand mehr.
    """
    befund = (d or {}).get("pruefung") or {}
    if not befund or befund.get("ok"):
        return ""
    zeilen = "".join("<li>%s</li>" % _e(b) for b in befund.get("befunde", []))
    return ("<div class='hinweis hinweis-fehler' style='margin:20px 0'>%s<div>"
            "<b>Die Feldbelegung des Auszugs stimmt nicht mehr.</b> "
            "Der F&uuml;tterungsrechner liefert seine Daten anders als bisher. "
            "Bis das gekl&auml;rt ist, k&ouml;nnen die Zahlen unten falsch sein, "
            "obwohl sie plausibel aussehen."
            "<ul style='margin:8px 0 0 18px'>%s</ul>"
            "<div class=grau style='margin-top:6px'>Feldkarte und Herleitung: "
            "STAND.md, Abschnitt 2b.</div></div></div>"
            % (stil.icon("warnung"), zeilen))


def _fehl(p, art):
    """Wie weit ist dieses Pferd bei EINER Futterart zurueck?"""
    stufe = p.get(art + "_rueckstand")
    if not stufe:
        return "<span class=grau>&mdash;</span>"
    d = p.get(art) or {}
    return ("<strong>%s %%</strong> <span class=grau>von %s f&auml;llig</span>"
            % (_e(d.get("fortschritt_bisherig_prozent", 0)),
               _e(d.get("anspruch_bisherig", "?"))))


def serve(bot, run_abruf, status, port):
    hinweis = {}          # einmalige Meldung nach einem Formular
    pruef = {}            # letztes Ergebnis je Pruefung der Ersteinrichtung

    # ---------------------------------------------------------- Ersteinrichtung
    def _pruefkarte(kennung, titel, erklaerung, knopf):
        """Ein Pruefblock: was geprueft wird, ein Knopf, das letzte Ergebnis."""
        ok, text = pruef.get(kennung, (None, ""))
        if ok is None:
            ergebnis = ""
        else:
            ergebnis = ("<div class='hinweis hinweis-%s' style='margin-top:10px'>"
                        "%s<div>%s</div></div>"
                        % ("ok" if ok else "fehler",
                           stil.icon("haken" if ok else "warnung"), text))
        return ("<div class=card style='margin-bottom:12px'>"
                "<div class=card-header-sm><span class=card-title>%s</span>%s</div>"
                "<div class=grau style='margin:6px 0 10px'>%s</div>"
                "<button class=btn name=pruefen value='%s'>%s %s</button>%s</div>"
                % (_e(titel), stil.icon("server"), erklaerung, kennung,
                   stil.icon("start"), _e(knopf), ergebnis))

    def einrichtung_ansicht():
        werte = dict(einrichtung.laufende_werte())
        # Was gerade im Add-on-UI steht, ist maßgeblich - es kann neuer sein als
        # das, was beim Start in die Umgebung kam.
        for kennung, wert in (einrichtung.optionen() or {}).items():
            if kennung in einrichtung.UMGEBUNG and str(wert or "").strip():
                werte[kennung] = str(wert)

        offen = einrichtung.fehlend()
        fertig = einrichtung.erledigt()
        if fertig:
            kopf = ("<div class='hinweis hinweis-ok'>%s<div><b>Eingerichtet</b> "
                    "– abgeschlossen am %s. Hier stehen die Werte weiterhin "
                    "zum Nachbessern.</div></div>"
                    % (stil.icon("haken"),
                       _e(einrichtung.zustand().get("stand", "?"))))
        elif offen:
            # Je fehlendem Wert steht dabei, was ohne ihn nicht geht. Ein
            # pauschales "holt keine Daten" waere bei den meisten Feldern
            # schlicht falsch und macht die Warnung wertlos.
            punkte = "".join(
                "<li><b>%s</b> – sonst %s</li>"
                % (_e(titel),
                   _e(einrichtung.FOLGE.get(kennung, "fehlt dem Add-on etwas")))
                for kennung, titel, _h, _p, _f in einrichtung.FELDER
                if kennung in offen)
            kopf = ("<div class='hinweis hinweis-warn'>%s<div>Es fehlt noch:"
                    "<ul style='margin:6px 0 0 18px'>%s</ul></div></div>"
                    % (stil.icon("warnung"), punkte))
        else:
            kopf = ("<div class='hinweis hinweis-ok'>%s<div>Alle nötigen "
                    "Werte stehen. Prüfe unten die Verbindungen und hake die "
                    "Einrichtung dann ab.</div></div>" % stil.icon("haken"))

        darf, grund = einrichtung.schreibbar()
        if not darf:
            kopf += ("<div class='hinweis hinweis-fehler'>%s<div>Das Add-on kann "
                     "seine Optionen nicht selbst schreiben (%s). Trage die Werte "
                     "dann von Hand unter <b>Einstellungen → Add-ons → "
                     "HOCO-Abruf → Konfiguration</b> ein – die "
                     "Prüfungen hier unten funktionieren trotzdem."
                     "</div></div>" % (stil.icon("warnung"), _e(grund)))

        felder = ""
        for kennung, titel, hilfe, pflicht, _folge in einrichtung.FELDER:
            typ = "password" if kennung.endswith(("passwort", "secret")) else "text"
            felder += (
                "<div style='margin-bottom:14px'>"
                "<label class=feld-titel>%s%s</label>"
                "<div class=grau style='margin:2px 0 6px'>%s</div>"
                "<input class=input-text type=%s name='f_%s' value='%s' "
                "style='width:100%%;max-width:520px'></div>"
                % (_e(titel), " <b>*</b>" if pflicht else "", hilfe, typ,
                   _e(kennung), _e(werte.get(kennung, ""))))

        formularkopf = ("<form method=post action=einrichtung>"
                        "<input type=hidden name=ansicht value=view-einrichtung>")

        eingaben = (
            "<div class=card style='margin-bottom:16px'>"
            "<div class=card-header-sm><span class=card-title>Werte</span>%s</div>"
            "<div class=grau style='margin:6px 0 14px'>Mit <b>*</b> markierte "
            "Felder braucht das Add-on zwingend. Gespeichert wird in die "
            "Add-on-Konfiguration – dort stehen sie danach genauso."
            "</div>%s"
            "<button class='btn btn-success' name=speichern value=1>%s "
            "Werte speichern</button></div>"
            % (stil.icon("plaene"), felder, stil.icon("speichern")))

        pruefungen = (
            "<div class=section-header><h2>Verbindungen prüfen</h2></div>"
            + _pruefkarte(
                "hoco", "Fütterungsrechner",
                "Meldet sich am FTP an und sieht nach, ob dort Auszüge liegen. "
                "Geprüft werden die Werte, die oben im Formular stehen "
                "– auch ungespeicherte.",
                "Verbindung prüfen")
            + _pruefkarte(
                "notify", "Benachrichtigung ins Hofbüro",
                "Schickt eine Testmeldung an den eingetragenen Dienst. Über "
                "diesen Weg kommen später die Freigaben und die "
                "Morgenmeldung.",
                "Testmeldung senden")
            + _pruefkarte(
                "whatsapp", "WhatsApp",
                "Sieht nach, ob die WhatsApp-Integration in Home Assistant "
                "eingerichtet ist. Ohne sie läuft alles übrige weiter "
                "– nur der Bot antwortet dann nicht.",
                "Dienst suchen")
            + _pruefkarte(
                "website", "Website",
                "Fragt die Schnittstelle des Plugins ab und prüft dabei das "
                "gemeinsame Geheimnis.",
                "Website prüfen"))

        abschluss = (
            "<div class=card style='margin-top:16px'>"
            "<div class=card-header-sm><span class=card-title>Übernehmen</span>%s"
            "</div>"
            "<div class=grau style='margin:6px 0 12px'>Gespeicherte Werte "
            "erreichen das Add-on erst mit einem <b>Neustart</b> – danach "
            "beginnt der erste Abruf von selbst. Das Abhaken blendet diese "
            "Ansicht aus der Startseite aus; erreichbar bleibt sie."
            "</div>"
            "<div style='display:flex;gap:8px;flex-wrap:wrap'>"
            "<button class=btn name=neustart value=1 "
            "onclick=\"return confirm('Add-on jetzt neu starten? Die "
            "Oberfläche ist kurz nicht erreichbar.')\">%s Speichern und neu "
            "starten</button>"
            "<button class='btn btn-success' name=fertig value='%s'>%s "
            "Einrichtung %s</button></div></div>"
            % (stil.icon("start"), stil.icon("zurueck"),
               "0" if fertig else "1", stil.icon("haken"),
               "wieder öffnen" if fertig else "abhaken"))

        return (kopf + formularkopf + eingaben + pruefungen + abschluss
                + "</form>")

    # ------------------------------------------------------------------ Kopf
    def kopfzeile():
        d = _lade(PFERDE, {})
        titel = dict((k, ti) for k, ti, _s in ANSICHTEN).get(_start(), "Dashboard")
        return ("<div><h1 id=page-title>%s</h1>" % _e(titel) +
                "<div class=header-meta>%s Letzter Stand: %s</div></div>"
                "<div class=user-profile><div class=user-avatar>HB</div></div>"
                % (stil.icon("uhr"), _e(d.get("stand", "noch kein Abruf"))))

    def _start():
        """Welche Ansicht beim Aufruf oben liegt."""
        return "view-einrichtung" if einrichtung.noetig() else "view-dashboard"

    def seitenleiste():
        links = ""
        start = _start()
        for kennung, titel, symbol in ANSICHTEN:
            # Die Ersteinrichtung ist erledigt, sobald nichts mehr fehlt - dann
            # gehoert sie nicht dauerhaft in die Seitenleiste. Der Abschnitt
            # bleibt bestehen und ist ueber die Einstellungen erreichbar.
            if kennung == "view-einrichtung" and not einrichtung.noetig():
                continue
            aktiv = " active" if kennung == start else ""
            links += ("<li><a class='nav-link%s' data-target='%s'>%s %s</a></li>"
                      % (aktiv, kennung, stil.icon(symbol), _e(titel)))
        return ("<aside class=sidebar><div class=logo><span class=mark>&#128052;</span>"
                "<span>HOCO-Abruf</span></div><ul class=nav-links>%s</ul>"
                "<div class=sidebar-fuss>%s</div>"
                "</aside>" % (links, _e(texte.stall())))

    # ------------------------------------------------------------- Dashboard
    def dashboard():
        d = _lade(PFERDE, {})
        zuordnung = bot.store.get("zuordnung", {})
        aktiv = sum(1 for n, pf in zuordnung.items() if pf)
        offen = len(bot.store.get("offen", {}))

        d_stand = _lade(PFERDE, {})
        quelle = d_stand.get("quelle") or ""
        lauf_text = ("<div style='font-size:18px;font-weight:700'>%s</div>"
                     "<div class=grau>zuletzt verarbeiteter Auszug</div>" % _e(quelle)
                     ) if quelle else "<div class=grau>noch kein Auszug gelesen</div>"

        laeuft = status.get("laeuft")
        if laeuft:
            sys_badge = ("<span class='badge badge-warning'>%s Abruf l&auml;uft</span>"
                         % stil.icon("uhr"))
        else:
            sys_badge = ("<span class='badge badge-success'>%s System bereit</span>"
                         % stil.icon("haken"))

        # Offene Aenderungswuensche zuoberst - sie brauchen eine Handlung am
        # Panel, und niemand sonst sieht sie.
        wkarte = ""
        offen_w = getattr(bot, "wuensche", []) or []
        if offen_w:
            zeilen = "".join(
                "<div class=wunsch-zeile><div><b>Nr. %s %s</b> &ndash; %s auf <b>%s</b>"
                "<div class=grau>jetzt %s &middot; gestellt %s</div>%s</div>"
                "<form method=post action=wunsch_ablehnen style='margin-top:6px;"
                "display:flex;gap:6px;flex-wrap:wrap;align-items:center'>"
                "<input type=hidden name=ansicht value=view-dashboard>"
                "<input type=hidden name=id value='%s'>"
                "<input name=grund class=input-text placeholder='Grund der Ablehnung' "
                "style='flex:1;min-width:150px;font-size:12px'>"
                "<button class='btn btn-danger'>%s Ablehnen</button></form></div>"
                % (_e(w.get("nr")), _e(w.get("name")),
                   _e(_WUNSCH_TITEL.get(w.get("art"), w.get("art"))),
                   _e(w.get("wunsch")), _e(w.get("ist")), _e(w.get("gestellt")),
                   ("<div class=grau style='font-style:italic'>&bdquo;%s&ldquo;</div>"
                    % _e(w.get("notiz"))) if w.get("notiz") else "",
                   _e(w.get("id")), stil.icon("weg"))
                for w in offen_w)
            wkarte = (
                "<div class=card style='margin-bottom:16px'>"
                "<div class=card-header-sm><span class=card-title>&Auml;nderungsw&uuml;nsche "
                "&ndash; %d offen</span>%s</div>%s"
                "<div class=grau style='margin-top:10px'>Am Rechner eintragen &ndash; dann "
                "verschwindet der Eintrag von selbst. Steht er noch hier, stimmt der Wert "
                "dort noch nicht.</div>"
                "</div>"
                % (len(offen_w), stil.icon("warnung"), zeilen))

        karten = (
            "<div class=cards-grid>"
            "<div class=card><div><div class=card-header-sm>"
            "<span class=card-title>Einsteller</span>%s</div>"
            "<div class=stat-display><span class=stat-value>%d</span>"
            "<div class=stat-badges>"
            "<span class='badge badge-success'>%s %d aktiv</span>"
            "<span class='badge badge-neutral'>%d offen</span></div></div></div>"
            "<a class=card-link data-goto=view-einsteller>Alle verwalten %s</a></div>"

            "<div class=card><div><div class=card-header-sm>"
            "<span class=card-title>System-Status</span>%s</div>"
            "<div style='margin:12px 0'>%s"
            "<p class=grau style='margin-top:10px'>Letzter Abruf: %s</p></div></div>"
            "<form method=post action=abruf><input type=hidden name=ansicht "
            "value=view-dashboard><button class=card-link>Jetzt Daten abrufen %s"
            "</button></form>"
            "<form method=post action=wunsch_pruefen>"
            "<input type=hidden name=ansicht value=view-dashboard>"
            "<button class=card-link>Nach W&uuml;nschen sehen %s</button></form></div>"

            "<div class=card><div><div class=card-header-sm>"
            "<span class=card-title>Datenquelle</span>%s</div>"
            "<div style='margin:8px 0 16px'>%s</div></div>"
            "<a class=card-link data-goto=view-plaene>Einstellungen &ouml;ffnen %s</a></div>"
            "</div>"
            % (stil.icon("einsteller"), len(zuordnung), stil.icon("haken"), aktiv,
               offen, stil.icon("pfeil"),
               stil.icon("server"), sys_badge, _e(status.get("ergebnis") or "noch nie"),
               stil.icon("pfeil"), stil.icon("zurueck"),
               stil.icon("uhr"), lauf_text, stil.icon("pfeil")))

        pferde = _pferde(d)
        return wkarte + karten + _rueckstand_karte(pferde) + _kurz_karte(pferde)

    # ------------------------------------------------------------ Einsteller
    def einsteller():
        out = "<div class=section-header><h2>Aktivierte Einsteller &amp; Codes</h2></div>"
        # Der Mitarbeiter-Zugang gehoert hierher, nicht zu den Pferden: er
        # haengt an der Aufgabe (Koppelzeiten nachsehen, Wuensche abarbeiten),
        # nicht an einem Tier. Die Seite ist ausdruecklich nur zum Lesen -
        # eingetragen wird am Fuetterungsrechner.
        mlink = bot.mitarbeiter_link() or ""
        out += (
            "<div class=card style='margin-bottom:20px'>"
            "<div class=card-header-sm><span class=card-title>Zugang f&uuml;r den "
            "Stallmitarbeiter</span>%s</div>"
            "<div class=grau style='margin-bottom:10px'>Eine Seite f&uuml;r den ganzen "
            "Stall: offene &Auml;nderungsw&uuml;nsche und die Koppelzeiten aller Pferde. "
            "<b>Nur zum Nachsehen</b> &ndash; ge&auml;ndert wird am F&uuml;tterungsrechner. "
            "Kein Home-Assistant-Konto n&ouml;tig, der Link gen&uuml;gt.</div>"
            "%s"
            "<form method=post action=mitarbeiter_code style='margin-top:10px' "
            "onsubmit=\"return confirm('Neuen Code f&uuml;r den Mitarbeiter? "
            "Der alte Link wird ung&uuml;ltig.')\">"
            "<input type=hidden name=ansicht value=view-einsteller>"
            "<button class=btn>%s Neuen Code erzeugen</button></form>"
            "</div>"
            % (stil.icon("schluessel"),
               ("<a class=code-tag href='%s' target=_blank>%s</a>" % (_e(mlink), _e(mlink)))
               if mlink else "<span class=grau>Noch kein Code &ndash; oder keine Website "
                             "hinterlegt.</span>",
               stil.icon("schluessel")))

        st = bot.store.get("offen", {})
        if st:
            zeilen = ""
            for nummer, e in st.items():
                namen = ", ".join(bot.name_von(n) for n in bot.nrs(e))
                kn = bot.kontakt_name(nummer)
                wer = ((_e(kn) + " &middot; ") if kn else "") + "+" + _e(nummer)
                zeilen += ("<tr><td data-label='Anmeldung'>%s</td>"
                           "<td data-label='Pferde'>%s</td><td style='text-align:right'>"
                           "<form method=post action=freigeben style='display:inline'>"
                           "<input type=hidden name=ansicht value=view-einsteller>"
                           "<input type=hidden name=nummer value='%s'>"
                           "<button class='btn btn-success' name=ja value=1>%s Best&auml;tigen</button> "
                           "<button class='btn btn-danger' name=ja value=0>Ablehnen</button>"
                           "</form></td></tr>"
                           % (wer, _e(namen), _e(nummer), stil.icon("haken")))
            out += ("<div class=table-container style='margin-bottom:20px'>"
                    "<table class=styled-table><thead><tr><th>Offene Anmeldung</th>"
                    "<th>Pferde</th><th></th></tr></thead><tbody>%s</tbody></table></div>"
                    % zeilen)

        z = bot.store.get("zuordnung", {})
        if not z:
            return out + "<div class=table-container><div style='padding:24px' class=grau>Noch keine Einsteller freigegeben.</div></div>"

        zeilen = ""
        for nummer, e in z.items():
            kn = bot.kontakt_name(nummer)
            pferde = ""
            for nr in bot.nrs(e):
                link = bot._link(nr)
                schl = bot.keys.get(nr, "")
                # Teilt sich noch jemand dieses Pferd? Dann teilen sich beide
                # auch den Link - das gehoert sichtbar hierher, nicht nur in
                # die Abmelde-Meldung.
                mit = [bot.kontakt_name(n) or ("+" + n)
                       for n in bot.einsteller_von(nr, ausser=nummer)]
                mit_text = (" <span class='badge badge-warning' title='gemeinsamer "
                            "Link'>auch: %s</span>" % _e(", ".join(mit))) if mit else ""
                code = ("<a href='%s' target=_blank class=code-tag>%s</a>"
                        % (_e(link), _e(schl))) if link else \
                       ("<span class=code-tag>%s</span>" % (_e(schl) or "kein Code"))
                # flex-wrap ist hier nicht Kosmetik: ohne sie quetscht der
                # Flex-Container Name, Code und Plakette nebeneinander und
                # jedes Wort bricht auf dem Handy buchstabenweise um.
                pferde += ("<div style='display:flex;align-items:center;gap:8px;"
                           "margin:3px 0;flex-wrap:wrap'>"
                           "<span>&#128052;</span>"
                           "<strong style='white-space:nowrap'>%s</strong>%s%s"
                           "<form method=post action=code style='display:inline' "
                           "onsubmit=\"return confirm('Neuen Code f&uuml;r %s? Der alte Link "
                           "und der gedruckte Aufkleber werden ung&uuml;ltig.')\">"
                           "<input type=hidden name=ansicht value=view-einsteller>"
                           "<input type=hidden name=nr value='%s'>"
                           "<button class=btn title='Neuen Code erzeugen'>%s</button></form></div>"
                           % (_e(bot.name_von(nr)), code, mit_text,
                              _e(bot.name_von(nr)), _e(nr),
                              stil.icon("schluessel")))
            zeilen += (
                # Der Name kommt aus WhatsApp selbst (notify_name im Ereignis)
                # und steht unter der Nummer. Das Eingabefeld ist weg: es war
                # die breiteste Spalte der Tabelle und wurde von Hand gepflegt,
                # obwohl die Information ohnehin mitgeliefert wird.
                "<tr><td data-label='Einsteller' style='white-space:nowrap'>+%s%s</td>"
                "<td data-label='Pferde &amp; Codes'>%s</td>"
                "<td style='text-align:right'>"
                "<form method=post action=abmelden onsubmit=\"return confirm("
                "'Einsteller +%s wirklich abmelden?')\">"
                "<input type=hidden name=ansicht value=view-einsteller>"
                "<input type=hidden name=nummer value='%s'>"
                "<button class='btn btn-danger'>%s Abmelden</button></form></td></tr>"
                % (_e(nummer),
                   ("<div class=grau style='font-size:12px'>%s</div>" % _e(kn)) if kn else "",
                   pferde, _e(nummer), _e(nummer), stil.icon("weg")))

        return (out + "<div class=table-container><table class=styled-table><thead><tr>"
                "<th>Einsteller</th><th>Pferde &amp; Codes</th>"
                "<th></th></tr></thead><tbody>%s</tbody></table></div>"
                % zeilen)

    # -------------------------------------------------------- Fuetterungsplaene
    def plaene():
        """Was frueher 'Fuetterungsplaene' war.

        Es gibt nichts mehr zu planen: das Add-on sieht regelmaessig nach, ob
        der Fuetterungsrechner eine neue Datei geschrieben hat, und arbeitet
        nur dann. Uebrig bleiben die Morgenmeldung - die hat weiter eine feste
        Uhrzeit - und zwei Erklaerungen.
        """
        d = _lade(PFERDE, {})
        quelle = d.get("quelle") or "noch keine"
        zustand = einrichtung.zustand()
        einr = ("<div class=card style='margin-bottom:16px'>"
                "<div class=card-header-sm><span class=card-title>Ersteinrichtung"
                "</span>%s</div>"
                "<div class=grau style='margin:6px 0 10px'>Alle Werte stehen%s. "
                "Hier lassen sie sich nachbessern und die Verbindungen einzeln "
                "prüfen.</div>"
                "<a class=card-link data-goto=view-einrichtung>Ersteinrichtung "
                "öffnen %s</a></div>"
                % (stil.icon("haken"),
                   (" – abgehakt am %s" % _e(zustand.get("stand", "")))
                   if zustand.get("erledigt") else "",
                   stil.icon("pfeil"))) if not einrichtung.noetig() else ""

        out = ("<div class=section-header><h2>Einstellungen</h2></div>"
               + einr +
               "<div class=card style='margin-bottom:16px'>"
               "<div class=card-header-sm><span class=card-title>Datenquelle</span>%s</div>"
               "<div class=grau>CSV-Auszug von <b>%s%s</b>, etwa alle 30 Minuten neu.<br>"
               "Zuletzt verarbeitet: <b>%s</b>.</div></div>"
               % (stil.icon("server"), _e(hoco.FTP_HOST), _e(hoco.FTP_VERZEICHNIS),
                  _e(quelle)))
        out += _meldung_karte(bot.meldung)
        if hinweis.get("text"):
            art = hinweis.pop("art", "fehler")
            out += ("<div class='hinweis hinweis-%s'>%s<div>%s</div></div>"
                    % ("ok" if art == "ok" else "fehler",
                       stil.icon("haken" if art == "ok" else "warnung"),
                       _e(hinweis.pop("text"))))
        return out

    def vorlagen():
        out = ("<div class=section-header><h2>Nachrichten-Vorlagen</h2>"
               "<button class='btn btn-primary' form=texte-form>%s Vorlagen speichern"
               "</button></div>"
               "<div class=grau style='margin-bottom:16px'>{Platzhalter} werden beim "
               "Senden ersetzt. Feld leeren = Standardtext.</div>"
               "<form method=post action=texte id=texte-form>"
               "<input type=hidden name=ansicht value=view-vorlagen>" % stil.icon("speichern"))
        for gruppe in texte.GRUPPEN:
            out += "<h2 style='font-size:15px;margin:20px 0 12px'>%s</h2><div class=wa-grid>" % _e(gruppe)
            for key, meta in texte.STANDARD.items():
                if meta["gruppe"] != gruppe:
                    continue
                platz = ", ".join("{%s}" % p for p in meta["platzhalter"]) or "keine"
                zurueck = (" &middot; <a href='?standard=%s' class=card-link "
                           "style='display:inline'>auf Standard zur&uuml;cksetzen</a>"
                           % _e(key)) if texte.ist_geaendert(key) else ""
                out += ("<div class=wa-card>"
                        "<label class=titel>%s</label>"
                        "<div class=platzhalter style='margin:0 0 8px'>Platzhalter: %s%s</div>"
                        "<textarea class=wa-textarea name='t_%s' data-vorschau='v_%s'>%s</textarea>"
                        "<div class=wa-chat-preview><div class=wa-bubble id='v_%s'>%s"
                        "<span class=wa-time>%s &#10003;&#10003;</span></div></div>"
                        "</div>"
                        % (_e(meta["titel"]), _e(platz), zurueck, _e(key), _e(key),
                           _e(texte.roh(key)), _e(key), _e(texte.vorschau(key)),
                           _jetzt_uhr()))
            out += "</div>"
        return out + "</form>"

    def _jetzt_uhr():
        import time
        return time.strftime("%H:%M")

    # --------------------------------------------------------------- Monitor
    def monitor():
        import time as _t
        d = _lade(PFERDE, {})
        pferde = _pferde(d)
        heute = _t.strftime("%Y-%m-%d")
        monat_start = _t.strftime("%Y-%m-01")
        kopf = ("<div class=section-header><h2>Vollst&auml;ndiger F&uuml;tterungs-Monitor</h2>"
                "<a class=btn href='?export=csv'>%s Aktueller Stand</a></div>"
                % stil.icon("download"))
        kopf += (
            "<div class=card style='margin-bottom:20px'>"
            "<div class=card-header-sm><span class=card-title>Archiv</span>%s</div>"
            "<div class=grau style='margin-bottom:12px'>Nach jedem Abruf wird je Pferd "
            "eine Zeile mitgeschrieben. Vorhanden: <strong>%s</strong>.</div>"
            "<form method=get style='display:flex;gap:10px;align-items:center;flex-wrap:wrap'>"
            "<input type=hidden name=export value=archiv>"
            "von <input type=date name=von value='%s' class=input-text> "
            "bis <input type=date name=bis value='%s' class=input-text>"
            "<button class='btn btn-primary'>%s Zeitraum exportieren</button>"
            "</form>"
            "<a class=btn href='?export=archiv' style='margin-top:10px'>%s Alles exportieren</a>"
            "</div>"
            % (stil.icon("download"), _e(archiv.umfang_text()), monat_start, heute,
               stil.icon("download"), stil.icon("download")))
        # Ganz nach vorn: stimmt die Feldbelegung ueberhaupt noch? Steht dieser
        # Befund, sind alle Zahlen darunter fraglich - er gehoert vor die
        # Tabelle, nicht darunter.
        kopf += _feldbefund(d)
        if not pferde:
            return kopf + ("<div class=table-container><div style='padding:24px' class=grau>"
                           "Noch keine Daten.</div></div>")
        stand = d.get("stand", "")
        # Wem gehoert welches Pferd? Nur fuer die Warnung beim Loeschen.
        # Wer gehoert zu welchem Pferd? Bis 0.34.0 nur fuer die Warnung beim
        # Loeschen gebaut und nirgends sichtbar - dabei ist gerade der Fall
        # "zwei Einsteller auf einem Pferd" der, den man sehen muss: die beiden
        # teilen sich EINEN Zugangslink, und beim Abmelden des einen bleibt er
        # fuer den anderen bestehen.
        belegt = {}
        for nummer, e in bot.store.get("zuordnung", {}).items():
            for nr in bot.nrs(e):
                belegt.setdefault(str(nr), []).append(bot.kontakt_name(nummer)
                                                      or ("+" + nummer))
        moeglich = _urteil_moeglich(pferde)
        zeilen, alte = "", 0
        for p in pferde:
            sel = p.get("selektion") or []
            veraltet = _veraltet(p, stand, moeglich)
            alte += 1 if veraltet else 0
            zeilen += ("<tr%s><td data-label='Nr.'>%s</td>"
                       "<td data-label='Pferd'><strong>%s</strong></td>"
                       "<td data-label='Raufutter'>%s</td><td data-label='Kraftfutter'>%s</td>"
                       "<td data-label='Mineral'>%s</td><td data-label='Tor'>%s</td>"
                       "<td data-label='Einsteller'>%s</td><td data-label='Status'>%s</td>"
                       "<td>%s</td></tr>"
                       % (" style='opacity:.6'" if veraltet else "",
                          _e(p.get("nr")), _e(p.get("name")), _fmt(p.get("rf")),
                          _fmt(p.get("kf")), _fmt(p.get("min")), len(sel),
                          _einsteller_zelle(belegt.get(str(p.get("nr"))) or []),
                          _zustand(p), _weg_knopf(p, veraltet, belegt)))
        hinweis_alt = ""
        if alte:
            hinweis_alt = (
                "<div class='hinweis hinweis-warn'>%s<div><b>%d Pferd%s stand%s "
                "beim letzten Abruf nicht mehr im F&uuml;tterungsrechner.</b> "
                "Wahrscheinlich ausgezogen. Mit &bdquo;Entfernen&ldquo; "
                "verschwind%s aus dieser Liste &ndash; die Aufzeichnungen im "
                "Archiv bleiben erhalten.</div></div>"
                % (stil.icon("warnung"), alte, "" if alte == 1 else "e",
                   "" if alte == 1 else "en", "et es" if alte == 1 else "en sie"))
        return kopf + hinweis_alt + (
            _ausnahmen_karte(pferde) +
            "<div class=table-container><table class=styled-table><thead><tr>"
            "<th>#</th><th>Pferd</th><th>Raufutter</th>"
            "<th>Kraftfutter</th><th>Mineral</th>"
            "<th>Tor</th><th>Einsteller</th><th>Status</th><th></th>"
            "</tr></thead><tbody>%s</tbody></table></div>" % zeilen)

    def _weg_knopf(p, veraltet, belegt):
        """Entfernen-Knopf - nur fuer Pferde, die der Rechner nicht mehr fuehrt.

        Ein Pferd zu loeschen, das noch abgerufen wird, waere sinnlos: der
        naechste Lauf legt es sofort wieder an. Deshalb gibt es den Knopf dort
        gar nicht erst. Stattdessen steht dort der Schalter fuer die
        Ueberwachung - hier ist jedes Pferd erreichbar, nicht nur die gerade
        auffaelligen."""
        if not veraltet:
            return _ausnahme_knopf(p, p.get("ueberwacht") is not False, "view-monitor")
        nr = str(p.get("nr"))
        wer = belegt.get(nr) or []
        frage = ("%s (Nr. %s) aus der Liste entfernen?" % (p.get("name") or "Pferd", nr))
        if wer:
            frage += ("\\n\\nACHTUNG: %s ist darauf angemeldet - der Abruf "
                      "findet danach keine Zahlen mehr." % ", ".join(wer))
        frage += "\\n\\nDas Archiv bleibt unangetastet."
        warnung = (" <span class='badge badge-warning'>%s angemeldet</span>"
                   % _e(", ".join(wer))) if wer else ""
        return ("<form method=post action=pferd_weg style='display:inline' "
                "onsubmit=\"return confirm('%s')\">"
                "<input type=hidden name=ansicht value=view-monitor>"
                "<input type=hidden name=nr value='%s'>"
                "<button class='btn btn-danger'>Entfernen</button></form>%s"
                % (_e(frage).replace("'", "&#39;"), _e(nr), warnung))

    def csv_export():
        d = _lade(PFERDE, {})
        felder = ["nr", "name", "rf_geholt", "rf_anspruch", "rf_prozent",
                  "kf_geholt", "kf_anspruch", "kf_prozent",
                  "min_geholt", "min_anspruch", "min_prozent",
                  "selektionen", "rueckstand", "rueckstand_text", "hinweis"]
        zeilen = [";".join(felder)]
        for p in _pferde(d):
            rf, kf = p.get("rf") or {}, p.get("kf") or {}
            mi = p.get("min") or {}
            werte = [p.get("nr"), p.get("name"),
                     rf.get("fortschritt_gesamt", ""), rf.get("anspruch_gesamt", ""),
                     rf.get("fortschritt_gesamt_prozent", ""),
                     kf.get("fortschritt_gesamt", ""), kf.get("anspruch_gesamt", ""),
                     kf.get("fortschritt_gesamt_prozent", ""),
                     mi.get("fortschritt_gesamt", ""), mi.get("anspruch_gesamt", ""),
                     mi.get("fortschritt_gesamt_prozent", ""),
                     len(p.get("selektion") or []),
                     p.get("rueckstand") or "",
                     (p.get("rueckstand_text") or "").replace(";", ","),
                     (p.get("hinweis") or "").replace(";", ",")]
            zeilen.append(";".join(str(w if w is not None else "") for w in werte))
        return "﻿" + "\r\n".join(zeilen)      # BOM, damit Excel UTF-8 erkennt

    # ----------------------------------------------------------------- Rahmen
    def rahmen():
        # Reihenfolge zaehlt: plaene() verbraucht den Hinweis, die
        # Ersteinrichtung muss ihn also vorher sehen koennen.
        inhalte = {"view-einrichtung": einrichtung_ansicht(),
                   "view-dashboard": dashboard(), "view-einsteller": einsteller(),
                   "view-plaene": plaene(), "view-vorlagen": vorlagen(),
                   "view-monitor": monitor()}
        abschnitte = ""
        start = _start()
        for kennung, _titel, _symbol in ANSICHTEN:
            aktiv = " active" if kennung == start else ""
            abschnitte += ("<section id='%s' class='view-section%s'>%s</section>"
                           % (kennung, aktiv, inhalte[kennung]))
        return ("<!doctype html><html lang=de><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width, initial-scale=1'>"
                "<title>HOCO-Abruf</title><style>" + stil.CSS + "</style></head><body>"
                + seitenleiste()
                + "<div class=main-wrapper><header class=header>" + kopfzeile()
                + "</header><div class=content-area>" + abschnitte
                + "</div></div><script>" + JS + "</script></body></html>")

    # ---------------------------------------------------------------- Server
    class H(BaseHTTPRequestHandler):
        def _send(self, body, code=200, typ="text/html; charset=utf-8", extra=None):
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(b)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _zurueck(self, ansicht=""):
            ziel = "." + (("#" + ansicht) if ansicht else "")
            self.send_response(303)
            self.send_header("Location", ziel)
            self.end_headers()

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            art = q.get("export", [""])[0]
            if art == "csv":
                self._send(csv_export(), typ="text/csv; charset=utf-8",
                           extra={"Content-Disposition":
                                  "attachment; filename=fuetterung-aktuell.csv"})
                return
            if art == "archiv":
                von = q.get("von", [""])[0]
                bis = q.get("bis", [""])[0]
                name = ("fuetterung-%s-bis-%s.csv" % (von, bis)) if (von or bis) \
                    else "fuetterung-archiv.csv"
                self._send(archiv.als_csv(von, bis), typ="text/csv; charset=utf-8",
                           extra={"Content-Disposition":
                                  "attachment; filename=%s" % name})
                return
            if "standard" in q:
                texte.speichern({q["standard"][0]: ""})
                self._zurueck("view-vorlagen")
                return
            with bot.lock:
                self._send(rahmen())

        def do_POST(self):
            ln = int(self.headers.get("Content-Length", "0") or 0)
            form = parse_qs(self.rfile.read(ln).decode("utf-8"))
            pfad = urlparse(self.path).path
            ansicht = form.get("ansicht", [""])[0]

            if pfad.endswith("/einrichtung"):
                # Ein Formular, mehrere Knoepfe: geprueft wird immer mit dem,
                # was gerade in den Feldern steht - auch ungespeichert. Sonst
                # muesste man zum Ausprobieren jedes Mal speichern.
                werte = {k[2:]: v[0].strip() for k, v in form.items()
                         if k.startswith("f_")}
                was = form.get("pruefen", [""])[0]
                if was == "hoco":
                    pruef["hoco"] = einrichtung.pruefe_hoco(
                        werte.get("hoco_host", ""), werte.get("hoco_verzeichnis", ""),
                        werte.get("hoco_benutzer", ""), werte.get("hoco_passwort", ""))
                elif was == "notify":
                    pruef["notify"] = einrichtung.pruefe_notify(
                        bot, werte.get("hofbuero_notify", ""))
                elif was == "whatsapp":
                    pruef["whatsapp"] = einrichtung.pruefe_whatsapp()
                elif was == "website":
                    pruef["website"] = einrichtung.pruefe_website(
                        werte.get("website_api", ""), werte.get("website_secret", ""))
                elif form.get("fertig"):
                    einrichtung.abschliessen(form["fertig"][0] == "1")
                elif form.get("speichern") or form.get("neustart"):
                    try:
                        einrichtung.speichern(werte)
                        hinweis["art"] = "ok"
                        hinweis["text"] = ("Werte in die Add-on-Konfiguration "
                                           "geschrieben.")
                    except Exception as e:
                        hinweis["text"] = ("Speichern fehlgeschlagen: %s. Die "
                                           "Werte lassen sich auch im Add-on-UI "
                                           "von Home Assistant eintragen." % e)
                    if form.get("neustart") and hinweis.get("art") == "ok":
                        # Erst antworten, dann neu starten - sonst bricht die
                        # Verbindung mitten in der Antwort ab und der Browser
                        # zeigt einen Fehler statt der Seite.
                        def _spaeter():
                            time.sleep(2)
                            try:
                                einrichtung.neustart()
                            except Exception as e:
                                print("Neustart: %s" % e, flush=True)
                        threading.Thread(target=_spaeter, daemon=True).start()
                        hinweis["text"] = ("Werte gespeichert. Das Add-on startet "
                                           "gleich neu - die Seite ist kurz nicht "
                                           "erreichbar.")
            elif pfad.endswith("/freigeben"):
                nummer = form.get("nummer", [""])[0]
                if nummer:
                    with bot.lock:
                        bot._freigeben(nummer, form.get("ja", ["0"])[0] == "1")
            elif pfad.endswith("/mitarbeiter_code"):
                with bot.lock:
                    neu_code = bot.mitarbeiter_code_neu()
                bot.keys_pushen()          # ausserhalb des Locks: Netz
                hinweis["art"] = "ok"
                hinweis["text"] = ("Neuer Mitarbeiter-Zugang erzeugt (%s). Der alte "
                                   "Link ist ab sofort ung&uuml;ltig." % neu_code)
            elif pfad.endswith("/code"):
                nr = form.get("nr", [""])[0]
                if nr:
                    with bot.lock:
                        bot.code_neu(nr)
                    bot.keys_pushen()      # ausserhalb des Locks: Netz
            elif pfad.endswith("/abmelden"):
                nummer = form.get("nummer", [""])[0]
                if nummer:
                    with bot.lock:
                        war, verwaist, geteilt = bot.abmelden(nummer)
                    if war:
                        teile = ["Einsteller +%s abgemeldet." % nummer]
                        if verwaist:
                            teile.append("Link abgeschaltet f&uuml;r: %s."
                                         % ", ".join(verwaist))
                        if geteilt:
                            # Der Schluessel haengt am Pferd: solange noch
                            # jemand darauf steht, bleibt der Link gueltig -
                            # auch fuer den gerade Abgemeldeten, falls er ihn
                            # gespeichert hat. Das muss dastehen, sonst haelt
                            # das Hofbuero den Zugang faelschlich fuer entzogen.
                            teile.append("Noch vergeben (Link bleibt g&uuml;ltig, "
                                         "auch f&uuml;r den Abgemeldeten): %s "
                                         "&ndash; f&uuml;r vollen Entzug dort einen "
                                         "neuen Code erzeugen." % ", ".join(geteilt))
                        hinweis["art"] = "warn" if geteilt else "ok"
                        hinweis["text"] = " ".join(teile)
                        if verwaist:
                            bot.keys_pushen()
            elif pfad.endswith("/pferd_weg"):
                nr = form.get("nr", [""])[0]
                if nr:
                    with bot.lock:
                        raus = _pferd_entfernen(nr)
                        # Der Link muss mitsterben, sonst bleibt die Pferdeseite
                        # fuer jeden erreichbar, der den Aufkleber abfotografiert
                        # hat. Reihenfolge: erst hier weg, dann pushen - /keys
                        # ersetzt auf der Website die ganze Tabelle.
                        zugang = bot.zugang_entfernen(nr)
                        if not raus:
                            hinweis["text"] = "Pferd %s war nicht (mehr) in der Liste." % nr
                        else:
                            hinweis["art"] = "ok"
                            hinweis["text"] = ("Pferd %s entfernt%s. Das Archiv bleibt."
                                               % (nr, " und sein Link abgeschaltet"
                                                  if zugang else ""))
                    if zugang:
                        bot.keys_pushen()          # ausserhalb des Locks: Netz
            elif pfad.endswith("/ueberwachung"):
                nr = form.get("nr", [""])[0]
                if nr:
                    # Wird das Tier gerade als 'nicht erkannt' gemeldet? Dann
                    # endet die Ausnahme von selbst, sobald es wieder an einer
                    # Station auftaucht. Vorsorglich gesetzte bleiben stehen.
                    wegen = any(str(p.get("nr")) == str(nr) and p.get("hinweis")
                                for p in _pferde(_lade(PFERDE, {})))
                    ueberwachung.setzen(nr, form.get("aus", ["0"])[0] == "1",
                                        form.get("grund", [""])[0], wegen)
            elif pfad.endswith("/meldung"):
                if form.get("test"):
                    # Der Test meldet auch, wenn nichts vorliegt - sonst waere
                    # nicht zu erkennen, ob der Dienst ueberhaupt ankommt.
                    # Kein eigener Thread: das ist ein Dienstaufruf, keine
                    # Panel-Sitzung, und das Ergebnis soll auf der Seite stehen.
                    hinweis["text"] = "Testmeldung verschickt: %s" \
                        % bot.morgenmeldung("test")
                    hinweis["art"] = "ok"
                else:
                    fehler = bot.meldung.setzen({
                        "zeit": form.get("zeit", [""])[0],
                        "tage": form.get("tage", []),
                        "umfang": form.get("umfang", [""])[0],
                        "ziel": form.get("ziel", [""])[0],
                        "aktiv": bool(form.get("aktiv")),
                        "auch_ohne_befund": bool(form.get("auch_ohne_befund")),
                    })
                    if fehler:
                        hinweis["text"] = fehler
            elif pfad.endswith("/texte"):
                texte.speichern({k[2:]: v[0] for k, v in form.items() if k.startswith("t_")})
            elif pfad.endswith("/wunsch_ablehnen"):
                if bot.wunsch_ablehnen(form.get("id", [""])[0],
                                       form.get("grund", [""])[0]):
                    hinweis["text"] = ("Wunsch abgelehnt – der Einsteller sieht das "
                                       "mit deiner Begründung auf seiner Seite.")
                    hinweis["art"] = "ok"
                else:
                    hinweis["text"] = "Ablehnung nicht gespeichert (Website nicht erreichbar?)."
            elif pfad.endswith("/wunsch_pruefen"):
                try:
                    offen = bot.wuensche_pruefen(melden=False)
                    hinweis["text"] = ("Nachgesehen: %s"
                                       % ("kein Wunsch offen." if not offen
                                          else "%d Wunsch/W&uuml;nsche noch offen." % len(offen)))
                    hinweis["art"] = "ok"
                except Exception as e:
                    hinweis["text"] = ("Website nicht erreichbar (%s) &ndash; ob "
                                       "W&uuml;nsche offen sind, ist damit unbekannt." % e)
            elif pfad.endswith("/abruf"):
                threading.Thread(target=run_abruf, args=("web",), daemon=True).start()

            self._zurueck(ansicht)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print("Weboberflaeche laeuft auf Port %d." % port, flush=True)
    srv.serve_forever()


JS = """
var links=document.querySelectorAll('.nav-link');
var abschnitte=document.querySelectorAll('.view-section');
var titel=document.getElementById('page-title');
function zeige(ziel){
  var el=document.getElementById(ziel); if(!el) return;
  links.forEach(function(l){l.classList.remove('active')});
  abschnitte.forEach(function(s){s.classList.remove('active')});
  var link=document.querySelector(".nav-link[data-target='"+ziel+"']");
  if(link){link.classList.add('active'); titel.innerText=link.innerText.trim();}
  el.classList.add('active');
  if(location.hash!=='#'+ziel){history.replaceState(null,'','#'+ziel);}
  document.querySelector('.content-area').scrollTop=0;
}
links.forEach(function(l){l.addEventListener('click',function(e){
  e.preventDefault(); zeige(l.getAttribute('data-target'));});});
document.querySelectorAll('[data-goto]').forEach(function(b){
  b.addEventListener('click',function(e){e.preventDefault();
    zeige(b.getAttribute('data-goto'));});});
if(location.hash){zeige(location.hash.slice(1));}

/* Vorschau: Tippen spiegelt sofort in die gruene Blase */
document.querySelectorAll('textarea[data-vorschau]').forEach(function(t){
  t.addEventListener('input',function(){
    var b=document.getElementById(t.getAttribute('data-vorschau'));
    if(!b) return;
    var zeit=b.querySelector('.wa-time');
    b.textContent=t.value;
    if(zeit){b.appendChild(zeit);}
  });
});
"""
