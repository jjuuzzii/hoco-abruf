<?php
/*
Plugin Name: HOCO-Pferdeseiten
Description: Gegenstueck zum Home-Assistant-Add-on "HOCO-Abruf": nimmt die Fuetterungszahlen vom Wasserbauer-HOCO-Rechner entgegen und zeigt jedem Einsteller die Seite seines Pferds unter einem persoenlichen Link (?k=SCHLUESSEL). Mit Aenderungswuenschen, Verlauf und Ersteinrichtung unter Einstellungen -> HOCO-Pferdeseiten.
Version: 0.20.0
Author: HOCO-Abruf
Plugin URI: https://github.com/jjuuzzii/hoco-abruf
GitHub Plugin URI: jjuuzzii/hoco-abruf
Update URI: https://github.com/jjuuzzii/hoco-abruf
Requires at least: 5.8
Requires PHP: 7.0
Text Domain: hoco-pferdeseiten
*/

/*
 * Der Knopf "Aktualisieren" laedt die Seite neu - nichts weiter.
 *
 * Gebraucht wird er, weil die Pferdeseite im VOLLBILD laeuft (vom Startbildschirm
 * aus geoeffnet): dort gibt es keine Adresszeile und keinen Neu-laden-Knopf des
 * Browsers, man muesste die Seite sonst schliessen und neu oeffnen.
 *
 * Er loest ausdruecklich KEINEN Abruf am Fuetterungsrechner aus. Die Zahlen
 * schickt das Add-on von sich aus nach jedem Lauf hierher (rund 24 mal am Tag),
 * ein Neuladen holt also immer den letzten Stand.
 */

if (!defined('ABSPATH')) {
    exit;
}

/* ==================== Gemeinsames Geheimnis ====================
 *
 * Damit weist sich das Add-on aus, wenn es Zahlen schickt. Es steht NICHT im
 * Quelltext - sonst waere es in jeder Sicherung und jedem Repository mit
 * dabei. Drei Quellen, in dieser Reihenfolge:
 *
 *   1. Konstante HOCO_SECRET aus der wp-config.php - hat immer Vorrang,
 *      fuer alle, die Geheimnisse lieber in Dateien als in der Datenbank haben.
 *   2. Konstante FUETTERUNG_SECRET - wie 1., nur der alte Name. Bestehende
 *      Installationen laufen damit unveraendert weiter.
 *   3. Option in der Datenbank, erzeugt von der Ersteinrichtung. Das ist der
 *      Normalfall: einmal auf den Knopf, fertig.
 *
 * Ohne Geheimnis nimmt die Website nichts an - das ist Absicht und kein
 * Fehler. Eine frisch installierte Seite steht damit nie offen. */
function hoco_secret() {
    if (defined('HOCO_SECRET') && HOCO_SECRET !== '') {
        return HOCO_SECRET;
    }
    if (defined('FUETTERUNG_SECRET') && FUETTERUNG_SECRET !== '') {
        return FUETTERUNG_SECRET;
    }
    return (string) get_option('hoco_secret', '');
}

/* Woher das Geheimnis stammt - fuer die Anzeige in der Ersteinrichtung. */
function hoco_secret_quelle() {
    if (defined('HOCO_SECRET') && HOCO_SECRET !== '') {
        return 'wp-config.php (HOCO_SECRET)';
    }
    if (defined('FUETTERUNG_SECRET') && FUETTERUNG_SECRET !== '') {
        return 'wp-config.php (FUETTERUNG_SECRET)';
    }
    return get_option('hoco_secret', '') ? 'Datenbank' : '';
}

/* Name des Betriebs. Steht im Kopf jeder Pferdeseite. */
function hoco_stall() {
    $name = trim((string) get_option('hoco_stall', ''));
    return $name !== '' ? $name : get_bloginfo('name');
}

/* ==================== Empfang ====================
 *
 * Zwei Namensraeume, dieselben Routen: "hoco/v1" ist der aktuelle,
 * "fuetterung/v1" der aus Versionen vor 0.20.0. Der alte bleibt bestehen,
 * damit ein Add-on, das noch auf die alte Adresse zeigt, nach dem Update des
 * Plugins nicht ins Leere schickt. Neue Installationen nehmen "hoco/v1". */
add_action('rest_api_init', function () {
    $routen = array(
        // Pfad, Methode, Funktion
        array('/push',           'POST', 'hoco_push'),
        array('/keys',           'POST', 'hoco_keys_push'),
        // Aenderungswunsch eines Einstellers. Kommt von der Pferdeseite und
        // weist sich mit dem persoenlichen Zugangsschluessel aus - nicht mit
        // dem gemeinsamen Geheimnis, das nur das Add-on kennt.
        array('/wunsch',         'POST', 'hoco_wunsch_neu'),
        // Die beiden folgenden spricht nur das Add-on an.
        array('/wuensche',       'GET',  'hoco_wuensche_holen'),
        array('/wunsch_status',  'POST', 'hoco_wunsch_status'),
        // Ruecknahme durch den Einsteller - weist sich mit seinem Zugang aus.
        array('/wunsch_zurueck', 'POST', 'hoco_wunsch_zurueck'),
    );
    foreach (array('hoco/v1', 'fuetterung/v1') as $raum) {
        foreach ($routen as $r) {
            register_rest_route($raum, $r[0], array(
                'methods' => $r[1], 'callback' => $r[2],
                'permission_callback' => '__return_true',
            ));
        }
    }
});

/* ---- Aenderungswuensche -------------------------------------------------
   Gespeichert wird in einer Option als JSON-Liste. Kein eigener Beitragstyp:
   es sind wenige Eintraege, sie sollen nicht im WordPress-Backend auftauchen
   und mit dem Plugin wieder verschwinden.

   Der Fuetterungsrechner wird dabei NICHT angefasst - eintragen muss jemand am
   Panel. Das Add-on vergleicht nur regelmaessig und hakt ab, sobald der
   gewuenschte Wert dort steht. */
function hoco_wuensche_laden() {
    $roh = get_option('fuetterung_wuensche', '[]');
    $d = json_decode($roh, true);
    return is_array($d) ? $d : array();
}
function hoco_wuensche_sichern($liste) {
    update_option('fuetterung_wuensche', wp_json_encode(array_values($liste)), false);
}
function hoco_wunsch_neu($req) {
    $body = $req->get_json_params();
    if (!is_array($body)) { return new WP_REST_Response(array('ok' => false), 400); }
    $keys = hoco_keys();
    $k = isset($body['k']) ? (string) $body['k'] : '';
    if ($k === '' || !isset($keys[$k])) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'unbekannter Zugang'), 403);
    }
    $arten = array('rf', 'kf', 'min', 'sel', 'tnr');
    $art = isset($body['art']) ? (string) $body['art'] : '';
    $wunsch = isset($body['wunsch']) ? trim((string) $body['wunsch']) : '';
    if (!in_array($art, $arten, true) || $wunsch === '' || mb_strlen($wunsch) > 40) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'Eingabe unvollstaendig'), 400);
    }
    $d = hoco_daten();
    $nr = (int) $keys[$k];
    $p = hoco_pferd_by_nr($d, $nr);
    $liste = hoco_wuensche_laden();
    // Pro Pferd und Art nur EIN offener Wunsch - sonst sammeln sich
    // widerspruechliche Eintraege, und niemand weiss, welcher gilt.
    foreach ($liste as $i => $w) {
        if ((int) $w['nr'] === $nr && $w['art'] === $art && $w['status'] === 'offen') {
            unset($liste[$i]);
        }
    }
    $liste[] = array(
        'id'      => uniqid('w', true),
        'nr'      => $nr,
        'name'    => $p ? $p['name'] : '',
        'art'     => $art,
        'wunsch'  => $wunsch,
        'notiz'   => isset($body['notiz']) ? mb_substr(trim((string) $body['notiz']), 0, 200) : '',
        'gestellt' => current_time('d.m.Y H:i'),
        'status'  => 'offen',
        'ist'     => '',
    );
    hoco_wuensche_sichern($liste);
    return array('ok' => true);
}
function hoco_wunsch_zurueck($req) {
    /* Zuruecknehmen geht nur, solange der Wunsch offen ist - und nur fuer das
       eigene Pferd. Der Eintrag wird nicht geloescht, sondern auf
       'zurueckgenommen' gesetzt: das Add-on muss ihn noch einmal sehen, um zu
       pruefen, ob im Hofbuero inzwischen schon umgestellt wurde. */
    $body = $req->get_json_params();
    $keys = hoco_keys();
    $k = isset($body['k']) ? (string) $body['k'] : '';
    if ($k === '' || !isset($keys[$k])) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'unbekannter Zugang'), 403);
    }
    $nr = (int) $keys[$k];
    $id = isset($body['id']) ? (string) $body['id'] : '';
    $liste = hoco_wuensche_laden();
    $treffer = false;
    foreach ($liste as $i => $w) {
        if ($w['id'] === $id && (int) $w['nr'] === $nr && $w['status'] === 'offen') {
            $liste[$i]['status'] = 'zurueckgenommen';
            $liste[$i]['zurueck'] = current_time('d.m.Y H:i');
            $treffer = true;
        }
    }
    if (!$treffer) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'nicht mehr offen'), 409);
    }
    hoco_wuensche_sichern($liste);
    return array('ok' => true);
}
function hoco_wuensche_holen($req) {
    if (!hoco_check_key($req)) {
        return new WP_REST_Response(array('ok' => false), 403);
    }
    $offen = array();
    foreach (hoco_wuensche_laden() as $w) {
        // 'zurueckgenommen' kommt mit: das Add-on muss pruefen, ob im Hofbuero
        // schon umgestellt wurde, und dann warnen.
        if ($w['status'] === 'offen' || $w['status'] === 'zurueckgenommen') { $offen[] = $w; }
    }
    return array('ok' => true, 'wuensche' => $offen);
}
function hoco_wunsch_status($req) {
    if (!hoco_check_key($req)) {
        return new WP_REST_Response(array('ok' => false), 403);
    }
    $body = $req->get_json_params();
    $id = isset($body['id']) ? (string) $body['id'] : '';
    $liste = hoco_wuensche_laden();
    foreach ($liste as $i => $w) {
        if ($w['id'] === $id) {
            $liste[$i]['status'] = isset($body['status']) ? (string) $body['status'] : 'erledigt';
            $liste[$i]['ist'] = isset($body['ist']) ? (string) $body['ist'] : '';
            $liste[$i]['grund'] = isset($body['grund']) ? mb_substr((string) $body['grund'], 0, 200) : '';
            $liste[$i]['erledigt'] = current_time('d.m.Y H:i');
        }
    }
    hoco_wuensche_sichern($liste);
    return array('ok' => true);
}
function hoco_wuensche_fuer($nr) {
    $aus = array();
    foreach (hoco_wuensche_laden() as $w) {
        if ((int) $w['nr'] === (int) $nr) { $aus[] = $w; }
    }
    return array_slice(array_reverse($aus), 0, 6);
}

