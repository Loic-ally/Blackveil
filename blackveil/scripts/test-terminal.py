#!/usr/bin/env python3
"""Regression tests for the verifier's PTY framing, without a running lab."""
import importlib.util
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

spec = importlib.util.spec_from_file_location("chain", Path(__file__).with_name("verify-chain.py"))
chain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)


class TerminalTests(unittest.TestCase):
    def terminal(self):
        terminal = chain.Terminal.__new__(chain.Terminal)
        terminal.socket = Mock()
        terminal.buffered = bytearray()
        terminal.output = ""
        return terminal

    def test_echo_fragmentation_status_and_repeated_commands(self):
        terminal = self.terminal()
        frames = []

        def send(sock, line):
            # Real PTY echoes the command, including the separate printf args.
            tag = line.split("BV_BEGIN_ ", 1)[1].split(";", 1)[0]
            output = line + f"\r\nBV_BEGIN_{tag}\r\nresult\r\n\r\nBV_END_{tag}:7\r\n$ "
            frames.extend([(1, output[:53].encode(), bytearray()),
                           (0, output[53:].encode(), bytearray())])

        with patch.object(chain.vmverify, "send_websocket_text", side_effect=send), patch.object(
                chain.vmverify, "read_frame", side_effect=lambda *a: frames.pop(0)):
            for _ in range(2):
                self.assertEqual(terminal.run("printf result; exit 7"), (7, "result\n"))

    def test_deadline_on_silent_terminal(self):
        terminal = self.terminal()
        with patch.object(chain.vmverify, "send_websocket_text"), patch.object(
                chain.vmverify, "read_frame", side_effect=TimeoutError), patch.object(
                chain.time, "monotonic", side_effect=[0, 0, 2]):
            with self.assertRaisesRegex(AssertionError, "timed out"):
                terminal.run("sleep 99", timeout=1)

    def test_closed_terminal_is_failure(self):
        terminal = self.terminal()
        with patch.object(chain.vmverify, "send_websocket_text"), patch.object(
                chain.vmverify, "read_frame", return_value=(8, b"", bytearray())):
            with self.assertRaisesRegex(AssertionError, "terminal closed"):
                terminal.run("true")

    def test_nonzero_status_is_failure(self):
        terminal = self.terminal()
        terminal.run = Mock(return_value=(1, "permission denied"))
        with self.assertRaisesRegex(AssertionError, "exited 1"):
            terminal.ok("cat secret")


if __name__ == "__main__":
    unittest.main()
