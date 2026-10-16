import unittest
from ops.build_backend_shortcut import build


class ShortcutTests(unittest.TestCase):
    def test_confirmation_and_deploy_share_the_same_preview(self):
        original = {'WFWorkflowActions': [{'WFWorkflowActionIdentifier': 'is.workflow.actions.runsshscript',
                     'WFWorkflowActionParameters': {'WFSSHHost': 'test.invalid', 'WFSSHUser': 'test'}}]}
        actions = build(original)['WFWorkflowActions']
        preview = actions[2]['WFWorkflowActionParameters']['UUID']
        for index in (3, 5):
            value = actions[index]['WFWorkflowActionParameters']['WFInput']
            self.assertEqual(value['WFSerializationType'], 'WFTextTokenAttachment')
            self.assertEqual(value['Value']['OutputUUID'], preview)
        self.assertEqual(actions[4]['WFWorkflowActionIdentifier'], 'is.workflow.actions.alert')
        self.assertEqual(actions[3]['WFWorkflowActionParameters']['WFDictionaryKey'], 'summary')
        self.assertEqual(actions[5]['WFWorkflowActionParameters']['WFDictionaryKey'], 'sha')
        command = actions[6]['WFWorkflowActionParameters']['WFSSHScript']['Value']
        self.assertEqual(command['string'], 'wheel-backend-deploy \ufffc')
        self.assertEqual(next(iter(command['attachmentsByRange'].values()))['OutputUUID'],
                         actions[5]['WFWorkflowActionParameters']['UUID'])
        self.assertFalse(any(a['WFWorkflowActionIdentifier'].endswith('.ask') for a in actions))
