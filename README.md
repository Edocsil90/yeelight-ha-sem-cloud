# Yeelight Color (yeelink.light.color2) in Home Assistant — no app, no cloud

**English** | [Português](README.pt.md)

This guide sets up a Yeelight Color bulb from the Windows command line. You get the token, enable LAN control and connect the bulb to Wi‑Fi **without the Yeelight or Mi Home app and without a Xiaomi account**. The bulb is then added to Home Assistant with the official **Yeelight** integration.

## Quick setup (recommended)

The `yeelight-setup` tool runs steps 3 to 6 of the manual guide for you. You only enter your Wi‑Fi name and password. It is available in two forms, so pick one:

### Option A — Windows executable (nothing to install)

1. Download `yeelight-setup.exe` from the [Releases](../../releases) page.
2. Factory-reset the bulb (step 1) and connect your PC to its network (step 2).
3. Double-click `yeelight-setup.exe` and follow the instructions.

Windows SmartScreen may warn that the app is unrecognised, because it is not signed. Click **More info → Run anyway**. Each release also includes a `.sha256` file, so you can check that the download matches the build made by GitHub Actions from this repository's code:

```
powershell (Get-FileHash yeelight-setup.exe -Algorithm SHA256).Hash
```

### Option B — Python script

Requires Python 3.9 or later.

```
pip install -r requirements.txt
python yeelight_setup.py
```

### What the tool does

1. Finds the bulb on its setup network and reads the token, then saves it to `yeelight_token_<id>.txt` in the current folder.
2. Enables LAN control.
3. Asks for your Wi‑Fi name and password (the password is hidden as you type) and sends them to the bulb. It knows the "bulb closed its network" case is normal.
4. Asks you to reconnect to your usual network, finds the bulb and tests TCP port 55443.

It is in English or Portuguese, depending on the Windows language. You can force one with `--lang en` or `--lang pt`. Run `yeelight_setup.py --help` to see all options.

The tool does not change your router or firewall: create the rules in step 7 yourself.

> The tool talks to the bulb directly over the local network, using the miIO protocol (UDP 54321) and the Yeelight LAN protocol (TCP 55443). Nothing is sent to the Internet. Its only dependency is `cryptography`.

## Tested with

| Field | Value |
|---|---|
| Model | `yeelink.light.color2` |
| Firmware | `2.0.6_0065` |
| Hardware | `mw302` |
| OS | Windows (cmd / PowerShell) |

Other older `yeelink.light.*` models should work the same way, but have not been tested.

## Manual setup — requirements

