# -*- coding: utf-8 -*-
"""
COMECON Central Exchange Client (v2.1) — Verbatim Security, Credential, Disk I/O & Updater Excerpt
==================================================================================================
Scope & Limitations Notice:
  - This file is a partial source excerpt extracted verbatim from `raktarmutat.py` (v2.1.0.0).
  - Every function and constant below is copied character-for-character from the production
    client source without renaming or modification.
  - Because this is a partial excerpt (omitting the proprietary in-game memory pointer chains,
    anti-cheat telemetry signing salt, and custom Tkinter HUD classes), it does not by itself
    prove the behavior of the full compiled executable.
"""

import os
import sys
import time
import json
import shutil
import base64
import ctypes
import ctypes.wintypes
import hashlib
import secrets
import sqlite3
import subprocess
import requests
import tkinter as tk
from tkinter import ttk

# --- [Verbatim Slice 1: lines 103..375 of raktarmutat.py] ---
BASE_URL = "https://comecon.theoverlap.zone"
API_URL = f"{BASE_URL}/api"
TOKEN = None
COUNTRY_NAME = None
USERNAME = None
CSRF_TOKEN = None
WEB_SESSION = requests.Session()

WORKSHOP_ITEM_ID = "3826453788"
MOD_BUILDING_SOURCES = {
    "comecon_open": "warehouse_open_combined_big",
    "comecon_covered": "warehouse_covered_combined",
    "comecon_cooler": "storage_meat",
    "comecon_gravel": "storage_rumble_big",
    "comecon_cement": "storage_cement",
    "comecon_liquid": "oil_storage",
}

def is_compiled_binary():
    """True for Nuitka or PyInstaller executables; false for source execution."""
    return bool(
        "__compiled__" in globals()
        or hasattr(sys, "__compiled__")
        or getattr(sys, "frozen", False)
        or hasattr(sys, "_MEIPASS")
        or "NUITKA_ONEFILE_BINARY" in os.environ
    )


def get_real_executable_path():
    """
    Resolves the true on-disk executable path for self-updating and pathing,
    handling PyInstaller, Nuitka standalone, and Nuitka onefile.
    Returns None if not running as a compiled binary or if the outer executable
    cannot be safely validated.
    """
    if not is_compiled_binary():
        return None

    # Check Nuitka onefile environment variable first if present
    onefile_env = os.environ.get("NUITKA_ONEFILE_BINARY")
    if onefile_env:
        cand = os.path.abspath(onefile_env)
        if os.path.isfile(cand) and cand.lower().endswith(".exe"):
            return cand

    is_nuitka = bool(
        "__compiled__" in globals()
        or hasattr(sys, "__compiled__")
        or "NUITKA_ONEFILE_BINARY" in os.environ
    )
    if is_nuitka:
        # In Nuitka (especially onefile), sys.executable points to the extracted child in Temp.
        # Prefer sys.argv[0] if it points to a verified existing .exe file.
        if sys.argv and sys.argv[0]:
            cand = os.path.abspath(sys.argv[0])
            if os.path.isfile(cand) and cand.lower().endswith(".exe"):
                return cand
        # For Nuitka standalone (where it's not onefile and argv[0] might be missing/odd),
        # verify sys.executable only if NUITKA_ONEFILE_BINARY is NOT set:
        if "NUITKA_ONEFILE_BINARY" not in os.environ and sys.executable:
            cand = os.path.abspath(sys.executable)
            if os.path.isfile(cand) and cand.lower().endswith(".exe"):
                return cand
        return None

    # PyInstaller
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        if sys.executable:
            cand = os.path.abspath(sys.executable)
            if os.path.isfile(cand) and cand.lower().endswith(".exe"):
                return cand
        return None

    return None


