#!/usr/bin/env bash
# duckdns.sh — update your DuckDNS dynamic DNS record.
#
# Usage:
#   DUCKDNS_SUBDOMAINS=vault DUCKDNS_TOKEN=xxx ./duckdns.sh
#
# Cron (every 5 minutes):
#   */5 * * * * /home/<user>/vault/duckdns.sh >/dev/null 2>&1
set -euo pipefail

SUBDOMAIN="${DUCKDNS_SUBDOMAINS:-vault}"   # your subdomain (without .duckdns.org)
TOKEN="${DUCKDNS_TOKEN:-}"                 # your DuckDNS token

if [[ -z "$TOKEN" ]]; then
    echo "DUCKDNS_TOKEN is not set" >&2
    exit 1
fi

RESULT="$(curl -s "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${TOKEN}&ip=")"
echo "$(date '+%Y-%m-%d %H:%M:%S') duckdns(${SUBDOMAIN}): ${RESULT}"