function hoco_check_key($req) {
    $secret = hoco_secret();
    if ($secret === '') {
        return false;   // noch nicht eingerichtet - dann nimmt die Seite nichts an
    }
    $key = $req->get_param('key');
    return is_string($key) && hash_equals($secret, $key);
}
function hoco_push($req) {
    if (!hoco_check_key($req)) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'schluessel falsch'), 403);
    }
    $body = $req->get_json_params();
    if (!is_array($body) || empty($body['pferde'])) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'json fehlt/leer'), 400);
    }
    update_option('fuetterung_daten', wp_json_encode($body), false);
    return array('ok' => true, 'pferde' => count($body['pferde']),
                 'verlauf_tage' => isset($body['verlauf']) ? count($body['verlauf']) : 0);
}
function hoco_keys_push($req) {
    if (!hoco_check_key($req)) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'schluessel falsch'), 403);
    }
    $body = $req->get_json_params();
    if (!is_array($body)) {
        return new WP_REST_Response(array('ok' => false, 'msg' => 'json fehlt'), 400);
    }
    update_option('fuetterung_keys', wp_json_encode($body), false);
    return array('ok' => true, 'keys' => count($body));
}

/* ==================== Symbol (Favicon + Startbildschirm) ====================
 *
 * Ein Hufeisen in der Akzentfarbe des Berichts. Als SVG-Datenadresse direkt im
 * Kopf der Seite - kein Bild auf dem Server, kein zusaetzlicher Aufruf.
 *
 * Fuer den Startbildschirm braucht Apple ein PNG (SVG nimmt es dort nicht), und
 * eine Datenadresse akzeptiert es dabei nicht zuverlaessig. Deshalb liefert die
 * Seite das PNG unter ihrer eigenen Adresse mit '&symbol=1' aus.
 */
/* Die Geometrie ist einmal gezeichnet und angesehen worden, nicht gerechnet:
 * Bogen von 140 Grad ueber oben (270) bis 400 (= 40), Mittelpunkt 90/92,
 * Halbachsen 52/59, Strichdicke 22. Die Schenkel reichen damit unter die Mitte
 * und enden bei 50/130 und 130/130. Ein kuerzerer Bogen sah aus wie ein
 * Gesicht - zwei Punkte unter einem Huegel. Winkel zaehlen in GD wie in SVG:
 * 0 ist rechts, es geht im Uhrzeigersinn, 270 ist oben. */
function hoco_symbol_svg() {
    // Runde Linienenden ersetzen hier die Nagelpunkte des PNG.
    $svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180">'
         . '<rect width="180" height="180" rx="40" fill="#1F5F63"/>'
         . '<path d="M50 130 A52 59 0 1 1 130 130" fill="none" stroke="#FFFFFF"'
         . ' stroke-width="22" stroke-linecap="round"/></svg>';
    return 'data:image/svg+xml,' . rawurlencode($svg);
}

// Das PNG fuer den Startbildschirm: 180x180, mit GD gezeichnet (in WordPress
// vorhanden). Apple nimmt dort kein SVG und keine Datenadresse.
function hoco_symbol_png() {
    if (!function_exists('imagecreatetruecolor')) {
        return false;
    }
    $g = 180;
    $bild = imagecreatetruecolor($g, $g);
    $gruen = imagecolorallocate($bild, 0x1F, 0x5F, 0x63);
    $weiss = imagecolorallocate($bild, 0xFF, 0xFF, 0xFF);
    imagefilledrectangle($bild, 0, 0, $g, $g, $gruen);
    imagesetthickness($bild, 22);
    imagearc($bild, 90, 92, 104, 118, 140, 400, $weiss);
    // GD kennt keine runden Linienenden - die Nagelpunkte runden die Schenkel ab.
    imagefilledellipse($bild, 50, 130, 22, 22, $weiss);
    imagefilledellipse($bild, 130, 130, 22, 22, $weiss);
    ob_start();
    imagepng($bild);
    $roh = ob_get_clean();
    imagedestroy($bild);
    return $roh;
}

/* ==================== Daten-Helfer ==================== */
function hoco_daten() {
    $raw = get_option('fuetterung_daten', '');
    return $raw ? json_decode($raw, true) : null;
}
function hoco_keys() {
    $raw = get_option('fuetterung_keys', '');
    $k = $raw ? json_decode($raw, true) : null;
    return is_array($k) ? $k : array();
}
function hoco_pferd_by_nr($d, $nr) {
    if (!$d || empty($d['pferde'])) {
        return null;
    }
    foreach ($d['pferde'] as $p) {
        if ((string) $p['nr'] === (string) $nr) {
            return $p;
        }
    }
    return null;
}
function hoco_zahl($s) {
    if (is_numeric($s)) {
        return floatval($s);
    }
    if (is_string($s) && preg_match('/-?\d*[.,]?\d+/', str_replace(' ', '', $s), $m)) {
        return floatval(str_replace(',', '.', $m[0]));
    }
    return 0;
}
function hoco_feld($x, $einheit, $ton = 'neutral') {
    if (!is_array($x)) {
        return array('anspruch' => 0, 'geholt' => 0, 'soll_bisher' => 0, 'erreicht' => 0,
                     'einheit' => $einheit, 'ton' => $ton);
    }
    return array(
        'anspruch'    => hoco_zahl(isset($x['anspruch_gesamt']) ? $x['anspruch_gesamt'] : ''),
        'geholt'      => hoco_zahl(isset($x['fortschritt_gesamt']) ? $x['fortschritt_gesamt'] : ''),
        'soll_bisher' => hoco_zahl(isset($x['anspruch_bisherig']) ? $x['anspruch_bisherig'] : ''),
        'erreicht'    => intval(isset($x['fortschritt_bisherig_prozent']) ? $x['fortschritt_bisherig_prozent'] : 0),
        'einheit'     => $einheit,
        'ton'         => $ton,
    );
}
function hoco_verlauf($d, $nr) {
    $out = array();
    if (!empty($d['verlauf'])) {
        foreach ($d['verlauf'] as $tag) {
            $tp = hoco_pferd_by_nr($tag, $nr);
            $out[] = array(
                'tag' => isset($tag['stand']) ? $tag['stand'] : '',
                'rf'  => ($tp && isset($tp['rf']['fortschritt_gesamt'])) ? $tp['rf']['fortschritt_gesamt'] : '-',
                'kf'  => ($tp && isset($tp['kf']['fortschritt_gesamt'])) ? $tp['kf']['fortschritt_gesamt'] : '-',
                'min' => ($tp && isset($tp['min']['fortschritt_gesamt'])) ? $tp['min']['fortschritt_gesamt'] : '-',
            );
        }
    }
    return $out;
}
function hoco_urteil($p) {
    $stufe = isset($p['rueckstand']) ? $p['rueckstand'] : null;
    $name  = isset($p['name']) ? $p['name'] : 'Dein Pferd';
    // Vom Stall ausgenommene Nummern (kein Transponder, Weide, verkauft) tragen
    // kein Urteil - grau, nicht gruen: „alles in Ordnung" hat hier niemand geprueft.
    if (isset($p['ueberwacht']) && !$p['ueberwacht']) {
        return array('ton' => 'neutral', 'kopf' => 'Ohne &Uuml;berwachung',
            'text' => 'F&uuml;r ' . $name . ' wertet der Stall die Zahlen zurzeit '
                    . 'nicht aus. Die Werte unten kommen weiterhin direkt vom '
                    . 'F&uuml;tterungsrechner. Fragen? Im Hofb&uuml;ro melden.');
    }
    if ($stufe === 'transponder') {
        // Seit wann der Rechner das meldet, steht im Auszug (Feld 801905) und
        // kommt seit Add-on 0.33.0 mit. Ohne diese Angabe stand hier 'in den
        // letzten 12 Stunden' - und das war regelmaessig falsch: der Rechner
        // schreibt die Meldung einmal und laesst sie stehen, bis das Tier
        // wieder erkannt wird. Am 18.08.2026 waren alle fuenf Meldungen ueber
        // 29 Stunden alt.
        $seit = isset($p['hinweis_seit']) ? trim((string) $p['hinweis_seit']) : '';
        return array('ton' => 'kritisch', 'kopf' => 'Nicht erkannt',
            'text' => 'Der F&uuml;tterungsrechner meldet'
                    . ($seit ? ' seit ' . esc_html($seit) : '')
                    . ', dass ' . $name . ' an keiner Station erkannt wird. Das deutet '
                    . 'auf einen Transponderfehler hin &ndash; bitte im Hofb&uuml;ro melden.');
    }
    if ($stufe === 'nichts') {
        return array('ton' => 'kritisch', 'kopf' => 'Futter nicht geholt',
            'text' => $name . ' hat heute noch nichts abgeholt, obwohl schon etwas '
                    . 'f&auml;llig war (' . esc_html(hoco_arten_text($p)) . '). '
                    . 'Wenn das so bleibt, im Hofb&uuml;ro melden.');
    }
    if ($stufe === 'wenig') {
        return array('ton' => 'warn', 'kopf' => 'Hinweis',
            'text' => $name . ' liegt deutlich unter dem Soll: '
                    . esc_html(hoco_arten_text($p)) . '.');
    }
    return array('ton' => 'gut', 'kopf' => 'Alles in Ordnung',
        'text' => $name . ' ist gut versorgt.');
}

/* Farbe einer Futterkarte.
 *
 * Sie kommt aus dem Urteil des Add-ons ('<art>_rueckstand'), NICHT aus dem
 * Prozentwert. Am Prozentwert gemessen stand die Karte schon kurz nach dem
 * 6-Uhr-Reset rot - da war der Tag ja erst angefangen -, und Mineralfutter war
 * praktisch dauerrot: das holt fast kein Tier vollstaendig ab. Das Add-on
 * bewertet Mineralfutter deshalb gar nicht mehr; es schickt dazu das Merkmal
 * '<art>_bewertet'. Unbewertet heisst grau, nicht gruen - gruen waere eine
 * Aussage, die niemand geprueft hat. */
function hoco_ton($p, $feld) {
    if (isset($p[$feld . '_bewertet'])) {
        if (!$p[$feld . '_bewertet']) {
            return 'neutral';
        }
    } elseif ($feld === 'min') {
        // Daten aus einer aelteren Add-on-Fassung kennen das Merkmal noch
        // nicht; bis zum naechsten Push gilt die neue Regel hier trotzdem.
        return 'neutral';
    }
    $stufe = isset($p[$feld . '_rueckstand']) ? $p[$feld . '_rueckstand'] : null;
    if ($stufe === 'nichts') {
        return 'kritisch';
    }
    if ($stufe === 'wenig') {
        return 'warn';
    }
    return 'gut';
}

/* Welche Futterarten sind auffaellig? 'Raufutter, Mineralfutter' */
function hoco_arten_text($p) {
    $namen = array('rf' => 'Raufutter', 'kf' => 'Kraftfutter', 'min' => 'Mineralfutter');
    $treffer = array();
    foreach ($namen as $feld => $titel) {
        if (!empty($p[$feld . '_rueckstand'])) {
            $treffer[] = $titel;
        }
    }
    return $treffer ? implode(', ', $treffer) : 'siehe unten';
}

/* ==================== Mitarbeiter-Seite: ?k=MITARBEITERSCHLUESSEL ====================
 *
 * Fuer den Stallmitarbeiter, nicht fuer Einsteller. Zwei Dinge, beide zum
 * Abarbeiten am Fuetterungsrechner:
 *
 *   1. offene Aenderungswuensche - was eingetragen werden soll,
 *   2. Koppelzeiten - welches Pferd wann durchs Selektionstor darf.
 *
 * Ausdruecklich NUR LESEN. Eingetragen wird am Panel; dass es eingetragen
 * ist, meldet der Soll-Ist-Vergleich des Add-ons von selbst (wunsch.py) -
 * ein Knopf zum Abhaken waere ein Knopf zum Behaupten.
 */
function hoco_minuten($t) {
    if (!preg_match('/^(\d{1,2}):(\d{2})$/', (string) $t, $m)) {
        return -1;
    }
    return ((int) $m[1]) * 60 + (int) $m[2];
}

