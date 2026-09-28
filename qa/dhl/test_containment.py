"""Host-safe unit tests: no sockets, services, databases or provider calls."""

import errno
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from containment import verify
from sanitize import sanitize_reports


class ContainmentTests(unittest.TestCase):
    def probe(self, error, interfaces=None):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.connect.side_effect = error
        with patch(
            "containment.socket.if_nameindex", return_value=interfaces or [(1, "lo")]
        ), patch("containment.socket.socket", return_value=connection):
            return verify()

    def test_no_route_is_required_for_both_families(self):
        report = self.probe(OSError(errno.ENETUNREACH, "no route"))
        self.assertTrue(report["passed"])
        self.assertEqual(len(report["external_probes"]), 2)

    def test_ethernet_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.probe(OSError(errno.ENETUNREACH, "no route"), [(1, "lo"), (2, "eth0")])

    def test_successful_connection_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.probe(None)

    def test_timeout_and_refusal_are_not_proof(self):
        for code in (errno.ETIMEDOUT, errno.ECONNREFUSED):
            with self.subTest(code=code), self.assertRaises(RuntimeError):
                self.probe(OSError(code, "insufficient proof"))

    def test_reports_remove_private_payloads_but_keep_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.xml"
            path.write_text(
                '<testsuite failures="1"><testcase name="handoff"><failure message="private-token">tests/test_http.py:42 private-label</failure><system-out>private-body</system-out></testcase></testsuite>'
            )
            sanitize_reports(directory)
            report = path.read_text()
            self.assertNotIn("private-", report)
            self.assertIn("tests/test_http.py:42", report)
            self.assertIn('failures="1"', report)


if __name__ == "__main__":
    unittest.main()