- [Node.js](https://nodejs.org/) and the `miio` CLI:
  ```
  npm install -g miio
  ```
- Python 3 and the [python-miio](https://github.com/rytilahti/python-miio) library:
  ```
  pip install python-miio
  ```
- A **2.4 GHz** Wi‑Fi network using **WPA2**. Avoid WPA3 and SSIDs with special characters.

## Manual setup — steps

### 1. Factory-reset the bulb

Switch the bulb off and on 5 times in a row. It flashes and restarts in setup mode, creating its own Wi‑Fi network named something like `yeelink-light-color2_miapXXXX`.

### 2. Connect your PC to the bulb's network

On Windows, connect to the `yeelink-light-color2_miapXXXX` network. The bulb is at that network's gateway address. To find it, run `ipconfig` and look for *Default Gateway*. This guide calls that address `<AP_IP>`.

### 3. Get the token

```
miio inspect <AP_IP>
```

Example output:

```
Device ID: <DEVICE_ID>
Model info: yeelink.light.color2
Address: <AP_IP>
Token: <TOKEN> via auto-token
Support: At least generic

Firmware version: 2.0.6_0065
Hardware version: mw302

WiFi: Not Connected
```

The token is revealed automatically (`auto-token`) only while the bulb has not been set up yet. Save it, because you need it in the next step.

> ⚠️ The token gives full control of the bulb. Never publish it.

### 4. Enable LAN control (developer mode)

Do this step **before** connecting the bulb to Wi‑Fi:

```
python -c "from miio import Device; d=Device('<AP_IP>','<TOKEN>'); print(d.send('set_ps',['cfg_lan_ctrl','1']))"
```

Expected response:

```
['ok']
```

Alternatively, with the python-miio CLI:

```
miiocli yeelight --ip <AP_IP> --token <TOKEN> set_developer_mode 1
```

### 5. Connect the bulb to Wi‑Fi

```
miio configure <AP_IP> --ssid "<SSID>" --passwd "<PASSWORD>"
```

**Note:** this command may return

```
ERROR  Encountered an error while updating wireless
Failed updating wireless
```

even though the setup worked. The bulb shuts down its own network as soon as it accepts the credentials, so the CLI loses the connection before it gets a confirmation. Reconnect your PC to your usual network and look for the bulb in your router's list of DHCP clients.

### 6. Check that LAN control is enabled

With your PC back on your usual network, use the IP the router gave the bulb (`<BULB_IP>`):

```
powershell Test-NetConnection <BULB_IP> -Port 55443
```

Expected result:

```
RemoteAddress    : <BULB_IP>
RemotePort       : 55443
TcpTestSucceeded : True
```

Port `55443` is used by the Yeelight LAN protocol. If the connection is accepted, developer mode is on.

> Run this test from a PC on the **same VLAN as the bulb**. If your firewall blocks traffic between VLANs, a test from another VLAN returns `TcpTestSucceeded : False`, even when LAN control is enabled.

### 7. Firewall rules (Home Assistant and bulb on different VLANs)

Example with UniFi, with the bulb on an IoT VLAN and Home Assistant on another VLAN:

| Rule | Source | Destination | Port | Action |
|---|---|---|---|---|
| HA → Yeelight | Home Assistant IP | `<BULB_IP>` (or a group with your Yeelight bulbs) | TCP `55443` | Allow |
| Yeelight → Internet | `<BULB_IP>` (or the group) | Internet / External | All | Block |

- The first rule lets Home Assistant control the bulb. Reply traffic is allowed if the firewall is *stateful* (UniFi is).
- The second rule is optional but recommended: the bulb keeps working locally and stops getting automatic updates from the cloud.
- So that nothing depends on the IP changing, create a **DHCP reservation** for each bulb.

### 8. Add the bulb to Home Assistant

In Home Assistant, go to **Settings → Devices & services**.

- **Same VLAN:** the bulb is usually discovered automatically.
- **Different VLAN:** automatic discovery uses multicast and does not cross VLANs. Use **Add integration → Yeelight** and enter `<BULB_IP>`.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `miio inspect` doesn't show the token | The bulb has already been set up. Factory-reset it (step 1). |
| `Failed updating wireless` | This may be a false error (see step 5). Check the router before trying again. |
| The bulb doesn't show up on the router | 5 GHz or WPA3 network, an SSID with special characters, or a wrong password. Reset the bulb and start again from step 1. |
| `TcpTestSucceeded : False` | If you tested from another VLAN, the firewall is blocking the traffic: repeat the test on the bulb's VLAN. If it fails on the same VLAN, LAN control is not enabled: repeat step 4 against `<BULB_IP>`. |
| Home Assistant doesn't discover the bulb | Discovery uses multicast and does not cross VLANs or subnets. Add the bulb manually by IP (step 8). |
| Home Assistant can't control the bulb | The firewall rule allowing traffic from HA to the bulb on TCP port 55443 is missing (step 7). |

## Security

- Yeelight LAN control has **no authentication**: any device on the same network can control the bulb. Put it on its own IoT VLAN and allow only Home Assistant traffic (step 7).
- Block the bulb's Internet access (step 7). This prevents automatic firmware updates, which have removed LAN control on some models.
- Before publishing logs, replace the token, Device ID, IPs, SSID and password with placeholders.
- During setup, the bulb's own Wi‑Fi network is **open** and the token travels on it in clear text, just like with the official apps. Someone within Wi‑Fi range during those few minutes could read the token and decrypt the Wi‑Fi password sent to the bulb. Do the setup at home and finish it quickly.
- If more than one device answers in setup mode, the tool asks which one to use. Before sending the Wi‑Fi password, it always shows the model and IP and asks you to confirm.
- The `yeelight_token_*.txt` files created by the tool are listed in `.gitignore`, so they are not committed by mistake.

## References

- [python-miio](https://github.com/rytilahti/python-miio)
- [miio (Node.js CLI) — device management](https://github.com/aholstenson/miio/blob/master/docs/management.md)
- [Home Assistant Yeelight integration](https://www.home-assistant.io/integrations/yeelight/)