/* Ein Fenster, dessen Beginn eine Minute nach seinem Ende liegt, umfasst den
 * ganzen Tag - beobachtet an 10:01 bis 10:00 und 00:01 bis 00:00. Solche
 * Zeilen sind fuer den Mitarbeiter uninteressant und stehen deshalb getrennt. */
function hoco_ganztags($von, $bis) {
    $v = hoco_minuten($von);
    $b = hoco_minuten($bis);
    return ($v >= 0 && $b >= 0 && (($b + 1) % 1440) === $v);
}

function hoco_wunsch_titel($art) {
    $n = array('rf' => 'Raufutter', 'kf' => 'Kraftfutter', 'min' => 'Mineralfutter',
               'sel' => 'Zeit am Selektionstor', 'tnr' => 'Transpondernummer');
    return isset($n[$art]) ? $n[$art] : $art;
}

/* Was der Rechner JETZT sagt - dieselbe Grundlage wie im Add-on (wunsch.py):
 * verglichen wird der Anspruch, nicht das Geholte. */
function hoco_ist_wert($p, $art) {
    if (!$p) {
        return '?';
    }
    if ($art === 'tnr') {
        return (isset($p['transponder']) && $p['transponder'] !== '') ? $p['transponder'] : 'unbekannt';
    }
    if ($art === 'sel') {
        $f = (isset($p['zutrittszeiten']) && is_array($p['zutrittszeiten'])) ? $p['zutrittszeiten'] : array();
        $t = array();
        foreach ($f as $x) {
            $t[] = $x['von'] . '-' . $x['bis'];
        }
        return $t ? implode(', ', $t) : 'kein Fenster';
    }
    return (isset($p[$art]['anspruch_gesamt'])) ? $p[$art]['anspruch_gesamt'] : '?';
}

function hoco_mitarbeiter($d) {
    $pferde = (isset($d['pferde']) && is_array($d['pferde'])) ? $d['pferde'] : array();

    $offen = array();
    foreach (hoco_wuensche_laden() as $w) {
        if (isset($w['status']) && $w['status'] === 'offen') {
            $offen[] = $w;
        }
    }

    /* Koppelzeiten in drei Gruppen: echte Fenster zuerst, denn nur die sind
     * eine Arbeitsanweisung. */
    $mit = array();
    $ganz = array();
    $ohne = array();
    foreach ($pferde as $p) {
        $f = (isset($p['zutrittszeiten']) && is_array($p['zutrittszeiten'])) ? $p['zutrittszeiten'] : array();
        if (!$f) {
            $ohne[] = $p;
            continue;
        }
        $echt = array();
        foreach ($f as $x) {
            if (!hoco_ganztags($x['von'], $x['bis'])) {
                $echt[] = $x;
            }
        }
        if ($echt) {
            $mit[] = array('p' => $p, 'f' => $echt);
        } else {
            $ganz[] = $p;
        }
    }

    if (!headers_sent()) {
        header('Content-Type: text/html; charset=utf-8');
    }
    $selbst = esc_url(add_query_arg(array()));
    echo '<!doctype html><html lang="de"><head><meta charset="utf-8">';
    echo '<meta name="viewport" content="width=device-width, initial-scale=1">';
    echo '<link rel="icon" type="image/svg+xml" href="' . esc_attr(hoco_symbol_svg()) . '">';
    echo '<meta name="apple-mobile-web-app-title" content="Stall">';
    echo '<meta name="apple-mobile-web-app-capable" content="yes">';
    echo '<meta name="theme-color" content="#1F5F63">';
    echo '<title>Stall &ndash; Mitarbeiter</title><style>' . hoco_css() . '</style></head><body>';
    echo '<div class="huelle">';
    echo '<header class="kopf"><div class="stall">' . esc_html(hoco_stall()) . '</div>';
    echo '<h1 class="name">Stall&uuml;bersicht</h1>';
    echo '<div class="kennung">Stand ' . esc_html(isset($d['stand']) ? $d['stand'] : 'unbekannt') . '</div>';
    echo '<div class="frisch"><a class="knopf" href="' . $selbst . '">Aktualisieren</a></div>';
    echo '</header>';

    /* ---- Aenderungswuensche ---- */
    echo '<section class="karte"><div class="karte-kopf">'
       . '<div class="karte-titel">&Auml;nderungsw&uuml;nsche</div>'
       . '<div class="pille2">' . count($offen) . ' offen</div></div>';
    if (!$offen) {
        echo '<div class="klartext">Zurzeit ist nichts einzutragen.</div>';
    } else {
        foreach ($offen as $w) {
            $nr = isset($w['nr']) ? $w['nr'] : '';
            $p = hoco_pferd_by_nr($d, $nr);
            $name = $p && isset($p['name']) ? $p['name'] : (isset($w['name']) ? $w['name'] : '');
            $art = isset($w['art']) ? $w['art'] : '';
            echo '<div class="wzeile" style="display:block">'
               . '<div><b>Nr. ' . esc_html($nr) . ' ' . esc_html($name) . '</b></div>'
               . '<div style="margin-top:2px">' . esc_html(hoco_wunsch_titel($art))
               . ': <span class="grauklein">' . esc_html(hoco_ist_wert($p, $art))
               . '</span> &rarr; <b>' . esc_html(isset($w['wunsch']) ? $w['wunsch'] : '') . '</b></div>';
            if (!empty($w['notiz'])) {
                echo '<div class="grauklein" style="font-style:italic">&bdquo;'
                   . esc_html($w['notiz']) . '&ldquo;</div>';
            }
            echo '<div class="grauklein">gestellt ' . esc_html(isset($w['gestellt']) ? $w['gestellt'] : '')
               . '</div></div>';
        }
        echo '<div class="klartext">Eintragen am F&uuml;tterungsrechner. '
           . 'Abhaken muss niemand &ndash; sobald der Wert dort steht, verschwindet '
           . 'der Wunsch hier von selbst.</div>';
    }
    echo '</section>';

    /* ---- Koppelzeiten ---- */
    echo '<section class="karte"><div class="karte-kopf">'
       . '<div class="karte-titel">Koppelzeiten</div>'
       . '<div class="pille2">' . count($mit) . ' mit Fenster</div></div>';
    if ($mit) {
        foreach ($mit as $e) {
            $z = array();
            foreach ($e['f'] as $x) {
                $z[] = $x['von'] . ' &ndash; ' . $x['bis'];
            }
            echo '<div class="koppel"><span class="k-zeit">' . implode(', ', $z) . '</span>'
               . '<span>Nr. ' . esc_html($e['p']['nr']) . ' <b>' . esc_html($e['p']['name'])
               . '</b></span></div>';
        }
    } else {
        echo '<div class="klartext">Kein Pferd hat ein eingeschr&auml;nktes Zeitfenster.</div>';
    }
    if ($ganz) {
        $n = array();
        foreach ($ganz as $p) {
            $n[] = $p['name'];
        }
        echo '<div class="klartext"><b>Rund um die Uhr</b> (' . count($ganz) . '): '
           . esc_html(implode(', ', $n)) . '</div>';
    }
    if ($ohne) {
        $n = array();
        foreach ($ohne as $p) {
            $n[] = $p['name'];
        }
        echo '<div class="klartext"><b>Kein Fenster eingeschaltet</b> (' . count($ohne) . '): '
           . esc_html(implode(', ', $n)) . '</div>';
    }
    echo '<div class="klartext">Die Zeiten kommen direkt vom F&uuml;tterungsrechner '
       . '(Pferdeverwaltung &rarr; Selektionen). Ge&auml;ndert wird nur dort.</div>';
    echo '</section>';

    echo '<div class="fuss">Nur zum Nachsehen &middot; Fragen im Hofb&uuml;ro</div>';
    echo '</div></body></html>';
    exit;
}

/* ==================== Eigenstaendige Pferdeseite: ?k=SCHLUESSEL ==================== */
add_action('template_redirect', function () {
    if (empty($_GET['k'])) {
        return;
    }
    // Symbol fuer den Startbildschirm (siehe hoco_symbol_png). Steht vor
    // allem anderen, damit dafuer keine Daten geladen werden muessen.
    if (!empty($_GET['symbol'])) {
        $roh = hoco_symbol_png();
        if ($roh !== false) {
            header('Content-Type: image/png');
            header('Cache-Control: public, max-age=86400');
            echo $roh;
            exit;
        }
    }
    $k = sanitize_text_field(wp_unslash($_GET['k']));
    $keys = hoco_keys();
    if (!isset($keys[$k])) {
        return; // kein gueltiger Schluessel -> normale Seite (Shortcode zeigt Hinweis)
    }
    $d = hoco_daten();
    // Der Mitarbeiter-Zugang faehrt im selben Schluesselbund mit; er traegt
    // statt einer Pferdenummer den Wert 'mitarbeiter' (siehe bot.keys_pushen).
    if ((string) $keys[$k] === 'mitarbeiter') {
        hoco_mitarbeiter($d);
        return;
    }
    $p = hoco_pferd_by_nr($d, $keys[$k]);
    if (!$p) {
        return;
    }
    hoco_standalone($d, $p);
});

