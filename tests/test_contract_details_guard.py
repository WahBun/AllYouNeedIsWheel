import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from ib_async import Contract, ContractDetails
from ib_async.wrapper import Wrapper, RequestError
from core.contract_details import install_contract_details_guard


class ContractDetailsGuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ib = SimpleNamespace()
        self.ib.wrapper = Wrapper(self.ib)
        self.wrapper = self.ib.wrapper
        self.wrapper._logger = Mock()
        install_contract_details_guard(self.ib)

    async def test_active_multirow_request_completes_unchanged(self):
        future = self.wrapper.startReq(1, Contract(conId=7))
        rows = [ContractDetails(contract=Contract(conId=7)), ContractDetails(contract=Contract(conId=8))]
        for row in rows:
            self.wrapper.contractDetails(1, row)
        self.assertFalse(future.done())
        self.wrapper.contractDetailsEnd(1)
        self.assertEqual(await future, rows)
        self.wrapper._logger.warning.assert_not_called()

    async def test_late_reply_cannot_mutate_completed_result_or_other_request(self):
        finished = self.wrapper.startReq(1)
        row = ContractDetails(contract=Contract(conId=7))
        self.wrapper.contractDetails(1, row)
        self.wrapper.contractDetailsEnd(1)
        current = self.wrapper.startReq(2)
        self.wrapper.contractDetails(1, ContractDetails(contract=Contract(conId=99)))
        self.wrapper.contractDetailsEnd(1)
        self.assertEqual(await finished, [row])
        self.assertNotIn(1, self.wrapper._results)
        self.assertEqual(self.wrapper._results[2], [])
        self.assertFalse(current.done())
        self.wrapper.contractDetailsEnd(2)
        self.assertEqual(await current, [])
        self.wrapper._logger.warning.assert_called_once()

    async def test_reset_orphan_is_not_recreated(self):
        old = self.wrapper.startReq(1)
        old.cancel()
        self.wrapper.reset()
        self.wrapper.contractDetails(1, ContractDetails())
        self.assertEqual(self.wrapper._results, {})
        self.assertEqual(self.wrapper._futures, {})
        self.assertTrue(old.cancelled())

    async def test_failed_request_stays_failed(self):
        future = self.wrapper.startReq(1)
        # Default SDK error handling ends failed reads with an empty result.
        self.wrapper._endReq(1)
        self.wrapper.contractDetails(1, ContractDetails())
        self.assertEqual(await future, [])
        failed = self.wrapper.startReq(2)
        error = RequestError(2, 200, 'No security definition')
        self.wrapper._endReq(2, error, success=False)
        with self.assertRaises(RequestError):
            await failed
        self.wrapper.contractDetails(2, ContractDetails())
        self.assertIs(failed.exception(), error)
        # Explicit SDK errors can retain an empty slot after retiring the
        # future; late details must not turn it into a usable result either.
        self.assertEqual(self.wrapper._results[2], [])

    async def test_timeout_does_not_reanimate_canceled_future(self):
        future = self.wrapper.startReq(1)
        future.cancel()
        self.wrapper.contractDetails(1, ContractDetails())
        self.wrapper.contractDetailsEnd(1)
        self.assertTrue(future.cancelled())
        self.assertNotIn(1, self.wrapper._results)
        self.assertNotIn(1, self.wrapper._futures)

    async def test_installation_is_per_instance_and_idempotent(self):
        guarded = self.wrapper.contractDetails
        install_contract_details_guard(self.ib)
        self.assertIs(self.wrapper.contractDetails, guarded)
        other = Wrapper(SimpleNamespace())
        with self.assertRaises(KeyError):
            other.contractDetails(1, ContractDetails())

    async def test_active_callback_errors_are_not_swallowed(self):
        original = Mock(side_effect=ValueError('Invalid active response'))
        self.wrapper.contractDetails = original
        original._wheel_late_details_guard = False
        install_contract_details_guard(self.ib)
        future = self.wrapper.startReq(1)
        with self.assertRaisesRegex(ValueError, 'Invalid active response'):
            self.wrapper.contractDetails(1, ContractDetails())
        self.wrapper.contractDetailsEnd(1)
        self.assertEqual(await future, [])
