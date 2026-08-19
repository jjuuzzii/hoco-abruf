# -*- coding: utf-8 -*-
"""Aussehen der Weboberflaeche - Farben, Bausteine, Icons.

Uebernommen aus dem Entwurf "StallControl Pro" (Arbeitstitel der Oberflaeche). Zwei bewusste Abweichungen:

* **Keine externen Dateien.** Der Entwurf laedt Font Awesome von einem CDN. Im
  Ingress-Panel waere das eine Abhaengigkeit, die bei blockiertem oder fehlendem
  Netz stillschweigend wegfaellt - dann steht die Oberflaeche ohne Symbole da.
  Stattdessen liegen die benoetigten Symbole als eingebettetes SVG hier unten.
* **Alles in einer Datei.** Kein Build-Schritt, kein npm - die Auslieferung
  bleibt "Datei kopieren, Rebuild".
"""

CSS = """
:root{
  --bg-main:#f8fafc; --bg-card:#ffffff; --sidebar-bg:#0f172a;
  --sidebar-hover:#1e293b; --primary:#2563eb; --primary-light:#eff6ff;
  --text-main:#0f172a; --text-muted:#64748b; --border:#e2e8f0;
  --success:#10b981; --success-bg:#ecfdf5; --warning:#f59e0b;
  --warning-bg:#fffbeb; --danger:#ef4444; --danger-bg:#fef2f2;
  --progress-raufutter:#3b82f6; --progress-kraftfutter:#10b981;
  --progress-mineral:#8b5cf6;
  --radius:12px;
  --shadow-sm:0 1px 3px 0 rgba(0,0,0,.05),0 1px 2px -1px rgba(0,0,0,.05);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  background:var(--bg-main);color:var(--text-main);display:flex;height:100vh;
  overflow:hidden;-webkit-font-smoothing:antialiased}
svg{width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:2;
  stroke-linecap:round;stroke-linejoin:round;flex-shrink:0}

/* Sidebar */
.sidebar{width:260px;background:var(--sidebar-bg);color:#fff;padding:24px 16px;
  display:flex;flex-direction:column;flex-shrink:0}
.logo{font-size:20px;font-weight:700;margin-bottom:32px;display:flex;
  align-items:center;gap:12px;padding:0 12px}
.logo span.mark{font-size:22px}
.nav-links{list-style:none;display:flex;flex-direction:column;gap:4px}
.nav-link{display:flex;align-items:center;gap:12px;padding:10px 14px;
  text-decoration:none;color:#94a3b8;border-radius:8px;cursor:pointer;
  font-size:14px;font-weight:500;transition:all .15s ease}
.nav-link:hover{background:var(--sidebar-hover);color:#f8fafc}
.nav-link.active{background:var(--primary);color:#fff}
.nav-link svg{font-size:16px;width:20px}
.sidebar-fuss{margin-top:auto;font-size:11px;color:#475569;padding:0 12px}

/* Kopf und Inhalt */
.main-wrapper{flex:1;display:flex;flex-direction:column;overflow:hidden}
.header{display:flex;justify-content:space-between;align-items:center;
  padding:16px 32px;background:var(--bg-card);border-bottom:1px solid var(--border)}
.header h1{font-size:20px;font-weight:700;letter-spacing:-.02em}
.header-meta{font-size:13px;color:var(--text-muted);margin-top:2px;display:flex;
  align-items:center;gap:6px}
.user-avatar{width:36px;height:36px;background:#38bdf8;color:#fff;
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:13px;font-weight:600}
.content-area{padding:28px 32px;overflow-y:auto;flex:1}
.view-section{display:none}
.view-section.active{display:block;animation:fadeIn .2s ease-in-out}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}

/* Karten */
.cards-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:20px;margin-bottom:28px}
.wunsch-zeile{padding:9px 0;border-bottom:1px solid var(--rand,#e6e9ea);font-size:14px}
.wunsch-zeile:last-of-type{border-bottom:0}
.card{background:var(--bg-card);padding:20px;border-radius:var(--radius);
  box-shadow:var(--shadow-sm);border:1px solid var(--border);display:flex;
  flex-direction:column;justify-content:space-between}
.card-header-sm{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:12px}
.card-title{color:var(--text-muted);font-size:13px;font-weight:600;
  text-transform:uppercase;letter-spacing:.03em}
.stat-display{display:flex;align-items:baseline;gap:16px;margin:8px 0 16px}
.stat-value{font-size:36px;font-weight:800;line-height:1}
.stat-badges{display:flex;flex-direction:column;gap:6px}
.card-link{text-decoration:none;color:var(--primary);font-weight:600;
  font-size:13px;display:inline-flex;align-items:center;gap:6px;
  transition:gap .15s;cursor:pointer;background:none;border:none;padding:0}
.card-link:hover{gap:10px}

/* Badges */
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;
  border-radius:20px;font-size:12px;font-weight:600}
.badge-success{background:var(--success-bg);color:var(--success)}
.badge-danger{background:var(--danger-bg);color:var(--danger)}
.badge-warning{background:var(--warning-bg);color:var(--warning)}
.badge-neutral{background:#f1f5f9;color:var(--text-muted)}

/* Tabellen */
.table-container{background:var(--bg-card);border-radius:var(--radius);
  border:1px solid var(--border);box-shadow:var(--shadow-sm);overflow-x:auto}
.section-header{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:16px;gap:12px;flex-wrap:wrap}
.section-header h2{font-size:16px;font-weight:700}
.styled-table{width:100%;border-collapse:collapse;text-align:left}
.styled-table th{background:#f8fafc;padding:10px 10px;color:var(--text-muted);
  font-size:12px;font-weight:600;text-transform:uppercase;
  border-bottom:1px solid var(--border);white-space:nowrap}
.zell-ist{display:block;font-weight:600}
.zell-soll{display:block;font-size:11.5px;color:var(--text-muted);white-space:nowrap}
/* Tabellen beugen sich, statt zu scrollen: lange Zellen umbrechen,
   Zahlenspalten bleiben schmal. Auf dem Bildschirm ist das richtig - die
   Uebersicht war sonst breiter als jeder Monitor.
   ABER: `overflow-wrap:anywhere` (bis 0.35.0) bricht Woerter an JEDEM Zeichen,
   sobald eine Spalte eng wird. Auf dem Handy stand deshalb senkrecht
   'A b m e l d e n' und 'T a m i r a' - am 19.08.2026 an einer Aufnahme
   gesehen. Gebrochen wird jetzt nur noch zwischen Woertern; was gar nicht
   brechen darf (Knoepfe, Plaketten, Zahlenspalten), sagt es selbst. */
.styled-table{table-layout:auto;font-size:14px}
.styled-table td,.styled-table th{overflow-wrap:break-word;word-break:normal}
.styled-table .btn,.styled-table .badge,.styled-table .pille2{white-space:nowrap}
/* Nur die Zufallscodes duerfen mitten im Wort umbrechen - sie sind zehn
   zusammenhaengende Zeichen ohne Trennstelle. */
.code-tag{overflow-wrap:anywhere;word-break:break-all}
.styled-table td:first-child,.styled-table th:first-child{width:1%;white-space:nowrap}
.styled-table td{padding:9px 10px;border-bottom:1px solid var(--border);
  font-size:14px;vertical-align:middle}
.styled-table tbody tr:last-child td{border-bottom:none}
.styled-table tbody tr:hover{background:#f8fafc}

/* Bedienelemente */
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;
  border:1px solid var(--border);background:#fff;border-radius:8px;cursor:pointer;
  font-size:13px;font-weight:600;color:var(--text-main);transition:all .15s;
  font-family:inherit}
.btn:hover{background:#f1f5f9;border-color:#cbd5e1}
.btn-primary{background:var(--primary);color:#fff;border:none}
.btn-primary:hover{background:#1d4ed8}
.btn-danger{background:var(--danger-bg);color:var(--danger);border-color:#fca5a5}
.btn-danger:hover{background:#fee2e2}
.btn-success{background:var(--success-bg);color:var(--success);border-color:#a7f3d0}
.input-text{padding:8px 12px;border:1px solid var(--border);border-radius:8px;
  font-size:13px;outline:none;transition:border-color .15s;background:#fff;
  font-family:inherit;color:inherit}
.input-text:focus{border-color:var(--primary)}
select.input-text{cursor:pointer}
label.wahl{display:inline-flex;align-items:center;gap:6px;font-size:13px;
  margin-right:12px;cursor:pointer}

/* Fortschritt */
.progress-box{width:100%;max-width:220px}
.progress-bar-bg{height:8px;background:#e2e8f0;border-radius:4px;overflow:hidden;
  margin-bottom:4px}
.progress-fill{height:100%;border-radius:4px}
.progress-fill.raufutter{background:var(--progress-raufutter)}
.progress-fill.kraftfutter{background:var(--progress-kraftfutter)}
.progress-fill.mineral{background:var(--progress-mineral)}
.progress-meta{display:flex;justify-content:space-between;font-size:11px;
  color:var(--text-muted);font-weight:500}

/* Ersteinrichtung: Beschriftung ueber dem Eingabefeld */
label.feld-titel{font-size:14px;font-weight:600;display:block;
  color:var(--text-main)}

/* WhatsApp-Vorschau */
.wa-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));
  gap:20px;margin-bottom:20px}
.wa-card{background:var(--bg-card);border:1px solid var(--border);
  border-radius:var(--radius);padding:18px}
.wa-card label.titel{font-size:14px;font-weight:700;display:block;margin-bottom:4px}
.wa-textarea{width:100%;min-height:110px;padding:10px;border:1px solid var(--border);
  border-radius:8px;font-family:inherit;font-size:13px;resize:vertical;outline:none}
.wa-textarea:focus{border-color:var(--primary)}
.wa-chat-preview{background:#e5ddd5;border-radius:8px;padding:12px;margin-top:10px;
  background-image:radial-gradient(#00000022 .5px,transparent .5px);
  background-size:10px 10px}
.wa-bubble{background:#dcf8c6;padding:10px 12px;border-radius:8px 0 8px 8px;
  font-size:12.5px;color:#111b21;line-height:1.4;box-shadow:0 1px 1px rgba(0,0,0,.1);
  max-width:90%;margin-left:auto;white-space:pre-wrap;word-break:break-word}
.wa-time{font-size:10px;color:#667781;text-align:right;margin-top:4px;display:block}
.platzhalter{font-size:12px;color:var(--text-muted);margin-top:6px}
.code-tag{background:#f1f5f9;border:1px solid #e2e8f0;padding:2px 6px;
  border-radius:4px;font-family:ui-monospace,monospace;font-size:12px;color:#475569}
.hinweis{border-radius:8px;padding:10px 12px;margin-bottom:12px;font-size:13px;
  display:flex;gap:8px;align-items:flex-start}
.hinweis-warn{background:var(--warning-bg);border:1px solid #fde68a;color:#92400e}
.hinweis-fehler{background:var(--danger-bg);border:1px solid #fca5a5;color:#991b1b}
.hinweis-ok{background:var(--success-bg);border:1px solid #86efac;color:#166534}
.grau{color:var(--text-muted);font-size:13px}

@media(max-width:820px){
  body{overflow:auto}
  .sidebar{width:100%;flex-direction:row;flex-wrap:wrap;gap:8px;padding:12px}
  .logo{margin-bottom:0}
  .nav-links{flex-direction:row;flex-wrap:wrap}
  .sidebar-fuss{display:none}
  body{flex-direction:column;height:auto}
  .content-area{padding:16px}
  .header{padding:12px 16px}
  /* Auf dem Handy wird aus jeder Tabellenzeile eine KARTE: Kopfzeile weg,
     jede Zelle eine eigene Zeile mit ihrer Spaltenueberschrift davor
     (`data-label`). Damit passt alles in die Breite - kein seitliches
     Schieben, keine abgeschnittenen Namen, keine buchstabenweise
     umgebrochenen Woerter.

     Der Weg dahin ging ueber zwei Irrwege, beide am 19.08.2026 an
     Handy-Aufnahmen gesehen: erst `overflow-wrap:anywhere`, das senkrechte
     Buchstabensuppe erzeugte, dann ein Mindestmass mit seitlichem Schieben,
     das der Betrieb ausdruecklich nicht wollte. Karten sind die Antwort, die
     ohne Kompromiss auskommt. */
  .styled-table,.styled-table tbody,.styled-table tr,.styled-table td{
    display:block;width:auto}
  .styled-table thead{display:none}
  .styled-table tr{border-bottom:1px solid var(--border);padding:12px 4px}
  .styled-table tbody tr:last-child{border-bottom:none}
  .styled-table td{border:none;padding:4px 0;display:flex;gap:12px;
    align-items:baseline;text-align:left !important}
  .styled-table td::before{content:attr(data-label);flex:0 0 38%;
    color:var(--text-muted);font-size:11px;font-weight:600;
    text-transform:uppercase;letter-spacing:.02em;line-height:1.5}
  /* Zellen ohne Ueberschrift (Knopfspalten) nehmen die volle Breite. */
  .styled-table td:not([data-label])::before{display:none}
  .styled-table td:not([data-label]){padding-top:8px}
  .styled-table td:first-child{width:auto;white-space:normal}
  .styled-table .zell-ist,.styled-table .zell-soll{display:inline}
  .styled-table .zell-soll{margin-left:6px}
}
"""