def resource_path(rel_path):
    """
    Deterministic multi-location lookup for bundled assets.
    Priority:
    1. sys._MEIPASS (PyInstaller)
    2. os.path.dirname(os.path.abspath(__file__)) (Nuitka bundled data and source execution)
    3. __compiled__.containing_dir (Nuitka runtime attribute if available)
    4. Executable/script directory fallbacks
    Returns first existing path, or a deterministic fallback path.
    """
    candidates = []

    # 1. PyInstaller _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.abspath(meipass))

    # 2. __file__ directory (Nuitka unpacked temp dir in onefile, or source repo dir)
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass

    # 3. __compiled__.containing_dir (Nuitka module attribute if present)
    compiled_obj = globals().get("__compiled__") or getattr(sys, "__compiled__", None)
    if compiled_obj is not None:
        c_dir = getattr(compiled_obj, "containing_dir", None)
        if c_dir and isinstance(c_dir, str):
            candidates.append(os.path.abspath(c_dir))

    # 4. Executable and script directory fallbacks
    try:
        if sys.executable:
            candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass

    try:
        real_exe = get_real_executable_path()
        if real_exe:
            candidates.append(os.path.dirname(real_exe))
    except Exception:
        pass

    try:
        if sys.argv and sys.argv[0]:
            candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass

    # Remove duplicates preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    for base in unique_candidates:
        candidate_path = os.path.join(base, rel_path)
        if os.path.exists(candidate_path):
            return candidate_path

    primary_base = unique_candidates[0] if unique_candidates else os.path.abspath(".")
    return os.path.join(primary_base, rel_path)


def find_soviet_install_dir(soviet_exe_path=None):
    if not soviet_exe_path or not os.path.exists(soviet_exe_path):
        return None
    exe_dir = os.path.dirname(os.path.abspath(soviet_exe_path))
    for c in (exe_dir, os.path.dirname(exe_dir)):
        if c and os.path.isdir(os.path.join(c, "media_soviet", "buildings")):
            return c
    return None


def ensure_comecon_mod_installed(soviet_exe_path=None):
    """
    Checks if the COMECON Storage Pack (3826453788) is present either via Steam Workshop
    subscription or in media_soviet/workshop_wip/3826453788. If missing, automatically
    installs it using the bundled config files and the player's local vanilla 3D models.
    Also keeps bundled material/renderconfig files (including night material_e.mtl) up to date.
    Returns (status_str, installed_now_bool).
    """
    game_dir = find_soviet_install_dir(soviet_exe_path)
    if not game_dir:
        return ("Game directory not found yet", False)

    bundled_root = resource_path(os.path.join("mod_assets", WORKSHOP_ITEM_ID))
    cfg_files = ("building.ini", "material.mtl", "material_e.mtl", "renderconfig.ini")

    def _sync_bundled_configs(target_root):
        if not os.path.isdir(bundled_root) or not os.path.isdir(target_root):
            return None
        for comecon_name in MOD_BUILDING_SOURCES:
            b_src = os.path.join(bundled_root, comecon_name)
            b_dst = os.path.join(target_root, comecon_name)
            if not os.path.isdir(b_src) or not os.path.isdir(b_dst):
                continue
            for cfg_file in cfg_files:
                s_cfg = os.path.join(b_src, cfg_file)
                d_cfg = os.path.join(b_dst, cfg_file)
                if os.path.exists(s_cfg):
                    try:
                        need_copy = False
                        if not os.path.exists(d_cfg):
                            need_copy = True
                        else:
                            with open(s_cfg, "rb") as f1, open(d_cfg, "rb") as f2:
                                if f1.read() != f2.read():
                                    need_copy = True
                        if need_copy:
                            shutil.copy2(s_cfg, d_cfg)
                    except PermissionError as pe:
                        return f"Mod Config Sync Permission Error: Write permission required for {d_cfg} ({pe})"
                    except OSError as oe:
                        return f"Mod Config Sync Error: {oe}"
        return None

    media_dir = os.path.join(game_dir, "media_soviet")
    # 1. Check Steam Workshop subscribed folder (../../workshop/content/784150/3826453788)
    steamapps_dir = os.path.dirname(os.path.dirname(game_dir))
    ws_sub_dir = os.path.join(steamapps_dir, "workshop", "content", "784150", WORKSHOP_ITEM_ID)
    if os.path.exists(os.path.join(ws_sub_dir, "workshopconfig.ini")):
        all_ok = all(
            os.path.exists(os.path.join(ws_sub_dir, b, "building.ini"))
            for b in MOD_BUILDING_SOURCES
        )
        if all_ok:
            sync_err = _sync_bundled_configs(ws_sub_dir)
            if sync_err:
                return (sync_err, False)
            return (f"Workshop Mod Active ({WORKSHOP_ITEM_ID})", False)

    # 2. Check or install in media_soviet/workshop_wip/3826453788
    wip_dir = os.path.join(media_dir, "workshop_wip", WORKSHOP_ITEM_ID)
    already_complete = os.path.exists(os.path.join(wip_dir, "workshopconfig.ini")) and all(
        os.path.exists(os.path.join(wip_dir, b, "building.nmf")) and
        os.path.exists(os.path.join(wip_dir, b, "building.ini"))
        for b in MOD_BUILDING_SOURCES
    )
    if already_complete:
        sync_err = _sync_bundled_configs(wip_dir)
        if sync_err:
            return (sync_err, False)
        return (f"Local Mod Active ({WORKSHOP_ITEM_ID})", False)

    if not os.path.isdir(bundled_root):
        return ("Bundled mod_assets missing", False)

    try:
        os.makedirs(wip_dir, exist_ok=True)
        for root_file in ("workshopconfig.ini", "previewimage.png"):
            src_f = os.path.join(bundled_root, root_file)
            if os.path.exists(src_f):
                shutil.copy2(src_f, os.path.join(wip_dir, root_file))

        for comecon_name, vanilla_base in MOD_BUILDING_SOURCES.items():
            b_dst = os.path.join(wip_dir, comecon_name)
            b_src = os.path.join(bundled_root, comecon_name)
            os.makedirs(b_dst, exist_ok=True)

            # Copy bundled INI/MTL configs (including night material_e.mtl)
            for cfg_file in cfg_files:
                s_cfg = os.path.join(b_src, cfg_file)
                if os.path.exists(s_cfg):
                    shutil.copy2(s_cfg, os.path.join(b_dst, cfg_file))

            # Copy official 3D model, collision bbox, fire, and GUI icon from player's vanilla installation
            nmf_src = os.path.join(media_dir, "buildings", f"{vanilla_base}.nmf")
            bbox_src = os.path.join(media_dir, "buildings_types", f"{vanilla_base}.bbox")
            fire_src = os.path.join(media_dir, "buildings_types", f"{vanilla_base}.fire")
            icon_src = os.path.join(media_dir, "editor", f"tool_{vanilla_base}.png")

            if os.path.exists(nmf_src):
                shutil.copy2(nmf_src, os.path.join(b_dst, "building.nmf"))
            if os.path.exists(bbox_src):
                shutil.copy2(bbox_src, os.path.join(b_dst, "building.bbox"))
            if os.path.exists(fire_src):
                shutil.copy2(fire_src, os.path.join(b_dst, "building.fire"))
            if os.path.exists(icon_src):
                shutil.copy2(icon_src, os.path.join(b_dst, "imagegui.png"))

        return (f"Auto-Installed Mod Pack ({WORKSHOP_ITEM_ID})", True)
    except PermissionError as pe:
        return (f"Mod Install Permission Error: Write permission required for game folder ({pe})", False)
    except Exception as e:
        return (f"Mod Auto-Install Error: {e}", False)

