# QCY Arcbuds HT07 BLE control protocol

Reverse-engineered notes for controlling QCY Arcbuds HT07 earbuds over Bluetooth
LE without the QCY app: ANC, battery, EQ, touch gestures, and the rest. This is
interoperability research on a device I own, for personal use.

There's a working controller built from these notes in a separate repo,
[ht07menu](https://github.com/Tekkiech/ht07menu), a macOS menu-bar app.

## What's here

`QCY-HT07-protocol-report.md` is the full writeup: the transport (BLE GATT,
service `0xA001`), the frame format (`FF LEN CMD LEN2 ...`, start byte `0xFF`, no
checksum), the command-ID table, and the per-feature byte layouts. Section 6a
records what was confirmed live on the hardware.

`HANDOFF.md` is a short status note. `GADGETBRIDGE-CONTRIBUTION.md` is a plan for
adding HT07 support to Gadgetbridge, including the clean-room constraints.

`captures/` holds the observation-derived evidence that's safe to share:

- `DECODE-NOTES.md`, decoded frames checked against the protocol, from on-device
  capture.
- `ANC-UI-reference.md`, the app's noise-control UI (the scenes and levels).
- `anc_capture_frames_clean.txt` and `anc_labelled_frames_clean.txt`, real ANC
  frames seen on the wire.
- `eq_presets.txt`, the six EQ-preset frames (Default, Pop, Heavy Bass, Rock,
  Soft, Classic).
- `coreBluetooth_probe.txt`, the GATT table plus one verified write and battery
  read, sanitized.

`tools/dex_static_values.py` is a small DEX static-field extractor I used to pull
the command-ID constants. `exports/qcy_constants.txt` is its output.

## How this was obtained

Two independent methods, both on my own device.

First, the QCY app logs every BLE GATT frame in hex to Android `logcat` under the
`QCYCmdManager` tag. I captured that while exercising each feature.

Second, a macOS CoreBluetooth client connected to the earbuds and reproduced
every command, which confirmed the bytes on the hardware.

`QCY-HT07-protocol-report.md` also contains static-analysis (decompilation)
notes. For a clean-room contribution like Gadgetbridge, use only the
observation-derived material in `captures/`. The Gadgetbridge plan explains why.

## Quick reference

- Advertises over BLE as `QCY-APP`. Control service is `0xA001`.
- Write to `0x1001` (write without response), notify on `0x1002`, battery on
  `0x0008`.
- Frame is `FF <len> <cmd> <len2> <payload...>`, where `len` is the payload byte
  count. No checksum.
- ANC is command `0x0C` with one byte, `(scene << 4) | level`. `0x02` is Off.
  `0x4_` Indoor, `0x5_` Commuting, `0x6_` Noisy, `0x7_` Anti-wind at level 1 to 3.
  `0xA_` is Transparency at level 1 to 6.
- Battery on `0x0008` is `[L, R, box]`, with bit 7 as the charging flag and the
  low 7 bits as the percent. The case only reports while docked, so a connected
  client never sees it.
- Find-my-earbud runs over the Classic SPP channel, not BLE.

Not affiliated with or endorsed by QCY. "QCY" and "Arcbuds" belong to their
owner. This repo contains no vendor code or firmware.
