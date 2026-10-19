# QCY Arcbuds HT07 — Control Protocol (static analysis)

**Goal:** control ANC and other HT07 features without the QCY app, and assess a
Gadgetbridge contribution. Interoperability RE of a device the author owns, for
personal use. Everything below is **decompilation-derived** from the shipped
app unless marked **[observed]**; it is not yet confirmed against live traffic.
See *Verification status* per claim and the capture plan at the end.

## Subject
- **App package:** `com.qcymall.googleearphonesetup` (QCY, the global "QCY" app)
- **Version:** 4.0.7 (versionCode 682); minSdk 23, targetSdk 34
- **APK SHA-256:** `bd41c8d37278fb0b6fabc459a0c8e2f5fc2f85e1574103ab8d59a0365e80e109`
- **File:** `com.qcymall.googleearphonesetup_4.0.7-682_minAPI23(...)_apkmirror.com.apk`
- Engine: JADX 0.7.1 via REA android-provider (jar sha256 `6e5eac…73ff75`).
- APK manifest evidence: `ev_837ef72b05d0…c669a39d`.

## TL;DR
- The HT07 is controlled over **BLE GATT** using **QCY's own house protocol**
  (`com.qcymall.qcylibrary`), **not** a chipset SDK. The APK *also* bundles
  Realtek `bbpro`, Airoha `libbase`/`libfota`, Jieli `jl_rcsp`, and Qualcomm
  GAIA stacks — these are for *other* QCY models and are almost certainly not
  used by the HT07 (to be confirmed by capture).
- Control channel: GATT write (no response) to characteristic **`0x1001`**,
  notifications from **`0x1002`** (plus dedicated chars for battery/version/EQ/
  button). Client library is the open-source `com.inuker.bluetooth.library`
  (BluetoothKit).
- Frame: **`FF LEN  CMD LEN2 PAYLOAD…`** — SOF = `0xFF`, no checksum, no
  sequence number. One GATT write can carry several `CMD/LEN2/PAYLOAD` TLVs.
- **ANC is one command, `0x17`**, payload `[mode, noiseValue, subScene]`. A
  simpler single-byte noise command `0x0C` also exists (`[0x0C,0x01,mode]`).

---

## 1. Transport

QCY's client is `com.qcymall.qcylibrary.QCYHeadsetClient`
(evidence `ev_42693c92…71b378aa`). It holds a `com.inuker.bluetooth.library.BluetoothClient`
(BluetoothKit, a BLE/GATT wrapper) — so the control path is **BLE GATT**, not
Bluetooth-Classic RFCOMM/SPP. (`com.qcymall.qcylibrary.utils.ClassicBtUtil`
exists but the command path in `QCYHeadsetClient` uses GATT writes/notifies.)

### GATT UUIDs (from `QCYHeadsetClient` static finals, DEX static-values)
All are 16-bit shorts in the Bluetooth base UUID `0000xxxx-0000-1000-8000-00805f9b34fb`:

