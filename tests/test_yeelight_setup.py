"""Run with:  python -m unittest discover -s tests -v"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yeelight_setup as ys  # noqa: E402
from fake_bulb import FakeBulb  # noqa: E402


class ProtocolTests(unittest.TestCase):
    def test_hello_reveals_token(self):
        with FakeBulb() as bulb:
            device_id, ts, token = ys.hello("127.0.0.1", bulb.udp_port)
            self.assertEqual(token, bulb.token)
            self.assertEqual(int.from_bytes(device_id, "big"), bulb.device_id)
            self.assertTrue(ys.token_is_visible(token))

    def test_hidden_token(self):
        with FakeBulb(reveal_token=False) as bulb:
            _, _, token = ys.hello("127.0.0.1", bulb.udp_port)
            self.assertFalse(ys.token_is_visible(token))

    def test_commands(self):
        with FakeBulb() as bulb:
            dev = ys.MiioDevice("127.0.0.1", bulb.token, port=bulb.udp_port)
            self.assertEqual(dev.send("miIO.info")["model"], "yeelink.light.color2")
            self.assertEqual(dev.send("set_ps", ["cfg_lan_ctrl", "1"]), ["ok"])
            self.assertTrue(bulb.lan_control)
            dev.send("miIO.config_router", {"ssid": "MyNet", "passwd": "secret", "uid": 0})
            self.assertEqual(bulb.wifi, {"ssid": "MyNet", "passwd": "secret", "uid": 0})

    def test_device_error(self):
        with FakeBulb() as bulb:
            dev = ys.MiioDevice("127.0.0.1", bulb.token, port=bulb.udp_port)
            with self.assertRaises(ys.MiioError):
                dev.send("unknown_method")

    def test_wrong_token_times_out(self):
        with FakeBulb() as bulb:
            dev = ys.MiioDevice("127.0.0.1", b"\x01" * 16, port=bulb.udp_port, timeout=1)
            with self.assertRaises(ys.MiioTimeout):
                dev.send("miIO.info", retries=0)

    def test_lan_check(self):
        with FakeBulb() as bulb:
            self.assertEqual(ys.check_lan_control("127.0.0.1", bulb.tcp_port), "on")

    def test_malformed_packets_never_crash(self):
        """Random or truncated replies must raise MiioError, never another exception."""
        import random
        dev = ys.MiioDevice("127.0.0.1", bytes(range(16)))
        rng = random.Random(1234)
        samples = [b"", b"\x21\x31", b"\x21\x31\x00\x10" + b"\x00" * 28]
        samples += [b"\x21\x31" + bytes(rng.randrange(256) for _ in range(rng.randrange(0, 200)))
                    for _ in range(3000)]
        for data in samples:
            try:
                dev.parse_packet(data)
            except ys.MiioError:
                pass

    def test_valid_checksum_bad_payload(self):
        """A packet with a valid checksum but broken encryption is rejected cleanly."""
        token = bytes(range(16))
        dev = ys.MiioDevice("127.0.0.1", token)
        body = b"\x01" * 20  # not a multiple of the AES block size
        header = ys.struct.pack(">HHI4sI", 0x2131, 32 + len(body), 0, b"\x00" * 4, 1)
        packet = header + ys.md5(header + token + body) + body
        with self.assertRaises(ys.MiioError):
            dev.parse_packet(packet)

    def test_clean_removes_control_chars(self):
        self.assertEqual(ys.clean("model\x1b[2J\r\nx"), "model?[2J??x")
        self.assertTrue(ys.clean("a" * 500).endswith("..."))

    def test_valid_ip(self):
        self.assertEqual(ys.valid_ip(" 192.168.1.5 "), "192.168.1.5")
        self.assertIsNone(ys.valid_ip("example.com"))
        self.assertIsNone(ys.valid_ip("192.168.1.300"))

    @unittest.skipIf(os.name == "nt", "POSIX permissions only")
    def test_token_file_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                path = ys.save_token("yeelink.light.color2", b"\x00\x00\x00\x01", b"\x01" * 16, "x")
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            finally:
                os.chdir(cwd)

    def test_ssid_special_chars(self):
        self.assertFalse(ys.ssid_has_special_chars("Home_IoT2"))
        self.assertTrue(ys.ssid_has_special_chars("FELD-IOT"))


class FlowTests(unittest.TestCase):
    def run_flow(self, bulb, answers, extra_args=()):
        args = ["--lang", "en", "--ip", "127.0.0.1", "--port", str(bulb.udp_port),
                "--bulb-ip", "127.0.0.1", "--lan-port", str(bulb.tcp_port), "--no-pause",
                *extra_args]
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.input", side_effect=answers), \
                mock.patch("getpass.getpass", return_value="secret"), redirect_stdout(out):
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                code = ys.main(args)
                token_files = [f for f in os.listdir(tmp) if f.startswith("yeelight_token_")]
            finally:
                os.chdir(cwd)
        return code, out.getvalue(), token_files

    def test_full_flow(self):
        with FakeBulb() as bulb:
            code, out, files = self.run_flow(bulb, ["", "MyNet", "", ""])
        self.assertEqual(code, 0, out)
        self.assertTrue(bulb.lan_control)
        self.assertEqual(bulb.wifi["ssid"], "MyNet")
        self.assertIn("LAN control is working", out)
        self.assertEqual(len(files), 1)

    def test_flow_when_bulb_drops_network(self):
        with FakeBulb(drop_wifi_reply=True) as bulb:
            code, out, _ = self.run_flow(bulb, ["", "MyNet", "", ""])
        self.assertEqual(code, 0, out)
        self.assertIn("closed its network", out)

    def test_choose_candidate(self):
        candidates = [("10.0.0.2", (b"\x00\x00\x00\x02", 0, b"\x01" * 16)),
                      ("10.0.0.3", (b"\x00\x00\x00\x03", 0, b"\x02" * 16))]
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=["9", "x", "2"]), redirect_stdout(out):
            ip, _ = ys.choose_candidate(candidates)
        self.assertEqual(ip, "10.0.0.3")

    def test_flow_non_yeelight_device_is_not_sent_wifi(self):
        with FakeBulb(model="evil\x1b[2J.device") as bulb:
            code, out, files = self.run_flow(bulb, ["", ""])
        self.assertEqual(code, 1)
        self.assertIsNone(bulb.wifi)
        self.assertNotIn("\x1b", out)
        self.assertEqual(files, [])

    def test_flow_already_configured(self):
        with FakeBulb(reveal_token=False) as bulb:
            code, out, _ = self.run_flow(bulb, [""])
        self.assertEqual(code, 1)
        self.assertIn("already set up", out)


if __name__ == "__main__":
    unittest.main()
