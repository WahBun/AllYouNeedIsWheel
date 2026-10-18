#!/bin/zsh
# Forced-command entry for a dedicated renewal SSH key. Never install or launch.
set -eu
case "${SSH_ORIGINAL_COMMAND:-}" in
  check) wheel_mode=--check ;;
  renew) wheel_mode=--build-only ;;
  *) print -u2 'Use only "check" or "renew" with the renewal SSH key.'; exit 64 ;;
esac
wheel_script_dir=${0:A:h}
exec /usr/bin/python3 "$wheel_script_dir/renew_signing.py" "$wheel_mode"