| Field | Short UUID | Role |
|---|---|---|
| `CHARACTER_SETING_UUID`   | **0x1001** | **command write** (ANC, noise, all `setBytesValue`/`sendBleCmdData`) |
| `CHARACTER_READSET_UUID`  | **0x1002** | settings notify/read (`readEarbudSetting`) |
| `CHARACTER_VERSION_UUID`  | 0x0007 | firmware version |
| `CHARACTER_BATTERY_UUID`  | 0x0008 | battery |
| `CHARACTER_EQ_UUID`       | 0x000B | EQ |
| `CHARACTER_BUTTON_UUID`   | 0x000D | key/touch function |
| `CLIENT_CHARACTERISTIC_CONFIG` | 0x2902 | standard CCCD for notifications |
| `SERVICE_UUID` | **`0xA001`** [observed on-device]. (A second service `0x7033` = Realtek OTA; don't write control there.) |

Verification status: UUID strings **confirmed** from DEX static values. The
service UUID object value is the one gap (grep for a `0x1000` literal was
negative); confirm it by reading the GATT table on-device.

The write char is hard-coded in senders, e.g. `setANCSetting`/`setBytesValue`
call `sendBleCmdData(mac, "00001001-0000-1000-8000-00805f9b34fb", …)`
(evidence `ev_904d7981…327f33cb9`).

### Connection / handshake
`connectDevice(mac[,…])` → BluetoothKit connect → it enables notifications on
the QCY characteristics (`MyBleNotifyResponse`) and then the app polls values
with `0xFE` request commands (below). No app-layer auth or pairing token is set
up before commands are accepted (see §5). Device selection is by BLE scan +
name/vendor-service match at runtime, not a hardcoded model list (no "HT07"
string table in the DEX). **This is the main thing the capture must confirm for
the HT07 specifically.**

## 2. Frame format

Builder `DataAnalyse.getSendData(byte[]… parts)` (evidence `ev_dae92006…5cde78`):
```
frame[0]       = SOF              ; = 0xFF   (DataAnalyse.SOF, DEX static value)
frame[1]       = LEN              ; = total number of payload bytes that follow
frame[2..]     = parts concatenated
```
`SOF = 0xFF` is **confirmed** from the DEX static-values array (JADX emits an
empty `<clinit>`, so the value lives in encoded static_values — see
`scripts/dex_static_values.py`).

Inner command, built by `setBytesValue(mac, cmdId, data)` (evidence
`ev_029a7fda…cc4cbcb`) and by every `getXxxCMD` helper:
```
cmdId  (1 byte)
len2   (1 byte)  = data.length
data   (len2 bytes)
```
So a complete single-command write is:
```
FF  LEN  CMD  LEN2  <payload…>        where LEN = LEN2 + 2
```

RX parser `DataAnalyse.analyseAllCMD(byte[])` (evidence `ev_8d0f1545…0325ac`):
- requires `len>=4` and `len == (frame[1]&0xFF)+2` (validates LEN only);
- then walks TLVs from offset 2: `cmd=frame[i]`, `len2=frame[i+1]`, payload =
  next `len2` bytes; **multiple TLVs per frame are supported**;
- dispatches each via `DataBean.getDataBean(cmd, payload)`.
- **No checksum/CRC anywhere; SOF is not even validated on RX.**

## 3. Command map (CMD IDs)

All `CMDID_*` are `static final byte` on `com.qcymall.qcylibrary.dataBean.DataBean`,
recovered authoritatively from the DEX static-values array
(`scripts/dex_static_values.py`; dispatcher cross-check `ev_43e4c047…52ac8ed231`).
Send and receive use the **same** id for a given feature (e.g. ANC 0x17 both
ways), so this table is both the command and the notify map.

| CMD | hex | Feature | Notes |
|---:|---|---|---|
| 1  | 0x01 | RESET_DEFAULT | restore default settings |
| 2  | 0x02 | CLEAR_PAIR | clear pairing |
| 3  | 0x03 | FACTORY_RESET | |
| 4  | 0x04 | MUSICACTION | play/pause/next/prev |
| 5  | 0x05 | LIGHT | find-my-earbud / flash (`[05,01,on]`) |
| 6  | 0x06 | RUER | in-ear detection (入耳) |
| 7  | 0x07 | NOISE | noise/ANC level |
| 8  | 0x08 | VOICE | voice/volume |
| 9  | 0x09 | DIYANSHI | low-latency / game mode |
| 10 | 0x0A | JIANTING | monitor/passthrough |
| 12 | 0x0C | NOISEMODE | **noise/ANC mode, single byte** |
| 13 | 0x0D | TESTMODE | |
| 16 | 0x10 | SLEEPMODE | |
| 17 | 0x11 | COMPACTNESS | fit/seal test (密闭性) |
| 18 | 0x12 | LEDMODE | |
| 20 | 0x14 | POWERMANAGER | auto-power-off |
| 22 | 0x16 | BALANCE | L/R balance |
| **23** | **0x17** | **ANCSETTING** | **ANC mode+level+scene (3 bytes)** |
| 24 | 0x18 | PAIRNAME | rename |
| 25 | 0x19 | VOICENAME | voice language |
| 29 | 0x1D | TONEVOLUME | prompt-tone volume |
| 30 | 0x1E | TAKEPHOTO | |
| 31 | 0x1F | STANDBY | |
| 32 | 0x20 | MULTIEQ | multi-band EQ |
| 34 | 0x22 | MULTIEQ2 | EQ (variant 2) |
| 35 | 0x23 | LDAC | |
| 39 | 0x27 | AEQ | adaptive EQ |
| 40 | 0x28 | ANC_RESULT | ANC result/telemetry |
| 41 | 0x29 | ANC_WEAR | ANC wear state |
| 43 | 0x2B | KEYFUN | touch/key function config |
| 44 | 0x2C | PEIDAI | wear detection (佩戴) |
| 45 | 0x2D | SPACE_AUDIO | spatial audio |
| 46 | 0x2E | MUSIC_MODE | |
| 47 | 0x2F | BATTERY | battery (per-earbud + case) |
| 48 | 0x30 | VERSION | firmware version |
| 50 | 0x32 | ENV_ADAPTATION | |
| 52 | 0x34 | TWS_ENABLE | |
| 53 | 0x35 | LED_SWITCH | |
| 54 | 0x36 | LED_EFFECT | |
| 55 | 0x37 | PLAY_MODE | |
| 57 | 0x39 | FOCUS_MODE | |
| 58 | 0x3A | MUSIC_STATE | |
| 59 | 0x3B | MUSIC_INFO | |
| 61 | 0x3D | TONE_PLAY | |
| 62 | 0x3E | SYNC_TIME | |
| 63 | 0x3F | ALARM | |
| 67 | 0x43 | AI | |
| 68 | 0x44 | MAXEQ_COUNT | |
| 69 | 0x45 | CUSTOM_EQ_TEST | |
| 70 | 0x46 | MULTIEQ_LEFT | |
| 71 | 0x47 | MULTIEQ_RIGHT | |
| 72 | 0x48 | INEAR_SENSITIVITY | |
| 254 | 0xFE | REQUESTDATA | **poll: `[FE,01,targetCmd]`** asks earbud to report `targetCmd` |

## 4. Per-feature byte layouts (headline features)

Each line below is the **inner** command; wrap as `FF LEN <inner> …`.

### ANC / transparency / off — CMD 0x17  ★ main prize
`ANCSettingDataBean.getANCSettingCMD(mode,noiseValue,subScene)` returns
`{0x17,0x03,mode,noiseValue,subScene}` (evidence `ev_bc711b87…98274f0`).
Full frame:
```
FF 05 17 03 <mode> <noiseValue> <subScene>
```
- Reached from `QCYHeadsetClient.setANCSetting(mac,mode,noiseValue,subScene)`.
- RX parse `ANCSettingDataBean.setReceiveData` reads payload as
  `mode=b[0], subScene=b[1], noiseValue=b[2]` (evidence `ev_cf61c820…724b462`) —
  note the **send order is (mode,noiseValue,subScene) but the parsed RX order is
  (mode,subScene,noiseValue)**; confirm which the firmware actually emits.

### Noise mode (simpler path) — CMD 0x0C
`NoiseDataBean.getNoiseModeCMD(b)` = `{0x0C,0x01,mode}` (evidence `ev_e63b14a0…2a6e3fe1`):
```
FF 03 0C 01 <mode>
```
The `<mode>` byte is **[observed] decoded** (see §6a): `byte = (scene<<4)|level`
— `0x02`=Normal/Off, `0x4_`=ANC Indoor, `0x5_`=Commuting, `0x6_`=Noisy,
`0x7_`=Anti-wind (lo nibble = ANC level 1–3), `0xA_`=Transparency (lo nibble =
level 1–6). e.g. off=`02`, strong ANC=`63`, transparency L4=`A4`. (The app enum
`NOISEMODE_ANC=1/HUWAI=2/JIANTING=3` is an internal selector id, **not** this wire
byte.) `setNoiseMode(mac,i)` sends 0x0C when `i<=255`, else decomposes a packed
int into `setANCSetting` (0x17) (evidence `ev_1e1ab9c2…cd72581`); the HT07 uses
the 0x0C path.

### Noise level — CMD 0x07
`NoiseDataBean.getNoiseCMD(value)` = `{0x07,0x01,value}` (evidence `ev_ef859488…cdcd2393`):
```
FF 03 07 01 <value>
```
Read/query current level: `getReadNoiseCMD()` = `getNoiseCMD(0xFF)` →
`FF 03 07 01 FF` (0xFF = "report current", evidence `ev_1d135577…b86cce9a`).

### Battery — CMD 0x2F (dedicated char 0x0008)
Parsed by `BatteryDataBean.setReceiveData` (evidence `ev_bf6d9393…21dcbd8c`): payload
is **≥3 bytes `[left, right, box]`**; for each byte, **bit7 (`&0x80`) = charging
flag, bits0–6 (`&0x7F`) = battery percent**. Indices 0/1/2 = left/right/case
(`getBatteryValue`/`isChargeing`, evidence `ev_9ed2c3b9…2faf3ae5`,
`ev_06e20329…cce83a74`). Poll with `FF 03 FE 01 2F`.

### Firmware version — CMD 0x30 (dedicated char 0x0007)
`getVersion(mac)`; poll with `FF 03 FE 01 30`. `VersionDataBean` exposes
`getLeftVersion()` / `getRightVersion()` strings (evidence `ev_45c36f42…8afd7eca`).

### Find-my-earbud / flash — CMD 0x05 (static) — **NOT used on HT07's BLE path [observed]**
`DataBean.getFlashLightCMD(on)` = `{0x05,0x01,on?1:0}` (evidence `ev_bb44d34b…950e6d`):
```
FF 03 05 01 01   (start)      FF 03 05 01 00   (stop)
```
> **[observed]** Capturing the QCY app firing find-my-earbud (twice, all log tags)
> showed **zero GATT writes** — so on the HT07 this command does **not** travel
> over the BLE control channel. The buds are Realtek (RTKOTA; adv mfg `1C524D43`)
> with the Classic **SPP** profile and the app ships `ClassicBtUtil`; find-my is
> sent over **Classic SPP/RFCOMM**, not BLE. A BLE-only client (incl. the macOS
> app) cannot trigger it. The SPP command format was not captured.

### In-ear detection — CMD 0x06 (`ruerjiance(mac,on)`), wear — CMD 0x2C (`PEIDAI`)
Toggle on/off; 1-byte payload. Parse via `RuerDataBean` / `PeidaiDataBean`.

### Touch / key function — CMD 0x2B (KEYFUN, dedicated char 0x000D)
`setButtonFunction(mac, keyId, funId)` or a `HashMap` of several. Builder
`KeyFuncDataBean.getSettingFunctionCMD(map)` emits **`[keyId, funId]` pairs**
(evidence `ev_8771db99…79d4c5c7`), so the inner command is:
```
FF <2N+2> 2B <2N> <keyId1> <funId1> <keyId2> <funId2> …   (N = #gestures set)
```
Key IDs and function IDs (`QCYHeadsetClient` DEX static values):
- FUNID: NONE 0, PLAYPAUSE 1, PERVIOUS 2, NEXT 3, ASSISTANT 4, ADD 5, SUB 6,
  GAME 7, ANSWER 8, REFUSE 9, HOLDON 10, REDIAL 11.
- KEYID music L/R single/double/three/four/long = 1..10;
  voice L/R single/double/three/four/long = 21..30.

> **[observed] HT07 actually uses a simpler path:** the key map is read/written
> on characteristic **0x000D as raw `[keyId,funId]` pairs with NO `FF/LEN`
> framing** (e.g. writing `05 01` to 0x000D sets key 5 → PLAYPAUSE 1). The
> 0x2B-over-0x1001 form above was not used by this firmware. See §6a.

### Low-latency / game — CMD 0x09 (`diyanshi(mac,on)`); EQ — CMD 0x20/0x22; etc.
As per the table; payloads are small TLVs built by the matching `*DataBean`.

### Generic poll — CMD 0xFE
`getRequestDataCMD(target)` = `{0xFE,0x01,target}` (evidence `ev_a86d9de8…a1b00c28`).
Send `FF 03 FE 01 <anyCmdId>` to make the earbud report that item.

## 5. Security notes
- **No app-layer authentication / handshake token** before control commands are
  accepted; **no encryption** at the app layer; **no checksum/CRC/sequence** in
  the frame. Security rests only on the BLE link (standard pairing/bonding) and
  on knowing the vendor UUIDs. This makes the protocol easy to re-implement, and
  means anything that can write 0x1001 can control the buds.
- No hard-coded keys/tokens seen in the QCY protocol path. (The bundled
  Realtek/Airoha/… SDKs contain their own OTA/AES code — `com.realsil.sdk.dfu.utils.AesJni`
  etc. — but those are not on the HT07 control path as far as the static read shows.)
- DFU/OTA exists (Realtek `dfu`, Airoha `libfota`) but is **out of scope**:
  no firmware experiments were or will be done.

## 6a. On-device capture results (2026-10-18) — **[observed]**

Captured live from `adb logcat` tag `QCYCmdManager` on the S24 Ultra while
driving the QCY app against the real **"QCY ArcBuds" (HT07)**. The app logs every
GATT operation in hex, which sidesteps Samsung's missing HCI snoop entirely.
Raw + decode: `re-work/captures/anc_capture_frames_clean.txt`,
`re-work/captures/DECODE-NOTES.md`. This **confirms the static model**:

- Device binding **resolved**: the HT07 uses this QCY BLE protocol (not a
  bundled chipset SDK). Control frames observed on `0x1001`/`0x1002` with SOF
  `0xFF` and the exact command IDs below.
- Frame `FF LEN CMD LEN2 …`, SOF 0xFF, multi-TLV — confirmed both directions.
- Poll **0xFE** confirmed: `FF 03 FE 01 14` → `FF 06 14 04 FF FF 00 00`; also
  `FE 01 16` (balance) → `FF 03 16 01 32` (=50, centre); `FE 01 20/22` (EQ).
- Battery **0x0008** confirmed `[left,right,box]`, low-7=percent, bit7=charging:
  `5F 64 00` (L95/R100/box0, not charging), `DF 64 00` (**0x80|0x5F → charging**).
- EQ push confirmed: `FF 7D 20 7B <123 bytes>` = cmd **0x20 (MULTIEQ)**.
- "All settings" snapshot notify decoded cleanly:
  `FF 14  06 01 01  08 03 2B2B0F  09 01 02  0C 01 A0  10 01 00  16 01 32`
  (RUER, VOICE, DIYANSHI, NOISEMODE=A0, SLEEP, BALANCE=50).
- **ANC/noise = cmd 0x0C, one data byte — DECODED.** `FF 03 0C 01 <byte>`
  (write 0x1001, echoed as 0x1002 notify, also carried in the settings snapshot).
  **`byte = (scene << 4) | level`:**

  | scene (hi nibble) | mode | level (lo nibble) |
  |---|---|---|
  | `0x0` | **Normal / Off** | — (observed `0x02`) |
  | `0x4` | ANC **Indoor** | 1–3 |
  | `0x5` | ANC **Commuting** | 1–3 |
  | `0x6` | ANC **Noisy** | 1–3 |
  | `0x7` | ANC **Anti-wind** | 1 |
  | `0xA` | **Transparency** | 1–6 |

  Observed frames: `02`=Normal; `41`=Indoor L1; `51`=Commuting L1; `62/63`=Noisy
  L2/L3; `71`=Anti-wind L1; `A0/A4/A6`=Transparency L0/L4/L6. Matches the app UI
  (decode in `captures/DECODE-NOTES.md`, UI in `captures/ANC-UI-reference.md`).
  So: **ANC off** = `FF 03 0C 01 02`; **strong ANC** (Noisy L3) = `FF 03 0C 01 63`;
  **Transparency L4** = `FF 03 0C 01 A4`. Transparency "Vocal enhancement" toggle
  did not alter this byte (likely a separate command — minor, unconfirmed).
- **Touch/key config refined:** on the HT07 the key map is read/written on the
  dedicated characteristic **0x000D as raw `[keyId,funId]` pairs with NO FF/LEN
  framing** (observed: writing `05 01` to 0x000D set key 5 → PLAYPAUSE). The
  0x2B/`KeyFuncDataBean` path in the lib was not used by this firmware/app.
- `0x0009` read returns ASCII `WQ00` (model/version string).

Open after capture: whether find-my-earbud (0x05) uses 0x1001 or another char on
HT07 (no 0x05 frame seen); the Transparency "Vocal enhancement" command (separate
from 0x0C). Both minor. ANC 0x0C is fully decoded above.

## 6. Verification status (what is proven vs. to confirm on-device)
**Proven from the APK:** transport = BLE GATT; write char 0x1001; frame
`FF LEN CMD LEN2 …`; SOF 0xFF; no checksum; the full CMD-ID table; ANC=0x17
`[mode,noise,scene]`; noise mode 0x0C `[mode]`; noise level 0x07 `[value]`
(query 0xFF); flash 0x05 `[on]`; poll 0xFE `[targetCmd]`; battery 0x2F
`[left,right,box]` with bit7=charging / low-7=percent; key function 0x2B
`[keyId,funId]…` pairs; version 0x30 → left/right strings.
**To confirm by capture (see plan):** (1) the HT07 actually speaks this QCY BLE
protocol and not a bundled chipset SDK; (2) `SERVICE_UUID` value; (3) ANC mode
byte values incl. the OFF value and the send-vs-RX field order for 0x17;
(4) the exact string encoding of the version payload.

---

## 7. Capture plan (Samsung S24 Ultra has no usable HCI snoop)

The S24 Ultra does not export a usable Bluetooth HCI snoop (not via
`adb bugreport`, not via SysDump `*#9900#`). Two viable paths:

**A. App's own frame log (try first).** The QCY lib logs via
`com.qcymall.qcylibrary.utils.LogToFile` (ANC path logs "收到ANC设置数据：" +
hex, evidence `ev_cf61c820…724b462`). Enable `setDebug(true)` is internal, but
the app may already write logs under
`/sdcard/Android/data/com.qcymall.googleearphonesetup/files/`. Steps:
1. `adb shell run-as` is blocked for store apps; instead
   `adb shell ls -R /sdcard/Android/data/com.qcymall.googleearphonesetup/files/`
   and pull any `*.log`/`*.txt`/xlog. If it's Tencent **xlog**, the FV13
   project's `re-work/tools/xlog.py`/`fclog.py` decoders may apply — reuse them.
2. If frames are logged as hex, match them to the action list below.

**B. BLE sniff on a second host (if no app log).** Options, in order of ease:
- A spare **Android phone that *does* export snoop** (most non-Samsung):
  enable *Developer options → Enable Bluetooth HCI snoop log*, pair the HT07,
  drive it from that phone's QCY app, then pull
  `/sdcard/.../btsnoop_hci.log` (or from a bugreport) and open in Wireshark.
- A **Linux box** with the buds paired: `btmon -w ht07.snoop` while using a
  BLE GATT tool to poke 0x1001, or run the QCY app in an Android emulator with
  BLE passthrough (harder).
- An **nRF Sniffer** (nRF52840 dongle) + Wireshark for a pure over-the-air BLE
  capture (no phone cooperation needed).

**Action list to annotate with wall-clock times** (so packets ↔ actions):
1. Connect app to HT07 — note time ___
2. ANC → **Off/Normal** ___
3. ANC → **ANC on** ___
4. ANC → **Transparency** ___
5. (if present) ANC level up one step ___
6. EQ → pick a different preset ___
7. Find-my-earbud / flash on ___, off ___
8. Toggle in-ear detection off ___, on ___
9. Change a touch/gesture (e.g. left double-tap → Next) ___
10. Trigger a battery refresh (reopen case) ___

Then decode and, in this report, mark each §4 claim **[observed]** with the real
bytes, and fix the ANC mode/OFF values and field order. Do **not** paste any
personal data (account IDs, notification text) into the report.

---

## 8. Gadgetbridge assessment (plan only — no fork/build/PR without the owner)

- **QCY is not currently supported** (confirmed Oct 2026 against
  gadgetbridge.org/gadgets — the Headphones category lists 20 brands: 1MORE,
  Anker, Bose, Bowers & Wilkins, Cardo, EarFun, Google, Haylou, Huawei, Jabra,
  Moondrop, Nothing, Oppo, Realme, Samsung, Sennheiser, Shokz, Sony, UGREEN,
  Xiaomi — no QCY, and no QCY coordinator in the tree). So a contribution is new,
  not a duplicate.
- Gadgetbridge has a **headphones** device class and a BT-Classic base, with
  ANC/Transparency/Off audio-profile support for some brands (Nothing/CMF,
  Sony, Galaxy Buds, etc.). The HT07 differs in two ways that matter:
  1. It is **BLE GATT**, so model it on a **GATT** headphone coordinator, not
     the SPP ones; and
  2. QCY's protocol is **not yet supported** in Gadgetbridge (no `qcy`/`qcymall`
     coordinator upstream, to confirm against the current repo
     `codeberg.org/Freeyourgadget/Gadgetbridge`).
