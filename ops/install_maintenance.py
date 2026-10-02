#!/usr/bin/env python3
import argparse
from pathlib import Path
import plistlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--project', type=Path, required=True)
args = parser.parse_args()
project = args.project.resolve()
state = Path.home() / 'Library/Application Support/Wheel/Maintenance'
state.mkdir(parents=True, exist_ok=True, mode=0o700)
label = 'com.wahbun.wheel.maintenance'
path = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists():
    path.with_suffix('.plist.previous').write_bytes(path.read_bytes())
path.write_bytes(plistlib.dumps(dict(Label=label,
    ProgramArguments=[sys.executable, str(project / 'ops/maintenance.py'),
                      '--project', str(project), '--state', str(state)],
    WorkingDirectory=str(project), StartInterval=3600, RunAtLoad=True,
    ProcessType='Background', StandardOutPath='/dev/null', StandardErrorPath='/dev/null')))
path.chmod(0o600)
print('Maintenance LaunchAgent installed')