AUTH_CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "COMECON_Exchange")
AUTH_CONFIG_PATH = os.path.join(AUTH_CONFIG_DIR, "client_auth.json")
CLIENT_TASKS_DB_PATH = os.path.join(AUTH_CONFIG_DIR, ".client_tasks.db")
SHOW_HUD_SIGNAL_PATH = os.path.join(AUTH_CONFIG_DIR, "show_hud.signal")
_SINGLE_INSTANCE_MUTEX = None


# --- [Verbatim Slice 2: lines 585..606 of raktarmutat.py] ---
def _detect_default_os_lang():
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        primary = lang_id & 0x3FF
        if primary == 0x04:  # Chinese (Simplified / Traditional)
            return 'zh'
        if primary == 0x19:  # Russian
            return 'ru'
    except Exception:
        pass
    return 'en'


CLIENT_LANG = _detect_default_os_lang()


def L(en_s, ru_s, zh_s):
    if CLIENT_LANG == 'ru':
        return ru_s
    if CLIENT_LANG == 'zh':
        return zh_s
    return en_s

# --- [Verbatim Slice 3: lines 1047..1259 of raktarmutat.py] ---
# --- CREDENTIAL PERSISTENCE & PHASE 0: GRAPHICAL LOGIN WINDOW ---
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte))
    ]


def _atomic_write_json(file_path, data_dict):
    """Writes JSON dict to file atomically using a temporary file and os.replace."""
    dir_name = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(dir_name, exist_ok=True)
    temp_file = os.path.join(dir_name, f".tmp_{os.getpid()}_{secrets.token_hex(6)}.json")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, file_path)
        return True
    except Exception:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass
        return False