- Smallest contribution if it fits: a `QcyHt07Coordinator` +
  device-support class under the headphones packages, implementing the
  3 ANC states (0x17 or 0x0C), battery notify (0x0008 / CMD 0x2F) and firmware
  version (0x0007 / 0x30); a `DeviceType` entry; a display string; and a
  Bluetooth-name test (match the HT07's advertised name).
- **CONTRIBUTING / clean-room:** Gadgetbridge requires public-info-or-personal-
  observation only. **Everything in §1–§5 here is decompilation-derived and
  cannot go into a PR as-is.** For upstreaming, the protocol facts must be
  **re-derived from the on-device capture** (§7) — the capture's observed bytes
  are the citable source. Disclose AI assistance; the device owner must be the
  one who runs the buds and maintains the support. Flag per claim which items
  are observation-backed before submitting.

## Evidence index (REA)
- APK manifest/identity: `ev_837ef72b05d085114f22f909cf189640debf11e8e5a12dda3d86db54c669a39d`
- `QCYHeadsetClient` class: `ev_42693c927db731ad083cbd33b42aa170e41fb5c4d1aa4a20252a115d71b378aa`
- `setANCSetting`: `ev_904d798177044dabf871e2fda60ac50703890083f8802fd96b945b5327f33cb9`
- `setBytesValue`: `ev_029a7fda5972ca0b11bac0a1b4abfbdcd6d4aa45c02ed25150cbbba25cc4cbcb`
- `DataAnalyse.getSendData`: `ev_dae92006eeb5c72e569a65f3a5e7d8aafa4b619278f1b24c79452c523f5cde78`
- `DataAnalyse.analyseAllCMD`: `ev_8d0f154512c3f8ba45b028102a969f5c42d6aa1dca18362dc8fe26f0b10325ac`
- `ANCSettingDataBean.getANCSettingCMD`: `ev_bc711b8760020115e03e7b2b1044d6feca44e85361192c34bafe10d2b98274f0`
- `ANCSettingDataBean.setReceiveData`: `ev_cf61c8205576a2f4fa19d8dd19cf7c0c14754b85f31b4d16a8cb5abf8724b462`
- `DataBean.getDataBean` (RX dispatcher): `ev_43e4c047b5bce5c0602391e810e21fb535477cf76854dfa5e3ec0252ac8ed231`
- `DataBean.getFlashLightCMD`: `ev_bb44d34bf81ccb6c7ef703cb3c700958128036b8e1df64225c4acc6493950e6d`
- `DataBean.getRequestDataCMD`: `ev_a86d9de8cef5f4f9154946df73b0f9bb41cb0a1e8b9290cbb5314242a1b00c28`
- `NoiseDataBean.getNoiseModeCMD`: `ev_e63b14a03eca4e2add90d2632f0c67ee9cb246f2afda04e44afd8fb32a6e3fe1`
- `setNoiseMode`: `ev_1e1ab9c2b72d77e30f42ca3223626ae544ecc09c5120bc7ba5d7d7774cd72581`
- `analyseBatteryData`: `ev_2df7e6e934ba635e10f0cf30c6dc68792e9c8d8e1d1e0e0a582b5a9833a7e697`
- `BatteryDataBean.setReceiveData` (battery byte layout): `ev_bf6d93935072eac8f85d71c2dd8d0ca607b07aa3069fa520c2db347221dcbd8c`
- `BatteryDataBean.getBatteryValue` / `isChargeing`: `ev_9ed2c3b9bfc8147bff8b124800dbcd0f967be2962f9facffe868cdfa2faf3ae5`, `ev_06e203292f331d5f3b0378d366fb54bdbc447c7453929217ae247de4cce83a74`
- `NoiseDataBean.getNoiseCMD` / `getReadNoiseCMD`: `ev_ef859488a193e94c177474e3d62c0a449c5882b38ac95d9bfcda5408cdcd2393`, `ev_1d1355773a3e2084e55ae7f1cdbfd464d8f22d638419f66a3c12b66cb86cce9a`
- `KeyFuncDataBean.getSettingFunctionCMD` (key layout): `ev_8771db9927549ceab1696f85b36fb42a8250dad4a54b8e1563297a8c79d4c5c7`
- `VersionDataBean`: `ev_45c36f4276e56f3924e43dea35906d54703f425d0715f568521dea948afd7eca`
- CMDID / SOF / UUID constants: extracted by `scripts/dex_static_values.py` from the DEX static-values arrays (output archived in `re-work/exports/qcy_constants.txt`).
