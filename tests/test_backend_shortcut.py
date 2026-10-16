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
        self.assertEqual(actions[6]['WFWorkflowActionIdentifier'], 'is.workflow.actions.choosefrommenu')
        self.assertEqual(actions[6]['WFWorkflowActionParameters']['WFMenuItems'],
                         ['Deploy only', 'Deploy & Restart Backend'])
        for index, prefix in ((8, 'wheel-backend-deploy-only '), (11, 'wheel-backend-deploy ')):
            command = actions[index]['WFWorkflowActionParameters']['WFSSHScript']['Value']
            self.assertEqual(command['string'], prefix + '\ufffc')
            self.assertEqual(next(iter(command['attachmentsByRange'].values()))['OutputUUID'],
                             actions[5]['WFWorkflowActionParameters']['UUID'])
        self.assertNotEqual(actions[0]['WFWorkflowActionParameters']['GroupingIdentifier'],
                            actions[6]['WFWorkflowActionParameters']['GroupingIdentifier'])
        self.assertFalse(any(a['WFWorkflowActionIdentifier'].endswith('.ask') for a in actions))
