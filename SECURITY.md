# Security policy

## Reporting a vulnerability

Please do not open a public issue. Use **Security → Report a vulnerability** on this repository to report it privately.

## Scope

- `yeelight_setup.py` and the `yeelight-setup.exe` built from it by GitHub Actions.
- The setup guides (`README.md`, `README.pt.md`).

## Design notes

- The tool only talks to devices on the local network: miIO (UDP 54321), Yeelight discovery (UDP 1982) and Yeelight LAN control (TCP 55443). It never contacts the Internet.
- The Wi‑Fi password is read with a hidden prompt, never from the command line, and is not written to disk.
- The bulb token is saved to `yeelight_token_<id>.txt`, readable only by the current user on Linux and macOS. This file is listed in `.gitignore`.
- The miIO protocol uses MD5 and AES-128-CBC with a fixed IV derived from the token. These come from the device protocol and cannot be changed.
- Each release includes a SHA-256 file for the `.exe`.
