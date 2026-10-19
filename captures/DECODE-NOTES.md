# HT07 live capture — decode notes (2026-10-18)

Source: `adb logcat` tag `QCYCmdManager` on the S24 Ultra (SM-S928B), QCY app
build 717, earbuds **"QCY ArcBuds" (HT07)**. The app logs every GATT op in hex.
Raw: `anc_capture_frames_clean.txt`. No personal data (control frames only;
MACs not present in these lines). This **confirms the static protocol**.

## Confirmed exactly as predicted
- **Transport/UUIDs:** writes to `0x1001`, notifies on `0x1002`, battery on
  `0x0008`, "version"/serial on `0x0007`/`0x0009`, key map on `0x000D`.
- **Frame:** `FF LEN CMD LEN2 PAYLOAD…`, SOF `0xFF`, LEN = payload byte count,
  multi-TLV per frame. No checksum.
- **Poll 0xFE:** `FF 03 FE 01 14` (request POWERMANAGER 0x14) → notify
  `FF 06 14 04 FF FF 00 00`. Also saw requests `FE 01 20` (MULTIEQ), `FE 01 22`
  (MULTIEQ2), `FE 01 16` (BALANCE) → reply `FF 03 16 01 32` (balance=0x32=50,
  centre). All match `getRequestDataCMD`.
- **Battery 0x0008** `[left,right,box]`, low-7=percent, bit7=charging — proven:
  `5F 64 00` = L95% R100% box0 (not charging); `DF 64 00` = **0xDF = 0x80|0x5F
  → charging bit set**, L95%; `00 64 00` = L0%. 
- **EQ:** big push `FF 7D 20 7B <123 bytes>` = cmd **0x20 (MULTIEQ)**, 123-byte
  curve; read back via `FE 01 20` / `FE 01 22`.
- **"All settings" snapshot notify on 0x1002:**
  `FF 14 06 01 01  08 03 2B2B0F  09 01 02  0C 01 A0  10 01 00  16 01 32`
  = RUER(0x06)=01, VOICE(0x08)=2B2B0F, DIYANSHI(0x09)=02, **NOISEMODE(0x0C)=A0**,
  SLEEP(0x10)=00, BALANCE(0x16)=32. (LEN 0x14=20 ✓)

## Touch / key config — mechanism refined by capture
The HT07 does **not** use the 0x2B-over-0x1001 path for reading/writing the key
map; it uses the dedicated **characteristic 0x000D** with **raw `[keyId,funId]`
pairs and NO `FF/LEN` framing**:
- Read `0x000D`: `01 00 02 00 03 01 04 01 05 00 06 03 07 00 08 00 00 00 00 00`
  = key1→0, key2→0, key3→1, key4→1, key5→0, key6→3, key7→0, key8→0.
- Action 7 (change a gesture) = **write `0x000D` = `05 01`** (keyId 5 → funId 1
  = PLAYPAUSE). Readback then shows `…05 01…` (byte flipped from 00→01). ✓
So on HT07, key/touch functions are set by writing `[keyId,funId]` directly to
0x000D. (The 0x2B/`KeyFuncDataBean` path exists in the lib but wasn't used here.)

## ANC / noise — cmd 0x0C, ONE data byte — FULLY DECODED
All ANC changes are single-byte writes `FF 03 0C 01 <byte>` to 0x1001, echoed as
a 0x1002 notify and carried in the settings snapshot. Combining the observed
values with the app UI screenshots (`ANC-UI-reference.md`; Noise-cancel scenes
Indoor/Commuting/Noisy each 3 levels + Anti-wind; Transparency 6 levels + vocal
toggle; Normal):

**`byte = (scene << 4) | level`**
| scene hi-nibble | mode | level lo-nibble |
|---|---|---|
| 0x0 | Normal / Off | — (seen 0x02) |
| 0x4 | ANC Indoor | 1–3 |
| 0x5 | ANC Commuting | 1–3 |
| 0x6 | ANC Noisy | 1–3 |
| 0x7 | ANC Anti-wind | 1 |
| 0xA | Transparency | 1–6 |

Observed frames (write 0x1001 and/or notify 0x1002 and/or snapshot):
`02`=Normal · `41`=Indoor L1 · `51`=Commuting L1 · `62/63`=Noisy L2/L3 ·
`71`=Anti-wind L1 · `A0/A4/A6`=Transparency L0/L4/L6.

Send examples: ANC off `FF 03 0C 01 02` · strong ANC (Noisy L3) `FF 03 0C 01 63`
· Transparency L4 `FF 03 0C 01 A4`. The Transparency "Vocal enhancement" toggle
did NOT change this byte — likely a separate command (unconfirmed, minor).

## Other observed
- `0x0009` read = ASCII `WQ00` (model/version-ish string).
- No `FF 03 05 01 xx` (find-my-earbud/flash) frame appeared — that control may
  use a different trigger/char on HT07, or action 6 didn’t emit on 0x1001;
  re-check in the labelled pass.

## macOS CoreBluetooth control — CONFIRMED (2026-10-18)
Built a Swift/CoreBluetooth probe (`macos-ht07/`) and controlled the HT07 from
the Mac, independent of the phone/QCY app. Proven:
- BLE **advertising name = `QCY-APP`** (distinct from the Classic name "QCY ArcBuds");
  manufacturer data begins `1C524D43…` (ASCII "RMC").
- Control **service UUID = `0xA001`** containing: `1001` (write-without-response,
  command), `1002` (read+notify), `0008` (battery R/N), `000D` (button R/W),
  `0007` (version R), `0009` (R/W), `000B` (EQ R/W). A second service `7033`
  (`1001/1002/2001/2002`) is the Realtek OTA channel — do NOT write control there.
- `1001` is **Write Without Response** (not plain Write).
- Sent `FF 03 0C 01 A4` (Transparency L4) → earbud **echoed `FF030C01A4` on 1002**
  = accepted & applied. Battery read `64 64 00` (L100 R100 box0).
- The buds only expose this BLE control link when **not** audio-connected to
  another host; disconnect from phone/Mac first, then they advertise & accept it.
Raw: `macos_coreBluetooth_probe_success.txt`.

## EQ "sound effect" presets — captured (2026-10-18)
Preset switch = one full cmd-0x20 frame `FF 7D 20 7B <id> <curve…>` (127 bytes,
123-byte payload; trailing zeros pad the band table). byte[4] = preset id:
**01 Default, 02 Pop, 03 Heavy Bass, 04 Rock, 05 Soft, 06 Classic** (confirmed
via EQTestLog page ids + tap order). The app replays these exact frames to set a
preset (the firmware takes a full curve, not just an id, so custom EQ is possible
but the per-band encoding isn't broken out yet). Full frames: `eq_presets.txt`.
Wired into HT07Menu.app → Equalizer picker.

## Find-my-earbud — NOT on the BLE channel (2026-10-18)
Captured the QCY app firing find-my-earbud twice (broad all-tag logcat). The app
sent ZERO GATT writes — only battery reads (0x0008) and a noise notify (0x1002).
The buds are Realtek (RTKOTA tag; adv mfg 1C524D43 "RMC") and expose the Classic
SPP profile, and the app ships `ClassicBtUtil`. Conclusion: find-my-earbud (and
possibly other features) is sent over the **Classic Bluetooth SPP/RFCOMM channel,
not BLE GATT**. The static `0x05`/`getFlashLightCMD` frame is not used on this
model's BLE path. => the macOS BLE app cannot trigger find-my; removed the Ring
button. Supporting it would require an IOBluetooth RFCOMM/SPP channel + the SPP
command format (not yet captured; Samsung can't snoop Classic either).
