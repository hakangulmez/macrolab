#!/bin/sh
# Keep Chromium itself, including background services, on local transports only.
set -eu
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/sandbox-exec -f "$script_directory/loopback-only.sb" "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$@"
