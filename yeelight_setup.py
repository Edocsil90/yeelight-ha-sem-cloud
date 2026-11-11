#!/usr/bin/env python3
"""
yeelight-setup - set up a Yeelight bulb for Home Assistant without the app or the cloud.

Steps performed:
  1. Find the bulb while it is in setup mode (its own Wi-Fi network) and read its token.
  2. Enable LAN control (developer mode).
  3. Send your Wi-Fi name and password to the bulb.
  4. Find the bulb on your network and check that LAN control (TCP 55443) works.

Only dependency: cryptography  (pip install cryptography)
License: MIT
"""

import argparse
import getpass
import hashlib
import ipaddress
import json
import locale
import os
import random
import socket
import struct
import sys
import time

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:  # pragma: no cover
    print("Missing dependency / Falta uma dependência: pip install cryptography")
    sys.exit(1)

__version__ = "1.0.0"

MIIO_PORT = 54321
YEELIGHT_PORT = 55443
SSDP_ADDR = ("239.255.255.250", 1982)
HELLO_PACKET = bytes.fromhex("21310020") + b"\xff" * 28
HIDDEN_TOKENS = (b"\x00" * 16, b"\xff" * 16)
MAX_LAN_REPLY = 64 * 1024
MAX_DISCOVERED = 32


# --------------------------------------------------------------------------- #
# Messages (English / Portuguese - Portugal)
# --------------------------------------------------------------------------- #

