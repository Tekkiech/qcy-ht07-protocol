# Gadgetbridge support for the QCY Arcbuds HT07 — contribution plan

A concrete, follow-along plan to add QCY HT07 support to **Gadgetbridge**
(codeberg.org/Freeyourgadget/Gadgetbridge). This is a *plan*, not a patch — don't
fork, build, or submit anything until you've read the clean-room section and
decided you want to maintain it.

Status inputs: protocol in `QCY-HT07-protocol-report.md`; observed byte evidence
in `re-work/captures/DECODE-NOTES.md`; working reference implementation in
`macos-ht07/` (CoreBluetooth). Gadgetbridge architecture confirmed against its
[new-gadget tutorial](https://gadgetbridge.org/internals/development/new-gadget/)
and [gadgets list](https://gadgetbridge.org/gadgets/) (Oct 2026).

---

## 0. Viability (read first)

- **Not a duplicate.** QCY is not supported today — the Headphones category lists
  20 brands (1MORE, Anker, Bose, B&W, Cardo, EarFun, Google, Haylou, Huawei,
  Jabra, Moondrop, Nothing, Oppo, Realme, Samsung, Sennheiser, Shokz, Sony,
  UGREEN, Xiaomi) and QCY is not among them, nor is there a QCY coordinator.
- **The catch — transport.** Every existing Gadgetbridge earbud (Galaxy Buds,
  Sony, Nothing) is **Bluetooth Classic** (`AbstractHeadphoneBTBRDeviceSupport` /
  `btbr`). The HT07's control is **BLE GATT**. Gadgetbridge's BLE stack is mature
  (it's a smartwatch app at heart), but a **BLE earbud with ANC settings is an
  uncommon combination** there — you won't be able to copy an existing headphone
  class wholesale; you'll compose the BLE base + the device-settings UI yourself.
- **Clean-room is satisfiable.** We already re-derived the whole protocol from
  **observation** (on-device `logcat` frame dumps + macOS CoreBluetooth), not just
  decompilation — see §2.
- **Maintainership.** Gadgetbridge expects the person who owns the device to
  maintain its support and test changes. That's you.
- **Honest effort estimate:** ~2–4 focused evenings for a first MR (coordinator +
  BLE support + battery + the ANC setting), plus review iterations. EQ presets,
  touch-gesture editing, and game mode are add-ons once the skeleton is accepted.

---

## 1. The one hard design problem: identification

The HT07's **BLE advertising name is `QCY-APP`** — which is **shared by every QCY
model that uses this app**, not unique to the HT07. Its Classic name is "QCY
ArcBuds". So:

- Matching on the BLE name `QCY-APP` (Gadgetbridge's usual `getSupportedDeviceName()`
  `Pattern`) would claim *all* QCY buds, many of which have different feature sets
  (scene counts, levels, whether they even have ANC).
- Better: match on the **vendor GATT service `0xA001`** (and/or the Classic name
  `QCY ArcBuds`). Gadgetbridge can inspect the scan record / advertised service
  UUIDs in `getSupportedType(GBDeviceCandidate)` — override that, not just the
  name pattern, and key off service `A001` + name prefix.
- **Strategic choice to make up front:** is this *"QCY HT07"* support, or a
  *"QCY (house BLE protocol)"* generic device with per-model feature flags? The
  protocol (`FF LEN CMD LEN2 …`, service `A001`) is shared across QCY's BLE
  line-up, so a generic `QcyBleCoordinator` with a small per-model capability
  table may age better than an HT07-only class. Recommend raising this with the
  maintainers in the issue *before* coding — it affects the whole structure.

---

## 2. Clean-room compliance (do this right or it can't be merged)

Gadgetbridge's CONTRIBUTING requires protocol knowledge to come from **public
information or your own observation of your own device** — **not** from
decompiling the vendor app.

- **Do not** copy any constant, class name, or structure *from the APK decompile*
  into the MR, and don't cite `QCY-HT07-protocol-report.md` §1–§5 (those are
  decompilation-derived) as the source.
- **Do** derive everything from the **observed** material, which you already have:
  - `re-work/captures/*.txt` / `DECODE-NOTES.md` — real frames from `adb logcat`
    (`QCYCmdManager` logs every GATT op) and the macOS CoreBluetooth probe.
  - The macOS app (`macos-ht07/`) is itself an independent re-implementation built
    and **verified against the live device** — it's clean-room evidence that the
    bytes work.
- **Disclose AI assistance** in the MR description (Gadgetbridge asks for this).
- Keep a short "how this was obtained" note in the MR: *sniffed my own device's
  BLE control channel via the app's own debug log and a CoreBluetooth client;
  confirmed each command on the hardware.* That's the citable provenance.
- **find-my-earbud is out of scope** — it's on the Classic SPP channel, not BLE
  (see report §4), so it has no place in a BLE coordinator.

---

## 3. What to build (file-by-file)

Package base: `nodomain.freeyourgadget.gadgetbridge`. Create under a new
`devices/qcy/` (coordinator) and `service/devices/qcy/` (support) area; check the
current tree for the exact convention before creating files.

### 3.1 Register the DeviceType
- File: `app/src/main/java/.../model/DeviceType.java`
- Add: `QCY_HT07(QcyHt07Coordinator.class)` (or `QCY_BLE(...)` if going generic),
  and import the coordinator. (Newer trees register the type via the coordinator;
  verify whether the enum still lists the class or a ServiceLoader is used.)

### 3.2 Coordinator — `QcyHt07Coordinator`
- Extend the **BLE** coordinator base (`AbstractBLEDeviceCoordinator`; confirm the
  exact name in the current source — the tutorial's examples are watch-centric).
- Implement:
  - `getSupportedType(GBDeviceCandidate)` / `getSupportedDeviceName()` — match on
    **service `A001`** + name (`QCY-APP` / `QCY ArcBuds`), per §1.
  - `getDeviceSupportClass()` → `QcyHt07DeviceSupport.class`.
  - `getManufacturer()` → "QCY"; `getDeviceNameResource()` → "QCY Arcbuds HT07".
  - `getBondingStyle()` → `BONDING_STYLE_NONE` (the control chars read/wrote with
    **no bonding** in our captures) — verify; use `BONDING_STYLE_ASK` if the OS
    forces pairing.
  - `getBatteryCount()` → 2 (left, right). Case battery is **not** exposed over
    BLE (report §6a) — don't advertise it.
  - `supportsFindDevice()` → **false** (SPP-only). `supportsActivityTracking()`
    → false. No sample provider / no DAO tables (it's not a fitness device — skip
    the GBDaoGenerator step entirely).
  - `getSupportedDeviceSpecificSettings(GBDevice)` → the XML screens from §3.4.

### 3.3 Device support — `QcyHt07DeviceSupport`
- Extend `service.btle.AbstractBTLESingleDeviceSupport`.
- UUID constants (observed): service `0000A001-…`, write `00001001-…`
  (**write WITHOUT response**), notify `00001002-…`, battery `00000008-…`.
- `initializeDevice(builder)`:
  - set state INITIALIZING → discover services → `builder.notify(0x1002, true)`
    and `builder.notify(0x0008, true)`; read `0x0008` once; set state INITIALIZED.
  - optionally poll noise state with a `FE 01 0C` request so the UI starts synced.
- `onCharacteristicChanged(gatt, ch)`:
  - `0x0008` (3 bytes `[L,R,box]`, bit7=charging, low7=%): emit battery via
    `GBDeviceEventBatteryInfo` for indices 0/1 (skip box). Handle the "0 while
    charging" placeholder like the macOS app does.
  - `0x1002`: parse `FF LEN (CMD LEN2 PAYLOAD)…`; on CMD `0x0C` update the stored
    ANC state so the settings screen reflects the device.
- `onSendConfiguration(key)`: map each preference key to a frame written to
  `0x1001` **without response** via a `TransactionBuilder`:
  - ANC: `FF 03 0C 01 <byte>` where `byte = (scene<<4)|level` — `0x02` Off,
    `0x4_/0x5_/0x6_/0x7_` ANC Indoor/Commuting/Noisy/Anti-wind (level 1–3),
    `0xA_` Transparency (level 1–6). (ANC 0x17 exists too but 0x0C is what the
    HT07 uses — report §6a.)
  - EQ preset: write the captured 127-byte `FF 7D 20 7B <id> …` frame
    (`re-work/captures/eq_presets.txt`): 01 Default, 02 Pop, 03 Heavy Bass, 04
    Rock, 05 Soft, 06 Classic.
  - Game/low-latency: `FF 03 09 01 <0|1>`. Balance: `FF 03 16 01 <0..100>`.
  - Touch gesture: write `[keyId,funId]` pairs to char `0x000D` (raw, no framing).
- Add `BatteryInfoProfile`/`DeviceInfoProfile` only if you also wire the **standard**
  GATT battery/device-info services — the HT07's battery is a *vendor* char, so
  you'll likely feed battery through the event path above instead.

### 3.4 Device-specific settings XML
- `app/src/main/res/xml/`:
  - `devicesettings_qcy_anc.xml` — a list/radio for **Off / ANC / Transparency**,
    a scene list (Indoor/Commuting/Noisy/Anti-wind) and a level stepper shown when
    ANC, a 1–6 level when Transparency. (Model the interaction on the existing
    `devicesettings_*_anc*.xml` headphone screens, but these drive a BLE write.)
  - `devicesettings_qcy_eq.xml` — the 6 preset list.
  - `devicesettings_qcy_gestures.xml` — key → function pickers.
- Reference them from `getSupportedDeviceSpecificSettings`. Read values with
  `GBApplication.getDeviceSpecificSharedPrefs(address)`. For live apply, handle
  the keys in `onSendConfiguration` (and register them in
  `DeviceSpecificSettingsFragment` if a key needs a custom handler). Newer trees
  use the settings DSL from PR #6350 — check `project-overview/device-settings`.

### 3.5 Resources
- `DeviceType` display string, a headphones icon (reuse an existing earbuds
  drawable), and string resources for the setting labels.

---

## 4. Protocol appendix for the MR (observation-derived only)

Cite these as **observed on-device**, not from the app:

| Thing | Value |
|---|---|
| Control service | `0000A001-0000-1000-8000-00805f9b34fb` |
| Command write | `00001001-…` — **write without response** |
| Notify | `00001002-…` (read/notify) |
| Battery | `00000008-…` read/notify, `[L,R,box]`, bit7=charging, low7=percent |
| Frame | `FF <len> <cmd> <len2> <payload…>`, `len` = payload byte count, no checksum |
| ANC (cmd `0x0C`) | 1 byte `(scene<<4)|level`: `02`=Off; `4_`Indoor `5_`Commuting `6_`Noisy `7_`Anti-wind (lvl 1–3); `A_`Transparency (lvl 1–6) |
| Poll | `FF 03 FE 01 <cmd>` asks the buds to report `<cmd>` |
| EQ preset (cmd `0x20`) | full 127-byte frame per preset — see `eq_presets.txt` |
| Game/low-latency | `FF 03 09 01 <0|1>` |
| Balance | `FF 03 16 01 <0..100>` (50 = centre) |
| Touch map | char `0x000D`, raw `[keyId,funId]` pairs |
| Adv name / mfg | `QCY-APP` / manufacturer data begins `1C524D43` |

Verified round-trips (the buds echo the command back on `0x1002`): ANC
`FF030C0163`, Transparency `FF030C01A4`; battery `5F6400`/`DF6400` (charging bit).

---

## 5. CONTRIBUTING checklist before opening the MR

- [ ] Opened an **issue** first describing the device + the generic-vs-HT07
      identification question (§1); got maintainer steer.
- [ ] All protocol facts sourced from **observation**, none copied from the APK
      decompile; provenance note included.
- [ ] **AI assistance disclosed** in the MR description.
- [ ] Identification keys off **service `A001`**, not just the shared `QCY-APP`
      name (won't hijack other QCY models).
- [ ] Builds against current `master`; tested on the real HT07 (connect, battery,
      ANC switch, EQ, reconnect).
- [ ] No fitness/DAO code; `supportsFindDevice()` false; case battery not claimed.
- [ ] Follows current code style + the settings DSL if the tree has migrated.
- [ ] You're prepared to maintain it and respond to review.

## 6. Getting started (when you decide to)
1. Watch an existing **BLE** device + a **headphone** device in the source to see
   both patterns (`service/btle/…` and a `devices/*/…coordinator`).
2. Fork on Codeberg, branch `qcy-ht07`.
3. Build the app (`./gradlew assembleDebug`), sideload, enable the device, test.
4. Iterate on the ANC setting first (smallest useful slice), then battery, then
   EQ/gestures.
5. Open the MR against Codeberg with the checklist above.

Sources: [new-gadget tutorial](https://gadgetbridge.org/internals/development/new-gadget/),
[gadgets list](https://gadgetbridge.org/gadgets/),
[Samsung headphones page](https://gadgetbridge.org/gadgets/headphones/samsung/).
