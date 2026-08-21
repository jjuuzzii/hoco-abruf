#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
#
# Start des HOCO-Abruf-Add-ons.
#
# Hier wird nichts mehr aus der Add-on-Konfiguration geholt: seit 0.41.0 fuehrt
# das Add-on seine Einstellungen selbst (/data/konfig.json) und liest sie bei
# jedem Zugriff frisch. Eine Aenderung im Panel gilt damit sofort - frueher
# musste dafuer das Add-on neu starten, weil Umgebungsvariablen sich zur
# Laufzeit nicht aendern.
set -euo pipefail

# Der Ingress-Port ist keine Einstellung, sondern eine Eigenschaft des Add-ons
# (config.yaml). Er gehoert deshalb weiter hierher.
export ABRUF_INGRESS_PORT="8099"

# SUPERVISOR_TOKEN stellt der Supervisor bereit (homeassistant_api: true).

bashio::log.info "HOCO-Abruf startet – Einstellungen im Add-on unter „Ersteinrichtung“."

cd /opt/fuetterungsabruf
exec python3 -m app.bot
