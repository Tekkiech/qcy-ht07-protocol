# HANDOFF — QCY Arcbuds HT07 RE

## State (2026-10-18)
Static analysis of the QCY app is essentially complete for the HT07 control
protocol. Full findings + evidence IDs in `QCY-HT07-protocol-report.md`.

## What's done
1. **Tools confirmed** — REA android-provider (JADX 0.7.1) available.
2. **APK identified** — `com.qcymall.googleearphonesetup` 4.0.7 (682),
   SHA-256 `bd41c8d37278fb0b6fabc459a0c8e2f5fc2f85e1574103ab8d59a0365e80e109`.
3. **Transport mapped** — BLE GATT via QCY house lib `com.qcymall.qcylibrary`
   (BluetoothKit). Write char **0x1001**, notify **0x1002**; battery 0x0008,
   version 0x0007, EQ 0x000B, button 0x000D. (App also bundles Realtek/Airoha/
   Jieli/Qualcomm SDKs — for other models, not the HT07 path.)
4. **Frame mapped** — `FF LEN CMD LEN2 PAYLOAD…`, SOF=0xFF, no checksum/seq,
   multi-TLV per frame.
5. **Command table** — full `CMDID_*` recovered from DEX static values
   (`re-work/exports/qcy_constants.txt`). ANC=0x17 `[mode,noise,scene]`;
   noise mode=0x0C `[mode]` (ANC1/transp2/passthrough3); flash=0x05; poll=0xFE;
   battery=0x2F; version=0x30; keyfun=0x2B; etc.
6. **Security** — no app-layer auth/encryption/CRC.

## Capture DONE (2026-10-18) — logcat tag `QCYCmdManager` logs every frame in hex
On the S24, `adb logcat QCYCmdManager:V *:S` dumps all GATT ops (no Samsung HCI
snoop needed). Confirmed live on "QCY ArcBuds" (HT07): transport/UUIDs, frame
`FF LEN CMD LEN2 …` SOF 0xFF, poll 0xFE, battery 0x0008 (incl. charging bit),
EQ 0x20, settings-snapshot TLV. Raw/decoded in `re-work/captures/`
(`anc_capture_frames_clean.txt`, `DECODE-NOTES.md`). Report §6a has the summary.

## ANC 0x0C — DECODED (report §6a / DECODE-NOTES.md)
`FF 03 0C 01 <byte>`, byte = (scene<<4)|level: 0x02=Off, 0x4_=Indoor,
0x5_=Commuting, 0x6_=Noisy, 0x7_=Anti-wind (lo=level 1–3), 0xA_=Transparency
(lo=level 1–6). off=02, strong ANC=63, transparency L4=A4. Verified vs UI
the app UI (`captures/ANC-UI-reference.md`).

## Minor open items (optional)
- Find-my-earbud (0x05): no frame seen on 0x1001; confirm its char/trigger.
- Transparency "Vocal enhancement" command (separate from 0x0C).
- `SERVICE_UUID` object value (cosmetic; 0x1001 write / 0x1002 notify are what matter).
- HT07 key map uses char **0x000D raw `[keyId,funId]` pairs** (observed) — in report §4/§6a.

## Byte layouts now fully static-resolved (report §4)
- Battery 0x2F: `[left,right,box]`, bit7=charging, low-7=percent.
- Key function 0x2B: `[keyId,funId]` pairs, inner `[2B, 2N, …]`.
- Noise level 0x07: `[value]`; query = 0xFF. Noise mode 0x0C: `[mode]`.
- Version 0x30 → VersionDataBean left/right strings.

## Layout
- `QCY-HT07-protocol-report.md` — the report (command map, byte layouts, evidence).
- `scripts/dex_static_values.py` — minimal DEX static-values parser (reusable).
- `re-work/exports/qcy_constants.txt` — extracted CMDID/UUID/SOF/enum constants.
- `re-work/tools/dex_static_values.py` — copy of the parser.
- `re-work/{evidence,captures}/` — for evidence bundles and future captures.
- scratchpad `.../apk/classes*.dex` — extracted DEX (untrusted; not in project).

## Next session, start with
`BatteryDataBean` + `KeyFuncDataBean` byte offsets (REA, small classes), then
the capture per report §7, then confirm/annotate each §4 claim as **[observed]**.
Gadgetbridge plan is in report §8 (clean-room: re-derive from capture, not decomp).
