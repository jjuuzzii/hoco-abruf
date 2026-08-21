# HOCO-Abruf — Projektstand

**Betrieb:** Aktivstall (Pferde)
**Stand gesichert:** 19.08.2026 vormittags, Add-on **0.39.0** im Betrieb,
WordPress-Plugin **0.19.0** (liegt bereit, muss von Hand hoch)
**Diese Datei ist der Einstieg.** Alles Weitere liegt in den Unterordnern.

> **Kurzfassung:** Es läuft. Ein Home-Assistant-Add-on holt alle paar Minuten
> den CSV-Auszug vom Fütterungsrechner, schickt die Zahlen an die Website und
> antwortet den Einstellern per WhatsApp auf `/abruf`. Die lokalen `skripte/`
> waren die Werkstatt — im Betrieb ist `addon/` maßgeblich.
>
> **Seit 18.08.2026 ist das überholt.** Der Fütterungsrechner gibt seine Daten
> per FTP heraus; das Add-on liest sie direkt (0.20.0). Das Abfahren des Panels
> und die Modell-Auslesung sind **ausgebaut** — siehe Abschnitt 2b.

---

## 1. Ziel

Automatisch vom Stall-Fütterungsrechner ablesen, **wie viel jedes
Pferd geholt hat** — Raufutter (RF, in Minuten) und Kraftfutter (KF / „Hafer", in
kg) — und diese Zahlen jedem **Einsteller** für sein Pferd zugänglich machen.
Vorbild ist die fertige Beispielseite für *Tamira* (`ausgabe/tamira.html`, auch als
Artifact auf claude.ai).

---

## 2. Wie es früher funktionierte (die Bildschirm-Pipeline)

> **Überholt seit 18.08.2026 — dieser Abschnitt ist Geschichte.** Der Rechner
> hat doch eine Datenschnittstelle (Abschnitt 2b), und der hier beschriebene Weg
> ist aus dem Add-on ausgebaut. Er steht noch hier, weil er erklärt, warum
> manches so gebaut ist wie es ist — und weil er in
> `addon-sicherung-0.19.1-mit-ki/` wieder aktivierbar wäre.

Der Fütterungsrechner hatte **keine bekannte Datenschnittstelle** — nur einen
Bildschirm. Deshalb wurde der Bildschirm abgelesen. Im Betrieb macht das alles das Add-on
(`addon/app/`); die gleichnamigen Schritte in `skripte/` waren die Werkstatt und
sind nur noch zum Ausprobieren da.

1. **Bild holen** — `wasserbauer.py` verbindet sich über das Wasserbauer-Gateway
   (Guacamole/VNC) mit dem Panel, fährt die Reiter ab und speichert je Seite ein
   PNG nach `/share/fuetterungsabruf/seiten/` (wartet auf „Bildruhe", nimmt die
   tickende Uhr aus dem Vergleich).
2. **Auslesen** — `ablesen.py` + `modell.py`: zugeschnittene Bilder, kompakte
   `|`-getrennte Zeilen, Einheiten setzt der Code. Anbieter umschaltbar,
   standardmäßig **Gemini** (`gemini-flash-lite-latest`, ~0,023 ct je Aufnahme);
   Claude Haiku 4.5 bleibt eingebaut.
3. **Zusammenführen** — `wasserbauer.abrufen()` baut **einen Datensatz je Pferd**
   (`/share/fuetterungsabruf/pferde.json`): RF, KF, Mineral, Torerkennungen,
   Hinweise. Teil-Abrufe mischen ein, statt zu überschreiben. Rückstand rechnet
   `rueckstand.py` — **im Code**, nicht vom Modell geraten.
4. **Archivieren** — `archiv.py` hängt nach **jedem** Lauf je Pferd eine Zeile an
   `/share/fuetterungsabruf/archiv/JJJJ-MM.csv` (17 Spalten). Der letzte Lauf vor
   6 Uhr schreibt zusätzlich die Tageshistorie nach `verlauf/<datum>.json`.
5. **Ausliefern** — zwei Wege parallel, siehe Abschnitt 5: WhatsApp-Bot
   (`bot.py`) und Pferdeseiten auf der Website (WordPress-Plugin).

---

## 2b. Der FTP-Weg (18.08.2026) — ersetzt die Bildschirmerfassung

Der Rechner hat doch eine Datenschnittstelle. Er legt **alle 30 Minuten** einen
vollständigen CSV-Auszug seiner Datenbank auf seinem eigenen FTP-Server ab
(`172.16.1.49:21`, **anonym**, `/export/HOCO_JJJJMMTT_HHMM.csv`, ~1,5 MB, die
letzten fünf Dateien bleiben liegen). Erreichbar, seit die **FritzBox** einen
WireGuard-Tunnel ins Wasserbauer-Netz hält — der Home Assistant hängt am selben
Router und braucht deshalb **kein eigenes VPN**. Der Rechner blockt ICMP; ein
fehlgeschlagener Ping sagt nichts, TCP antwortet (`220 ProFTPD`).

**Aufbau:** `DSC;<event>;<felder…>` gibt die Spaltenköpfe eines Blocks als
Zahlencodes, `DTA;<event>;<werte…>` die Zeilen, `COM;` ist Kommentar. 27 Blöcke,
cp1252, jede Zeile endet mit einem überzähligen Semikolon. Es ist ein
**Vollauszug** über ein rollendes 14-Tage-Fenster, kein Zuwachs — Einlesen ist
damit wiederholbar und zustandslos.

**Belegung** (nachgewiesen, nicht dokumentiert — es gibt keine Dokumentation):

| was | Block / Feld |
|---|---|
| Tierstamm: Nr., Name, Transponder | `100001` / `900070`, `900045`, `900056` |
| **Raufutter** Anspruch / geholt / offen | `100034` / `801406`, `900064`, `900065` |
| **Kraftfutter** Anspruch / geholt / offen | `100014` / `900061`, `900060`, `900063` |
| **Mineral** Anspruch / geholt / offen | `100016` / `900061`, `900060`, `900063` |
| letzter Zyklus (RF / KF / Min) | `801419` / `801415` / `801615` |
| vorletzter Zyklus (RF / KF / Min) | `801420` / `801416` / `801616` |
| Besuche je Station, mit Uhrzeit | `100017`, Mengen dazu in `100037` |
| Meldungen („nicht erkannt") | `100019` / `801903`, Art `801902 = 6` |
| Zyklusbeginn (06:00) | `100011` / `801142` |
| Selektions-Zutrittszeiten | `100035` / `803503` von, `803501` bis, `803505` ein |
| Max KF pro Tag / pro Mahlzeit | `100001` / `800152`, `800139` |
| Intervalldauer / Verdauzeit / Zyklusdauer | `100001` / `800147`, `800148`, `800159` |
| Max Mineral pro Mahlzeit / Intervall | `100001` / `800140`, `800158` |
| Menge kg / bisher gefüttert (KF) | `100014` / `801405`, `801418` |
| Portionsgewicht (33 g/U) | `100032` / `HF_PORT_WEIGHT_CON_2` |

**Zwei Fallen, beide teuer gelernt:**

1. **Jede Futterart steht zweimal drin** — laufender Zyklus und voriger. Ich hatte
   beim Mineral `801615` genommen: Tamira wurden 30 g angezeigt, während das
   Panel 0 g zeigte. Die 30 g waren die von gestern. Aufgefallen ist es erst
   durch eine Panel-Aufnahme mitten im Zyklus; meine beiden „Prüfungen" davor
   hatten gegen Tagesabschlüsse verglichen und deshalb **denselben Irrtum
   bestätigt**. Wieder die alte Lehre: *ein Test, der die Annahme des Codes
   teilt, prüft nichts.*
2. **`801704` ist der Port, nicht die Stations-Kennung** (siehe unten).

**`anspruch_bisherig` kommt jetzt aus dem Auszug**, nicht mehr aus einer
Schätzung: `geholt + offen`. Der Wert ist nämlich **nicht** der anteilige
Tagesanspruch — der Rechner deckelt ihn auf „schon geholt + eine Mahlzeit".
Tamira (300 Min/Tag) stand am 18.08. um 09:57 *und* um 11:22 unverändert bei
32 Min fällig; geradlinig gerechnet wären es 67 gewesen. Geprüft: RF 28/28 und
KF 28/28 gegen den Archivlauf 50 Sekunden neben dem Auszug, Mineral 6/6 und
RF 9/9 gegen Panel-Aufnahmen im laufenden Zyklus.

**Die Falle:** `801704` im Besuchsprotokoll ist die **Port**-Nummer, nicht die
Stations-Kennung. Erst `100031` bildet Port auf Station ab, dann gibt `100030`
den Namen. Wer `100030` direkt anwendet, verschiebt alles um eine Stelle — mir
selbst passiert, ich hielt das Selektionstor für den Fütterungsrechner. Richtig:
**Port 1 = Komp.Sel. = das Selektionstor** (Erkennung + Kraftfutter + Mineral),
Port 2 = Heuschieber (nur RF-Minuten), Port 11 = Easy St. 11 (gemischt).

**Was fehlt: `anspruch_bisherig`.** In keinem der 27 Blöcke gespeichert; das
Panel rechnet ihn aus den Plantabellen `100042`/`100043`. Entschieden wurde,
ihn **selbst zu rechnen** — geradlinig über den Zyklus (`hoco._zyklus_anteil`).
Das Panel schaltet in Stufen und liegt etwas höher; unsere Zahl fällt damit auf
die sichere Seite, weil ein niedrigerer *fälliger* Wert im Zweifel **keine**
Warnung auslöst. Passt zu „Warnungen sparsam halten".

**Gemessen** (`skripte/vergleich_hoco.py`, fünf Auszüge gegen die Archivläufe
vom 18.08.): Beim geringsten Zeitversatz (50 Sekunden) **Raufutter 28/28 und
Kraftfutter 28/28 exakt**. Mit wachsendem Abstand wird es erwartungsgemäß
schlechter — und **jede** Abweichung läuft mit der Zeitrichtung. Kein einziger
Wert und keine einzige Torzeit steht im FTP, die die Ablesung nicht auch hat.

**Umgekehrt schon:** Die Ablesung erfindet. In `pferde.json` steht ein Pferd
**Nr. 28 „Blackjack"** samt Torzeiten, das es im Panel nicht gibt (Dublette von
Nr. 25); dazu Torzeiten wie Duque 04:00 und Leonhard 01:21, die nirgends
existieren. Sie bleiben stehen, weil Selektionszeiten nur ergänzt, nie entfernt
werden.

