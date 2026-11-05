"""Exercise the real X11 layout script against an in-memory display."""
from pathlib import Path
import runpy
import struct
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / 'ops/gateway-window-layout.py'


class Display:
    def __init__(self):
        self.windows = {20: (0, 0, 1024, 768), 10: (0, 0, 1024, 768)}
        self.names = {10: 'IBKR Gateway', 20: 'IBKR Gateway'}
        self.hidden = set()
        self.pending = bytearray()
        self.configured = []
        self.commands = []
        self.handshake = True
        self.fail_setup = False

    def reply(self, payload=b''):
        result = bytearray(32)
        result[0] = 1
        struct.pack_into('<I', result, 4, len(payload) // 4)
        return result + payload

    def write(self, packet):
        if self.handshake:
            self.handshake = False
            if self.fail_setup:
                self.pending += bytes(8)
                return
            body = bytearray(72)
            struct.pack_into('<I', body, 32, 1)
            struct.pack_into('<HH', body, 52, 1024, 768)
            header = bytearray(8)
            header[0] = 1
            struct.pack_into('<H', header, 6, len(body) // 4)
            self.pending += header + body
            return
        op = packet[0]
        self.commands.append(op)
        window = struct.unpack_from('<I', packet, 4)[0] if len(packet) >= 8 else None
        if op == 15:
            result = self.reply(struct.pack('<' + 'I' * len(self.windows), *self.windows))
            struct.pack_into('<H', result, 16, len(self.windows))
        elif op == 20:
            name = self.names.get(window, 'Login dialog').encode()
            result = self.reply(name + bytes(-len(name) % 4))
        elif op == 3:
            result = self.reply()
            result[26] = 0 if window in self.hidden else 2
        elif op == 14:
            result = self.reply()
            struct.pack_into('<hhHH', result, 12, *self.windows[window])
        elif op == 12:
            self.windows[window] = struct.unpack_from('<IIII', packet, 12)
            self.configured.append(window)
            return
        elif op == 43:
            result = self.reply()
        else:
            raise AssertionError(f'Unexpected X11 operation {op}')
        self.pending += result

    def read(self, fd, count):
        result = self.pending[:count]
        del self.pending[:count]
        return bytes(result)

    def run(self):
        self.handshake = True
        process = Mock()
        process.stdout.fileno.return_value = 99
        process.stdin.write.side_effect = self.write
        with patch('subprocess.Popen', return_value=process),                 patch('subprocess.check_output', side_effect=AssertionError('No container identity query needed')),                 patch('select.select', return_value=([process.stdout], [], [])),                 patch('os.read', side_effect=self.read):
            try:
                runpy.run_path(str(SCRIPT))
            finally:
                process.terminate.assert_called_once()
                process.wait.assert_called_once_with(timeout=2)


class GatewayWindowLayoutTests(unittest.TestCase):
    def test_same_windows_are_repaired_after_gateway_restores_overlapping_positions(self):
        display = Display()
        display.run()
        expected = {10: (0, 2, 505, 762), 20: (519, 2, 505, 762)}
        self.assertEqual(display.windows, expected)
        display.configured.clear()
        display.run()
        self.assertEqual(display.configured, [])
        # Daily auto-restart or a late saved-position callback reuses the IDs.
        display.windows[20] = display.windows[10]
        display.run()
        self.assertEqual(display.windows, expected)
        self.assertEqual(display.configured, [20])
        self.assertLessEqual(set(display.commands), {3, 12, 14, 15, 20, 43})

    def test_waits_for_both_gateway_windows_and_ignores_login_dialogs(self):
        display = Display()
        display.hidden.add(20)
        display.run()
        self.assertEqual(display.configured, [])
        display.hidden.clear()
        display.windows[30] = (100, 100, 300, 200)
        display.run()
        self.assertEqual(display.configured, [10, 20])
        self.assertEqual(display.windows[30], (100, 100, 300, 200))

    def test_connection_setup_failure_cleans_up_owned_transport(self):
        display = Display()
        display.fail_setup = True
        with self.assertRaises(RuntimeError):
            display.run()


if __name__ == '__main__':
    unittest.main()
