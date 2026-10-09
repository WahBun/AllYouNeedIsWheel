#!/usr/bin/env python3
"""Install the user-login LaunchAgent on the backend Mac, preserving its state."""
import argparse
from pathlib import Path
import plistlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--project', type=Path, required=True)
args = parser.parse_args()
project = args.project.resolve()
state = Path.home() / 'Library/Application Support/Wheel/PaperGatewayWatchdog'
state.mkdir(parents=True, exist_ok=True, mode=0o700)
logs = project / 'logs'
logs.mkdir(exist_ok=True)
label = 'com.wahbun.wheel.paper-gateway-watchdog'
path = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
path.parent.mkdir(parents=True, exist_ok=True)
contents = dict(Label=label, ProgramArguments=[sys.executable, str(project/'ops/paper_gateway_watchdog.py'),
    '--project', str(project), '--state-dir', str(state)],
    WorkingDirectory=str(project), StartInterval=60, RunAtLoad=True,
    ProcessType='Background', StandardOutPath=str(logs/'paper-gateway-watchdog.log'),
    StandardErrorPath=str(logs/'paper-gateway-watchdog-error.log'))
if path.exists():
    backup = path.with_suffix('.plist.previous')
    backup.write_bytes(path.read_bytes())
path.write_bytes(plistlib.dumps(contents))
path.chmod(0o600)
print(path)