MESSAGES = {
    "en": {
        "title": "Yeelight setup for Home Assistant (no app, no cloud) v{v}",
        "intro": (
            "Before you start:\n"
            "  1. Factory-reset the bulb: switch it off and on 5 times in a row.\n"
            "     It flashes and creates its own Wi-Fi network (yeelink-light-...).\n"
            "  2. Connect this PC to that network.\n"
        ),
        "press_enter": "Press Enter when ready (Ctrl+C to quit)...",
        "step": "\n=== Step {n}/4: {name} ===",
        "s1": "Find the bulb and read the token",
        "s2": "Enable LAN control",
        "s3": "Connect the bulb to Wi-Fi",
        "s4": "Find the bulb on your network and test it",
        "searching": "Searching for the bulb...",
        "found_at": "[OK] Bulb found at {ip}",
        "not_found": "[!] Could not find the bulb automatically.",
        "multiple": "[!] More than one device in setup mode answered:",
        "choose": "Number of the bulb to use (Enter to quit): ",
        "bad_ip": "[!] Invalid IPv4 address.",
        "ask_ip": "Bulb IP address (usually the gateway of the yeelink network, see 'ipconfig'), or Enter to quit: ",
        "no_reply": "[!] No reply from {ip}.",
        "hidden_token": (
            "[X] The bulb did not reveal its token, so it is already set up.\n"
            "    Factory-reset it (off/on 5 times) and run this tool again."
        ),
        "model": "    Model: {model} | Firmware: {fw} | Hardware: {hw}",
        "not_yeelight": "[!] This does not look like a Yeelight bulb ({model}). Continue anyway? [y/N] ",
        "token_saved": "[OK] Token saved to {path}\n     Keep this file private and never publish it.",
        "token_save_fail": "[!] Could not save the token file: {err}",
        "token_show": "     Token: {token}",
        "lan_ok": "[OK] LAN control enabled.",
        "lan_unexpected": "[!] Unexpected reply: {res}",
        "comm_error": "[X] Communication error: {err}",
        "ask_ssid": "Wi-Fi name (SSID, 2.4 GHz): ",
        "ask_pwd": "Wi-Fi password (hidden): ",
        "empty": "[!] This field cannot be empty.",
        "ssid_warn": "[!] The SSID has special characters. Some bulbs fail with these.",
        "confirm_wifi": "Send the Wi-Fi settings (SSID: \"{ssid}\") to {model} at {ip}? [Y/n] ",
        "aborted": "Cancelled.",
        "wifi_ok": "[OK] Wi-Fi settings accepted by the bulb.",
        "wifi_timeout": (
            "[i] The bulb closed its network before replying. This is normal:\n"
            "    it usually means the settings were accepted."
        ),
        "wifi_error": "[X] The bulb rejected the Wi-Fi settings: {err}",
        "reconnect": (
            "Now reconnect this PC to your usual network.\n"
            "Tip: use the same network/VLAN as the bulb, otherwise the firewall may block the test."
        ),
        "discovering": "Looking for the bulb on the network (up to {s} s)...",
        "found_lan": "[OK] Bulb found at {ip}",
        "not_found_lan": "[!] The bulb did not answer the network discovery.",
        "ask_bulb_ip": "Bulb IP from your router's DHCP list (Enter to skip the test): ",
        "testing": "Testing LAN control on {ip}:{port}...",
        "test_ok": "[OK] LAN control is working (power: {power}).",
        "test_fail": (
            "[X] Could not connect to {ip}:{port} ({err}).\n"
            "    - Different VLAN? The firewall may be blocking it: test from the bulb's VLAN.\n"
            "    - Same VLAN? LAN control may be off: reset the bulb and run this tool again."
        ),
        "next": (
            "\nNext steps:\n"
            "  - Create a DHCP reservation for the bulb in your router.\n"
            "  - Different VLANs: allow Home Assistant -> bulb on TCP 55443.\n"
            "  - Optional: block the bulb's Internet access.\n"
            "  - Home Assistant: Settings > Devices & services > Add integration > Yeelight{ip_hint}."
        ),
        "ip_hint": " > {ip}",
        "done": "\nDone.",
        "exit": "Press Enter to close...",
        "yes": ("y", "yes"),
    },
    "pt": {
        "title": "Configuração Yeelight para o Home Assistant (sem app e sem cloud) v{v}",
        "intro": (
            "Antes de começar:\n"
            "  1. Reponha as definições de fábrica da lâmpada: desligue e ligue 5 vezes seguidas.\n"
            "     A lâmpada pisca e cria uma rede Wi-Fi própria (yeelink-light-...).\n"
            "  2. Ligue este PC a essa rede.\n"
        ),
        "press_enter": "Carregue em Enter quando estiver pronto (Ctrl+C para sair)...",
        "step": "\n=== Passo {n}/4: {name} ===",
        "s1": "Encontrar a lâmpada e ler o token",
        "s2": "Ativar o controlo LAN",
        "s3": "Ligar a lâmpada ao Wi-Fi",
        "s4": "Encontrar a lâmpada na sua rede e testá-la",
        "searching": "A procurar a lâmpada...",
        "found_at": "[OK] Lâmpada encontrada em {ip}",
        "not_found": "[!] Não foi possível encontrar a lâmpada automaticamente.",
        "multiple": "[!] Responderam vários dispositivos em modo de configuração:",
        "choose": "Número da lâmpada a usar (Enter para sair): ",
        "bad_ip": "[!] Endereço IPv4 inválido.",
        "ask_ip": "IP da lâmpada (normalmente o gateway da rede yeelink, veja com 'ipconfig'), ou Enter para sair: ",
        "no_reply": "[!] Sem resposta de {ip}.",
        "hidden_token": (
            "[X] A lâmpada não revelou o token, por isso já está configurada.\n"
            "    Reponha as definições de fábrica (desligar/ligar 5 vezes) e volte a executar esta ferramenta."
        ),
        "model": "    Modelo: {model} | Firmware: {fw} | Hardware: {hw}",
        "not_yeelight": "[!] Isto não parece uma lâmpada Yeelight ({model}). Continuar na mesma? [s/N] ",
        "token_saved": "[OK] Token guardado em {path}\n     Guarde este ficheiro em privado e nunca o publique.",
        "token_save_fail": "[!] Não foi possível guardar o ficheiro do token: {err}",
        "token_show": "     Token: {token}",
        "lan_ok": "[OK] Controlo LAN ativado.",
        "lan_unexpected": "[!] Resposta inesperada: {res}",
        "comm_error": "[X] Erro de comunicação: {err}",
        "ask_ssid": "Nome da rede Wi-Fi (SSID, 2,4 GHz): ",
        "ask_pwd": "Palavra-passe do Wi-Fi (não aparece no ecrã): ",
        "empty": "[!] Este campo não pode ficar vazio.",
        "ssid_warn": "[!] O SSID tem caracteres especiais. Algumas lâmpadas falham com estes caracteres.",
        "confirm_wifi": "Enviar as definições do Wi-Fi (SSID: \"{ssid}\") para {model} em {ip}? [S/n] ",
        "aborted": "Cancelado.",
        "wifi_ok": "[OK] A lâmpada aceitou as definições do Wi-Fi.",
        "wifi_timeout": (
            "[i] A lâmpada desligou a sua rede antes de responder. Isto é normal:\n"
            "    normalmente significa que as definições foram aceites."
        ),
        "wifi_error": "[X] A lâmpada recusou as definições do Wi-Fi: {err}",
        "reconnect": (
            "Agora volte a ligar este PC à sua rede habitual.\n"
            "Dica: use a mesma rede/VLAN da lâmpada, senão a firewall pode bloquear o teste."
        ),
        "discovering": "A procurar a lâmpada na rede (até {s} s)...",
        "found_lan": "[OK] Lâmpada encontrada em {ip}",
        "not_found_lan": "[!] A lâmpada não respondeu à descoberta na rede.",
        "ask_bulb_ip": "IP da lâmpada na lista DHCP do router (Enter para saltar o teste): ",
        "testing": "A testar o controlo LAN em {ip}:{port}...",
        "test_ok": "[OK] O controlo LAN está a funcionar (estado: {power}).",
        "test_fail": (
            "[X] Não foi possível ligar a {ip}:{port} ({err}).\n"
            "    - VLAN diferente? A firewall pode estar a bloquear: teste a partir da VLAN da lâmpada.\n"
            "    - Mesma VLAN? O controlo LAN pode estar desligado: reponha a lâmpada e repita."
        ),
        "next": (
            "\nPróximos passos:\n"
            "  - Crie uma reserva DHCP para a lâmpada no router.\n"
            "  - VLANs diferentes: permita Home Assistant -> lâmpada na porta TCP 55443.\n"
            "  - Opcional: bloqueie o acesso da lâmpada à Internet.\n"
            "  - Home Assistant: Definições > Dispositivos e serviços > Adicionar integração > Yeelight{ip_hint}."
        ),
        "ip_hint": " > {ip}",
        "done": "\nConcluído.",
        "exit": "Carregue em Enter para fechar...",
        "yes": ("s", "sim", "y", "yes"),
    },
}