def _dpapi_encrypt(plaintext_bytes: bytes) -> str:
    """Encrypts bytes using Windows DPAPI (CryptProtectData). Returns base64 string or None."""
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_blob = DATA_BLOB(len(plaintext_bytes), ctypes.cast(ctypes.create_string_buffer(plaintext_bytes), ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if crypt32.CryptProtectData(ctypes.byref(in_blob), "comecon_auth", None, None, None, 0x1, ctypes.byref(out_blob)):
            raw_data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            kernel32.LocalFree(out_blob.pbData)
            return base64.b64encode(raw_data).decode('ascii')
    except Exception:
        pass
    return None


def _dpapi_decrypt(b64_cipher: str) -> str:
    """Decrypts base64 string encrypted with Windows DPAPI. Returns plaintext string or None."""
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        cipher_bytes = base64.b64decode(b64_cipher)
        in_blob = DATA_BLOB(len(cipher_bytes), ctypes.cast(ctypes.create_string_buffer(cipher_bytes), ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0x1, ctypes.byref(out_blob)):
            raw_data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            kernel32.LocalFree(out_blob.pbData)
            return raw_data.decode('utf-8')
    except Exception:
        pass
    return None


def get_migration_warning_message(migration_error: str) -> str:
    """Returns localized warning message for status_label based on credential migration error."""
    if migration_error == "plaintext_remained_on_disk":
        return L(
            "Security Alert: Migration failed. Please delete client_auth.json manually and re-login!",
            "Безопасность: Ошибка миграции. Удалите client_auth.json вручную и войдите снова!",
            "安全警告：密码迁移失败。请手动删除 client_auth.json 并重新登录！"
        )
    elif migration_error in ("atomic_write_failed_file_removed", "dpapi_failed_file_removed"):
        return L(
            "Security Notice: Saved password cleared due to migration error. Please re-enter password.",
            "Безопасность: Сохраненный пароль удален из-за ошибки. Введите пароль заново.",
            "安全通知：由于迁移错误已清除已保存的密码。请重新输入密码。"
        )
    elif migration_error == "dpapi_failed_cleared":
        return L(
            "Notice: Windows DPAPI encryption failed; saved credentials were sanitized.",
            "Внимание: Ошибка шифрования DPAPI; учетные данные очищены.",
            "通知：Windows DPAPI 加密失败，已清除凭据。"
        )
    return ""


def load_saved_credentials():
    global CLIENT_LANG
    try:
        if os.path.exists(AUTH_CONFIG_PATH):
            with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            saved_lang = data.get("lang")
            if saved_lang in ("en", "ru", "zh"):
                CLIENT_LANG = saved_lang

            if "password_enc" in data:
                enc = data.get("password_enc", "")
                data["password"] = _dpapi_decrypt(enc) if enc else ""
            elif "password" in data and data["password"]:
                # Legacy plaintext found: migrate to Windows DPAPI
                plain = data["password"]
                enc = _dpapi_encrypt(plain.encode('utf-8'))
                if enc:
                    migrated = {
                        "username": data.get("username", ""),
                        "password_enc": enc,
                        "remember": bool(data.get("remember", True)),
                        "lang": data.get("lang", CLIENT_LANG)
                    }
                    if _atomic_write_json(AUTH_CONFIG_PATH, migrated):
                        data["password_enc"] = enc
                        del data["password"]
                        data["password"] = plain
                        data["migration_success"] = True
                    else:
                        print("[AUTH] Error: Atomic write during migration failed. Attempting removal of plaintext file.")
                        try:
                            os.remove(AUTH_CONFIG_PATH)
                        except OSError:
                            pass
                        if not os.path.lexists(AUTH_CONFIG_PATH):
                            data["migration_error"] = "atomic_write_failed_file_removed"
                        else:
                            data["migration_error"] = "plaintext_remained_on_disk"
                        data["password"] = ""
                else:
                    # DPAPI encryption failed! Plaintext must NOT remain silently in file.
                    print("[AUTH] Error: Windows DPAPI encryption failed during migration.")
                    sanitized = {
                        "username": data.get("username", ""),
                        "password_enc": "",
                        "remember": False,
                        "lang": data.get("lang", CLIENT_LANG)
                    }
                    if _atomic_write_json(AUTH_CONFIG_PATH, sanitized):
                        data["migration_error"] = "dpapi_failed_cleared"
                    else:
                        print("[AUTH] CRITICAL: Failed to sanitize plaintext file. Attempting removal of plaintext file.")
                        try:
                            os.remove(AUTH_CONFIG_PATH)
                        except OSError:
                            pass
                        if not os.path.lexists(AUTH_CONFIG_PATH):
                            data["migration_error"] = "dpapi_failed_file_removed"
                        else:
                            data["migration_error"] = "plaintext_remained_on_disk"
                    data["password"] = ""
            else:
                data["password"] = ""
            return data
    except Exception:
        pass
    return {}


def save_credentials(username, password, remember=True):
    try:
        enc_pass = ""
        if remember and password:
            enc_pass = _dpapi_encrypt(password.encode('utf-8'))
            if not enc_pass:
                # Do NOT store plaintext password if DPAPI fails!
                print("[AUTH] Warning: Windows DPAPI encryption failed. Password not saved.")
                _atomic_write_json(AUTH_CONFIG_PATH, {
                    "username": username,
                    "password_enc": "",
                    "remember": False,
                    "lang": CLIENT_LANG
                })
                return False

        payload = {
            "username": username,
            "password_enc": enc_pass,
            "remember": bool(remember and enc_pass),
            "lang": CLIENT_LANG
        }
        return _atomic_write_json(AUTH_CONFIG_PATH, payload)
    except Exception:
        return False


def save_lang_preference(lang_code):
    global CLIENT_LANG
    if lang_code not in ("en", "ru", "zh"):
        return
    CLIENT_LANG = lang_code
    try:
        existing = {}
        if os.path.exists(AUTH_CONFIG_PATH):
            with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing["lang"] = CLIENT_LANG
        _atomic_write_json(AUTH_CONFIG_PATH, existing)
    except Exception:
        pass


def clear_saved_credentials():
    try:
        _atomic_write_json(AUTH_CONFIG_PATH, {
            "username": "",
            "password_enc": "",
            "remember": False,
            "lang": CLIENT_LANG
        })
    except Exception:
        pass

# --- [Verbatim Slice 4: lines 2199..2296 of raktarmutat.py] ---
# --- ACCOUNT-ISOLATED PERSISTENT SQLITE TASK JOURNAL (.client_tasks.db) ---
def _get_account_hash(token=None):
    tok = token or TOKEN or ""
    return hashlib.sha256(str(tok).encode("utf-8")).hexdigest()[:16]


def init_client_task_db(db_path=None):
    path = db_path or CLIENT_TASKS_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = FULL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS client_tasks ("
        "account_hash TEXT NOT NULL, "
        "task_uuid TEXT NOT NULL, "
        "task_id INTEGER, "
        "action TEXT NOT NULL, "
        "resource TEXT NOT NULL, "
        "amount REAL NOT NULL, "
        "state TEXT NOT NULL, "
        "snapshot_json TEXT, "
        "created_at REAL NOT NULL, "
        "updated_at REAL NOT NULL, "
        "PRIMARY KEY (account_hash, task_uuid)"
        ")"
    )
    # Prune ONLY ACKED entries older than 7 days
    cutoff = time.time() - (7 * 86400.0)
    conn.execute("DELETE FROM client_tasks WHERE state = 'ACKED' AND updated_at < ?", (cutoff,))
    conn.commit()
    return conn


def get_client_task_record(conn, account_hash, task_uuid):
    cur = conn.execute(
        "SELECT account_hash, task_uuid, task_id, action, resource, amount, state, snapshot_json, created_at, updated_at "
        "FROM client_tasks WHERE account_hash = ? AND task_uuid = ?",
        (account_hash, str(task_uuid))
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "account_hash": row[0],
        "task_uuid": row[1],
        "task_id": row[2],
        "action": row[3],
        "resource": row[4],
        "amount": row[5],
        "state": row[6],
        "snapshot_json": row[7],
        "created_at": row[8],
        "updated_at": row[9],
    }


def upsert_client_task_state(conn, account_hash, task_uuid, task_id, action, resource, amount, state, snapshot_obj=None, retries=3):
    now = time.time()
    if isinstance(snapshot_obj, str):
        snap_str = snapshot_obj
    elif snapshot_obj is not None:
        snap_str = json.dumps(snapshot_obj, sort_keys=True)
    else:
        snap_str = None
    for attempt in range(retries):
        try:
            if snap_str is not None:
                conn.execute(
                    "INSERT INTO client_tasks "
                    "(account_hash, task_uuid, task_id, action, resource, amount, state, snapshot_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(account_hash, task_uuid) DO UPDATE SET "
                    "task_id = excluded.task_id, state = excluded.state, "
                    "snapshot_json = excluded.snapshot_json, updated_at = excluded.updated_at",
                    (account_hash, str(task_uuid), int(task_id or 0), action, resource, float(amount), state, snap_str, now, now)
                )
            else:
                conn.execute(
                    "INSERT INTO client_tasks "
                    "(account_hash, task_uuid, task_id, action, resource, amount, state, snapshot_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?) "
                    "ON CONFLICT(account_hash, task_uuid) DO UPDATE SET "
                    "task_id = excluded.task_id, state = excluded.state, updated_at = excluded.updated_at",
                    (account_hash, str(task_uuid), int(task_id or 0), action, resource, float(amount), state, now, now)
                )
            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[TASK DB RETRY {attempt+1}/{retries}] {e}")
            time.sleep(0.05)
    return False


# --- [Verbatim Slice 5: lines 6701..7071 of raktarmutat.py] ---
def _compute_file_sha256(fpath):
    h = hashlib.sha256()
    with open(fpath, "rb") as fh:
        while True:
            chunk = fh.read(262144)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


UPDATER_LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", AUTH_CONFIG_DIR), "COMECON_Exchange")
UPDATER_LOG_PATH = os.path.join(UPDATER_LOG_DIR, "updater.log")
UPDATER_HELPER_PATH = os.path.join(UPDATER_LOG_DIR, "updater_helper.ps1")

UPDATER_POWERSHELL_SCRIPT = r'''# COMECON Central Exchange Client - Detached Post-Exit Updater Helper
param(
    [string]$TargetExe,
    [string]$NewExe,
    [string]$OldExe,
    [string]$ExpectedSha,
    [string]$LogFile,
    [int]$ParentPid
)

$ErrorActionPreference = "Stop"

function Write-Log([string]$msg) {
    try {
        $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        "[$ts] $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
    } catch {}
}

Write-Log "=== COMECON Detached Updater Started ==="
Write-Log "TargetExe: $TargetExe"
Write-Log "NewExe: $NewExe"
Write-Log "OldExe: $OldExe"
Write-Log "ParentPid: $ParentPid"

# 1. Wait for parent process and any TargetExe instances to exit
if ($ParentPid -gt 0) {
    Write-Log "Waiting for parent PID $ParentPid to exit..."
    try {
        $proc = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
        if ($proc) {
            $proc.WaitForExit(10000)
            Write-Log "Parent process has exited."
        }
    } catch {
        Write-Log "Parent process check notice: $_"
    }
}
try {
    $targetProcs = Get-Process | Where-Object { $_.Path -eq $TargetExe }
    foreach ($tp in $targetProcs) {
        Write-Log "Waiting for TargetExe process $($tp.Id) to exit..."
        $tp.WaitForExit(10000)
    }
} catch {
    Write-Log "TargetExe process wait notice: $_"
}

# 2. Verify NewExe exists and matches ExpectedSha before modifying TargetExe
if (-not (Test-Path -LiteralPath $NewExe)) {
    Write-Log "ERROR: Downloaded binary not found at $NewExe"
    exit 1
}

$hashNew = (Get-FileHash -LiteralPath $NewExe -Algorithm SHA256).Hash.ToLower()
if ($hashNew -ne $ExpectedSha.ToLower()) {
    Write-Log "ERROR: Pre-swap SHA-256 mismatch (Got: $hashNew, Expected: $ExpectedSha)"
    Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue
    exit 1
}

# 3. Swap with bounded retry loop (up to 30 attempts x 500ms = 15s)
$swapped = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        if (Test-Path -LiteralPath $OldExe) {
            Remove-Item -LiteralPath $OldExe -Force -ErrorAction Stop
        }
        Move-Item -LiteralPath $TargetExe -Destination $OldExe -Force -ErrorAction Stop
        Move-Item -LiteralPath $NewExe -Destination $TargetExe -Force -ErrorAction Stop
        $swapped = $true
        Write-Log "Swap succeeded on attempt $i"
        break
    } catch {
        Write-Log "Swap attempt $i failed: $_. Retrying in 500ms..."
        Start-Sleep -Milliseconds 500
    }
}

if (-not $swapped) {
    Write-Log "ERROR: Swap failed after 30 attempts. Attempting rollback..."
    if ((-not (Test-Path -LiteralPath $TargetExe)) -and (Test-Path -LiteralPath $OldExe)) {
        try {
            Move-Item -LiteralPath $OldExe -Destination $TargetExe -Force -ErrorAction Stop
            Write-Log "Rollback succeeded: restored original executable from $OldExe"
        } catch {
            Write-Log "CRITICAL: Rollback failed: $_"
        }
    }
    exit 1
}

# 4. Verify post-swap SHA-256 of TargetExe
$hashTarget = (Get-FileHash -LiteralPath $TargetExe -Algorithm SHA256).Hash.ToLower()
if ($hashTarget -ne $ExpectedSha.ToLower()) {
    Write-Log "ERROR: Post-swap SHA-256 verification failed on $TargetExe. Rolling back..."
    try {
        Move-Item -LiteralPath $TargetExe -Destination $NewExe -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $OldExe -Destination $TargetExe -Force -ErrorAction Stop
        Write-Log "Rollback completed after post-swap hash verification failure."
    } catch {
        Write-Log "CRITICAL: Post-swap rollback failed: $_"
    }
    exit 1
}

Write-Log "Update verified successfully. Launching: $TargetExe --updated"
try {
    Start-Process -FilePath $TargetExe -ArgumentList "--updated"
    Write-Log "Relaunch initiated successfully."
} catch {
    Write-Log "ERROR: Failed to relaunch updated binary: $_"
    exit 1
}
'''


def _spawn_detached_updater(exe_path, new_path, old_path, remote_sha, parent_pid=None):
    if parent_pid is None:
        parent_pid = os.getpid()
    os.makedirs(UPDATER_LOG_DIR, exist_ok=True)
    with open(UPDATER_HELPER_PATH, "w", encoding="utf-8") as f:
        f.write(UPDATER_POWERSHELL_SCRIPT)

    powershell_exe = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )
    if not os.path.exists(powershell_exe):
        powershell_exe = "powershell.exe"

    cmd = [
        powershell_exe,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        UPDATER_HELPER_PATH,
        "-TargetExe",
        exe_path,
        "-NewExe",
        new_path,
        "-OldExe",
        old_path,
        "-ExpectedSha",
        remote_sha,
        "-LogFile",
        UPDATER_LOG_PATH,
        "-ParentPid",
        str(parent_pid),
    ]
    creation_flags = 0x08000000  # CREATE_NO_WINDOW (Do NOT combine with DETACHED_PROCESS: mutually exclusive in Win32)
    return subprocess.Popen(cmd, close_fds=True, creationflags=creation_flags)


def check_and_apply_auto_update():
    """
    Defender-safe Self-Updater for compiled COMECON_Client.exe (Nuitka / PyInstaller):
    1. Only runs for compiled binaries; returns immediately in source execution.
    2. Exits immediately if relaunched with --updated (preventing infinite update loop
       and preserving .old rollback file).
    3. Resolves the real on-disk executable via get_real_executable_path().
    4. Cleans up stale leftover .old/.new files from earlier sessions.
    5. Queries /api/client_version and compares remote SHA-256 with real exe SHA-256.
    6. Streams the new binary with progress UI, verifies size, SHA-256, and MZ header.
    7. Spawns detached PowerShell updater helper and cleanly exits so Windows releases file handles.
    """
    global _SINGLE_INSTANCE_MUTEX
    if not is_compiled_binary():
        return

    # Prevent infinite relaunch loop and preserve rollback file right after update
    if "--updated" in sys.argv:
        return

    if "--no-update" in sys.argv or os.environ.get("COMECON_NO_UPDATE") == "1":
        return

    exe_path = get_real_executable_path()
    if not exe_path:
        print("[AUTO-UPDATE] Warning: Real executable path could not be resolved. Skipping auto-update.")
        return

    old_path = exe_path + ".old"
    new_path = exe_path + ".new"

    # Clean up stale leftover .old or partial .new files from earlier sessions
    for p in (old_path, new_path):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    try:
        local_sha = _compute_file_sha256(exe_path)
    except Exception:
        return

    try:
        r = requests.get(f"{API_URL}/client_version", timeout=4)
        if r.status_code != 200:
            return
        meta = r.json()
        if meta.get("status") != "success":
            return
        remote_sha = str(meta.get("sha256") or "").strip().lower()
        remote_size = int(meta.get("size") or 0)
        remote_mtime = int(meta.get("mtime") or 0)
        dl_rel = str(meta.get("download_url") or "/api/client_download")
    except Exception:
        return

    if not remote_sha or len(remote_sha) != 64 or remote_size < 65536:
        return

    if local_sha.lower() == remote_sha:
        return

    # If the local executable has a timestamp strictly newer than the remote binary,
    # do not downgrade to an older server version (e.g. freshly compiled client).
    try:
        local_mtime = int(os.path.getmtime(exe_path))
        if remote_mtime > 0 and local_mtime > remote_mtime + 5:
            print(f"[AUTO-UPDATE] Local binary is newer than server ({local_mtime} > {remote_mtime}). Skipping auto-update.")
            return
    except Exception:
        pass

    # Load saved language preference so the update window is localized
    load_saved_credentials()

    dl_url = dl_rel if dl_rel.startswith("http") else f"{BASE_URL}{dl_rel}"
    print(f"[AUTO-UPDATE] New client version detected (Server SHA256: {remote_sha[:12]}...). Downloading update...")

    upd_root = tk.Tk()
    upd_root.title(L(
        "COMECON Client — Automatic Update",
        "Клиент СЭВ — Автообновление",
        "经互会客户端 — 自动更新"
    ))
    upd_root.geometry("420x165")
    upd_root.configure(bg="#1a0505")
    upd_root.resizable(False, False)
    upd_root.attributes("-topmost", True)
    try:
        upd_root.iconbitmap(resource_path("comecon.ico"))
    except Exception:
        pass

    sw = upd_root.winfo_screenwidth()
    sh = upd_root.winfo_screenheight()
    upd_root.geometry(f"420x165+{(sw - 420) // 2}+{(sh - 165) // 2}")

    tk.Label(
        upd_root,
        text=L(
            "☭ COMECON SECRETARIAT AUTO-UPDATER ☭",
            "☭ АВТООБНОВЛЕНИЕ КЛИЕНТА СЭВ ☭",
            "☭ 经互会秘书处自动更新程序 ☭"
        ),
        bg="#1a0505", fg="#d4af37", font=("Segoe UI", 11, "bold")
    ).pack(pady=(16, 6))

    prog_lbl = tk.Label(
        upd_root,
        text=L(
            "Downloading latest COMECON_Client.exe (0%)...",
            "Загрузка новой версии COMECON_Client.exe (0%)...",
            "正在下载最新经互会客户端 COMECON_Client.exe (0%)..."
        ),
        bg="#1a0505", fg="#f5f5f5", font=("Segoe UI", 9)
    )
    prog_lbl.pack(pady=4)

    prog_bar = ttk.Progressbar(upd_root, orient="horizontal", length=350, mode="determinate", maximum=100)
    prog_bar.pack(pady=8)
    upd_root.update()

    update_ok = False
    try:
        with requests.get(dl_url, stream=True, timeout=25) as dl_resp:
            if dl_resp.status_code == 200:
                hasher = hashlib.sha256()
                downloaded = 0
                first_bytes = b""
                with open(new_path, "wb") as out_f:
                    for chunk in dl_resp.iter_content(chunk_size=131072):
                        if not chunk:
                            continue
                        if not first_bytes:
                            first_bytes = chunk[:2]
                        out_f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if remote_size > 0:
                            pct = min(100, int((downloaded * 100) / remote_size))
                            prog_bar["value"] = pct
                            mb_done = downloaded / (1024 * 1024)
                            mb_tot = remote_size / (1024 * 1024)
                            prog_lbl.config(
                                text=L(
                                    f"Downloading update... {pct}% ({mb_done:.1f} / {mb_tot:.1f} MB)",
                                    f"Загрузка обновления... {pct}% ({mb_done:.1f} / {mb_tot:.1f} МБ)",
                                    f"正在下载更新... {pct}% ({mb_done:.1f} / {mb_tot:.1f} MB)"
                                )
                            )
                            upd_root.update()

                calc_sha = hasher.hexdigest().lower()
                if first_bytes == b"MZ" and calc_sha == remote_sha and downloaded == remote_size:
                    update_ok = True
                else:
                    print(f"[AUTO-UPDATE] Checksum/header mismatch (got {calc_sha[:12]}, expected {remote_sha[:12]}). Aborting update.")
    except Exception as e:
        print(f"[AUTO-UPDATE] Download failed: {e}")

    try:
        upd_root.destroy()
    except Exception:
        pass

    if not update_ok:
        if os.path.exists(new_path):
            try:
                os.remove(new_path)
            except OSError:
                pass
        return

    # Detached post-exit PowerShell updater helper with bounded retries and rollback
    try:
        log_trace("Spawning detached updater helper")
        _spawn_detached_updater(exe_path, new_path, old_path, remote_sha)
        log_trace("Detached updater spawned, calling os._exit(0)")
        print("[AUTO-UPDATE] Detached updater helper spawned successfully. Exiting for update...")
        os._exit(0)
    except Exception as e:
        log_trace(f"Failed to spawn detached updater helper: {e}")
        print(f"[AUTO-UPDATE] Failed to spawn detached updater helper: {e}")
        # Leave client running; do not exit, preserve existing executable
        return


def log_trace(msg):
    try:
        os.makedirs(AUTH_CONFIG_DIR, exist_ok=True)
        with open(os.path.join(AUTH_CONFIG_DIR, "client_trace.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

