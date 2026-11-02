#!/bin/sh
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/python3 -B "$here/private_web_preview.py" --source "${1:-$here/..}" --share
