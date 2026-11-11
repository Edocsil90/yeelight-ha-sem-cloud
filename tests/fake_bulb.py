"""
Fake Yeelight bulb for tests: answers the miIO protocol (UDP) and the
Yeelight LAN protocol (TCP). Written separately from yeelight_setup.py
so the tests do not reuse the code they are checking.
"""

import hashlib
import json
import socket
import struct
import threading
import time

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _md5(data):
    return hashlib.md5(data).digest()


class FakeBulb:
    def __init__(self, token=bytes(range(16)), device_id=0x07F5E6A1, reveal_token=True,
                 drop_wifi_reply=False, model="yeelink.light.color2"):
        self.token = token
        self.device_id = device_id
        self.reveal_token = reveal_token
        self.drop_wifi_reply = drop_wifi_reply
        self.model = model
        self.start_ts = 1000
        self.received = []
        self.lan_control = False
        self.wifi = None
        self._stop = threading.Event()

        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.udp.settimeout(0.2)
        self.udp_port = self.udp.getsockname()[1]

        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp.bind(("127.0.0.1", 0))
        self.tcp.listen(1)
        self.tcp.settimeout(0.2)
        self.tcp_port = self.tcp.getsockname()[1]

        self._threads = [threading.Thread(target=self._udp_loop, daemon=True),
                         threading.Thread(target=self._tcp_loop, daemon=True)]

    # -- lifecycle -------------------------------------------------------------
    def __enter__(self):
        for thread in self._threads:
            thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        self.udp.close()
        self.tcp.close()

    # -- crypto ------------------------------------------------------------------
    def _key_iv(self):
        key = _md5(self.token)
        return key, _md5(key + self.token)

    def _encrypt(self, plaintext):
        key, iv = self._key_iv()
        padder = padding.PKCS7(128).padder()
        data = padder.update(plaintext) + padder.finalize()
        enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        return enc.update(data) + enc.finalize()

    def _decrypt(self, ciphertext):
        key, iv = self._key_iv()
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        data = dec.update(ciphertext) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(data) + unpadder.finalize()

    def _ts(self):
        return self.start_ts + int(time.monotonic() - self._t0)

    # -- miIO --------------------------------------------------------------------
    def _udp_loop(self):
        self._t0 = time.monotonic()
        while not self._stop.is_set():
            try:
                data, addr = self.udp.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if data == bytes.fromhex("21310020") + b"\xff" * 28:
                token = self.token if self.reveal_token else b"\xff" * 16
                reply = struct.pack(">HHII", 0x2131, 32, 0, self.device_id)
                reply += struct.pack(">I", self._ts()) + token
                self.udp.sendto(reply, addr)
                continue
            # Encrypted request: check checksum, decrypt, answer.
            if _md5(data[:16] + self.token + data[32:]) != data[16:32]:
                continue  # wrong token: a real device stays silent
            request = json.loads(self._decrypt(data[32:]).rstrip(b"\x00"))
            self.received.append(request)
            method = request["method"]
            if method == "miIO.info":
                result = {"model": self.model, "fw_ver": "2.0.6_0065", "hw_ver": "mw302"}
            elif method == "set_ps" and request["params"] == ["cfg_lan_ctrl", "1"]:
                self.lan_control = True
                result = ["ok"]
            elif method == "miIO.config_router":
                self.wifi = request["params"]
                if self.drop_wifi_reply:
                    continue
                result = ["ok"]
            else:
                result = None
            body = {"id": request["id"]}
            if result is None:
                body["error"] = {"code": -5001, "message": "invalid params"}
            else:
                body["result"] = result
            encrypted = self._encrypt(json.dumps(body).encode() + b"\x00")
            header = struct.pack(">HHII", 0x2131, 32 + len(encrypted), 0, self.device_id)
            header += struct.pack(">I", self._ts())
            self.udp.sendto(header + _md5(header + self.token + encrypted) + encrypted, addr)

    # -- Yeelight LAN ------------------------------------------------------------
    def _tcp_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                conn.settimeout(2)
                try:
                    line = conn.recv(1024).split(b"\r\n")[0]
                    request = json.loads(line)
                    conn.sendall(json.dumps({"id": request["id"], "result": ["on"]}).encode() + b"\r\n")
                except (OSError, ValueError):
                    pass