LANG = "en"


def t(key, **kwargs):
    text = MESSAGES[LANG][key]
    return text.format(**kwargs) if kwargs else text


def detect_language():
    candidates = [os.environ.get(k, "") for k in ("LC_ALL", "LC_MESSAGES", "LANG")]
    try:
        candidates.append(locale.getlocale()[0] or "")
    except (ValueError, TypeError):
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if lang_id & 0x3FF == 0x16:  # LANG_PORTUGUESE
                return "pt"
        except Exception:
            pass
    for value in candidates:
        if value.lower().startswith(("pt", "portuguese")):
            return "pt"
    return "en"


# --------------------------------------------------------------------------- #
# miIO protocol (UDP 54321)
# --------------------------------------------------------------------------- #


class MiioError(Exception):
    """The device answered with an error."""


class MiioTimeout(Exception):
    """The device did not answer."""


def md5(data):
    return hashlib.md5(data).digest()


def parse_hello(data):
    """Return (device_id, timestamp, token) from a hello reply, or None."""
    if len(data) != 32 or data[:2] != b"\x21\x31":
        return None
    device_id = data[8:12]
    timestamp = struct.unpack(">I", data[12:16])[0]
    token = data[16:32]
    return device_id, timestamp, token


def token_is_visible(token):
    return token not in HIDDEN_TOKENS


def hello(ip, port=MIIO_PORT, timeout=3.0, attempts=3):
    """Send a hello packet to one IP. Return (device_id, timestamp, token) or None."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        for _ in range(attempts):
            try:
                sock.sendto(HELLO_PACKET, (ip, port))
                data, _addr = sock.recvfrom(1024)
            except (socket.timeout, OSError):
                continue
            parsed = parse_hello(data)
            if parsed:
                return parsed
    return None


def discover_broadcast(port=MIIO_PORT, timeout=3.0):
    """Broadcast a hello packet. Return {ip: (device_id, timestamp, token)}."""
    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        try:
            sock.sendto(HELLO_PACKET, ("255.255.255.255", port))
        except OSError:
            return found
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            parsed = parse_hello(data)
            if parsed:
                found[addr[0]] = parsed
                if len(found) >= MAX_DISCOVERED:
                    break
    return found


def guess_gateway():
    """Guess the gateway (x.y.z.1) of the network this PC is on."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            local_ip = sock.getsockname()[0]
    except OSError:
        return None
    if local_ip.startswith("127."):
        return None
    return ".".join(local_ip.split(".")[:3] + ["1"])