function hoco_standalone($d, $p) {
    $daten = array(
        'nr'      => $p['nr'],
        'name'    => $p['name'],
        'stand'   => isset($d['stand']) ? $d['stand'] : '',
        'rf'      => hoco_feld(isset($p['rf']) ? $p['rf'] : null, 'Min', hoco_ton($p, 'rf')),
        'kf'      => hoco_feld(isset($p['kf']) ? $p['kf'] : null, 'kg', hoco_ton($p, 'kf')),
        'min'     => hoco_feld(isset($p['min']) ? $p['min'] : null, 'g', hoco_ton($p, 'min')),
        'hat_min' => isset($p['min']) && is_array($p['min']),
        'urteil'  => hoco_urteil($p),
        'selektion' => (isset($p['selektion']) && is_array($p['selektion'])) ? array_values($p['selektion']) : array(),
        // Jeder Stationsbesuch des Tages mit Uhrzeit und Menge. Kommt erst seit
        // dem CSV-Auszug vom Fuetterungsrechner - am Bildschirm gab es nur die
        // Tagessumme. Aeltere Push-Daten haben das Feld nicht; dann bleibt die
        // Karte einfach aus.
        'besuche' => (isset($p['besuche']) && is_array($p['besuche'])) ? array_values($p['besuche']) : array(),
        'zutritt' => (isset($p['zutrittszeiten']) && is_array($p['zutrittszeiten'])) ? array_values($p['zutrittszeiten']) : array(),
        'wuensche' => hoco_wuensche_fuer($p['nr']),
        'k'       => isset($_GET['k']) ? sanitize_text_field(wp_unslash($_GET['k'])) : '',
        'rest'    => esc_url_raw(rest_url('fuetterung/v1/wunsch')),
        'transponder' => isset($p['transponder']) ? (string) $p['transponder'] : '',
        'verlauf' => hoco_verlauf($d, $p['nr']),
    );
    if (!headers_sent()) {
        header('Content-Type: text/html; charset=utf-8');
    }
    // Dieselbe Adresse mit '&symbol=1' - add_query_arg nimmt ohne dritten
    // Parameter die laufende Anfrage, das bleibt auch in Unterverzeichnissen richtig.
    $selbst = esc_url(add_query_arg('symbol', '1'));
    echo '<!doctype html><html lang="de"><head><meta charset="utf-8">';
    echo '<meta name="viewport" content="width=device-width, initial-scale=1">';
    // Symbol: SVG fuer Browser-Reiter, PNG fuer den Startbildschirm (Apple nimmt
    // dort kein SVG). Der Name auf dem Startbildschirm ist der des Pferds.
    echo '<link rel="icon" type="image/svg+xml" href="' . esc_attr(hoco_symbol_svg()) . '">';
    echo '<link rel="apple-touch-icon" href="' . $selbst . '">';
    echo '<meta name="apple-mobile-web-app-title" content="' . esc_attr($p['name']) . '">';
    echo '<meta name="apple-mobile-web-app-capable" content="yes">';
    echo '<meta name="theme-color" content="#1F5F63">';
    echo '<title>Tagesbericht ' . esc_html($p['name']) . '</title><style>' . hoco_css() . '</style></head><body>';
    echo '<div class="huelle">';
    echo '<header class="kopf"><div class="stall">' . esc_html(hoco_stall()) . '</div>';
    echo '<h1 class="name">' . esc_html($p['name']) . '</h1><div class="kennung" id="kennung"></div>';
    // Neu laden. Nur ein Knopf, weil die Seite im Vollbild keinen Browser-Knopf
    // dafuer hat. Bewusst ein echter <a> auf dieselbe Adresse: das laedt auch
    // dann neu, wenn JavaScript klemmt.
    echo '<div class="frisch"><a class="knopf" id="knopf-neu" href="'
       . esc_url(add_query_arg(array())) . '">Aktualisieren</a>'
       . '<span class="frisch-text" id="frisch-text"></span></div>';
    echo '</header>';
    // Zwei Reiter statt einer langen Seite. Auf dem Handy im Vollbild war das
    // Scrollen bis zum Verlauf zu weit; Besuche und Verlauf sind ausserdem
    // Nachschlagewerk, nicht Tagesblick.
    echo '<nav class="reiter"><button class="rtab an" data-ziel="blatt-heute">Heute</button>'
       . '<button class="rtab" data-ziel="blatt-verlauf">Verlauf &amp; Besuche</button>'
       . '<button class="rtab" data-ziel="blatt-wunsch">Mein Pferd</button></nav>';
    echo '<div id="blatt-heute" class="blatt">';
    echo '<section class="urteil" id="urteil"></section>';
    echo '<section class="karte" id="karte-rf"></section>';
    echo '<section class="karte" id="karte-kf"></section>';
    echo '<section class="karte" id="karte-min"></section>';
    echo '<section class="karte" id="karte-sel"><div class="karte-kopf"><div class="karte-titel">Am Selektionstor</div><div class="pille2" id="sel-anzahl"></div></div>';
    echo '<div class="band-huelle"><div class="band" id="band"></div><div class="band-achse"><span>0 Uhr</span><span>6</span><span>12</span><span>18</span><span>24 Uhr</span></div></div>';
    echo '<div class="zeitliste" id="zeitliste"></div>';
    echo '<div class="klartext">Jeder Strich ist eine Erkennung am Tor. Ein gleichm&auml;&szlig;ig verteilter Tag spricht daf&uuml;r, dass dein Pferd normal unterwegs ist.</div></section>';
    echo '</div>';
    echo '<div id="blatt-verlauf" class="blatt" hidden>';
    echo '<section class="karte" id="karte-besuche"><div class="karte-kopf"><div class="karte-titel">Besuche &ndash; letzte 24 Stunden</div><div class="pille2" id="besuche-anzahl"></div></div>';
    echo '<div class="besuchsliste" id="besuchsliste"></div>';
    echo '</section>';
    echo '<section class="karte" id="karte-verlauf"><div class="karte-kopf"><div class="karte-titel">Verlauf &ndash; letzte Tage</div></div>';
    echo '<table class="vtab"><thead><tr><th>Tag</th><th>Raufutter</th><th>Kraftfutter</th><th>Mineral</th></tr></thead><tbody id="verlauf-body"></tbody></table><div class="klartext">Ein F&uuml;tterungstag l&auml;uft von 6 Uhr bis 6 Uhr am n&auml;chsten Morgen &ndash; der 17.08. endet also am Morgen des 18.08.</div></section>';
    echo '</div>';
    echo '<div id="blatt-wunsch" class="blatt" hidden>';
    echo '<div class="klartext" style="margin-top:0">Vorschlag ans Hofb&uuml;ro. '
       . 'Sobald es dort eingetragen ist, steht hier <b>eingetragen</b>.</div>';
    echo '<section class="karte" id="karte-koppel"><div class="karte-kopf">'
       . '<div class="karte-titel">Koppelzeiten</div></div>';
    echo '<div id="koppelliste"></div>';
    echo '</section>';
    echo '<section class="karte"><div class="karte-kopf"><div class="karte-titel">&Auml;nderung w&uuml;nschen</div></div>';
    echo '<form id="wunsch-form" class="wform">';
    echo '<label>Was soll sich &auml;ndern?<select name="art" id="w-art">'
       . '<option value="rf">Raufutter &ndash; Minuten am Tag</option>'
       . '<option value="kf">Kraftfutter &ndash; kg am Tag</option>'
       . '<option value="min">Mineralfutter &ndash; Gramm am Tag</option>'
       . '<option value="sel">Zeit am Selektionstor</option>'
       . '<option value="tnr">Transpondernummer</option>'
       . '</select></label>';
    // Fuer jede Art ein eigenes Eingabefeld - keine Freitexte. Die Stufen sind
    // die, die am Fuetterungsrechner tatsaechlich vorkommen (Raufutter in
    // 30-Minuten-Schritten bis 360, Mineral in 10-g-Schritten bis 250).
    //
    // Kraftfutter geht in 10-g-Schritten bis 5 kg, und das ist kein Geschmack,
    // sondern eine Reparatur: das Feld stand auf 50-g-Schritten bis 3 kg,
    // wurde aber mit dem IST-Wert vorbelegt. Wer 0,790 kg eingestellt hat
    // (Wira, Auryn, Dutsty, Hidalgo), bekam '0.79' vorgelegt - kein Vielfaches
    // von 0,05 - und der Browser verweigerte das Abschicken, ohne zu sagen
    // warum. Temperino mit 3,990 kg lag zusaetzlich ueber dem Maximum. Fuenf
    // von 28 Einstellern konnten so ueberhaupt keinen Kraftfutter-Wunsch
    // stellen.
    echo '<div class="feld" data-fuer="rf"><label>Minuten am Tag'
       . '<input type="number" id="e-rf" min="0" max="360" step="30" inputmode="numeric"></label></div>';
    echo '<div class="feld" data-fuer="kf" hidden><label>Kilogramm am Tag'
       . '<input type="number" id="e-kf" min="0" max="5" step="0.01" inputmode="decimal"></label></div>';
    echo '<div class="feld" data-fuer="min" hidden><label>Gramm am Tag'
       . '<input type="number" id="e-min" min="0" max="250" step="10" inputmode="numeric"></label></div>';
    echo '<div class="feld" data-fuer="sel" hidden><div class="zeitpaar">'
       . '<label>von<input type="time" id="e-sel-von" step="60"></label>'
       . '<label>bis<input type="time" id="e-sel-bis" step="60"></label></div></div>';
    echo '<div class="feld" data-fuer="tnr" hidden><label>Neue Transpondernummer '
       . '<span class="grauklein">(8 Ziffern)</span>'
       . '<input type="text" id="e-tnr" inputmode="numeric" pattern="[0-9]{8}" maxlength="8"></label></div>';
    echo '<div class="jetzt" id="w-jetzt"></div>';
    echo '<label>Begr&uuml;ndung<select name="notiz" id="w-notiz">'
       . '<option value="">&ndash; keine Angabe &ndash;</option>'
       . '<option>nimmt ab</option><option>nimmt zu</option>'
       . '<option>Tierarzt hat es empfohlen</option>'
       . '<option>frisst nicht auf</option><option>hat st&auml;ndig Hunger</option>'
       . '<option>Transponder verloren</option>'
       . '<option>Absprache mit dem Hofb&uuml;ro</option></select></label>';
    echo '<button class="knopf" type="submit">Abschicken</button>';
    echo '<div class="wmeldung" id="w-meldung"></div></form></section>';
    echo '<section class="karte" id="karte-wliste"><div class="karte-kopf"><div class="karte-titel">Deine W&uuml;nsche</div></div>';
    echo '<div id="wliste"></div></section>';
    echo '</div>';
    echo '<footer class="fuss">';
    echo '<div><b>Woher kommen die Zahlen?</b> Sie kommen alle paar Minuten direkt aus dem F&uuml;tterungsrechner im Stall. Sie beziehen sich auf den laufenden F&uuml;tterungszyklus, nicht auf den Kalendertag.</div>';
    echo '<div><b>Etwas stimmt nicht?</b> Melde dich einfach im Hofb&uuml;ro &mdash; wir schauen gemeinsam nach.</div>';
    echo '</footer></div>';
    echo '<script>const daten=' . wp_json_encode($daten) . ';' . hoco_js() . '</script>';
    echo '</body></html>';
    exit;
}

/* ==================== [fuetterung] – einfache Tabelle (Admin-Uebersicht) ==================== */
add_shortcode('fuetterung', function () {
    $d = hoco_daten();
    if (!$d || empty($d['pferde'])) {
        return '<p>Noch keine F&uuml;tterungsdaten.</p>';
    }
    $stufen = array('transponder' => 'Nicht erkannt', 'nichts' => 'Nicht geholt',
                    'wenig' => 'R&uuml;ckstand');
    $farben = array('transponder' => '#A8322A', 'nichts' => '#A8322A',
                    'wenig' => '#B4571A');
    $out = '<table style="width:100%;border-collapse:collapse"><thead><tr>'
         . '<th style="text-align:left">Nr</th><th style="text-align:left">Name</th>'
         . '<th style="text-align:left">Raufutter</th><th style="text-align:left">Kraftfutter</th>'
         . '<th style="text-align:left">Mineral</th><th style="text-align:left">Status</th>'
         . '</tr></thead><tbody>';
    foreach ($d['pferde'] as $p) {
        $rf = isset($p['rf']['fortschritt_gesamt']) ? $p['rf']['fortschritt_gesamt'] . ' / ' . $p['rf']['anspruch_gesamt'] : '-';
        $kf = isset($p['kf']['fortschritt_gesamt']) ? $p['kf']['fortschritt_gesamt'] . ' / ' . $p['kf']['anspruch_gesamt'] : '-';
        $mi = isset($p['min']['fortschritt_gesamt']) ? $p['min']['fortschritt_gesamt'] . ' / ' . $p['min']['anspruch_gesamt'] : '-';
        $st = isset($p['rueckstand']) ? $p['rueckstand'] : null;
        $zustand = isset($stufen[$st])
            ? '<b style="color:' . $farben[$st] . '">' . $stufen[$st] . '</b>'
            : '<span style="color:#5E6862">in Ordnung</span>';
        $out .= '<tr><td>' . esc_html($p['nr']) . '</td><td>' . esc_html($p['name'])
              . '</td><td>' . esc_html($rf) . '</td><td>' . esc_html($kf)
              . '</td><td>' . esc_html($mi) . '</td><td>' . $zustand . '</td></tr>';
    }
    return $out . '</tbody></table>';
});

// [fuetterung_key] – Platzhalter, falls jemand die Seite ohne gueltigen ?k= aufruft
add_shortcode('fuetterung_key', function () {
    return '<p>Bitte den pers&ouml;nlichen Link mit Zugangsschl&uuml;ssel verwenden. Fragen? Im Hofb&uuml;ro melden.</p>';
});