# Eingebettete Symbole (Strichzeichnung, 24x24) - ersetzen Font Awesome.
_PFADE = {
    "dashboard": "<path d='M21.21 15.89A10 10 0 1 1 8 2.83'/><path d='M22 12A10 10 0 0 0 12 2v10z'/>",
    "einsteller": "<path d='M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2'/><circle cx='9' cy='7' r='4'/><path d='M23 21v-2a4 4 0 0 0-3-3.87'/>",
    "plaene": "<rect x='3' y='4' width='18' height='18' rx='2'/><path d='M16 2v4M8 2v4M3 10h18'/>",
    "vorlagen": "<path d='M21 11.5a8.38 8.38 0 0 1-9 8.5 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.2A8.38 8.38 0 0 1 4 11.5 8.5 8.5 0 0 1 12.5 3 8.5 8.5 0 0 1 21 11.5z'/>",
    "monitor": "<rect x='2' y='3' width='20' height='14' rx='2'/><path d='M8 21h8M12 17v4'/>",
    "uhr": "<circle cx='12' cy='12' r='10'/><path d='M12 6v6l4 2'/>",
    "server": "<rect x='2' y='2' width='20' height='8' rx='2'/><rect x='2' y='14' width='20' height='8' rx='2'/><path d='M6 6h.01M6 18h.01'/>",
    "plus": "<path d='M12 5v14M5 12h14'/>",
    "schluessel": "<path d='M21 2l-2 2m-7.6 7.6a5 5 0 1 1-7.1 7.1 5 5 0 0 1 7.1-7.1zm0 0L15 8m0 0l3 3 3-3-3-3'/>",
    "weg": "<path d='M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6'/>",
    "download": "<path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3'/>",
    "speichern": "<path d='M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z'/><path d='M17 21v-8H7v8M7 3v5h8'/>",
    "pfeil": "<path d='M5 12h14M12 5l7 7-7 7'/>",
    "haken": "<path d='M20 6L9 17l-5-5'/>",
    "start": "<path d='M5 3l14 9-14 9V3z'/>",
    "warnung": "<path d='M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'/><path d='M12 9v4M12 17h.01'/>",
    "zurueck": "<path d='M3 12a9 9 0 1 0 3-6.7L3 8'/><path d='M3 3v5h5'/>",
}


def icon(name, groesse="1em"):
    """Eingebettetes SVG-Symbol."""
    pfad = _PFADE.get(name)
    if not pfad:
        return ""
    return ("<svg viewBox='0 0 24 24' style='width:%s;height:%s' aria-hidden='true'>%s</svg>"
            % (groesse, groesse, pfad))