class MiioDevice:
    """Minimal miIO client: encrypted JSON commands over UDP."""

    def __init__(self, ip, token, port=MIIO_PORT, timeout=5.0):
        if len(token) != 16:
            raise ValueError("token must be 16 bytes")
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.token = token
        self.key = md5(token)
        self.iv = md5(self.key + token)
        self.device_id = None
        self.timestamp = None
        self.request_id = random.randint(1, 1000)

    # -- crypto -------------------------------------------------------------
    def _encrypt(self, plaintext):
        padder = padding.PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()
        encryptor = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).encryptor()
        return encryptor.update(padded) + encryptor.finalize()

    def _decrypt(self, ciphertext):
        decryptor = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()

    # -- packets ------------------------------------------------------------
    def build_packet(self, payload):
        encrypted = self._encrypt(payload)
        header = struct.pack(
            ">HHI4sI", 0x2131, 32 + len(encrypted), 0, self.device_id, self.timestamp
        )
        checksum = md5(header + self.token + encrypted)
        return header + checksum + encrypted

    def parse_packet(self, data):
        """Validate and decrypt a reply. Any malformed input raises MiioError."""
        if len(data) < 32 or data[:2] != b"\x21\x31":
            raise MiioError("invalid packet")
        length = struct.unpack(">H", data[2:4])[0]
        if length < 32 or length > len(data):
            raise MiioError("invalid packet length")
        data = data[:length]
        if md5(data[:16] + self.token + data[32:]) != data[16:32]:
            raise MiioError("checksum mismatch (wrong token?)")
        self.timestamp = struct.unpack(">I", data[12:16])[0]
        if len(data) == 32:
            return None
        try:
            plaintext = self._decrypt(data[32:]).rstrip(b"\x00")
            reply = json.loads(plaintext.decode("utf-8", errors="replace"))
        except ValueError as err:  # bad padding, block size or JSON
            raise MiioError("invalid reply: %s" % err)
        if not isinstance(reply, dict):
            raise MiioError("invalid reply")
        return reply

    # -- api ----------------------------------------------------------------
    def handshake(self):
        reply = hello(self.ip, self.port, timeout=self.timeout / 2)
        if not reply:
            raise MiioTimeout("no reply to handshake from %s" % self.ip)
        self.device_id, self.timestamp, _token = reply

    def send(self, method, params=None, retries=2):
        last_error = None
        for attempt in range(retries + 1):
            if self.device_id is None or attempt > 0:
                self.handshake()
            self.request_id += 100 if attempt else 1
            request = {
                "id": self.request_id,
                "method": method,
                "params": params if params is not None else [],
            }
            payload = json.dumps(request).encode("utf-8") + b"\x00"
            self.timestamp += 1
            packet = self.build_packet(payload)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout)
                try:
                    sock.sendto(packet, (self.ip, self.port))
                    data, _addr = sock.recvfrom(4096)
                except (socket.timeout, OSError) as err:
                    last_error = err
                    continue
            reply = self.parse_packet(data)
            if reply is None:
                last_error = MiioError("empty reply")
                continue
            if reply.get("id") != self.request_id:
                last_error = MiioError("reply id mismatch")
                continue
            if "error" in reply:
                raise MiioError(reply["error"])
            return reply.get("result")
        raise MiioTimeout(str(last_error))


# --------------------------------------------------------------------------- #
# Yeelight LAN protocol (SSDP 1982 + TCP 55443)
# --------------------------------------------------------------------------- #


