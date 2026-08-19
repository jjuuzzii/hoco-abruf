# HOCO-Abruf

Fütterungsdaten vom Wasserbauer-HOCO-Rechner zu den Einstellern — automatisch,
ohne Nachfragen im Hofbüro.

Ein Home-Assistant-Add-on holt alle paar Minuten den CSV-Vollauszug vom
Fütterungsrechner (per FTP), rechnet je Pferd Raufutter (Minuten) und
Kraftfutter (kg) aus und stellt die Zahlen auf zwei Wegen bereit:

* **WhatsApp-Bot** — der Einsteller schreibt `/abruf` und bekommt die Zahlen
  seines Pferds als Nachricht. `/anmelden` koppelt Rufnummer und Pferd, die
  Freigabe erteilt das Hofbüro per Benachrichtigung aufs Telefon.
* **Pferdeseite auf der Website** — das WordPress-Plugin *HOCO-Pferdeseiten*
  nimmt die Zahlen entgegen und zeigt sie unter einem persönlichen Link je
  Pferd.

Entstanden im Betrieb eines Aktivstalls. Betriebseigene Werte stehen
alle in der Konfiguration, nicht im Quelltext — andere Ställe mit einem
HOCO-Fütterungsrechner können es übernehmen.

> *HOCO* und *Wasserbauer* sind Bezeichnungen des Herstellers der
> Fütterungstechnik. Dieses Projekt stammt nicht von ihm und steht in keiner
> Verbindung zu ihm; die Namen stehen hier nur dafür, mit welchem Gerät es
> zusammenarbeitet.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| [addon/](addon/) | das Home-Assistant-Add-on „HOCO-Abruf" — im Betrieb maßgeblich |
| [hoco-pferdeseiten.php](hoco-pferdeseiten.php) | das WordPress-Plugin „HOCO-Pferdeseiten" |
| [dokumentation/](dokumentation/) | Anleitungen für Ställe und Einsteller (HTML — die PDFs entstehen daraus) |
| [STAND.md](STAND.md) | ausführlicher Projektstand: Entscheidungen, Messwerte, offene Punkte |

`STAND.md` ist der eigentliche Einstieg, wenn es um das *Warum* geht — dort
steht auch, welche Wege verworfen wurden und warum.

## Einrichten

Beide Teile bringen einen Assistenten mit; von Hand in Konfigurationsdateien
schreiben muss man nichts.

### 1. Add-on installieren

