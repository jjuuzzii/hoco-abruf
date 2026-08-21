#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
#
# Start des HOCO-Abruf-Add-ons. Optionen holen, als Umgebungsvariablen
# weiterreichen, dann den Bot ausführen (der startet WhatsApp-Empfang,
# Weboberfläche und den täglichen Datenabruf).
set -euo pipefail

export ABRUF_HOFBUERO_NOTIFY="$(bashio::config 'hofbuero_notify' 'notify.mobile_app_iphone')"
export ABRUF_TAKT_MINUTEN="$(bashio::config 'abruf_takt_minuten' '5')"
export ABRUF_LOG_STUFE="$(bashio::config 'log_stufe' 'info')"
export STALL_NAME="$(bashio::config 'stall_name' '')"

export HOCO_HOST="$(bashio::config 'hoco_host' '')"
export HOCO_VERZEICHNIS="$(bashio::config 'hoco_verzeichnis' '')"
export HOCO_BENUTZER="$(bashio::config 'hoco_benutzer' '')"
export HOCO_PASSWORT="$(bashio::config 'hoco_passwort' '')"

# Website (WordPress-Plugin): Link-Basis, Push-Endpunkt, geheimer Schluessel.
export WEBSITE_LINK="$(bashio::config 'website_link' '')"
export WEBSITE_API="$(bashio::config 'website_api' '')"
export WEBSITE_SECRET="$(bashio::config 'website_secret' '')"

# Ingress-Port (die Weboberfläche lauscht darauf; der Supervisor proxyt ihn).
export ABRUF_INGRESS_PORT="8099"

# SUPERVISOR_TOKEN kommt vom Supervisor selbst (homeassistant_api: true).

bashio::log.info "HOCO-Abruf startet – Auszug von ${HOCO_HOST:-<nicht gesetzt>}, Freigabe an ${ABRUF_HOFBUERO_NOTIFY}."

cd /opt/fuetterungsabruf
exec python3 -m app.bot