def ssdp_discover(timeout=3.0):
    """Return a list of dicts with the headers of each Yeelight that answered."""
    message = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1982\r\n"
        'MAN: "ssdp:discover"\r\n'
        "ST: wifi_bulb\r\n\r\n"
    ).encode("ascii")
    results = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(0.5)
        try:
            sock.sendto(message, SSDP_ADDR)
        except OSError:
            return []
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            headers = {}
            for line in data.decode("utf-8", errors="replace").split("\r\n")[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
            headers["ip"] = addr[0]
            results[addr[0]] = headers
            if len(results) >= MAX_DISCOVERED:
                break
    return list(results.values())


def find_bulb_on_lan(device_id, total_seconds=60):
    """Repeat SSDP discovery until the bulb with this device id answers."""
    wanted = int.from_bytes(device_id, "big")
    end = time.monotonic() + total_seconds
    while time.monotonic() < end:
        for bulb in ssdp_discover(timeout=3.0):
            try:
                if int(bulb.get("id", "0"), 16) == wanted:
                    return bulb["ip"]
            except ValueError:
                continue
        time.sleep(2)
    return None


def check_lan_control(ip, port=YEELIGHT_PORT, timeout=4.0):
    """Connect to the Yeelight LAN port and read the power state."""
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        request = {"id": 1, "method": "get_prop", "params": ["power"]}
        sock.sendall(json.dumps(request).encode("ascii") + b"\r\n")
        buffer = b""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            chunk = sock.recv(1024)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > MAX_LAN_REPLY:
                break
            while b"\r\n" in buffer:
                line, buffer = buffer.split(b"\r\n", 1)
                try:
                    reply = json.loads(line)
                except ValueError:
                    continue
                if reply.get("id") == 1:
                    result = reply.get("result") or ["?"]
                    return result[0]
    return "?"


# --------------------------------------------------------------------------- #
# Interactive flow
# --------------------------------------------------------------------------- #


def valid_ip(text):
    try:
        return str(ipaddress.IPv4Address(text.strip()))
    except ValueError:
        return None


def clean(value, max_length=120):
    """Make text received from the network safe to print (no control characters)."""
    text = "".join(ch if ch.isprintable() else "?" for ch in str(value))
    return text if len(text) <= max_length else text[:max_length] + "..."


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def ask_yes(prompt, default):
    answer = ask(prompt).strip().lower()
    if not answer:
        return default
    return answer in t("yes")


def ssid_has_special_chars(ssid):
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
    return any(ch not in allowed for ch in ssid)


def save_token(model, device_id, token, ip):
    did_hex = device_id.hex()
    path = os.path.abspath("yeelight_token_%s.txt" % did_hex)
    content = (
        "# KEEP PRIVATE / GUARDAR EM PRIVADO\n"
        "model={model}\ndevice_id={did}\ntoken={token}\nsetup_ip={ip}\n"
    ).format(model=model, did=int(did_hex, 16), token=token.hex(), ip=ip)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)  # readable by the current user only
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def choose_candidate(candidates):
    print(t("multiple"))
    for number, (ip, reply) in enumerate(candidates, 1):
        print("  %d) %s (id %d)" % (number, ip, int.from_bytes(reply[0], "big")))
    while True:
        answer = ask(t("choose")).strip()
        if not answer:
            return None, None
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]


def step_find_bulb(args):
    print(t("searching"))
    if args.ip:
        reply = hello(args.ip, args.port)
        if reply:
            return args.ip, reply
        print(t("no_reply", ip=args.ip))
    else:
        found = discover_broadcast(args.port)
        # A bulb in setup mode reveals its token; already set up devices do not.
        candidates = [(ip, r) for ip, r in found.items() if token_is_visible(r[2])]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return choose_candidate(candidates)
        gateway = guess_gateway()
        if gateway:
            reply = hello(gateway, args.port)
            if reply:
                return gateway, reply
        if found:
            return next(iter(found.items()))
    print(t("not_found"))
    while True:
        answer = ask(t("ask_ip")).strip()
        if not answer:
            return None, None
        ip = valid_ip(answer)
        if not ip:
            print(t("bad_ip"))
            continue
        reply = hello(ip, args.port)
        if reply:
            return ip, reply
        print(t("no_reply", ip=ip))


