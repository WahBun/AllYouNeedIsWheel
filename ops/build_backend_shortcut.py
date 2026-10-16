#!/usr/bin/env python3
"""Build a two-branch Shortcut from a privately exported restart .wflow file.

Output contains the existing SSH host/user settings; keep it outside Git.
Sign with Apple's `shortcuts sign` and import through Shortcuts.
"""
import argparse
import copy
from pathlib import Path
import plistlib
import uuid


def uid():
    return str(uuid.uuid4()).upper()


def action(name, **params):
    return dict(WFWorkflowActionIdentifier='is.workflow.actions.' + name,
                WFWorkflowActionParameters=params)


def token(output, name, prefix=''):
    return {'WFSerializationType': 'WFTextTokenString', 'Value': {
        'string': prefix + '\ufffc', 'attachmentsByRange': {
            '{' + str(len(prefix)) + ', 1}': {'OutputUUID': output, 'Type': 'ActionOutput', 'OutputName': name}}}}


def build(original):
    result = copy.deepcopy(original)
    originals = original['WFWorkflowActions']
    ssh = next(a for a in originals if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.runsshscript')
    group, preview, summary, sha, deploy, restart = [uid() for _ in range(6)]
    labels = ['Deploy latest & Restart Backend', 'Restart Backend only']

    def connection(command, output):
        row = copy.deepcopy(ssh)
        row['WFWorkflowActionParameters'].update(WFSSHScript=command, UUID=output)
        # Explicit command text only; do not forward previous action output as stdin.
        row['WFWorkflowActionParameters'].pop('WFInput', None)
        return row

    result['WFWorkflowActions'] = [
        action('choosefrommenu', WFControlFlowMode=0, GroupingIdentifier=group,
               WFMenuPrompt='Wheel Backend', WFMenuItems=labels),
        action('choosefrommenu', WFControlFlowMode=1, GroupingIdentifier=group, WFMenuItemTitle=labels[0]),
        connection('wheel-backend-deploy-preview', preview),
        action('getvalueforkey', WFDictionaryKey='summary', WFInput=token(preview, 'Release preview'),
               WFGetDictionaryValueType='Value', UUID=summary),
        action('alert', WFAlertActionTitle='Deploy & Restart Backend?',
               WFAlertActionMessage=token(summary, 'Deployment summary')),
        action('getvalueforkey', WFDictionaryKey='sha', WFInput=token(preview, 'Release preview'),
               WFGetDictionaryValueType='Value', UUID=sha),
        connection(token(sha, 'Confirmed commit SHA', 'wheel-backend-deploy '), deploy),
        action('showresult', Text=token(deploy, 'Deployment result')),
        action('choosefrommenu', WFControlFlowMode=1, GroupingIdentifier=group, WFMenuItemTitle=labels[1]),
        action('alert', WFAlertActionTitle='Restart Backend only?',
               WFAlertActionMessage='Restart Backend without updating code. Continue only when no order request is pending. Gateway stays running.'),
        connection('wheel-backend-restart', restart),
        action('showresult', Text=token(restart, 'Restart result')),
        action('choosefrommenu', WFControlFlowMode=2, GroupingIdentifier=group),
    ]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_bytes(plistlib.dumps(build(plistlib.loads(args.source.read_bytes())), fmt=plistlib.FMT_BINARY))