**Was damit wegfällt:** Ein-Sitzungs-Sperre am Panel und der Pause-Knopf, die
von selbst wechselnde Sortierung, der verschluckte Scroll, der Seiten-Vorrat,
die Modellkosten (~2 €/Monat → 0), die Lesefehler — und der Unterschied
zwischen `alles` und `ohne_min`: Mineral ist in jedem Auszug aktuell.

**Umgestellt am 18.08.2026, Add-on 0.20.0.** Der Bildschirmweg ist **ganz
ausgebaut**, nicht abgeschaltet: Auf Wunsch („nur den Datenexport, das ist das
einzige verlässliche") sind `wasserbauer.py`, `ablesen.py`, `modell.py`,
`selektion.py`, `ziffern.py` und `vorlagen.json` entfernt, dazu in der
Oberfläche die Auslesungs-Karte und die Aufwand-/Token-Rechnung, im Zeitplan
die Umfänge (`alles`/`ohne_min`/`schnell` → nur noch `alles`) und die
Kostenschätzung. Gerettet wurden aus `ablesen.py` nur `zahl()` und `EINHEIT` —
sie stehen jetzt in `einheiten.py`.

Damit fallen auch **alle Fremdbibliotheken bis auf eine** weg: `requests`,
`Pillow`, `anthropic` und `google-genai` sind aus `requirements.txt` raus, übrig
ist `websocket-client`. Der Auszug wird mit `ftplib` aus der Standardbibliothek
geholt. Aus den Optionen sind Gateway-Zugang und Modellschlüssel verschwunden.

**Falls es zurück muss:** `addon-sicherung-0.19.1-mit-ki/` ist der vollständige,
laufende Stand mit beiden Wegen — dort gab es die Option `datenquelle`
(`export`/`ki`) und einen Schattenlauf. Zurückholen heißt: Ordner kopieren,
Version hochsetzen, ausrollen. Die Zugangsdaten zum Wasserbauer-Gateway stehen
in Abschnitt 6, die Modellschlüssel müssten neu hinterlegt werden.

### Was seit 0.20.0 noch dazukam (alles am 18.08.2026)

**Kein Zeitplan mehr (0.21.0).** Statt fester Abrufzeiten sieht das Add-on alle
fünf Minuten nach, ob der Rechner eine **neue Datei** geschrieben hat, und
arbeitet nur dann (`bot._scheduler`, `hoco.neuester_name`). Damit sind Umfänge,
Läufe und der Pause-Knopf verschwunden; `zeitplan.py` ist auf zwei Zeit-Helfer
für die Morgenmeldung zusammengeschrumpft. Die Seite „Fütterungspläne" heißt
jetzt „Einstellungen".

**Halbe Dateien werden abgewiesen (0.24.1).** Der Auszug 15:29 kam mit 198 KB
statt 1,5 MB — mitten im Schreiben gelesen. Das Ergebnis sah gültig aus
(28 Pferde), hatte aber **null** Torzeiten, weil das Besuchsprotokoll am
Dateiende steht. Geprüft wird jetzt über die Blockklammern: der Rechner
schreibt 27× `Begin Event` und 27× `End Event`; stimmt das nicht überein, wird
der vorige Auszug genommen. Eine Prüfung nur auf „sind die Blöcke da" hätte bei
90 % der Datei durchgelassen.

**Besuchsprotokoll (0.22.0).** Je Pferd steht jetzt jeder Stationsbesuch des
Tages in `pferde.json`: Uhrzeit, Station, Dauer und Menge — auch die Besuche
**ohne Ausgabe** (Tamira war am 18.08. fünfzehnmal an einer Station und bekam
viermal etwas). `801706` ist die **Aufenthaltsdauer in Sekunden**; nachgewiesen
daran, dass bei 1503 Sätzen der nächste Besuch derselben Station auf die
Sekunde am Ende des vorigen beginnt.

**Die Easy Station gibt kein Heu.** Sie bucht zwar eine Komponente 10
(„Raufutter_1"), aber immer mit `ist = 1`, unabhängig von der Verweildauer —
eine Marke, keine Fressminute. Im Panel sind dort nur KF1 (33 g) und Min1
(15 g) eingerichtet. Als Heu-Station gilt deshalb nur, wer **ausschließlich**
Komponente 10 ausgibt (`hoco._heu_stationen`).

**… und der Rechner schreibt trotzdem eine Minute gut — je Futterportion.**
Aufgeklärt am 18.08.2026 nachts, nachdem ein Abzugsversuch (0.33.0) nach fünf
Minuten wieder zurückgenommen werden musste: **die Minuten sind echt und
sollen stehenbleiben.** Temperino hat 8, Leonhard 6, Tamira 4 — so steht es im
Panel, so gilt es im Stall.

Woher sie kommen, ist jetzt belegt. Die Easy Station bucht **genau eine
Raufutter-Minute pro Futterausgabe**, und nur für Tiere, die überhaupt einen
Raufutter-Anspruch haben. Über alle 14 Tage des Auszugs (1483 Ausgaben):

* **keine einzige** Heu-Minute ohne Futterausgabe im selben Besuch,
* **keine einzige** für eines der 13 Tiere ohne RF-Anspruch — obwohl die
  zusammen 729 Portionen dort geholt haben (Farina 140, Duque 111, Pepsi 108),
* bei Tieren *mit* Anspruch praktisch eins zu eins: Wira 107 Marken auf
  108 Ausgaben, Fiora 67/67, Boca 36/36, Temperino 126/130.

Es ist also **keine Messung, sondern ein Pauschalsatz**. Am Heuschieber folgt
`ist` der Verweildauer (rund 0,9 Minuten je Minute Aufenthalt, gedeckelt durch
„Max RF pro Mahlzeit“) und nimmt jeden Wert von 1 bis über 40 an; an der Easy
Station steht bei 731 Buchungen **immer exakt 1**, obwohl die Tiere dort
gleichmäßig 137–190 Sekunden stehen und das Kraftfutter im selben Satz
**genau** gemessen wird (soll 200 g, ist 198 g).

Der Auslöser steht in der Stationskonfiguration (Block 100032):

| | RF_ENABLE | HB_SLIDER_TYPE |
|---|---|---|
| Heuschieber | `00000011` (3) | 1 |
| Easy St. 11 | `00000100` (4) | **0** |
| Raufe, Komp.Sel. | `00000001` (1) | 1 / 0 |

Die Easy Station hat **kein Heuschieber-Gerät** (`HB_SLIDER_TYPE = 0`) und
steht bei `RF_ENABLE` auf einem **anderen Bit** als der Heuschieber — Bit 2
statt Bit 0+1. Raufutter ist dort also eingeschaltet, aber ohne Messtechnik
dahinter; deshalb bucht die Station je Fressvorgang die kleinste Einheit, eine
Minute, während sie das Kraftfutter im selben Satz auf zwei Gramm genau
abrechnet.

> **Vierte Falle mit den zwei Nummernkreisen, und die teuerste an diesem
> Abend:** `803201` in Block 100032 ist **ebenfalls die Port-Nummer**, nicht die
> Stations-Kennung — genau wie `801704`. Wer sie als Kennung liest, bekommt die
> Konfiguration der jeweils übernächsten Station. Mir passiert: Ich hielt die
> Werte von *Raufe 12* für die der Easy Station und schrieb, beide Stationen
> seien gleich konfiguriert. Aufgefallen ist es nur, weil der Betriebsinhaber
> die vier `RF_ENABLE`-Werte aus dem Panel vorgelesen hat und keiner passte.
> **Merksatz: wo eine Zahl eine Station meinen könnte, ist es hier meistens der
> Port.**

**Entschieden am 18.08.2026 nachts:** Die Minute **zählt still mit** — die
Tagessumme bleibt die des Panels, ohne Abzug und ohne Sternchen. In der
Besuchsliste erscheinen weiterhin nur die Besuche an der **echten** Heustation.
Karte und Liste gehen beim Raufutter deshalb bewusst nicht auf; das ist der
Preis dafür, dass in der Liste kein Heu an einer Station steht, die keins hat.
Kraftfutter und Mineral gehen auf.

**Umstellversuch am 18.08.2026 abends — gescheitert und zurückgesetzt.** Der
Betrieb hat gegen 21:20 `RF_ENABLE` an der Easy St. 11 von `00000100` auf
`00000001` gesetzt. **Es hat nicht gewirkt:** Wira (RF-Anspruch 120) holte um
21:43:33 Kraftfutter an der Station und bekam weiterhin `K10 = 1`. Noch am
selben Abend zurückgesetzt — **aktueller Stand ist wieder `00000100`.**

Mein Fehler in der Empfehlung: Ich hatte auf das Selektionstor gezeigt
(`00000001`, keine Raufutter-Buchungen) und daraus geschlossen, Bit 0 heiße
„aus“. Übersehen habe ich, dass die **Raufen 3–14 ebenfalls `00000001` haben
und sehr wohl buchen** (43 Min, auf die Gruppe). Bit 0 ist also eher
„Raufutter grundsätzlich aktiv“; am Selektionstor kommt nichts an, weil dort
kein Raufutter eingerichtet ist — nicht wegen des Bits. Die Korrelation trug
die Empfehlung nicht.

**Nicht weiter am Bit raten.** Offen und eine Frage an Wasserbauer: Welcher
Wert schaltet die Buchung an einer Station ohne Heuschieber
(`HB_SLIDER_TYPE = 0`) ab? Und ist `HB_STATE = 1` nach dem Speichern normal —
Port 11 stand danach als einzige Station auf 1, während Heuschieber und
Selektionstor auf 6 und die Raufen auf 2/3 stehen. Solange das offen ist,
zählt der Rechner wie bisher, und das Add-on zeigt seine Zahlen unverändert.
**Nichts am Panel verstellen**, ohne dass es der Betrieb ausdrücklich will.

**Entschieden am 18.08.2026 nachts:** Die Minute **zählt still mit** — die
Tagessumme bleibt die des Panels, ohne Abzug und ohne Sternchen. In der
Besuchsliste erscheinen weiterhin nur die Besuche an der **echten** Heustation.
Karte und Liste gehen beim Raufutter deshalb bewusst nicht auf; das ist der
Preis dafür, dass in der Liste kein Heu an einer Station steht, die keins hat.
Kraftfutter und Mineral gehen auf.

**Am 18.08.2026 gegen 21:20 hat der Betrieb es umgestellt:** `RF_ENABLE` an
der Easy St. 11 von `00000100` auf `00000001` — den Wert des Selektionstors,
der einzigen anderen Station ohne Heuschieber, die genau deshalb keine
Raufutter-Zeile bucht.

**Folge ab dem 6-Uhr-Reset am 19.08.2026:** 10 der 28 Pferde verlieren ihre
Pauschalminuten. Stand 19:59 wären das gewesen: Auryn −21, Temperino −8,
Leonhard −6, Wira −7, Boca −4, Dutsty −4, Fiora −3, Tamira −2, Hidalgo −2,
Blackjack −2. **Temperino und Leonhard stehen dann bei 0 Minuten** und damit
rot auf ihrer Einstellerseite — richtig so, beide waren nachweislich nicht am
Heuschieber, aber es wird Nachfragen geben.

> **Wer später niedrigere Raufutter-Zahlen sieht als im Panel-Verlauf davor:
> das ist kein Datenfehler, sondern diese Umstellung.** Nicht im Add-on
> „korrigieren“. Die heute schon gebuchten Marken verschwinden nicht
> rückwirkend — der erste saubere Tag ist der 19.08.2026.

Wofür Bit 2 genau steht, ist weiterhin nicht dokumentiert; die Zuordnung stammt
aus der Korrelation (einzige Station mit diesem Bit, einzige mit
Pauschalbuchung). Sonst gilt weiter: **nichts am Panel verstellen**, ohne dass
es der Betrieb ausdrücklich will.

**Besuchsliste und Summen laufen jetzt über denselben Ausschnitt (0.33.0).**
Die Liste lief über den Kalendertag, die Zahlen über den Fütterungszyklus —
bei **21 von 28** Tieren standen deshalb Besuche des Vortags-Zyklus in der
Liste (Temperino 3,300 kg in der Liste gegen 2,310 kg auf der Karte, Tamira
34 Min gegen 4). `hoco._zyklusfenster` gibt den Ausschnitt jetzt einmal vor.
Die **Torzeiten bleiben beim Kalendertag**: die Selektionsliste des Panels
läuft so, und das Zeitband auf der Pferdeseite ist von 0 bis 24 Uhr
beschriftet.

**Der Verlauf war um einen Tag verschoben (0.33.0).** `verlauf/2026-08-18.json`
ist der Zyklus, der an dem Morgen **endete** — also im Wesentlichen der 17.
August. Beschriftet war die Zeile mit dem Enddatum, und damit standen auf
derselben Pferdeseite unter „18.08." zwei verschiedene Zahlen: im Verlauf
9 Min / 3,960 kg, im Reiter „Heute" 8 Min / 2,31 kg. Jetzt trägt die Zeile das
**Anfangsdatum** des Zyklus.

**„In den letzten 12 Stunden" stimmte nie (0.33.0).** Block 100019 führt einen
Zeitstempel (`801905`), der nicht gelesen wurde. Die fünf Meldungen vom
18.08. waren alle vom **17.08. 14:30** — der Rechner schreibt sie einmal und
lässt sie stehen, bis das Tier wieder erkannt wird. Der Wortlaut bleibt der
des Panels (dort steht er auch heute noch genauso), dazu kommt jetzt
`hinweis_seit`: im Ingress „(gemeldet …)", auf der Pferdeseite „Der
Fütterungsrechner meldet seit …".

**Auryn wird gegen den ganzen Tag gemessen — zu Recht.** Sein Feld
`Intervalldauer` (800147) steht auf **1 Minute** statt 60 wie bei allen
anderen; dadurch gibt der Rechner die komplette Tagesration sofort frei, und
`geholt + offen` ergibt konstant den vollen Tagesanspruch. Die Panel-Aufnahme
vom 18.08. bestätigt es: Anspruch gesamt 0,790 kg **und** Anspruch bisherig
0,790 kg. Kein Fehler im Add-on, eine Einstellung am Panel. Das abweichende
Feld `801413 = 1,790` ist damit ebenfalls erledigt — das Panel zeigt 0,790,
also ist `900061` das richtige Feld.

**Das Wunsch-Formular wies fünf Einsteller ab (Plugin 0.15.0).** Das
Kraftfutter-Feld stand auf `max="3" step="0.05"`, wurde aber mit dem Ist-Wert
vorbelegt: 0,790 kg (Wira, Auryn, Dutsty, Hidalgo) ergab „0.79", kein
Vielfaches von 0,05; Temperino mit 3,990 kg lag zusätzlich über dem Maximum.
Der Browser verweigerte das Abschicken, ohne zu sagen warum. Jetzt
`max="5" step="0.01"`.

**`/abruf` mischte zwei Bezugsgrößen (0.33.0).** „Raufutter: 8 Min / 90 Min
(24 %)" — vorne der Tag, in der Klammer der Anteil am *bis jetzt Fälligen*.
Schon das eingebaute Beispiel war in sich falsch (93 von 360, ausgewiesen als
67 %). Jetzt: „… von … – bis jetzt fällig … (… %)", mit stimmigen Beispielen.

### Zugangslinks und geteilte Pferde (0.35.0)

Zwei Befunde des Betriebsinhabers vom 18.08.2026 abends, beide echt:

**Der Link überlebte jede Löschung.** `_keys_speichern()` hat bis dahin nur
**ergänzt**, nie entfernt — ein gelöschter Zugang stand weiter in
`schluessel.json`, wurde beim nächsten Start wieder geladen und beim nächsten
Push wieder an die Website geschickt. Ein ausgezogenes Pferd hatte also
dauerhaft eine erreichbare Seite, die jeder mit dem alten QR-Aufkleber aufrufen
konnte. Jetzt gibt es `bot.zugang_entfernen(nr)`; die Reihenfolge ist wichtig:
erst dort löschen, dann `keys_pushen()` — `/keys` **ersetzt** auf der Website
die ganze Tabelle, ein Push ohne den Schlüssel nimmt ihn dort mit weg.

Ausgelöst wird das an zwei Stellen:

* **Pferd entfernen** (Monitor) → Zugang immer weg.
* **Einsteller abmelden** → Zugang nur weg, wenn danach **niemand mehr** auf
  dem Pferd steht.

Der Grund für diese Unterscheidung ist der zweite Befund.

**Der Schlüssel hängt am Pferd, nicht an der Person.** Zwei Einsteller eines
Pferds benutzen **denselben** Link (Tamira hat zwei). Würde das Abmelden des
einen den Schlüssel löschen, spränge dem anderen still der Zugang weg. Nur
stand nirgends, dass ein Pferd geteilt ist — man meldete jemanden ab und hielt
dessen Zugang für entzogen, obwohl der gemeinsame Link weiterlief. Sichtbar
gemacht an drei Stellen:

* neue Spalte **Einsteller** im Monitor, mit `2 Personen · ein gemeinsamer Link`,
* Plakette `auch: …` in der Einsteller-Tabelle an jedem geteilten Pferd,
* die Meldung nach dem Abmelden nennt ausdrücklich, welche Links abgeschaltet
  wurden und welche **gültig bleiben, auch für den gerade Abgemeldeten** —
  mit dem Hinweis auf „Neuen Code erzeugen“, wenn wirklich entzogen werden soll.

Trocken geprüft an vier Fällen: erste von zwei Personen abmelden (Link bleibt),
zweite abmelden (Link stirbt), Pferd ohne Einsteller entfernen (Link stirbt),
nicht vorhandenen Zugang löschen (sauberes `False`). Danach stimmen
`schluessel.json` und `bot.keys` in allen Fällen überein.

### Mitarbeiter-Seite (Add-on 0.39.0, Plugin 0.19.0)

Eine eigene Seite für den Stallmitarbeiter, gewünscht am 19.08.2026. Zwei
Karten, beide zum Abarbeiten am Fütterungsrechner:

* **Änderungswünsche** — was eingetragen werden soll, mit dem Wert, der jetzt
  am Rechner steht („120 Min → 180 Min“), Begründung und Datum.
* **Koppelzeiten** — in drei Gruppen: Pferde mit **echtem** Zeitfenster zuerst
  (das ist die Arbeitsliste, am 19.08. sechs Stück), darunter „rund um die Uhr“
  und „kein Fenster eingeschaltet“ als bloße Namensliste.

Ein Fenster gilt als ganztägig, wenn sein Beginn **eine Minute nach seinem
Ende** liegt — beobachtet an `10:01 bis 10:00` und `00:01 bis 00:00`. Ohne
diese Unterscheidung stünden 22 Zeilen da, von denen 16 nichts bedeuten.

**Ausdrücklich nur zum Lesen**, so entschieden. Eingetragen wird am Panel; dass
es eingetragen ist, meldet der Soll-Ist-Vergleich von selbst (`wunsch.py`) —
ein Knopf zum Abhaken wäre ein Knopf zum Behaupten.

**Der Zugang fährt im vorhandenen Schlüsselbund mit.** Statt eines zweiten
Mechanismus trägt der Mitarbeiter-Schlüssel im Push `/keys` den Wert
`mitarbeiter` statt einer Pferdenummer; die Website verzweigt darauf. Damit
gilt für ihn ohne Zusatzaufwand alles, was für die Pferdeschlüssel gilt:
erneuern, entfernen, pushen. Er steht in `schluessel.json` neben `pferde` und
wird beim ersten Start **sofort festgeschrieben** — sonst erzäugte jeder
Neustart einen anderen und der Link auf dem Handy wäre jedes Mal tot.

Zu finden im Ingress unter „Einsteller verwalten“, mit Knopf zum Erneuern.

### Das Handy hat drei Anläufe gebraucht (19.08.2026)

Am Handy sahen die Ingress-Tabellen zerbröselt aus — senkrecht ein Buchstabe
je Zeile. Der Weg zur Lösung ist lehrreich genug, um ihn festzuhalten:

1. **`overflow-wrap:anywhere`** stand seit jeher auf allen Tabellenzellen. Auf
   dem Desktop harmlos, auf 390 Pixeln wird daraus „A b m e l d e n“. Ersetzt
   durch `break-word`; Knöpfe, Plaketten und Namen bekamen `nowrap`, nur die
   zehnstelligen Zufallscodes dürfen mitten im Wort brechen.
2. **Mindestbreite mit seitlichem Schieben** — funktionierte, war aber nicht
   gewollt („kein links rechts scrollen“). Wieder raus.
3. **Karten.** Unter 820 Pixeln wird jede Tabellenzeile ein Block: Kopfzeile
   weg, jede Zelle eine Zeile mit ihrer Spaltenüberschrift davor
   (`data-label`, 275 Stück über fünf Tabellen). Nichts schiebt, nichts wird
   abgeschnitten, nichts bricht buchstabenweise.

Auf der Pferdeseite dasselbe Muster bei den **Besuchen**: vier Angaben
nebeneinander passten nicht, und ausgerechnet die Station wurde per
`text-overflow:ellipsis` gekürzt („Easy St. …“). Jetzt zweizeilig — oben wann
und wo, darunter was es gab.

**Die Besuchsliste läuft seit 0.37.0 über die letzten 24 Stunden**, nicht mehr
über den Zyklus: um halb neun morgens war sie sonst fast leer. Sie zählt sich
damit bewusst **nicht** mehr zu den Zahlen im Reiter „Heute“ zusammen — der
gehört zum Zyklus ab 6 Uhr. Ein Datum steht nicht dabei; die Liste ist nach
Zeit sortiert und läuft höchstens einen Tag zurück.

> **Die Verlaufstabelle blieb bei den Fütterungstagen 6→6 Uhr.** Sie war am
> 19.08. kurz auf rollende 24-Stunden-Fenster umgestellt und wurde auf Wunsch
> zurückgebaut. Wer es noch einmal versuchen will: die älteren Fenster lassen
> sich nur aus dem Besuchsprotokoll rechnen, und das weicht für den vorletzten
> Zyklus bei 7 von 28 Tieren von den Zählern des Rechners ab.

### Die Feldbelegung überwacht sich jetzt selbst (0.34.0)

`addon/app/pruefung.py`, läuft bei **jedem** Abruf. Anlass ist der Abend des
18.08.2026: drei der vier Fallen dieses Projekts waren Zuordnungsfehler, die
**keine Fehlermeldung** erzeugt haben — falsches Mineral-Feld, `801704` als
Station gelesen, `803201` als Station gelesen. Nichts davon ist dokumentiert,
und niemand sagt uns Bescheid, wenn eine Firmware etwas verschiebt.

Vier Ebenen, von grob nach fein:

1. **Formatgedächtnis** (`/data/exportformat.json`). Beim ersten Lauf werden
   die Kopfzeilen aller 27 Blöcke gemerkt. Danach fällt jeder neue Block, jedes
   weggefallene Feld und jede Umsortierung auf — ohne Annahme darüber, *was*
   sich ändern könnte.
2. **Kreuzprobe.** Der Rechner führt seine Zahlen doppelt: als Tagessumme je
   Tier (100034/100014/100016) und als Protokoll jedes Besuchs mit Menge
   (100017/100037). Beide müssen dasselbe ergeben — am 18.08. über fünf
   Auszüge hinweg **28/28 Tiere in allen drei Futterarten, Abweichung null**.
3. **Schlüssel im Klartext.** 100032 nennt seine Parameter selbst
   (`RF_ENABLE`, `HF_PORT_WEIGHT_CON_2`), die Sortenblöcke ihre Namen
   (`Kraftfutter_1`, `Mineral_1`, `Raufutter_1`).
4. **Größenordnung.** Fängt ein Feld, das auf ein anderes verrutscht ist, in
   dem zufällig auch Zahlen stehen.

Nachgewiesen an vier nachgestellten Änderungen — jede wird erkannt:

| Änderung | gefunden von |
|---|---|
| Feldnummer umbenannt | Formatgedächtnis |
| Block fällt weg | Formatgedächtnis |
| Komponenten-Nummer verschoben | Klartext + unbekannte Komponente |
| Selektionstor heißt anders | Stationsprüfung |
| **gleiches Feld, andere Bedeutung** | **Kreuzprobe** |
| Datumsformat geändert | Kreuzprobe |

Die vorletzte Zeile ist der Grund für den ganzen Aufwand: Ebene 1 kann sie
nicht sehen, und genau dieser Fall hat hier schon zweimal zugeschlagen.

Gemeldet wird **laut und nur im Befund**: rotes Feld ganz oben im Ingress, ein
Zusatz in der Statuszeile und Einzelheiten im Protokoll. Solange alles stimmt,
steht nirgends etwas — eine tägliche Bestätigung liest nach einer Woche
niemand mehr.

Eine Bemerkung zum Vertrauen in solche Prüfungen: Beim allerersten Lauf hat sie
**einen Fehler in sich selbst** gefunden — in der Feldkarte stand für die
Mineralsorten `801303` statt `801503`. Das ist kein Schönheitsfehler, sondern
der Beleg, dass sie tatsächlich nachsieht statt zu nicken.

**Wer die Feldkarte erweitert**, trägt das neue Feld in `pruefung.FELDKARTE`
ein — dann ist es mitüberwacht. Das ist die einzige Pflege, die dieses Modul
braucht.

**Kostenlos (0.20.0 folgende).** Abo, Zahlungsprüfung in `/abruf`,
Erinnerungen, `paypal_me` und `abo_jahrespreis` sind ausgebaut. Grund: Der
Flyer begründete den Beitrag mit „deckt die laufenden Kosten … per KI
ausgelesen" — beide Hälften stimmten nach dem Umstieg nicht mehr.
**Offen: die vier, die bereits bezahlt haben.**

**Änderungswünsche (0.25.0, Plugin 0.10.0–0.14.0).** Einsteller schlagen auf
dem Reiter „Mein Pferd" Werte vor (RF, KF, Mineral, Koppelzeit,
Transpondernummer) — strukturierte Felder, keine Freitexte. Der Wunsch liegt
auf der Website; das Add-on vergleicht ihn bei jedem Takt mit dem Auszug.
**Bestätigen kann man im Add-on nicht** — das wäre ein Knopf zum Behaupten;
„eingetragen" meldet ausschließlich der Soll-Ist-Vergleich. Ablehnen mit
Begründung geht. Der Einsteller kann zurücknehmen, solange offen; hat das
Hofbüro es da schon eingetragen, **warnt** das Add-on (`wunsch.warntext`).

**Falle:** Die Website hängt hinter einer Firewall, die Anfragen ohne
Browser-Kennung mit `error code: 1010` als **403** abweist — für jede Adresse,
auch nicht vorhandene. Ein 403 heißt dort **nicht** „Schlüssel falsch".

**Aufgeräumt am 18.08.2026 abends:** Alles, was zum Bildschirmweg gehörte,
liegt in `skripte/alt-bildschirmweg/` (zwölf Skripte plus 23 Vorlagenbilder) —
es läuft nicht mehr, weil die Module dazu ausgebaut sind. Der lauffähige
Gesamtstand mit beiden Wegen bleibt in `addon-sicherung-0.19.1-mit-ki/`.

**Eine Falle beim Ausrollen**, die einen Ausfall gekostet hat: `run.sh` mit
Windows-Zeilenenden zu speichern lässt den Container mit
`exec: fatal: unable to exec bashio` sterben — das CR klebt am Shebang. Vor
jedem Kopieren auf LF prüfen. Das Protokoll des Add-ons ist übrigens **doch**
über REST lesbar (`/api/hassio/addons/<slug>/logs`), anders als in
`ha-zugang.md` vermerkt.

---

## 3. Getroffene Entscheidungen

- **Modell:** zuerst Haiku 4.5 (`claude-haiku-4-5`), ausgewählt nach
  Vergleich/Konstanz-Tests (`skripte/modellvergleich.py`, `skripte/konstanz.py`).
  **Seit 16.08. im Betrieb Gemini** (`gemini-flash-lite-latest`): beide lasen alle
  Testaufnahmen fehlerfrei, Gemini ist rund **achtmal günstiger** (0,023 gegen
  0,180 ct je Aufnahme). Umschaltbar in einer Option (`modell_anbieter`), Claude
  bleibt vollständig eingebaut.
- **Abruf-Takt: überholt.** Geplant war **1× pro Tag**; tatsächlich läuft der
  Takt-Lauf **alle 39 Minuten** von 06:15 bis 21:00, dazu einer um 05:30 — rund
  **24 Läufe am Tag**. Möglich wurde das durch den Preissturz beim Auslesen; die
  ursprüngliche Begründung („bei 1×/Tag sind die Kosten vernachlässigbar") gilt
  in der Sache weiter, nur die Zahl stimmt nicht mehr. Aktueller Aufwand:
  ~0,25 ct je Lauf, also grob **2 € im Monat**.
- **Bezug der Zahlen:** laufender **Fütterungszyklus**, nicht Kalendertag.
- **Zugangsschlüssel ist dauerhaft** und hängt an der **Panel-Nummer**, nicht am
  Namen: Pferd umbenennen → Aufkleber bleibt gültig. Steht an einer Nummer plötzlich
  ein anderes Pferd → neuer Schlüssel (alter Aufkleber ungültig).
- **Filtern/Rechnen im Code, nicht im Prompt** — das Modell liest nur ab, die Logik
  (Rückstand, Dubletten) macht Python. (Lehre aus den Tests.)
- **Gemessen am 16.08.** (9 echte Aufnahmen, `gesamtlauf.py --vergleich`):
  alt **0,427 ct/Aufnahme**, schlank **0,137 ct** → **68 % weniger**. Der Löwenanteil
  liegt in der Ausgabe (4484 Token weniger, zählt fünffach), nicht im Bild
  (3679 Token weniger bei Zuschnitt + kürzerem Schema).
  Hochrechnung bei 30 Aufnahmen/Tag: 3,84 → 1,23 $/Monat. Die real beobachteten
  6–7 €/Monat liegen darüber — es sind also mehr als 30 Aufnahmen/Tag
  (`SEL_MAX = 40` im Add-on lässt die Selektionsseite weit hochlaufen).
- **Aussetzer beim Ablesen** (16.08.): Bei etwa jeder fünften Anfrage kam auf eine
  volle Seite eine **leere Liste** zurück — nicht unterscheidbar von „ans Listenende
  gescrollt". Zwei Gegenmittel, beide gemessen: Beispiel im Prompt an die Einheit
  angepasst (RF ganze Minuten statt Kommazahlen) + ausdrücklicher Satz, wann eine
  leere Liste richtig ist → **0 von 10** Aussetzern bei gleicher Ausgabegröße.
  Zusätzlich fragt `sammler.py` bei leerer Antwort **einmal nach**.
- **Kompakte Ausgabe + zugeschnittene Bilder** (`skripte/ablesen.py`, 16.08.):
  Das Modell gibt je Zeile einen `|`-getrennten String mit reinen Zahlen zurück
  statt eines JSON-Objekts mit deutschen Schlüsselnamen; Einheiten, Namen und
  Rückstand ergänzt der Code. Bilder werden auf den Tabellenbereich beschnitten
  (Bild-Tokens = Breite·Höhe/750, spart ~34 %). Grund: die **Ausgabe** war mit
  ~78 % der teuerste Posten, nicht das Bild — sie kostet das Fünffache der
  Eingabe. Prompt-Caching hilft hier **nicht**: Haiku 4.5 cached erst ab 4096
  Token Präfix, unser Vorspann liegt bei ~450.
- **Prompts ein zweites Mal gekürzt** (17.08., Add-on 0.17.0): alle vier
  Anweisungen um rund ein Drittel kürzer (5500 → 3700 Eingabe-Token je
  Voll-Lauf), **ohne eine Vorgabe wegzulassen**. Gestrichen wurde nur
  Selbstverständliches (der Rechner nennt sich im Bild selbst) und Doppeltes;
  der Nachkomma-Hinweis steht jetzt nur noch beim einzigen Reiter mit
  Nachkommastellen (KF). Die beiden gemessenen Gegenmittel gegen leere
  Antworten (Beispiel in der Einheit des Reiters, Satz zur leeren Liste)
  **bleiben** — nur straffer formuliert.
- **Selektionsliste hört früh auf** (17.08., Add-on 0.17.1): Die Liste
  `Aktivitäten > Selektionsb. > Heute` steht **absteigend nach Erkennungszeit**
  (an den Aufnahmen nachgesehen: Seite 1 begann 11:33, Seite 15 endete 00:01) —
  es muss also nicht mehr sortiert oder ganz durchgescrollt werden. Der Lauf
  blättert nur noch bis zur Grenze zurück und hört dann auf; eine Seite
  Überlappung bleibt, damit ein Eintrag auf der Grenzminute nicht durchfällt.
  Dafür wird die Selektionsseite **sofort beim Abfahren** ausgelesen statt erst
  nach dem Tunnel — anders ließe sich nicht entscheiden, wann Schluss ist.
  Wirkung: ein ganzer Tag kostete 15 Aufnahmen, nach einem Lauf drei Stunden
  zuvor sind es 4–5. Das ist der größere Hebel als die Prompts, weil die
  Selektion über die Hälfte aller Aufnahmen stellte (`SEL_MAX = 40`).
  Nach Mitternacht oder ohne Lesestand läuft weiterhin der volle Durchgang.
- **Die Abbruchgrenze ist die Uhr, nicht das Gelesene** (17.08., aus dem ersten
  Praxislauf gelernt): In `pferde.json` standen um 12:20 Uhr Erkennungszeiten
  **16:46 und 18:48** — genau die Uhrzeiten aus dem Beispiel im Selektions-Prompt,
  vom Modell an echte Pferde gehängt (Corazon, Dutsty, Szilaj). Falsch waren sie
  schon vorher; als **Grenze** genommen hieß das „alles gelesen", und der
  Durchgang hörte nach **einer** Seite auf. Seitdem merkt sich der Lauf in
  `selektion_gelesen_bis` die **Uhrzeit des letzten fertigen Selektionslaufs**
  (minus 5 Min Karenz) — die stammt nicht aus dem Bild und kann nicht verlesen
  werden. Zusätzlich werden Erkennungszeiten **aus der Zukunft verworfen** (eine
  Erkennung kann nie später sein als jetzt), auch die schon gespeicherten.
  Lehre, wieder einmal: was das Modell liefert, darf keine Steuergröße sein.
- **Eine halb gelesene Seite darf nicht abbrechen** (17.08., Add-on 0.17.2, aus
  dem Trockentest `skripte/test_selektion_grenze.py`): Fehlen dem Modell auf
  einer Seite die obersten Zeilen, sieht die Seite **älter** aus als sie ist –
  ihre „neueste Zeit" liegt vor der Grenze und der Durchgang hört genau dort auf.
  Im Test (Fall 7) gingen so **sieben Erkennungen** still verloren. Beenden darf
  jetzt nur eine Seite mit mindestens `SEL_ZEILEN_VOLL = 7` Zeilen (voll sind 9
  im 800×600-Panel); eine ehrlich kurze Seite kostet dadurch eine Aufnahme mehr.
  Fall 8 zeigt zugleich, warum das kein Datenverlust ist: die Grenze ist die
  **Uhr**, also liest der nächste Lauf dieselbe Seite noch einmal und sammelt das
  Verpasste ein. Merksatz: die Zukunftszeit verlängert nur, die halbe Seite
  verkürzt – gefährlich ist allein das Verkürzen.
- **Endstand gemessen** (17.08. 16:56, Add-on 0.17.7): `ohne_min`-Lauf mit
  **9 Aufnahmen, 4 Seiten aus dem Vorrat, 0,176 ct** — gegen **22 Aufnahmen und
  0,45 ct** am Vormittag. Das sind **61 % weniger**, bei gleichzeitig
  *vollständigeren* Daten (28 von 28 Pferden mit RF und Mineral). Der Lauf davor
  (16:37) lag bei 12 Aufnahmen / 0,246 ct.
  **Vorsicht beim Vergleichen einzelner Läufe:** Ein billiger Lauf kann ein
  *unvollständiger* sein. Belegt an drei Beispielen dieses Tages: 12:23 mit 0,37 ct
  war der Fehlabbruch durch eine Zukunftszeit, 13:25 mit 0,227 ct hatte den halben
  Stall nicht gelesen (verschluckter Scroll), und die 16–19-Seiten-Läufe zwischen
  13:25 und 16:18 waren teuer, weil eine Sperre falsch zählte. Nur ein Lauf, der
  **alle 28 Pferde** liefert, ist überhaupt vergleichbar.
- **Der verschluckte Scroll ist Alltag, nicht Ausnahme** (17.08.): Das Protokoll
  meldete „der Reiter wäre hier zu früh abgebrochen" **dreimal in 40 Minuten**
  (16:15, 16:35 zweimal). Vor 0.17.5 hieß das jedes Mal: ein Teil des Stalls ohne
  frische Zahlen.
- **Token-Zählung zurücksetzen** (17.08., Add-on 0.17.3): In „Fütterungspläne →
  Aufwand dieses Plans" gibt es jetzt einen Knopf **„Zählung zurücksetzen"**.
  Nötig, weil der Monatspreis der Schnitt der letzten 20 Läufe ist — nach einer
  Sparmaßnahme rechnen die alten, teuren Läufe tagelang mit. Zurückgesetzt wird
  nur `verbrauch.json` (Marke `seit`); das **Archiv bleibt** erhalten.
  `_verbrauch_buchen` schreibt seitdem die ganze Datei zurück statt nur `laeufe`,
  sonst wischt der nächste Lauf die Marke weg.
- **Bei RF/KF/Mineral trägt der Trick nicht — der Gedanke dahinter schon**
  (17.08., Add-on 0.17.4, gemessen mit `skripte/analyse_seiten_unveraendert.py`):
  Diese drei Reiter stehen nach **Pferdenummer**, nicht nach Zeit — es gibt kein
  „ab hier nur noch Altes". Übertragbar ist nur *nicht lesen, was man schon
  weiß*, und das in zwei Formen, die beide eingebaut sind:
  1. **Vorrat gelesener Seiten** (`_ocr_tabelle_gemerkt`): Schlüssel ist der
     Bild-Hash des Tabellenbereichs (ohne Uhr und Scrollbalken) samt Reiter.
     Identische Pixel heißen identische Zahlen — ein Fehlgriff ist ausgeschlossen.
     Gehasht wird die **ganze** Tabelle. Das war die entscheidende Entscheidung:
     schneidet man die Spalten „Anspruch/Fortschritt bisherig" weg, springt die
     Trefferquote von **37 % auf 48 %** — aber genau diese Spalten wandern mit
     der **Uhr**, und `rueckstand.py` urteilt über sie. Wer sie wegschneidet,
     spart elf Prozentpunkte und übersieht Rückstände. Gemessen am Archiv
     (13 Vergleiche im echten 39-Min-Takt): **38 % der RF- und 35 % der
     KF-Seiten** sind unverändert = 4,4 von 12 Aufnahmen. Der Vorrat lebt im
     Arbeitsspeicher — nach einem Neustart kostet der erste Lauf wieder alles
     (Pythons `hash()` ist je Prozess anders gesalzen, gespeichert wäre er
     wertlos).
  2. **Mineralfutter nur 1× am Tag:** 6 der 21 Aufnahmen (29 %) für Zahlen, die
     `rueckstand.py` ausdrücklich **nicht bewertet**. Neuer Umfang **`ohne_min`**
     („Alles ohne Mineralfutter"). Wichtig war der richtige Schnitt: **nicht**
     „nur Rau- und Kraftfutter" — die **Selektion** muss oft gelesen werden,
     sonst steht die Torliste der Einsteller den halben Tag still; nur das
     Mineralfutter darf selten kommen. Ein `ohne_min`-Lauf lässt die zuletzt
     gelesenen Mineral-Zahlen stehen (überschrieben wird nur, was der Lauf
     wirklich geholt hat).
- **Die Sortierung der Selektionsliste ist keine Voraussetzung, sondern eine
  Annahme** (17.08. nachmittags, Add-on 0.17.6 — der schwerwiegendste Fund):
  Um 15:56 stand die Liste `Aktivitäten > Selektionsb. > Heute` nach
  **Pferdenummer** (Sortierpfeil auf „Nr."): Delana 13:12, 09:44, 07:31, 05:59,
  dann Tamira 11:36 … Die neueste Erkennung des Tages (Lina 15:46) lag auf
  Seite 3. Vormittags stand dieselbe Liste noch nach „Erkannt in Selektionstor".
  **Die Sortierspalte lässt sich am Panel umstellen, und niemand sagt es uns.**
  Ein Abbruch nach Seite 1 hätte den Pferden 3–29 die Torzeiten genommen — ohne
  Fehlermeldung. Seitdem wird die Sortierung **an den Seiten nachgewiesen**: keine
  Erkennung einer Seite darf neuer sein als die älteste der Seite davor (gleich ist
  erlaubt, die Seiten überlappen). Trifft das nicht zu, wird die ganze Liste
  gelesen. Innerhalb **einer** Seite lässt sich nichts prüfen, weil das Auslesen
  die Zeiten je Tier bündelt und die Bildschirm-Reihenfolge verloren geht — darum
  kann frühestens auf der **zweiten** Seite Schluss sein. Diese eine Aufnahme mehr
  ist der Preis dafür, die Voraussetzung zu prüfen statt sie zu glauben.
- **Das Add-on richtet die Sortierung selbst ein** (17.08., Add-on 0.17.7, so
  gewünscht): Steht die Liste nachweislich nicht rückwärts, klickt der Lauf **am
  Ende** auf den Spaltenkopf „Erkannt in Selektionstor" (`SEL_ZEIT_SPALTE`,
  630/204). Das ist die **einzige** Stelle, an der der Abruf am Panel etwas
  verstellt — eine Anzeige-Einstellung, keinen Wert; wer danach am Panel steht,
  sieht die Liste nach Zeit sortiert.
  Drei Feinheiten, die alle drei nötig sind:
  1. **Nur im Fehlerfall klicken.** Ein Klick schaltet um — bei jedem Lauf blind
     zu klicken würde zwischen auf- und absteigend pendeln und jeden zweiten Lauf
     verderben, statt die Sortierung einzurichten.
  2. **Erst am Ende klicken.** Da ist alles gelesen, der Klick kann diesem Lauf
     nichts mehr verderben.
  3. **Aufsteigend und „gar nicht nach Zeit" unterscheiden.** Es gibt beides.
     Ist die Liste nach Zeit sortiert, nur vorwärts (`"auf"`), dreht ein Klick auf
     dieselbe Spalte die Richtung — der nächste Lauf sitzt richtig. Ist sie nach
     etwas anderem sortiert (`"keine"`), sortiert der Klick nach Zeit, aber die
     Richtung ist offen; die prüft der nächste Lauf und klickt notfalls noch
     einmal. **Nach höchstens zwei Läufen stimmt es**, danach bleibt es stehen.
  Erkannt wird die Richtung an den Seitenpaaren: absteigend heißt „keine
  Erkennung neuer als die älteste der Vorseite", aufsteigend das Spiegelbild,
  und überlappt beides, ist es keine Zeitsortierung.
- **Die Sortierung wechselt von selbst** (Beobachtung 17.08.): Sie stand
  vormittags nach Zeit, um 15:56 nach **Nummer**, und um 16:36 wieder nach Zeit —
  **ohne dass das Add-on geklickt hätte** (die Klick-Funktion kam erst danach mit
  0.17.7). Wer oder was sie umstellt, ist offen: jemand am Panel, oder der Rechner
  selbst. Deshalb wird sie bei **jedem** Lauf neu nachgewiesen und nicht ein für
  alle Mal eingerichtet. Wer hier später „das haben wir doch geklärt" denkt, irrt.
- **Zeilen sind Tiere, nicht Erkennungen** (17.08., Add-on 0.17.6): Die Sperre aus
  0.17.2 („nur eine volle Seite darf abbrechen") zählte **Zeilen**.
  `selektion_aufbereiten` gibt aber eine Zeile je **Tier** mit einer Liste von
  Zeiten zurück — im Betrieb 1–3 Zeilen je Seite, nie die verlangten sieben. Die
  Sperre griff also **immer**, jeder Lauf las die ganze Liste, und die Ersparnis
  vom Vormittag war still wieder weg (13:25 bis 15:58: vier Läufe mit 16–17
  Selektionsseiten). Gezählt werden jetzt die **Erkennungen**. Der Trockentest
  hatte den Fehler nicht gefunden, weil er dieselbe falsche Annahme nachbaute —
  eine Zeile je Erkennung. **Lehre: ein Test, der die Annahme des Codes teilt,
  prüft nichts.** Beide Fälle stehen jetzt drin (Fall 9 und 10).
  Glücksfall im Unglück: Weil die Sperre den Abbruch verhinderte, hat der
  Zählfehler den viel schlimmeren Sortierfehler oben **verdeckt** — hätte ich nur
  die Sperre „reparieren" und ausrollen lassen, wären ab dem nächsten Lauf
  Torzeiten verschwunden.
- **Ein verschluckter Scroll hat den halben Stall gekostet** (17.08., Add-on
  0.17.5 — der wichtigste Fund des Tages): Im Lauf um 13:25 waren `rf_2.png` und
  `rf_3.png` **dasselbe Bild** (Nr. 7–15, eine Sekunde auseinander). Der Scroll
  hatte nicht gewirkt; zwei gleiche Tabellen sahen für `_reiter_abfahren` wie das
  **Listenende** aus, der Reiter brach nach Nr. 15 ab und die **Pferde 16–29
  bekamen keine frischen RF-Zahlen** — ohne Fehlermeldung, mit gültig aussehenden
  (weil alten) Werten in `pferde.json`. Der Fehler ist **alt**, nicht neu: die
  Abbruchbedingung stand von Anfang an so da. Aufgefallen ist er nur, weil der
  neue Seiten-Vorrat `vorrat=2` meldete und ich nachsah, welche Seiten das waren.
  Seitdem wird **in zwei Stufen nachgefasst**: erst noch einmal hinsehen (hatte
  das Panel nur langsam gezeichnet), erst dann noch einmal scrollen (der Klick
  war verloren). Sofort ein zweites Mal zu scrollen wäre falsch — hat der erste
  Scroll doch gewirkt, wäre die Liste zwei Schritte weiter und eine Zeile fällt
  durch. Erst wenn auch danach nichts Neues kommt, ist es das Listenende.
  Lehre: **eine stille Abkürzung ist gefährlicher als eine laute Störung.**
- **Zeitplan seit 17.08. 13:20:** „Tagsüber (Takt)" alle 39 Min von 06:15 bis
  21:00 mit **`ohne_min`** (16 statt 22 Aufnahmen) + „Voll vor dem Reset"
  täglich **05:30** mit `alles` (holt Mineral und schreibt die Tageshistorie vor
  dem 6-Uhr-Reset). Vorher war es ein einziger Takt-Lauf „alles" 05:45–21:00.
- **Trockentest statt Panel-Lauf** (17.08.): Die Abbruchlogik wird von
  `skripte/test_selektion_grenze.py` ohne Gateway, Modell und Kosten geprüft
  (Panel-Abfahren und Auslesen sind ersetzt). Die Seitendichte darin ist echt,
  abgelesen am Lauf vom 17.08. 12:29: Seite 1 lief von 12:19 bis 11:27, also
  ~10 Zeilen und ~5 Minuten Abstand je Seite. Der Test bestätigt auch die
  Hochrechnung von oben: bei einer Grenze drei Stunden zuvor sind es
  **5 von 17 Seiten**.
- **Namen nur im Voll-Abruf** — sie hängen an der Panel-Nummer und werden nach
  `daten/pferde_namen.json` fortgeschrieben; die Teil-Abrufe (12/18 Uhr) lesen
  nur Nummern. Ändert sich ein Name an einer Nummer, meldet der Sammler das
  (Aufkleber-Regel, siehe oben).

---

## 4. Datenstand

- **28 Pferde** im Panel erfasst (Nr. 1–27 + 29). Namensliste steht in
  `skripte/schluessel.py` / `skripte/zuordnung2.py`.
- **Einsteller-Zuordnung** (`daten/zuordnung.json`): zugeordnet und **erledigt**.
  Die drei Treffer mit abweichender Schreibweise — Nr. 10 *Tiffy* ← „Tiffany",
  Nr. 12 *Sisi* ← „Sissi", Nr. 5 *Fini* ← „Finesse" — sind am 18.08.2026 vom
  Betrieb bestätigt worden und stehen im Betrieb aktiv — die Einsteller sind
  vom Hofbüro einzeln bestätigt. Nicht noch einmal aufrollen.
  - **Echte offene Fälle:** „Dora" hat **kein** passendes Panel-Pferd;
    Panel-Pferde **Nr. 2 Tamira, 7 Wira, 21 Dutsty** haben **keinen** Einsteller in
    der Liste (evtl. Schul-/eigene Pferde — klären).
- **Zugangsschlüssel** für alle Pferde erzeugt, im Betrieb unter
  `/share/fuetterungsabruf/schluessel.json` (lokale Kopie `daten/schluessel.json`),
  Aufkleberblatt fertig (`ausgabe/aufkleber.html`). Das Add-on pusht sie beim
  Start an die Website.
- **`pferde.json` wird laufend erzeugt** — vom Add-on, rund 24× am Tag nach
  `/share/fuetterungsabruf/pferde.json`; Stand 17.08. 16:56 mit 28 von 28 Pferden.
  Zusätzlich Archiv (`archiv/JJJJ-MM.csv`, jeder Lauf) und Tageshistorie
  (`verlauf/<datum>.json`, der letzte Lauf vor 6 Uhr).

---

## 5. Auslieferung — entschieden und gebaut

Die Frage „wie kommen die Zahlen zum Einsteller" ist beantwortet: **beide** Wege
laufen, und zwar aus derselben `pferde.json`.

**A — WhatsApp-Bot** (`addon/app/bot.py`, eigene Bot-Rufnummer)

Befehle: `/anmelden` (auch `start`, `register`) → Bot fragt nach dem Pferd, Name
wird unscharf erkannt → **Freigabe durchs Hofbüro** per aktionierbarer
iPhone-Benachrichtigung (Bestätigen/Ablehnen). Danach `/abruf` (auch `futter`,
`fuetterung`) → die Zahlen als Nachricht. Dazu `/hilfe` und `/abmelden`. Eine
Nummer kann mehrere Pferde haben. Weil die Bot-Nummer auch privat genutzt wird,
antwortet er **nur** auf echte Befehle und schweigt sonst. Alle 21 Texte sind im
Ingress änderbar (`texte.py`), Zuordnung dauerhaft in `/data/zuordnung.json`.
Die AppDaemon-Testapp von 14.08. ist abgeschaltet (`apps.yaml`).

**B — Pferdeseite auf der Website des Betriebs** (`hoco-pferdeseiten.php`)

WordPress-Plugin, damit ist Weg A („bestehende Website") und Weg B („eigene
Seite") dasselbe geworden — keine Subdomain nötig. Aufruf über den persönlichen
Zufalls-Link `https://perwein-hofgut.de/fuetterung/?k=<schlüssel>` (QR-Aufkleber
an der Box). Das Add-on pusht nach **jedem** Lauf die Daten nach
`/wp-json/fuetterung/v1/push` und beim Start die Schlüssel nach `/keys`, beides
mit gemeinsamem Geheimnis. Die Seite zeigt Tagesbericht, Torzeiten als Zeitband
und den Verlauf der letzten 14 Tage.

**Knopf „Aktualisieren" und eigenes Symbol** (Plugin 0.7.0):
Die Seite läuft im **Vollbild** (vom Startbildschirm geöffnet) — dort gibt es
keine Adresszeile und keinen Neu-laden-Knopf des Browsers. Der Knopf lädt die
Seite neu, nichts weiter; er löst **keinen** Abruf am Fütterungsrechner aus
(die Zahlen schickt das Add-on von sich aus ~24× am Tag). Er ist ein echter
`<a>` auf dieselbe Adresse, damit er auch ohne JavaScript funktioniert; daneben
steht, wie alt die Zahlen sind — damit man sieht, ob Neuladen überhaupt etwas
bringt. Dazu ein Hufeisen-Symbol: SVG-Datenadresse für den Browser-Reiter, und
weil Apple auf dem Startbildschirm kein SVG nimmt, liefert die Seite unter
`&symbol=1` ein 180×180-PNG (mit GD gezeichnet). Auf dem Startbildschirm steht
der **Name des Pferds**.

> **Kurz gebaut und wieder entfernt** (0.18.0 → 0.18.1): Zuerst hatte ich den
> Knopf so verstanden, dass er einen echten Abruf am Panel auslösen soll — mit
> Anfrage-Endpunkt, Nachfragen aus dem Add-on und drei Bremsen. Gewollt war das
> nicht. Falls es doch je gebraucht wird, ist der Weg der: Die Website kann das
> Add-on **nicht anrufen** (es sitzt hinter dem Router), also muss das Add-on
> nachfragen; und dann braucht es Bremsen, weil am Panel nur eine Sitzung möglich
> ist. Der Code dafür steht in der Versionsgeschichte, nicht mehr im Projekt.

**Abo (Stufe 1):** `/abruf` prüft, ob der Zugang bezahlt ist; sonst kommt der
Ablauftext mit PayPal-Zahlhinweis (`paypal_me`, `abo_jahrespreis`).
Erinnerungen laufen einmal täglich ab 9 Uhr.

**Begleitmaterial:** `flyer/` (Aushang), `ausgabe/aufkleber.html` (A4-QR-Blatt
für die Boxen), `einsteller-update.html`, `ausgabe/tamira.html` (das Vorbild).

---

## 5b. Nachtrag zur Kanalwahl (Entscheidung vom 14.08.)

Gewählt wurde **WhatsApp** über `FaserF/ha-whatsapp` (Baileys) — bewusst gegen
die Empfehlung Telegram, weil die Einsteller WhatsApp schon haben. Das ist der
einzige bekannte Wackelstein des Projekts und der Grund für zwei Vorkehrungen:

- Die Anbindung ist **inoffiziell** (WhatsApp-Web) → AGB-Verstoß und **Sperrgefahr
  für die Nummer**. Deshalb eine **separate** Nummer, nicht die
  Hofbüro-WhatsApp: eine Sperre träfe nur den Bot.
- Anti-Ban-Muster: eingespielte Nummer, Einsteller sollen sie als Kontakt
  speichern, Sendeverzögerung, **kein Massenversand**. `/abruf` ist reaktiv und
  verursacht wenig Verkehr — das günstigste Muster.
- **Falls die Nummer doch gesperrt wird:** Die Pferdeseite auf der Website (5B)
  trägt den Dienst allein weiter; sie hängt nicht am Bot. Umstieg auf Telegram
  wäre möglich (`schluessel.py` erzeugt schon Telegram-Codes), die offizielle
  WhatsApp Business Cloud API wäre der saubere, aber aufwändige Weg.

Infrastruktur (14.08. geprüft): Gateway-Add-on `605cee21_whatsapp` läuft
(Port 8066), Integration `whatsapp` verbunden. Eingang über HA-Event
`whatsapp_message_received`, Ausgang über Dienst `whatsapp.send_message`.

Nicht mehr verfolgt: eigene Subdomain `stall.perwein-hofgut.de` (unnötig, seit
das Plugin auf der Hauptseite läuft) und `perwein-admin/` als eigener Weg.

---

## 6. Zugang & Sicherheitsregeln

- **Gateway:** <https://secure.wasserbauer.eu/webconnect/> (Apache Guacamole).
  Login: `thomas.kuerzeder@t-online.de`. Eine VNC-Verbindung hinterlegt →
  Panel `10.81.0.97` (HOCO-Fütterungsrechner, HIT-Aktivstall).
  Zugangsdaten sind auch in den Skripten hinterlegt (`skripte/guac_nav2.py`).
- **Nur eine VNC-Sitzung gleichzeitig.** Wenn jemand das Panel im Browser offen hat
  und der Abruf verbindet, kickt einer den anderen. Wer selbst am Panel arbeiten
  will, drückt im Add-on unter „Fütterungspläne → Pause" auf 15/30/60/120 Minuten —
  dann fallen die Läufe in dieser Zeit aus (sie werden **nicht** nachgeholt), und
  auch der Aktualisieren-Knopf der Website löst nichts aus.
- **Es ist ein LIVE-Fütterungsrechner.** Der Abruf **navigiert und liest** —
  keine Werte ändern, keine Bestätigungsdialoge, am Ende auf der Statusseite
  stehen lassen.
  **Eine Ausnahme, seit 17.08. ausdrücklich gewünscht:** Steht die Selektionsliste
  nicht nach Zeit sortiert, klickt der Lauf am Ende auf den Spaltenkopf „Erkannt in
  Selektionstor" (`SEL_ZEIT_SPALTE` in `wasserbauer.py`). Das ist eine
  **Anzeige-Einstellung, kein Fütterungswert** — aber es ist sichtbar: wer danach
  am Panel steht, findet die Liste anders sortiert als vorher. Soll das nicht sein,
  genügt es, diesen einen Klick zu entfernen; der Abruf bleibt dann korrekt, liest
  die Selektionsliste aber jedes Mal ganz.
- **Direkter IP-Zugriff auf 10.81.0.97 geht nicht** — liegt im Wasserbauer-VPN-Netz,
  nur über das Gateway erreichbar.

---

## 7. Dateien im Projekt

**Maßgeblich ist `addon/`** — das läuft. `skripte/` war die Werkstatt.

```
wasserbauer/
├─ STAND.md                  ← diese Datei (Einstieg)
├─ WHATSAPP-BOT.md           Änderungsprotokoll des Add-ons (0.5.1 … 0.7.1)
├─ addon/                    ← DAS PRODUKTIVE ADD-ON (HA, Version 0.18.0)
│   ├─ config.yaml           Optionen, Version (Version hoch = Supervisor baut neu)
│   ├─ Dockerfile / build.yaml / run.sh / requirements.txt
│   └─ app/
│       ├─ bot.py            WhatsApp-Bot, Zeitplan-Faden, Website-Push,
│       │                    Abfrage des „Jetzt aktualisieren"-Knopfs, Abo
│       ├─ wasserbauer.py    Panel abfahren + auslesen → pferde.json
│       │                    (Selektions-Abbruch, Sortierungsnachweis,
│       │                     Seiten-Vorrat, Nachfassen bei gleicher Seite)
│       ├─ ablesen.py        Bildzuschnitt, kompakte Anweisungen, Prüfungen
│       ├─ modell.py         Gemini/Anthropic umschaltbar
│       ├─ rueckstand.py     Urteil je Pferd (Mineral wird NICHT bewertet)
│       ├─ selektion.py      Torzeiten zusammenführen
│       ├─ web.py            Ingress-Oberfläche „HOCO-Abruf" (6 Ansichten)
│       ├─ einrichtung.py   Ersteinrichtung: Optionen schreiben, Verbindungen prüfen
│       ├─ stil.py           CSS + eingebettete SVG-Symbole
│       ├─ zeitplan.py       Läufe, Umfänge (alles / ohne_min / schnell), Kosten
│       ├─ texte.py          21 WhatsApp-Texte, im UI änderbar
│       ├─ meldung.py        Morgenmeldung ans Hofbüro
│       ├─ ueberwachung.py   Ausnahmen (Weide, kein Transponder, verkauft)
│       ├─ archiv.py         jede Zeile jedes Laufs → archiv/JJJJ-MM.csv
│       ├─ pruefung.py       prueft bei jedem Abruf die Feldbelegung
│       └─ ziffern.py        Zahlen/Einheiten
├─ hoco-pferdeseiten.php   WordPress-Plugin 0.20.0
├─ hoco-pferdeseiten.zip   dasselbe zum Hochladen in WP
├─ addon-sicherung-0.5.1/ / -0.6.1/ / -0.8.0/   Rückfallkopien
├─ flyer/                    Aushang für den Stall (html + gen_pdf.py)
├─ einsteller-update.html    Rundschreiben an die Einsteller
├─ panel-navigation.md       Klickwege im Panel
├─ skripte/                  was noch gebraucht wird (5 Skripte)
│   ├─ verlauf_neu.py        Tageshistorie aus dem Auszug neu erzeugen
│   ├─ schluessel.py         Zugaenge + QR-Aufkleberblatt
│   ├─ zuordnung.py / zuordnung2.py   Panel-Pferd <-> Einsteller
│   └─ alt-bildschirmweg/    alles zum Panel-Weg, laeuft nicht mehr
├─ (frueher hier: ~19 Skripte der Bildschirm-Werkstatt)
│   ├─ guac_nav2.py          Panel verbinden + Seiten als PNG (Produktiv-Version)
│   ├─ guac_shot.py          einfacher Einzel-Screenshot (read-only)
│   ├─ ablesen.py            Bildzuschnitt, kompakte Prompts/Schemata, Prüfungen
│   ├─ sammler.py            Screenshots → ein Datensatz je Pferd (pferde.json)
│   │                        `--umfang voll` (mit Namen) / `teil` (mischt ein)
│   ├─ gesamtlauf.py         Voll-Auslesung + Kosten (`--vergleich` alt/neu)
│   ├─ zuordnung2.py         Panel-Pferd ↔ Einsteller matchen
│   ├─ schluessel.py         dauerhafte Zugänge + QR-Aufkleberblatt
│   ├─ test_selektion_grenze.py   Trockentest der Selektions-Abbruchlogik
│   │                        (ohne Gateway/Modell/Kosten, 13 Fälle)
│   ├─ test_seiten_vorrat.py  Vorrat + Nachfassen bei gleicher Seite (9 Fälle)
│   ├─ analyse_seiten_unveraendert.py  wie oft sich RF/KF-Seiten zwischen
│   │                        zwei Läufen überhaupt ändern (aus dem Archiv)
│   ├─ modellvergleich.py / konstanz.py   Modellauswahl (→ Haiku 4.5)
│   └─ … (tamira_test, enum_test, endmessung, recall_test, zuordnung.py, …)
├─ panel-seiten/             37 Screenshots der Panel-Seiten
│   ├─ rfa_*.png  Raufutter „abgeholt"       kfb_*.png  Kraftfutter „abgeholt"
│   ├─ sel_*/selt_*.png  Selektionstor        pv_*.png   Pferde-Stammdaten
│   └─ e_*/a_*/…          Übersichten/Hinweise
├─ daten/
│   ├─ einsteller.csv       Einstellerliste (PERSONENDATEN — nur lokal!)
│   ├─ zuordnung.json       Ergebnis Pferd↔Einsteller
│   ├─ schluessel.json      dauerhafte Zugangsschlüssel je Pferd
│   ├─ pferde.json          Tages-Datensatz aus sammler.py
│   ├─ pferde_namen.json    Nr → Name, vom Voll-Abruf fortgeschrieben
│   └─ tamira.json          Beispiel-Datensatz (eine Pferdeseite)
├─ ausgabe/
│   ├─ tamira.html          Vorbild-Einstellerseite (= das Artifact)
│   └─ aufkleber.html       A4-QR-Aufkleber für die Boxen
└─ logs/                    Lauf-Protokolle der Erfassung
```

**Wo die Betriebsdaten liegen** (nicht im Projektordner, sondern am Home
Assistant, erreichbar über Samba `\\192.168.188.60\share\fuetterungsabruf\`):

```
pferde.json        aktueller Stand aller Pferde (jeder Lauf schreibt neu)
verbrauch.json     Token/Kosten je Lauf + Marke 'seit' (Zählung zurücksetzen)
schluessel.json    Zugangsschlüssel je Pferd
seiten/            die Aufnahmen des letzten Laufs (rf_*, kf_*, min_*, sel_*, hinweis_*)
verlauf/<datum>.json   Tagesabschluss (vom letzten Lauf vor 6 Uhr)
archiv/JJJJ-MM.csv     jede Zeile jedes Laufs, 17 Spalten
```

Die dauerhafte Zuordnung Nummer↔Pferd liegt **privat** in `/data/zuordnung.json`
(nicht auf `/share`), ebenso `zeitplan.json` und `texte.json`.

---

## 8. Offen — Stand 17.08.2026 abends

**Muss von Hand gemacht werden (nur du kannst das):**

1. **Plugin 0.7.0 in WordPress hochladen** (`hoco-pferdeseiten.zip`,
   Plugins → Installieren → Hochladen, überschreibt 0.6.0). Bringt den
   Aktualisieren-Knopf und das Symbol. Am Add-on ist dafür **nichts** zu tun.
   Wer die Seite schon auf dem Startbildschirm hat, muss sie **einmal neu
   ablegen** — das alte Symbol bleibt sonst stehen.
2. Die vier echten offenen Fälle klären: „Dora" hat kein
   Panel-Pferd; Tamira, Wira und Dutsty haben keinen Einsteller in der Liste.
   *(Die drei Schreibweisen-Treffer sind am 18.08.2026 bestätigt — erledigt.)*

**Zu beobachten, kein Handlungsbedarf:**

0. **Am 18.08.2026 abends geprüft und für richtig befunden** (nicht wieder
   aufrollen): Auryns `Intervalldauer` von 1 Minute ist so gewollt, und die
   Meldungen „nichts geholt“ bei Lina und Tiffy sind in Ordnung.

3. **Vorrat-Trefferquote**: steht ab morgen echt in `verbrauch.json` (Feld
   `vorrat` je Lauf, Zählung läuft seit 17.08. 12:53). Meine Schätzung war 38 % der
   RF- und 35 % der KF-Seiten — nachrechnen mit
   `skripte/analyse_seiten_unveraendert.py`.
4. **Sortierung der Selektionsliste**: wechselt von selbst (Abschnitt 3). Das
   Add-on stellt sie nach höchstens zwei Läufen wieder richtig. Im Protokoll
   sichtbar als „Sortierung 'auf'/'keine' — Spalte angeklickt".
5. **Mineralfutter** kommt jetzt nur noch um 05:30. Falls das für die
   Einstellerseiten zu selten ist: ein zweiter `alles`-Lauf am Nachmittag kostet
   6 Aufnahmen.

**Ideen, bewusst nicht gebaut:**

6. **Panel-Filter „Zeige Pferde: bis 100 % abgeholt"** (oben rechts im RF-Reiter).
   Stünde er auf 50 %, fiele RF/KF von 12 auf 2–3 Aufnahmen — der größte
   verbleibende Hebel. Verstellt aber, was am Panel angezeigt wird, und zwar
   dauerhaft und für jeden sichtbar. Nur auf ausdrücklichen Wunsch.
7. **Weniger Läufe.** 23 am Tag für Zahlen, die sich langsam bewegen. Der
   billigste Hebel überhaupt — aber eine Entscheidung über den Dienst, nicht über
   die Technik.

---

## 9. Umbenennung und Ersteinrichtung (19.08.2026)

Anlass war die Veröffentlichung auf GitHub: was ein anderer Stall installieren
soll, darf nicht nach diesem Hof heißen und nicht voraussetzen, dass jemand die
Werte kennt.

**Neuer Name.** Das Add-on heißt **HOCO-Abruf**, das Plugin
**HOCO-Pferdeseiten**. *Wasserbauer* steht nur noch in den Beschreibungen, als
Angabe, mit welchem Gerät das Ganze zusammenarbeitet — nicht im Produktnamen;
es ist der Name des Herstellers.

Umbenannt wurde nur, was man sieht. Die technischen Kennungen bleiben, damit
die laufende Installation nichts merkt:

| bleibt | warum |
| --- | --- |
| Add-on-Slug `fuetterungsabruf` | ein neuer Slug hieße für Home Assistant: neues Add-on mit leerem `/data` — Zuordnungen, Pläne und Vorlagen wären weg |
| `/share/fuetterungsabruf/` | dort liegen `pferde.json`, Verlauf und Archiv |
| Optionen `fuetterung_daten`, `_keys`, `_wuensche` in WordPress | die Daten der bestehenden Website hängen daran |
| Kurzcodes `[fuetterung]`, `[fuetterung_key]` | stehen in veröffentlichten Seiten |

Geändert **mit** Rückwärtsgang: Der REST-Namensraum heißt jetzt `hoco/v1`, der
alte `fuetterung/v1` wird weiterhin bedient. Die Funktionen im Plugin heißen
jetzt `hoco_*` (29 Stück, mechanisch umbenannt). Die Plugin-Datei heißt
`hoco-pferdeseiten.php` — **das alte Plugin muss vor dem Hochladen deaktiviert
werden**, sonst kollidieren die Funktionsnamen.

Betriebseigenes ist aus den Vorgaben heraus: Stallname ist jetzt eine Option
(`stall_name`, in den WhatsApp-Texten als `{stall}`), die Website-Adressen und
die PayPal-Kennung sind leer.

**Ersteinrichtung.** Beide Teile führen jetzt durch die Einrichtung, statt sie
vorauszusetzen.

Im Add-on eine eigene Ansicht (`app/einrichtung.py` + Ansicht in `web.py`). Sie
geht von selbst auf, solange ein Pflichtwert fehlt. Der Kniff: Sie schreibt die
Add-on-Optionen selbst über die Supervisor-API (`POST /addons/self/options`,
dafür `hassio_api: true`) — es gibt also keinen zweiten Satz Einstellungen
neben dem Add-on-UI. Vier Prüfungen, jede einzeln auslösbar und mit den Werten,
die gerade im Formular stehen: FTP-Verbindung (listet die Dateien),
Testmeldung ans Hofbüro, WhatsApp-Dienst vorhanden, Website erreichbar samt
Geheimnis. Schlägt der Schreibzugriff fehl, bleibt die Ansicht als Prüfwerkzeug
brauchbar und sagt, wo man die Werte von Hand einträgt.

Im Plugin eine Seite unter **Einstellungen → HOCO-Pferdeseiten**: Geheimnis
erzeugen, Stallname setzen, `/fuetterung/` anlegen, und die drei Werte fürs
Add-on zum Kopieren. Dazu ein Statusblock (zuletzt empfangen, Anzahl Pferde,
Schlüssel, offene Wünsche) — ohne den sieht eine falsch eingerichtete Seite
genauso aus wie eine, an die noch nichts geschickt wurde.

**Das Geheimnis** steht nicht mehr im Quelltext. Reihenfolge: Konstante
`HOCO_SECRET` in der `wp-config.php`, dann `FUETTERUNG_SECRET` (alter Name),
dann die Option aus der Ersteinrichtung. Ohne Geheimnis nimmt die Website
nichts an — eine frisch installierte Seite steht damit nie offen.

**Nachgewiesen, nicht angenommen:** Die Oberfläche wurde einmal komplett
gerendert (Ersatz-Bot, ohne Home Assistant) — 13 Prüfpunkte, alle grün. Für das
Plugin gibt es keinen PHP-Interpreter auf dem Rechner; stattdessen eine eigene
Prüfung (Klammerbalance über einen kleinen Lexer, jeder `hoco_`-Aufruf hat eine
Definition, Datenbankschlüssel und Kurzcodes unverändert, Nonce und
Rechteprüfung vorhanden) — 17 Punkte, alle grün. Das ersetzt kein `php -l`.

---

## 10. Einstellungen ins Add-on verlagert (21.08.2026)

Bis 0.40.x standen sie in der Add-on-Konfiguration von Home Assistant und kamen
als Umgebungsvariablen an (`run.sh`). Zwei Folgen, beide lästig: zwei
Oberflächen für dieselbe Sache, und jede Änderung brauchte einen Neustart —
Umgebungsvariablen ändern sich zur Laufzeit nicht.

Seit **0.41.1** führt das Add-on sie selbst in `/data/konfig.json`
(`app/konfig.py`). Gelesen wird bei jedem Zugriff, nicht beim Start: Deshalb
gibt es keine Modulkonstanten mehr, und die vier FTP-Werte stehen nicht mehr in
den Vorgabe-Parametern von `hoco.py` — die werden beim Import einmal gebunden,
eine später geänderte Adresse wäre nie angekommen.

In Home Assistant ist die Konfiguration jetzt **leer** (`options`/`schema` aus
`config.yaml` entfernt, `hassio_api` ebenfalls — die Ersteinrichtung braucht den
Supervisor nicht mehr).

**Der Umstieg lief in zwei Schritten**, weil Home Assistant gespeicherte Werte
verwirft, sobald sie nicht mehr im Schema stehen:

1. **0.41.0** — `konfig.py` eingeführt, beim Start Übernahme aus den
   Umgebungsvariablen. `config.yaml` und `run.sh` blieben unverändert, damit
   dabei überhaupt etwas zu übernehmen war. Im Protokoll nachgewiesen:
   *„Einstellungen aus den Add-on-Optionen übernommen (9 Werte)"*.
2. **0.41.1** — `options`/`schema` entfernt, `run.sh` ohne `bashio::config`.
   Danach die verwaisten Werte in `options.json` geleert (der Supervisor räumt
   sie nicht selbst weg; das Geheimnis stand dort im Klartext) und zur Probe neu
   gestartet: läuft, Werte halten.

Nebenbei aufgefallen: `hofbuero_notify` hatte `notify.mobile_app_iphone` als
Vorgabe — einen Dienst, den es nur auf dieser Anlage gibt. Damit hätte die
Prüfung auf fehlende Pflichtwerte bei einem fremden Betrieb geschwiegen. Vorgabe
entfernt; die Rückfallebene sitzt jetzt beim Aufrufer.

`paypal_me` und `abo_jahrespreis` sind ganz entfallen — der Dienst ist seit dem
18.08.2026 kostenlos, gelesen hat die Werte längst keine Zeile mehr.