/* ==================== CSS (1:1 aus der Vorgabe, ASCII) ==================== */
function hoco_css() {
    return <<<'CSS'
:root{--grund:#F2F4F1;--flaeche:#FFFFFF;--rand:#DFE4DF;--tinte:#1B221E;--gedaempft:#5E6862;--akzent:#1F5F63;--gut:#2E7D4F;--warn:#B4571A;--kritisch:#A8322A;--neutral:#5E6862;--gut-weich:#E4F0E8;--warn-weich:#F7EADD;--kritisch-weich:#F6E3E1;--neutral-weich:#EAEEE9;--schatten:0 1px 2px rgba(27,34,30,.05),0 4px 16px rgba(27,34,30,.06);--sans:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,Roboto,sans-serif;--mono:ui-monospace,"Cascadia Mono","SF Mono",Consolas,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--grund:#121614;--flaeche:#1A211D;--rand:#2B342E;--tinte:#E8EDE9;--gedaempft:#94A099;--akzent:#4FB3B8;--gut:#58B87E;--warn:#E08A47;--kritisch:#E0685C;--neutral:#94A099;--gut-weich:#1B2F23;--warn-weich:#322317;--kritisch-weich:#33201E;--neutral-weich:#212824;--schatten:0 1px 2px rgba(0,0,0,.3),0 4px 16px rgba(0,0,0,.35);}}
*{box-sizing:border-box;}
body{margin:0;background:var(--grund);color:var(--tinte);font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased;}
.huelle{max-width:560px;margin:0 auto;padding:28px 20px 64px;display:flex;flex-direction:column;gap:22px;}
.kopf{display:flex;flex-direction:column;gap:6px;}
.stall{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--akzent);}
.name{margin:0;font-size:clamp(38px,12vw,52px);font-weight:300;letter-spacing:-.02em;line-height:1.02;}
.kennung{font-family:var(--mono);font-size:12.5px;color:var(--gedaempft);font-variant-numeric:tabular-nums;}
.frisch{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:4px;}
.knopf{display:inline-block;font-family:inherit;font-size:13px;font-weight:600;color:var(--akzent);background:var(--flaeche);border:1px solid var(--rand);border-radius:3px;padding:8px 14px;cursor:pointer;text-decoration:none;-webkit-tap-highlight-color:transparent;}
.knopf:hover{border-color:var(--akzent);}
.knopf:active{background:var(--neutral-weich);}
.knopf.laeuft::before{content:"";display:inline-block;width:9px;height:9px;margin-right:7px;border-radius:50%;border:2px solid var(--akzent);border-top-color:transparent;vertical-align:-1px;animation:dreh 1s linear infinite;}
@keyframes dreh{to{transform:rotate(360deg);}}
.frisch-text{font-size:12.5px;color:var(--gedaempft);flex:1;min-width:180px;}
.urteil{display:flex;gap:13px;align-items:flex-start;padding:15px 17px;border-radius:3px;border-left:3px solid var(--ton);background:var(--ton-weich);}
.urteil-punkt{width:9px;height:9px;border-radius:50%;background:var(--ton);margin-top:7px;flex:none;}
.urteil-text{display:flex;flex-direction:column;gap:2px;}
.urteil-kopf{font-weight:650;font-size:15.5px;color:var(--ton);}
.urteil-detail{font-size:14px;color:var(--gedaempft);}
.karte{background:var(--flaeche);border:1px solid var(--rand);border-radius:4px;padding:18px;box-shadow:var(--schatten);display:flex;flex-direction:column;gap:14px;}
.karte-kopf{display:flex;justify-content:space-between;align-items:baseline;gap:12px;}
.karte-titel{font-weight:640;font-size:16px;}
.pille{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:3px 8px;border-radius:2px;background:var(--ton-weich);color:var(--ton);white-space:nowrap;}
.zahlen{display:flex;gap:26px;flex-wrap:wrap;}
.zahl-block{display:flex;flex-direction:column;gap:1px;}
.zahl-wert{font-family:var(--mono);font-size:21px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;}
.zahl-label{font-size:11.5px;color:var(--gedaempft);letter-spacing:.02em;}
.balken-feld{display:flex;flex-direction:column;gap:7px;}
.balken{position:relative;height:26px;background:var(--grund);border:1px solid var(--rand);border-radius:2px;overflow:hidden;}
.balken-fuellung{position:absolute;inset:0 auto 0 0;background:var(--ton);opacity:.82;}
.balken-marke{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--tinte);}
.balken-marke::after{content:"";position:absolute;top:-3px;left:-3px;border-left:4px solid transparent;border-right:4px solid transparent;border-top:5px solid var(--tinte);}
.balken-legende{display:flex;justify-content:space-between;font-size:11.5px;color:var(--gedaempft);font-family:var(--mono);font-variant-numeric:tabular-nums;}
.klartext{font-size:13.5px;color:var(--gedaempft);}
.vtab{width:100%;border-collapse:collapse;font-size:13.5px;}
.vtab th{text-align:left;color:var(--gedaempft);font-weight:600;padding:2px 0 6px;font-size:11.5px;}
.vtab td{padding:6px 0;border-top:1px solid var(--rand);font-family:var(--mono);font-variant-numeric:tabular-nums;}
.band-huelle{display:flex;flex-direction:column;gap:9px;}
.band{position:relative;height:54px;background:var(--grund);border:1px solid var(--rand);border-radius:2px;}
.band-stunde{position:absolute;top:0;bottom:0;width:1px;background:var(--rand);}
.band-marke{position:absolute;top:9px;bottom:9px;width:3px;margin-left:-1.5px;background:var(--akzent);border-radius:2px;}
.band-achse{display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px;color:var(--gedaempft);font-variant-numeric:tabular-nums;}
.wform label{display:block;margin:10px 0;font-size:13px;color:#455a64;font-weight:700}
.wform select,.wform input,.wform textarea{display:block;width:100%;margin-top:5px;padding:10px;
  border:1px solid #cfd8dc;border-radius:9px;font:inherit;font-weight:400;color:#263238;
  background:#fff;-webkit-appearance:none;box-sizing:border-box}
.wform .knopf{margin-top:6px;width:100%;text-align:center}
.feld[hidden]{display:none}
.koppel{display:flex;justify-content:space-between;align-items:baseline;
  padding:9px 2px;border-bottom:1px solid var(--rand);font-size:15px}
.koppel:last-child{border-bottom:0}
.k-zeit{font-variant-numeric:tabular-nums;font-weight:700}
.zeitpaar{display:flex;gap:12px}
.zeitpaar label{flex:1;margin:10px 0}
.jetzt{font-size:13px;color:#666;margin:-4px 0 4px}
.grauklein{font-weight:400;color:#90a4ae}
.wmeldung{margin-top:10px;font-size:14px}
.wmeldung.ok{color:#2e7d32}.wmeldung.fehler{color:#c62828}
.wzeile{display:flex;gap:10px;align-items:baseline;padding:8px 2px;border-bottom:1px solid #eee;font-size:14px}
.wzeile:last-child{border-bottom:0}
.wzeile .wstatus{margin-left:auto;font-size:12px;font-weight:700;white-space:nowrap}
.wzeile .offen{color:#ef6c00}.wzeile .fertig{color:#2e7d32}
.wzeile .nein{color:#c62828}
.zurueck{margin-left:10px;padding:5px 9px;border:1px solid var(--rand);border-radius:8px;
  background:transparent;color:var(--gedaempft);font:inherit;font-size:12px;cursor:pointer}
.reiter{display:flex;gap:6px;margin:0 0 12px}
.rtab{flex:1;padding:10px 8px;border:0;border-radius:11px;background:#eceff0;color:#37474f;
      font:inherit;font-weight:700;font-size:14px;cursor:pointer}
.rtab.an{background:var(--gruen,#1F5F63);color:#fff}
/* Die Blaetter uebernehmen den Abstand, den die Huelle ihren Kindern gab -
   sonst kleben die Karten aneinander, seit sie in einem Container stecken. */
.blatt{display:flex;flex-direction:column;gap:22px}
.blatt[hidden]{display:none}
/* Rechts Platz lassen: der Rollbalken lag sonst ueber dem Text ("1 Min He|").
   Und die Ortsspalte darf schrumpfen - auf schmalen Handys sprengte ihre feste
   Breite die Zeile. */
.besuchsliste{margin:4px 0 10px;max-height:340px;overflow-y:auto;padding-right:12px;
  -webkit-overflow-scrolling:touch}
/* Zweizeilig: oben wann und wo, darunter was es gab.
   Einzeilig stand am 19.08.2026 auf dem Handy 'Easy St. ...' und
   'Komp.S...' - vier Angaben nebeneinander passen auf 390 Pixel nicht,
   und die Station als erste abzuschneiden trifft die wichtigste. */
.besuch{display:block;padding:9px 2px;
  border-bottom:1px solid var(--rand);font-size:15px}
.b-kopf{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.besuch:last-child{border-bottom:0}
.b-zeit{font-variant-numeric:tabular-nums;font-weight:700}
.b-dauer{color:var(--gedaempft);font-size:12px;white-space:nowrap}
.b-ort{color:var(--gedaempft);font-size:13px}
.b-was{margin-top:2px}
.b-was .leer{color:var(--gedaempft);font-style:italic}
.zeitliste{display:flex;flex-wrap:wrap;gap:5px;}
.zeit{font-family:var(--mono);font-size:12px;font-variant-numeric:tabular-nums;padding:2px 6px;background:var(--grund);border:1px solid var(--rand);border-radius:2px;color:var(--gedaempft);}
.pille2{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:3px 8px;border-radius:2px;color:var(--gedaempft);border:1px solid var(--rand);white-space:nowrap;}
.fuss{border-top:1px solid var(--rand);padding-top:16px;display:flex;flex-direction:column;gap:8px;font-size:12.5px;color:var(--gedaempft);}
.fuss b{color:var(--tinte);font-weight:620;}
CSS;
}

/* ==================== JS (aus der Vorgabe, Umlaute als \u, ohne Selektion, mit Verlauf) ==================== */
function hoco_js() {
    return <<<'JS'
var zahl=function(w,e){return e==="kg"?Number(w).toFixed(3).replace(".",","):String(Math.round(w));};
var tonVars=function(s){return "--ton:var(--"+s+"); --ton-weich:var(--"+s+"-weich);";};
document.getElementById("kennung").textContent="Nr. "+daten.nr+" · Stand "+daten.stand+" Uhr";
// Das Urteil kommt fertig aus dem Add-on (siehe hoco_urteil) - hier wird
// nichts nachgerechnet, damit Website und Stallbuero dasselbe sagen.
var u=document.getElementById("urteil");
u.setAttribute("style",tonVars(daten.urteil.ton));
u.innerHTML='<div class="urteil-punkt"></div><div class="urteil-text"><div class="urteil-kopf">'+daten.urteil.kopf+'</div><div class="urteil-detail">'+daten.urteil.text+'</div></div>';
function karte(el,titel,d,klartext){
  // Die Farbe kommt fertig aus dem Add-on (siehe hoco_ton) - hier wird
  // nichts aus dem Prozentwert abgeleitet.
  var s=d.ton||"neutral";
  var fuellung=d.anspruch>0?Math.min(100,d.geholt/d.anspruch*100):0;
  var marke=d.anspruch>0?Math.min(100,d.soll_bisher/d.anspruch*100):0;
  el.setAttribute("style",tonVars(s));
  el.innerHTML='<div class="karte-kopf"><div class="karte-titel">'+titel+'</div><div class="pille">'+d.erreicht+'&nbsp;% vom Soll</div></div>'
   +'<div class="zahlen">'
   +'<div class="zahl-block"><div class="zahl-wert">'+zahl(d.geholt,d.einheit)+'&thinsp;'+d.einheit+'</div><div class="zahl-label">geholt</div></div>'
   +'<div class="zahl-block"><div class="zahl-wert">'+zahl(d.soll_bisher,d.einheit)+'&thinsp;'+d.einheit+'</div><div class="zahl-label">Soll bis jetzt</div></div>'
   +'<div class="zahl-block"><div class="zahl-wert">'+zahl(d.anspruch,d.einheit)+'&thinsp;'+d.einheit+'</div><div class="zahl-label">Anspruch gesamt</div></div>'
   +'</div>'
   +'<div class="balken-feld"><div class="balken"><div class="balken-fuellung" style="width:'+fuellung+'%"></div><div class="balken-marke" style="left:'+marke+'%"></div></div>'
   +'<div class="balken-legende"><span>0</span><span>▲ Soll bis jetzt</span><span>'+zahl(d.anspruch,d.einheit)+'&thinsp;'+d.einheit+'</span></div></div>'
   +'<div class="klartext">'+klartext+'</div>';
}
if(daten.rf.anspruch>0){karte(document.getElementById("karte-rf"),"Raufutter",daten.rf,"Von "+zahl(daten.rf.anspruch,"Min")+" Minuten am Tag bisher "+zahl(daten.rf.geholt,"Min")+" geholt – Soll bis jetzt rund "+zahl(daten.rf.soll_bisher,"Min")+" Minuten.");}else{document.getElementById("karte-rf").style.display="none";}
karte(document.getElementById("karte-kf"),"Kraftfutter",daten.kf,"Von "+zahl(daten.kf.anspruch,"kg")+" kg am Tag bisher "+zahl(daten.kf.geholt,"kg")+" kg geholt – Soll bis jetzt "+zahl(daten.kf.soll_bisher,"kg")+" kg.");
// Mineralfutter: nur zeigen, wenn es abgerufen wurde UND ein Anspruch besteht -
// viele Tiere bekommen keins, eine Karte mit lauter Nullen verwirrt nur.
if(daten.hat_min&&daten.min.anspruch>0){karte(document.getElementById("karte-min"),"Mineralfutter",daten.min,"Von "+zahl(daten.min.anspruch,"g")+" g am Tag bisher "+zahl(daten.min.geholt,"g")+" g geholt – Soll bis jetzt "+zahl(daten.min.soll_bisher,"g")+" g. Mineralfutter wird nur angezeigt, nicht bewertet – die meisten Pferde holen es nur ab und zu.");}else{document.getElementById("karte-min").style.display="none";}
var sel=daten.selektion||[];
if(sel.length){
  document.getElementById("sel-anzahl").textContent=sel.length+"× erkannt";
  var VON=0,BIS=1440,SP=BIS-VON,band=document.getElementById("band");
  for(var h=3;h<24;h+=3){var l=document.createElement("div");l.className="band-stunde";l.style.left=((h*60-VON)/SP*100)+"%";band.appendChild(l);}
  sel.forEach(function(t){var pp=(""+t).split(":");var mm=(+pp[0])*60+(+pp[1]);var mk=document.createElement("div");mk.className="band-marke";mk.style.left=Math.max(0,Math.min(100,(mm-VON)/SP*100))+"%";mk.title=t;band.appendChild(mk);});
  document.getElementById("zeitliste").innerHTML=sel.map(function(t){return '<span class="zeit">'+t+'</span>';}).join("");
}else{document.getElementById("karte-sel").style.display="none";}
var bes=daten.besuche||[];
if(bes.length){
  document.getElementById("besuche-anzahl").textContent=bes.length+"× an einer Station";
  document.getElementById("besuchsliste").innerHTML=bes.map(function(b){
    var teile=[];
    if(b.rf){teile.push(zahl(b.rf,"Min")+" Min Heu");}
    if(b.kf){teile.push(zahl(b.kf,"g")+" g Kraftfutter");}
    if(b.min){teile.push(zahl(b.min,"g")+" g Mineral");}
    var was=teile.length?teile.join(", "):"<span class=\"leer\">ohne Ausgabe</span>";
    // Dauer als "bis hh:mm" - der Rechner protokolliert sie sekundengenau.
    var spanne=b.bis?('<span class="b-dauer">bis '+b.bis+'</span>'):'';
    return '<div class="besuch"><div class="b-kopf">'
         + '<span class="b-zeit">'+b.zeit+'</span>'+spanne
         + '<span class="b-ort">'+(b.station||"")+'</span></div>'
         + '<div class="b-was">'+was+'</div></div>';
  }).join("");
}else{document.getElementById("karte-besuche").style.display="none";}
var vb=document.getElementById("verlauf-body");
if(daten.verlauf&&daten.verlauf.length){
  vb.innerHTML=daten.verlauf.map(function(t){return '<tr><td>'+t.tag+'</td><td>'+t.rf+'</td><td>'+t.kf+'</td><td>'+(t.min||"-")+'</td></tr>';}).join("");
}else{
  document.getElementById("karte-verlauf").style.display="none";
}

/* ---- Reiter ---- */
(function(){
  var tabs=document.querySelectorAll(".rtab"), blaetter=document.querySelectorAll(".blatt");
  Array.prototype.forEach.call(tabs,function(t){
    t.addEventListener("click",function(){
      Array.prototype.forEach.call(tabs,function(x){x.classList.remove("an");});
      t.classList.add("an");
      Array.prototype.forEach.call(blaetter,function(b){b.hidden=(b.id!==t.dataset.ziel);});
      window.scrollTo(0,0);
    });
  });
})();

/* ---- Aenderungswunsch ----
   Keine Freitexte: je Art ein passendes Feld mit den Stufen, die am
   Fuetterungsrechner wirklich vorkommen. Der Wunsch wird nur eingetragen -
   geaendert wird am Rechner nichts. */
(function(){
  var form=document.getElementById("wunsch-form");
  if(!form){return;}
  var art=document.getElementById("w-art"), jetzt=document.getElementById("w-jetzt"),
      meldung=document.getElementById("w-meldung"),
      felder=document.querySelectorAll(".feld");

  function aktuell(a){
    if(a==="rf"){return daten.rf?zahl(daten.rf.anspruch,"Min")+" Min am Tag":"0 Min";}
    if(a==="kf"){return daten.kf?zahl(daten.kf.anspruch,"kg")+" kg am Tag":"0 kg";}
    if(a==="min"){return daten.min?zahl(daten.min.anspruch,"g")+" g am Tag":"0 g";}
    if(a==="tnr"){return daten.transponder||"unbekannt";}
    var f=daten.zutritt||[];
    return f.length?f.map(function(x){return x.von+" bis "+x.bis;}).join(", "):"kein Fenster eingerichtet";
  }
  function wert(a){
    if(a==="sel"){
      var v=document.getElementById("e-sel-von").value, s=document.getElementById("e-sel-bis").value;
      return (v&&s)?(v+"-"+s):"";
    }
    return (document.getElementById("e-"+a).value||"").trim();
  }
  function zeigen(){
    var a=art.value;
    Array.prototype.forEach.call(felder,function(f){f.hidden=(f.dataset.fuer!==a);});
    jetzt.textContent="Jetzt eingestellt: "+aktuell(a);
    // Vorbelegen mit dem aktuellen Wert - so muss nur geaendert werden, was
    // sich aendern soll.
    if(a==="rf"&&daten.rf){document.getElementById("e-rf").value=Math.round(daten.rf.anspruch);}
    if(a==="kf"&&daten.kf){document.getElementById("e-kf").value=Number(daten.kf.anspruch).toFixed(2);}
    if(a==="min"&&daten.min){document.getElementById("e-min").value=Math.round(daten.min.anspruch);}
    if(a==="tnr"){document.getElementById("e-tnr").value=daten.transponder||"";}
    if(a==="sel"&&(daten.zutritt||[]).length){
      document.getElementById("e-sel-von").value=daten.zutritt[0].von;
      document.getElementById("e-sel-bis").value=daten.zutritt[0].bis;
    }
  }
  art.addEventListener("change",zeigen); zeigen();

  function liste(){
    var w=daten.wuensche||[], el=document.getElementById("wliste");
    if(!w.length){document.getElementById("karte-wliste").style.display="none";return;}
    document.getElementById("karte-wliste").style.display="";
    var NAME={rf:"Raufutter",kf:"Kraftfutter",min:"Mineralfutter",
              sel:"Zeit am Selektionstor",tnr:"Transpondernummer"};
    el.innerHTML=w.map(function(x){
      var TXT={offen:"offen", erledigt:"eingetragen", abgelehnt:"abgelehnt",
               zurueckgenommen:"zurückgenommen", geschlossen:"erledigt"};
      var offen=x.status==="offen", nein=x.status==="abgelehnt";
      var grund=(nein&&x.grund)?('<br><span class="grauklein">'+x.grund+'</span>'):'';
      return '<div class="wzeile"><span>'+(NAME[x.art]||x.art)+' &rarr; <b>'+x.wunsch+'</b>'
           + '<br><span class="grauklein">'+x.gestellt+'</span>'+grund+'</span>'
           + '<span class="wstatus '+(offen?"offen":(nein?"nein":"fertig"))+'">'
           + (TXT[x.status]||x.status)+'</span>'
           + (offen?('<button class="zurueck" data-id="'+x.id+'">zurücknehmen</button>'):'')
           + '</div>';
    }).join("");
  }
  function koppel(){
    var f=(daten.zutritt||[]), el=document.getElementById("koppelliste");
    if(!f.length){
      el.innerHTML='<div class="grauklein">Zurzeit ist kein Zeitfenster eingeschaltet.</div>';
      return;
    }
    el.innerHTML=f.map(function(x){
      return '<div class="koppel"><span class="k-zeit">'+x.von+' &ndash; '+x.bis+'</span>'
           + '<span class="grauklein">Fenster '+x.nr+'</span></div>';
    }).join("");
  }
  koppel();
  liste();

  // Zuruecknehmen - nur solange offen. Die Seite laedt danach neu, damit die
  // Liste stimmt.
  document.getElementById("wliste").addEventListener("click",function(e){
    var b=e.target.closest?e.target.closest(".zurueck"):null;
    if(!b){return;}
    b.disabled=true; b.textContent="…";
    fetch(daten.rest.replace("/wunsch","/wunsch_zurueck"),
      {method:"POST",headers:{"Content-Type":"application/json"},
       body:JSON.stringify({k:daten.k, id:b.dataset.id})})
      .then(function(r){return r.json().catch(function(){return {ok:false};});})
      .then(function(a){
        if(a&&a.ok){location.reload();}
        else{b.disabled=false;b.textContent="zurücknehmen";
             meldung.className="wmeldung fehler";
             meldung.textContent=(a&&a.msg)?("Ging nicht: "+a.msg):"Ging nicht.";}
      })
      .catch(function(){b.disabled=false;b.textContent="zurücknehmen";});
  });

  form.addEventListener("submit",function(e){
    e.preventDefault();
    var v=wert(art.value);
    if(!v){
      meldung.className="wmeldung fehler";
      meldung.textContent="Bitte einen Wert eintragen.";
      return;
    }
    if(art.value==="tnr"&&!/^[0-9]{8}$/.test(v)){
      meldung.className="wmeldung fehler";
      meldung.textContent="Die Transpondernummer hat genau 8 Ziffern.";
      return;
    }
    meldung.className="wmeldung"; meldung.textContent="Wird abgeschickt …";
    fetch(daten.rest,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({k:daten.k, art:art.value, wunsch:v,
                           notiz:document.getElementById("w-notiz").value})})
      .then(function(r){return r.json().catch(function(){return {ok:false};});})
      .then(function(a){
        if(a && a.ok){
          meldung.className="wmeldung ok";
          meldung.textContent="Angekommen. Das Hofbüro sieht es beim nächsten Blick.";
        }else{
          meldung.className="wmeldung fehler";
          meldung.textContent=(a && a.msg)?("Ging nicht: "+a.msg):"Ging nicht – bitte später noch einmal.";
        }
      })
      .catch(function(){
        meldung.className="wmeldung fehler";
        meldung.textContent="Keine Verbindung – bitte später noch einmal.";
      });
  });
})();

/* ---- Aktualisieren ----
   Der Knopf ist ein Link auf dieselbe Seite, das genuegt zum Neuladen. Hier wird
   nur zweierlei ergaenzt:
   - der Cache uebergangen (im Vollbild haelt Safari Seiten sonst gern fest),
   - und daneben steht, wie alt die Zahlen sind, damit man sieht, ob Neuladen
     ueberhaupt etwas bringt. Der Abruf am Fuetterungsrechner laeuft alle 39
     Minuten von allein. */
(function(){
  var knopf=document.getElementById("knopf-neu"), text=document.getElementById("frisch-text");
  if(!knopf){return;}
  knopf.addEventListener("click",function(e){
    e.preventDefault();
    knopf.classList.add("laeuft");
    text.textContent="Wird geladen …";
    location.reload();
  });
  // "Stand 17.08.2026 16:56" -> wie lange ist das her?
  var m=/(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})/.exec(daten.stand||"");
  if(m){
    var dann=new Date(+m[3],+m[2]-1,+m[1],+m[4],+m[5]);
    var min=Math.round((Date.now()-dann.getTime())/60000);
    if(min>=0&&min<24*60){
      text.textContent=min<1?"gerade eben geholt":(min===1?"vor 1 Minute geholt":"vor "+min+" Minuten geholt");
    }
  }
})();
JS;
}

/* ==================== Ersteinrichtung ====================
 *
 * Einstellungen -> HOCO-Pferdeseiten.
 *
 * Die Seite hat zwei Aufgaben. Erstens das Geheimnis: es wird hier erzeugt und
 * hier angezeigt - der einzige Ort, an dem es je zu sehen ist. Zweitens die
 * drei Werte, die im Add-on eingetragen werden muessen (Schnittstelle,
 * Link-Basis, Geheimnis); die stehen zum Kopieren bereit, statt dass sie
 * jemand aus der Dokumentation zusammensuchen muss.
 *
 * Dazu ein Statusblock: kommen ueberhaupt Zahlen an, und wie alt sind sie?
 * Ohne den sieht eine falsch eingerichtete Seite genauso aus wie eine, an der
 * das Add-on einfach noch nichts geschickt hat. */

add_action('admin_menu', function () {
    add_options_page(
        'HOCO-Pferdeseiten', 'HOCO-Pferdeseiten', 'manage_options',
        'hoco-pferdeseiten', 'hoco_admin_seite'
    );
});

/* Direkter Weg aus der Plugin-Liste in die Einrichtung. */
add_filter('plugin_action_links_' . plugin_basename(__FILE__), function ($links) {
    $url = admin_url('options-general.php?page=hoco-pferdeseiten');
    array_unshift($links, '<a href="' . esc_url($url) . '">Einrichtung</a>');
    return $links;
});

/* Solange kein Geheimnis gesetzt ist, nimmt die Seite nichts an. Das darf man
   nicht uebersehen - sonst sucht man den Fehler spaeter im Add-on. */
add_action('admin_notices', function () {
    if (!current_user_can('manage_options') || hoco_secret() !== '') {
        return;
    }
    $url = admin_url('options-general.php?page=hoco-pferdeseiten');
    echo '<div class="notice notice-warning"><p><b>HOCO-Pferdeseiten:</b> '
       . 'Noch kein gemeinsames Geheimnis - die Seite nimmt bis dahin keine '
       . 'Zahlen an. <a href="' . esc_url($url) . '">Jetzt einrichten</a>.'
       . '</p></div>';
});

/* Formular der Einrichtungsseite. Gibt die Meldung zurueck, die oben auf der
   Seite steht - oder einen leeren String, wenn nichts geschickt wurde. */
function hoco_admin_speichern() {
    if (empty($_POST['hoco_aktion']) || !current_user_can('manage_options')) {
        return '';
    }
    check_admin_referer('hoco_einrichtung');
    $aktion = sanitize_text_field(wp_unslash($_POST['hoco_aktion']));

    if ($aktion === 'geheimnis') {
        if (hoco_secret_quelle() !== '' && strpos(hoco_secret_quelle(), 'wp-config') === 0) {
            return '<div class="notice notice-warning"><p>Das Geheimnis steht in '
                 . 'der wp-config.php und hat dort Vorrang. Zum Wechseln dort '
                 . 'aendern.</p></div>';
        }
        update_option('hoco_secret', wp_generate_password(32, false, false));
        return '<div class="notice notice-success"><p>Neues Geheimnis erzeugt. '
             . 'Es muss jetzt <b>auch im Add-on</b> eingetragen werden - bis '
             . 'dahin kommen keine Zahlen mehr an.</p></div>';
    }

    if ($aktion === 'stall') {
        $roh = isset($_POST['hoco_stall']) ? wp_unslash($_POST['hoco_stall']) : '';
        $name = sanitize_text_field($roh);
        update_option('hoco_stall', $name);
        return '<div class="notice notice-success"><p>Name des Betriebs '
             . 'gespeichert.</p></div>';
    }

    if ($aktion === 'update') {
        delete_transient('hoco_release');
        $release = hoco_release(true);
        if (!$release) {
            return '<div class="notice notice-error"><p>GitHub war nicht '
                 . 'erreichbar. Spaeter noch einmal versuchen.</p></div>';
        }
        if (version_compare($release['version'], hoco_version(), '>')) {
            return '<div class="notice notice-success"><p>Fassung '
                 . esc_html($release['version']) . ' liegt bereit. Sie steht '
                 . 'jetzt unter <b>Dashboard &rarr; Aktualisierungen</b> und in '
                 . 'der Plugin-Liste.</p></div>';
        }
        return '<div class="notice notice-success"><p>Nichts Neues - '
             . esc_html(hoco_version()) . ' ist die aktuelle Fassung.</p></div>';
    }

    if ($aktion === 'seite') {
        $vorhanden = get_page_by_path('fuetterung');
        if ($vorhanden) {
            return '<div class="notice notice-warning"><p>Es gibt bereits eine '
                 . 'Seite <code>/fuetterung/</code>.</p></div>';
        }
        $id = wp_insert_post(array(
            'post_title'   => 'Fuetterung',
            'post_name'    => 'fuetterung',
            'post_status'  => 'publish',
            'post_type'    => 'page',
            'post_content' => '[fuetterung]',
        ));
        if (!$id || is_wp_error($id)) {
            return '<div class="notice notice-error"><p>Die Seite liess sich '
                 . 'nicht anlegen.</p></div>';
        }
        return '<div class="notice notice-success"><p>Seite '
             . '<code>/fuetterung/</code> angelegt. Sie ist die Link-Basis fuer '
             . 'die Pferdeseiten.</p></div>';
    }

    return '';
}

/* Eine Zeile im Block "Werte fuers Add-on": Beschriftung, Wert zum Kopieren. */
function hoco_admin_wertzeile($titel, $wert, $hinweis = '') {
    if ($wert === '') {
        $feld = '<i>noch nicht vorhanden</i>';
    } else {
        $feld = '<input type="text" readonly onclick="this.select()" '
              . 'value="' . esc_attr($wert) . '" '
              . 'style="width:100%;max-width:520px;font-family:monospace">';
    }
    return '<tr><th scope="row">' . esc_html($titel) . '</th><td>' . $feld
         . ($hinweis ? '<p class="description">' . $hinweis . '</p>' : '')
         . '</td></tr>';
}

function hoco_admin_seite() {
    if (!current_user_can('manage_options')) {
        return;
    }
    $meldung = hoco_admin_speichern();

    $secret  = hoco_secret();
    $quelle  = hoco_secret_quelle();
    $daten   = hoco_daten();
    $keys    = hoco_keys();
    $pferde  = isset($daten['pferde']) && is_array($daten['pferde'])
             ? count($daten['pferde']) : 0;
    $stand   = isset($daten['stand']) ? (string) $daten['stand'] : '';
    $wuensche = hoco_wuensche_laden();
    $offen   = 0;
    foreach ($wuensche as $w) {
        if (isset($w['status']) && $w['status'] === 'offen') {
            $offen++;
        }
    }

    echo '<div class="wrap"><h1>HOCO-Pferdeseiten</h1>';
    echo '<p>Gegenstueck zum Add-on <b>HOCO-Abruf</b> in Home Assistant. Diese '
       . 'Seite nimmt die Fuetterungszahlen entgegen und zeigt jedem Einsteller '
       . 'die Seite seines Pferds.</p>';
    echo $meldung;

    /* ---- Schritt 1: Geheimnis ---- */
    echo '<h2>1. Gemeinsames Geheimnis</h2>';
    if ($secret === '') {
        echo '<p>Noch keines gesetzt. Ohne Geheimnis weist die Seite jeden '
           . 'Push ab - das ist Absicht, damit eine frisch installierte Seite '
           . 'nicht offen steht.</p>';
    } else {
        echo '<p>Gesetzt, Quelle: <b>' . esc_html($quelle) . '</b>. Derselbe '
           . 'Wert muss im Add-on unter <code>website_secret</code> stehen.</p>';
    }
    echo '<form method="post">';
    wp_nonce_field('hoco_einrichtung');
    echo '<input type="hidden" name="hoco_aktion" value="geheimnis">';
    echo '<p><button class="button button-primary" '
       . 'onclick="return confirm(\'Neues Geheimnis erzeugen? Bis es auch im '
       . 'Add-on steht, kommen keine Zahlen mehr an.\')">'
       . ($secret === '' ? 'Geheimnis erzeugen' : 'Neues Geheimnis erzeugen')
       . '</button></p></form>';

    /* ---- Schritt 2: Name des Betriebs ---- */
    echo '<h2>2. Name des Betriebs</h2>';
    echo '<p>Steht im Kopf jeder Pferdeseite. Leer lassen heisst: der Name der '
       . 'Website (<code>' . esc_html(get_bloginfo('name')) . '</code>).</p>';
    echo '<form method="post">';
    wp_nonce_field('hoco_einrichtung');
    echo '<input type="hidden" name="hoco_aktion" value="stall">';
    echo '<p><input type="text" name="hoco_stall" class="regular-text" value="'
       . esc_attr(get_option('hoco_stall', '')) . '" '
       . 'placeholder="Aktivstall Musterhof"> '
       . '<button class="button">Speichern</button></p></form>';

    /* ---- Schritt 3: Werte fuers Add-on ---- */
    echo '<h2>3. Diese drei Werte ins Add-on eintragen</h2>';
    echo '<p>In Home Assistant unter <b>HOCO-Abruf &rarr; Ersteinrichtung</b> '
       . '(oder in der Konfiguration des Add-ons).</p>';
    echo '<table class="form-table" role="presentation">';
    echo hoco_admin_wertzeile('Schnittstelle (website_api)',
        rest_url('hoco/v1'),
        'Nimmt die Zahlen entgegen und beantwortet Rueckfragen des Add-ons.');
    echo hoco_admin_wertzeile('Link-Basis (website_link)',
        home_url('/fuetterung/?k='),
        'Unter dieser Adresse erreichen die Einsteller ihre Pferdeseite. Es '
       . 'geht jede Seite der Website - der Schluessel <code>?k=</code> '
       . 'entscheidet, nicht der Pfad. Voraussetzung ist nur, dass die Seite '
       . 'existiert.');
    echo hoco_admin_wertzeile('Geheimnis (website_secret)', $secret,
        $quelle && strpos($quelle, 'wp-config') === 0
            ? 'Steht in der wp-config.php.'
            : 'Nur hier sichtbar. Wird es neu erzeugt, muss es auch im Add-on '
            . 'neu eingetragen werden.');
    echo '</table>';

    echo '<form method="post">';
    wp_nonce_field('hoco_einrichtung');
    echo '<input type="hidden" name="hoco_aktion" value="seite">';
    echo '<p><button class="button">Seite <code>/fuetterung/</code> anlegen'
       . '</button> <span class="description">Legt eine Seite mit dem '
       . 'Kurzcode <code>[fuetterung]</code> an - die Uebersicht fuers '
       . 'Hofbuero und zugleich die Link-Basis oben.</span></p></form>';

    /* ---- Schritt 4: Kommt etwas an? ---- */
    echo '<h2>4. Steht die Verbindung?</h2>';
    echo '<table class="widefat striped" style="max-width:640px"><tbody>';
    echo '<tr><td><b>Zuletzt empfangen</b></td><td>'
       . ($stand !== '' ? esc_html($stand)
                        : '<i>noch nichts angekommen</i>') . '</td></tr>';
    echo '<tr><td><b>Pferde in den Daten</b></td><td>' . (int) $pferde
       . '</td></tr>';
    echo '<tr><td><b>Zugangsschluessel</b></td><td>' . count($keys)
       . '</td></tr>';
    echo '<tr><td><b>Offene Aenderungswuensche</b></td><td>' . (int) $offen
       . '</td></tr>';
    echo '</tbody></table>';

    if ($stand === '') {
        echo '<p>Kommt hier nichts an, dann in dieser Reihenfolge pruefen: '
           . 'Steht im Add-on dasselbe Geheimnis? Ist die Schnittstelle oben '
           . 'unveraendert uebernommen? Erreicht Home Assistant die Website '
           . 'ueberhaupt? Das Add-on hat fuer alle drei Fragen einen '
           . 'Pruefknopf.</p>';
    }

    /* ---- Schritt 5: Aktualisierung ---- */
    echo '<h2>5. Aktualisierung</h2>';
    $release = hoco_release();
    $hier = hoco_version();
    echo '<p>Installiert ist <b>' . esc_html($hier) . '</b>. ';
    if (!$release) {
        echo 'Ob es etwas Neueres gibt, war gerade nicht zu erfahren - GitHub '
           . 'antwortet nicht oder das Repository ist nicht erreichbar.</p>';
    } elseif (version_compare($release['version'], $hier, '>')) {
        echo 'Auf GitHub liegt <b>' . esc_html($release['version']) . '</b> '
           . 'bereit. Einspielen geht wie bei jedem Plugin: <b>Dashboard '
           . '&rarr; Aktualisierungen</b>.</p>';
    } else {
        echo 'Das ist zugleich die neueste Fassung.</p>';
    }
    echo '<form method="post">';
    wp_nonce_field('hoco_einrichtung');
    echo '<input type="hidden" name="hoco_aktion" value="update">';
    echo '<p><button class="button">Jetzt nach einer neuen Fassung sehen'
       . '</button> <span class="description">Sonst wird zwoelf Stunden lang '
       . 'der zuletzt geholte Stand verwendet.</span></p></form>';

    echo '</div>';
}

/* ==================== Aktualisierung ueber GitHub ====================
 *
 * WordPress sucht Updates von Haus aus nur auf wordpress.org. Dieses Plugin
 * steht dort nicht, also fragt es selbst bei GitHub nach: gibt es eine
 * Veroeffentlichung mit einer hoeheren Versionsnummer, taucht sie unter
 * Dashboard -> Aktualisierungen auf und laesst sich mit einem Klick
 * einspielen - wie jedes andere Plugin.
 *
 * Geholt wird das ZIP, das an die Veroeffentlichung angehaengt ist. Es enthaelt
 * den Ordner hoco-pferdeseiten/ und passt damit ueber die vorhandene
 * Installation. Fehlt so ein Anhang, wird das von GitHub erzeugte Quell-ZIP
 * genommen; dessen Ordner heisst anders, deshalb benennt
 * hoco_update_ordner() ihn beim Einspielen um. Ohne das entstuende bei jedem
 * Update ein neuer Plugin-Ordner.
 *
 * Die Antwort wird zwoelf Stunden zwischengespeichert. GitHub laesst ohne
 * Anmeldung 60 Anfragen je Stunde zu, und WordPress fragt oefter, als man
 * denkt. */

define('HOCO_GITHUB', 'jjuuzzii/hoco-abruf');
define('HOCO_SLUG', 'hoco-pferdeseiten');

/* Die Version aus dem eigenen Dateikopf - eine Stelle, kein zweiter Wert,
   der auseinanderlaufen kann. */
function hoco_version() {
    $d = get_file_data(__FILE__, array('Version' => 'Version'), 'plugin');
    return isset($d['Version']) ? $d['Version'] : '0';
}

/* Neueste Veroeffentlichung auf GitHub -> array(version, zip, notizen, url)
   oder null. */
function hoco_release($frisch = false) {
    if (!$frisch) {
        $gemerkt = get_transient('hoco_release');
        if ($gemerkt !== false) {
            return $gemerkt ? $gemerkt : null;
        }
    }
    $antwort = wp_remote_get(
        'https://api.github.com/repos/' . HOCO_GITHUB . '/releases/latest',
        array('timeout' => 15, 'headers' => array(
            'Accept'     => 'application/vnd.github+json',
            'User-Agent' => HOCO_SLUG,
        ))
    );
    if (is_wp_error($antwort) || wp_remote_retrieve_response_code($antwort) !== 200) {
        // Auch der Fehlschlag wird gemerkt, sonst rennt jede Seitenladung
        // erneut ins Leere. Eine Stunde, dann wird wieder nachgesehen.
        set_transient('hoco_release', '', HOUR_IN_SECONDS);
        return null;
    }
    $d = json_decode(wp_remote_retrieve_body($antwort), true);
    if (!is_array($d) || empty($d['tag_name'])) {
        set_transient('hoco_release', '', HOUR_IN_SECONDS);
        return null;
    }

    // Angehaengtes ZIP bevorzugen, sonst das Quell-ZIP von GitHub.
    $zip = '';
    if (!empty($d['assets']) && is_array($d['assets'])) {
        foreach ($d['assets'] as $a) {
            if (!empty($a['browser_download_url'])
                && substr($a['browser_download_url'], -4) === '.zip') {
                $zip = $a['browser_download_url'];
                break;
            }
        }
    }
    if ($zip === '' && !empty($d['zipball_url'])) {
        $zip = $d['zipball_url'];
    }

    $release = array(
        'version' => ltrim((string) $d['tag_name'], 'vV'),
        'zip'     => $zip,
        'notizen' => isset($d['body']) ? (string) $d['body'] : '',
        'url'     => isset($d['html_url']) ? (string) $d['html_url']
                                           : 'https://github.com/' . HOCO_GITHUB,
        'datum'   => isset($d['published_at']) ? substr($d['published_at'], 0, 10) : '',
    );
    set_transient('hoco_release', $release, 12 * HOUR_IN_SECONDS);
    return $release;
}

/* Meldet WordPress, dass eine neuere Fassung bereitliegt. */
add_filter('site_transient_update_plugins', function ($transient) {
    if (!is_object($transient)) {
        return $transient;
    }
    $release = hoco_release();
    if (!$release || $release['zip'] === '') {
        return $transient;
    }
    $datei = plugin_basename(__FILE__);
    if (version_compare($release['version'], hoco_version(), '<=')) {
        // Nichts Neues - aber WordPress soll wissen, dass geprueft wurde.
        if (isset($transient->no_update)) {
            $transient->no_update[$datei] = (object) array(
                'slug'        => HOCO_SLUG,
                'plugin'      => $datei,
                'new_version' => hoco_version(),
                'url'         => $release['url'],
                'package'     => '',
            );
        }
        return $transient;
    }
    $transient->response[$datei] = (object) array(
        'slug'        => HOCO_SLUG,
        'plugin'      => $datei,
        'new_version' => $release['version'],
        'url'         => $release['url'],
        'package'     => $release['zip'],
        'tested'      => get_bloginfo('version'),
    );
    return $transient;
});

/* Der Kasten "Details anzeigen" in der Plugin-Liste. */
add_filter('plugins_api', function ($ergebnis, $aktion, $args) {
    if ($aktion !== 'plugin_information'
        || empty($args->slug) || $args->slug !== HOCO_SLUG) {
        return $ergebnis;
    }
    $release = hoco_release();
    if (!$release) {
        return $ergebnis;
    }
    return (object) array(
        'name'          => 'HOCO-Pferdeseiten',
        'slug'          => HOCO_SLUG,
        'version'       => $release['version'],
        'author'        => '<a href="https://github.com/' . HOCO_GITHUB . '">HOCO-Abruf</a>',
        'homepage'      => 'https://github.com/' . HOCO_GITHUB,
        'download_link' => $release['zip'],
        'last_updated'  => $release['datum'],
        'sections'      => array(
            'description' => 'Zeigt jedem Einsteller die Fuetterungszahlen '
                           . 'seines Pferds. Gegenstueck zum Home-Assistant-'
                           . 'Add-on HOCO-Abruf.',
            'changelog'   => $release['notizen'] !== ''
                           ? nl2br(esc_html($release['notizen']))
                           : 'Siehe die Veroeffentlichungen auf GitHub.',
        ),
    );
}, 10, 3);

/* Das ZIP von GitHub bringt womoeglich einen anders benannten Ordner mit
   (z. B. "jjuuzzii-hoco-abruf-a1b2c3"). Ohne Umbenennen landet das Plugin
   danach in einem neuen Verzeichnis und das alte bleibt liegen. */
add_filter('upgrader_source_selection', function ($quelle, $entfernt, $upgrader, $hook_extra = null) {
    if (empty($hook_extra['plugin']) || $hook_extra['plugin'] !== plugin_basename(__FILE__)) {
        return $quelle;
    }
    $soll = trailingslashit($entfernt) . HOCO_SLUG;
    if (untrailingslashit($quelle) === untrailingslashit($soll)) {
        return $quelle;
    }
    global $wp_filesystem;
    if ($wp_filesystem && $wp_filesystem->move(untrailingslashit($quelle),
                                               untrailingslashit($soll))) {
        return trailingslashit($soll);
    }
    return $quelle;
}, 10, 4);

/* Nach dem Aktualisieren ist der gemerkte Stand ueberholt. */
add_action('upgrader_process_complete', function ($upgrader, $extra) {
    if (isset($extra['type']) && $extra['type'] === 'plugin') {
        delete_transient('hoco_release');
    }
}, 10, 2);