**Voraussetzungen:** Home Assistant mit Supervisor, ein erreichbarer
HOCO-Fütterungsrechner mit FTP-Auszug und — für den Bot — die Integration
[`FaserF/ha-whatsapp`](https://github.com/FaserF/ha-whatsapp) mit einer eigenen,
nur dafür genutzten Rufnummer.

1. In Home Assistant: **Einstellungen → Add-ons → Add-on-Store → ⋮ →
   Repositories** und die Adresse dieses Repositorys eintragen.
2. „HOCO-Abruf" installieren und starten.
3. Das Panel in der Seitenleiste öffnen. Solange etwas fehlt, steht die
   **Ersteinrichtung** ganz oben.

### 2. Plugin installieren

1. Unter [Releases](https://github.com/jjuuzzii/hoco-abruf/releases) die Datei
   `hoco-pferdeseiten.zip` herunterladen und in WordPress unter **Plugins →
   Installieren → Plugin hochladen** einspielen. (Ohne Release: die Datei
   `hoco-pferdeseiten.php` in einen gleichnamigen Ordner legen und den als ZIP
   packen.)
2. **Einstellungen → HOCO-Pferdeseiten** öffnen. Dort auf *Geheimnis erzeugen*
   drücken, den Namen des Betriebs eintragen und bei Bedarf die Seite
   `/fuetterung/` anlegen lassen.
3. Die Seite zeigt drei Werte zum Kopieren: Schnittstelle, Link-Basis und
   Geheimnis.

Spätere Fassungen meldet das Plugin selbst — siehe unten.

### 3. Beides verbinden

Die drei Werte aus Schritt 2 in der Ersteinrichtung des Add-ons eintragen,
speichern, neu starten. Jeder Schritt hat dort einen Prüfknopf: FTP-Verbindung,
Testmeldung ins Hofbüro, WhatsApp-Dienst und Website werden einzeln geprüft und
sagen im Fehlerfall, woran es liegt.

Das Add-on schreibt seine Einstellungen dabei selbst in die Add-on-Konfiguration
(über die Supervisor-API). Es gibt also keinen zweiten Satz Einstellungen, der
auseinanderlaufen könnte.

## Aktualisieren

**Add-on:** Home Assistant prüft das Repository von sich aus und zeigt das
Update im Add-on-Store an.

**Plugin:** WordPress sucht Updates normalerweise nur auf wordpress.org. Dieses
Plugin fragt deshalb selbst bei GitHub nach: Liegt dort eine Veröffentlichung
mit höherer Versionsnummer, erscheint sie unter **Dashboard → Aktualisierungen**
und lässt sich mit einem Klick einspielen — wie jedes andere Plugin. Der Stand
wird zwölf Stunden zwischengespeichert; auf der Einrichtungsseite gibt es einen
Knopf, der sofort nachsieht.

Damit das trägt, muss jede Veröffentlichung ein ZIP mit dem Ordner
`hoco-pferdeseiten/` mitbringen. Das erledigt
[.github/workflows/plugin-release.yml](.github/workflows/plugin-release.yml)
automatisch, sobald ein Tag der Form `v0.20.0` gepusht wird — die Nummer im Tag
muss dabei zu der im Dateikopf passen, sonst bricht der Lauf ab.

```bash
git tag v0.20.0 && git push origin v0.20.0
```

## Das gemeinsame Geheimnis

Damit weist sich das Add-on aus, wenn es Zahlen schickt. Es steht **nicht** im
Quelltext. Das Plugin sucht es in dieser Reihenfolge:

1. Konstante `HOCO_SECRET` in der `wp-config.php`,
2. Konstante `FUETTERUNG_SECRET` ebenda (der alte Name, für bestehende
   Installationen),
3. Option in der Datenbank — das erzeugt die Ersteinrichtung.

Ist keins gesetzt, weist die Website jeden Push ab. Das ist Absicht: eine frisch
installierte Seite steht damit nie offen.

## Umstieg von „Fütterungsabruf" (vor 0.40.0)

* **Add-on:** einfach aktualisieren. Die technische Kennung ist unverändert,
  Zuordnungen, Fütterungspläne und Vorlagen bleiben stehen. Neu ist die Option
  `stall_name`.
* **Plugin:** Die Datei heißt jetzt `hoco-pferdeseiten.php`. WordPress sieht
  darin ein anderes Plugin — **erst das alte deaktivieren**, dann das neue
  hochladen und aktivieren, sonst gibt es doppelte Funktionsnamen. Die Daten
  liegen in der Datenbank und bleiben erhalten.
* **Schnittstelle:** Der Namensraum heißt jetzt `hoco/v1`. Der alte
  `fuetterung/v1` bleibt bestehen, ein noch nicht umgestelltes Add-on schickt
  also weiter erfolgreich.

## Was hier nicht liegt

Das Projektverzeichnis enthält mehr als dieses Repository. Draußen bleiben
bewusst: die Einstellerliste mit Adressen und Notfallkontakten, die
Pferd-zu-Einsteller-Zuordnung, die persönlichen Zugangsschlüssel der
Pferdeseiten, Bildschirmaufnahmen aus dem Stall, Laufprotokolle, die
WireGuard-Konfiguration und der Aushang mit der Bot-Rufnummer. Die
[.gitignore](.gitignore) arbeitet deshalb als weiße Liste: alles ist
ausgeschlossen, freigegeben wird einzeln.

## Lizenz

[MIT](LICENSE)
