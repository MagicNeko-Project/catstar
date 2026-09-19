"""Unit test suite for scripts/port.py."""

import unittest

from scripts.port import PORT_RANGES, choose_random_ports


class TestPortGenerator(unittest.TestCase):
    def test_choose_random_ports_ephemeral_default(self) -> None:
        ports = choose_random_ports(["ephemeral"], 5)
        self.assertEqual(len(ports), 5)
        self.assertEqual(len(set(ports)), 5)
        for p in ports:
            self.assertIn(p, PORT_RANGES["ephemeral"])

    def test_choose_random_ports_combined_ranges(self) -> None:
        ports = choose_random_ports(["privileged", "registered"], 10)
        self.assertEqual(len(ports), 10)
        self.assertEqual(len(set(ports)), 10)
        valid_ports = set(PORT_RANGES["privileged"]) | set(PORT_RANGES["registered"])
        for p in ports:
            self.assertIn(p, valid_ports)

    def test_choose_random_ports_exceeds_available(self) -> None:
        with self.assertRaises(ValueError):
            choose_random_ports(["privileged"], 2000)


if __name__ == "__main__":
    unittest.main()
