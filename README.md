# COMECON Central Exchange — Security & Transparency Notes (v2.1)

Security documentation, SHA-256 binary metadata, and a verbatim local-I/O source excerpt for the **COMECON Central Exchange** desktop companion client (`COMECON_Client.exe`) for *Workers & Resources: Soviet Republic* (64-bit).

* 🌐 **Official Web Exchange:** https://comecon.theoverlap.zone
* 🛠️ **Steam Workshop Mod (`#3826453788`):** https://steamcommunity.com/sharedfiles/filedetails/?id=3826453788
* 💬 **Official Discord Community:** https://discord.gg/d3QTtZ7zF3

---

## 1. Binary Metadata & Microsoft Defender Submission Result

* **File Name:** `COMECON_Client.exe`
* **FileVersion / ProductVersion:** `2.1.0.0`
* **File Size:** `14,632,448` bytes
* **SHA-256 Checksum:**
  ```text
  697cbb2e940b7b80c738b3641545c75d1657419e32a9947fb889fbc63ea11ed6
  ```
  *(Verify your local file anytime in Windows PowerShell: `Get-FileHash .\COMECON_Client.exe -Algorithm SHA256`)*
* **VirusTotal Report:** [View VirusTotal Analysis for `697cbb2e...`](https://www.virustotal.com/gui/file/697cbb2e940b7b80c738b3641545c75d1657419e32a9947fb889fbc63ea11ed6)

### Microsoft Defender submission result
The submitted `COMECON_Client.exe` (v2.1.0.0) binary received a **“Not malware”** determination from **Microsoft Security Intelligence** (Submission ID: `940de0cf-6462-44ea-9ac6-d27f0b5c85f3`), and the reported false-positive detection was removed.

*Note on scope:* This result concerns the submitted file sample. It is not a Microsoft endorsement, a code-signing certificate (SmartScreen reputation is tracked separately by Windows), or an independent third-party audit of the entire project.

| **v2.2 (`2.2.0.0`)** *(Latest)* | `COMECON_Client.exe` | `14,791,168` | `6fe85f3f62687f76f308e7cc42905200236b3e304f59fb67db290e8d19bc387d` | 2026-11-01 *(WDSI ID: `abcee599-7b1b-41e0-af90-03e23ef32f51`)* |

---

## 2. Scope of the Published Code Excerpt (`security_and_updater_excerpt.py`)

To prevent market-spoofing bots and unauthorized cloning of the mod, the full 7,200+ line codebase (server anti-cheat, in-game memory pointer chains, and the custom Tkinter HUD engine) is kept private.

However, [`security_and_updater_excerpt.py`](./security_and_updater_excerpt.py) contains **verbatim, unmodified slices** copied character-for-character from `raktarmutat.py` (lines `103–375`, `585–606`, `1047–1259`, `2199–2296`, and `6701–7071`) covering the client's local disk operations, DPAPI credential encryption, SQLite task journal, mod file syncing, and PowerShell self-updater. *(As a partial source excerpt, it illustrates these routines directly from the codebase but does not by itself prove the behavior of the full compiled binary.)*

---

## 3. Summary of Local Files, Game Memory & Network Activity

### A. In-Game Process Memory (`pymem` against `SOVIET64.exe`)
* Attaches strictly to `SOVIET64.exe` (`OpenProcess` / `ReadProcessMemory` / `WriteProcessMemory`) while the game is running.
* **Reads** the current in-game date (year and day) to calculate historical era price scaling.
* **Reads and updates** the player's State Treasury Ruble balance and commodity quantities inside linked COMECON custom storage buildings when executing market trades or escrow refunds.

### B. Local Files Read & Written by the Client
1. **AppData Configuration & Task Journal (`%APPDATA%\COMECON_Exchange\`):**
   * `client_auth.json` (and temporary `.tmp_<pid>_<hex>.json` during atomic writes) — Stores your username, UI language preference (`en`/`ru`/`zh`), and saved password encrypted via **Windows DPAPI (`CryptProtectData`)** bound to your current Windows user context. Legacy plaintext credential files are migrated to DPAPI on load. If migration fails, the client attempts to sanitize or remove the file. If neither operation succeeds, it displays a security warning and manual cleanup is required.
   * `.client_tasks.db` (plus SQLite `-wal` and `-shm` companion files) — Local SQLite WAL journal tracking `PREPARED -> EXECUTED -> ACKED` shipment and treasury tasks to prevent double-deductions on game crash. Stores a 16-character SHA-256 prefix of the session token (`account_hash`).
   * `client_trace.log` — Startup diagnostic trace log.
   * `show_hud.signal` — Single-instance signal file used to bring the existing HUD window to the front if `COMECON_Client.exe` is launched a second time.
2. **Self-Updater Files (`%LOCALAPPDATA%\COMECON_Exchange\` & Executable Directory):**
   * `COMECON_Client.exe.new` and `COMECON_Client.exe.old` — Temporary download and rollback files next to the executable during an update.
   * `updater_helper.ps1` and `updater.log` — Detached PowerShell helper script and log used to swap `.new` over the running `.exe` after process exit, verify the target file's SHA-256 hash, roll back to `.old` on failure, and relaunch `COMECON_Client.exe --updated`.
   * *Note:* The Nuitka onefile bootstrapper extracts bundled runtime files to a temporary directory. The exact location depends on the environment and build/runtime configuration.
3. **Game Workshop Folder (`<Game Folder>\media_soviet\workshop_wip\3826453788\` or Steam Workshop `784150\3826453788\`):**
   * Synchronizes configuration files (`building.ini`, `material.mtl`, `material_e.mtl`, `renderconfig.ini`) for the six COMECON building types.
   * Initial local installation may also copy workshop metadata (`workshopconfig.ini`), preview images (`previewimage.png`), and the required model/collision/icon assets (`.nmf`, `.bbox`, `.fire`, `tool_*.png`) from your local vanilla `media_soviet\buildings*` folders into `media_soviet\workshop_wip\3826453788\`.

### C. Network Communication
* By default, API requests are sent over HTTPS to `https://comecon.theoverlap.zone/api` (`/api/client_login`, `/api/sync`, `/api/tasks/complete`, `/api/market/*`, `/api/client_version`, `/api/client_download`).
* **Transmitted Data:**
  * `/api/client_login` transmits your COMECON username and password over HTTPS to obtain a session token.
  * `/api/sync` transmits the session token, linked-storage stock totals, and—when available and applicable to the negotiated protocol—the in-game balance and year/day.
  * `/api/tasks/complete` transmits the session token, task ID and task UUID.
  * Both `/api/sync` and `/api/tasks/complete` use timestamped HMAC-SHA256 telemetry headers with a nonce (`X-Comecon-Ts`, `X-Comecon-Nonce`, `X-Comecon-Sig`).
  * Self-update downloads check `/api/client_version` and stream the update from `/api/client_download` (or the `download_url` returned in the version metadata), verifying the exact byte size, `MZ` two-byte header, and SHA-256 hash before applying.

---

## Disclaimer
Unofficial, non-commercial community fan project for *Workers & Resources: Soviet Republic*. Not affiliated with or endorsed by 3Division or Hooded Horse.