def run(args):
    print(t("title", v=__version__))
    print()
    print(t("intro"))
    ask(t("press_enter"))

    # Step 1 -----------------------------------------------------------------
    print(t("step", n=1, name=t("s1")))
    ip, reply = step_find_bulb(args)
    if not ip:
        print(t("aborted"))
        return 1
    print(t("found_at", ip=ip))
    device_id, _ts, token = reply
    if not token_is_visible(token):
        print(t("hidden_token"))
        return 1

    device = MiioDevice(ip, token, port=args.port)
    try:
        info = device.send("miIO.info") or {}
    except (MiioError, MiioTimeout) as err:
        print(t("comm_error", err=clean(err)))
        return 1
    if not isinstance(info, dict):
        info = {}
    model = clean(info.get("model", "?"), 60)
    print(t("model", model=model, fw=clean(info.get("fw_ver", "?"), 40),
            hw=clean(info.get("hw_ver", "?"), 40)))
    if not model.startswith("yeelink.light") and not ask_yes(
        t("not_yeelight", model=model), default=False
    ):
        print(t("aborted"))
        return 1
    try:
        print(t("token_saved", path=save_token(model, device_id, token, ip)))
    except OSError as err:
        print(t("token_save_fail", err=err))
        print(t("token_show", token=token.hex()))

    # Step 2 -----------------------------------------------------------------
    print(t("step", n=2, name=t("s2")))
    try:
        result = device.send("set_ps", ["cfg_lan_ctrl", "1"])
    except (MiioError, MiioTimeout) as err:
        print(t("comm_error", err=clean(err)))
        return 1
    if result in (["ok"], "ok"):
        print(t("lan_ok"))
    else:
        print(t("lan_unexpected", res=clean(result)))

    # Step 3 -----------------------------------------------------------------
    print(t("step", n=3, name=t("s3")))
    ssid = args.ssid or ""
    while not ssid:
        ssid = ask(t("ask_ssid"))
        if not ssid:
            print(t("empty"))
    if ssid_has_special_chars(ssid):
        print(t("ssid_warn"))
    password = ""
    while not password:
        try:
            password = getpass.getpass(t("ask_pwd"))
        except EOFError:
            password = ""
        if not password:
            print(t("empty"))
    if not ask_yes(t("confirm_wifi", ssid=ssid, model=model, ip=ip), default=True):
        print(t("aborted"))
        return 1
    try:
        result = device.send(
            "miIO.config_router", {"ssid": ssid, "passwd": password, "uid": 0}, retries=0
        )
        print(t("wifi_ok") if result in (["ok"], "ok", 0, None) else t("lan_unexpected", res=clean(result)))
    except MiioTimeout:
        print(t("wifi_timeout"))
    except MiioError as err:
        print(t("wifi_error", err=clean(err)))
        return 1
    finally:
        password = None

    # Step 4 -----------------------------------------------------------------
    print(t("step", n=4, name=t("s4")))
    print(t("reconnect"))
    ask(t("press_enter"))
    bulb_ip = args.bulb_ip
    if not bulb_ip:
        print(t("discovering", s=args.wait))
        bulb_ip = find_bulb_on_lan(device_id, total_seconds=args.wait)
        if bulb_ip:
            print(t("found_lan", ip=bulb_ip))
        else:
            print(t("not_found_lan"))
            while True:
                answer = ask(t("ask_bulb_ip")).strip()
                bulb_ip = valid_ip(answer) if answer else None
                if bulb_ip or not answer:
                    break
                print(t("bad_ip"))
    if bulb_ip:
        print(t("testing", ip=bulb_ip, port=args.lan_port))
        try:
            power = check_lan_control(bulb_ip, args.lan_port)
            print(t("test_ok", power=clean(power, 20)))
        except OSError as err:
            print(t("test_fail", ip=bulb_ip, port=args.lan_port, err=err))

    print(t("next", ip_hint=t("ip_hint", ip=bulb_ip) if bulb_ip else ""))
    print(t("done"))
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Set up a Yeelight bulb for Home Assistant without the app or the cloud."
    )
    parser.add_argument("--lang", choices=("en", "pt"), help="interface language (default: auto)")
    parser.add_argument("--ip", help="bulb IP while in setup mode (default: auto-detect)")
    parser.add_argument("--ssid", help="Wi-Fi name (the password is always asked, hidden)")
    parser.add_argument("--bulb-ip", help="bulb IP on your network, skips discovery in step 4")
    parser.add_argument("--wait", type=int, default=60, help="seconds to look for the bulb in step 4")
    parser.add_argument("--port", type=int, default=MIIO_PORT, help=argparse.SUPPRESS)
    parser.add_argument("--lan-port", type=int, default=YEELIGHT_PORT, help=argparse.SUPPRESS)
    parser.add_argument("--no-pause", action="store_true", help="do not wait for Enter before closing")
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def main(argv=None):
    global LANG
    args = parse_args(argv)
    LANG = args.lang or detect_language()
    for name in ("ip", "bulb_ip"):
        value = getattr(args, name)
        if value and not valid_ip(value):
            print(t("bad_ip") + " --%s %s" % (name.replace("_", "-"), clean(value)))
            return 2
    try:
        code = run(args)
    except KeyboardInterrupt:
        print()
        print(t("aborted"))
        code = 130
    if getattr(sys, "frozen", False) and not args.no_pause:
        ask(t("exit"))
    return code


if __name__ == "__main__":
    sys.exit(main())
