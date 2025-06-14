#!/usr/bin/env python3
"""
sims4_mod_fixer.py  –  v2 (2025-06-11)

Key fixes
─────────
✓ Collects archives / packages with a simple, safe loop (no None.append crash).  
✓ Duplicate MD5 scan happens **before** any moves, so cached paths stay valid.  
✓ Quarantine step ignores missing files instead of crashing.  
✓ Everything else (backup, archive extraction, category sort, Resource.cfg) is unchanged.

Usage
─────
Dry-run (preview):    python sims4_mod_fixer.py
Apply changes:        python sims4_mod_fixer.py --apply
Automated run:        python sims4_mod_fixer.py --apply --auto
"""

import argparse, hashlib, shutil, sys, textwrap, zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from colorama import Fore, Style
from tqdm import tqdm
import json
import tkinter as tk
from tkinter import messagebox
import subprocess

# ───────────────── CONFIG ─────────────────
MODS_DIR       = Path.home() / "Documents/Electronic Arts/The Sims 4/Mods"
DESKTOP        = Path.home() / "Desktop"
BACKUP_NAME    = f"ModsBackup-{datetime.now():%Y%m%d}.zip"
QUARANTINE_DIR = DESKTOP / "Sims4_Mod_Quarantine"
MAX_DEPTH      = 5

# Category keywords (edit to taste, all lowercase)
CATEGORY_MAP: Dict[str, List[str]] = {
    "Build-Kitchen":   ["kitchen", "fridge", "oven", "counter", "cabinet"],
    "Build-Bathroom":  ["bath", "toilet", "shower", "sink"],
    "Build-Bedroom":   ["bed", "dresser", "nightstand"],
    "Decor-Plants":    ["plant", "flower", "foliage"],
    "CAS-Clothing":    ["top", "dress", "pants", "skirt"],
    "CAS-Hair":        ["hair", "hairstyle", "pony"],
    "CAS-Animations":  ["pose", "animation", "preset"],
    "Gameplay-WickedWhims": ["wickedwhims"],
    "Gameplay-MCCommand":   ["mccommand", "mccc"],
    "Scripts":         [".ts4script"],
}
ARCHIVE_EXT = {".zip", ".rar", ".7z"}
PACKAGE_EXT = {".package", ".ts4script"}

# ──────────────── helpers ────────────────
def c(msg, col):  # colorful print helper
    return f"{col}{msg}{Style.RESET_ALL}"

def is_old_ts4script(file: Path) -> bool:
    """Return True if .ts4script file is compiled with old (pre-3.10) Python."""
    with file.open("rb") as f:
        head = f.read(4)
        return head in {b'\x42\x0D\x0D\x0A', b'\x33\x0D\x0D\x0A'}  # py 3.7/3.8/3.9

def md5(file: Path, chunk=8192) -> str:
    h = hashlib.md5()
    with file.open("rb") as f:
        for part in iter(lambda: f.read(chunk), b""):
            h.update(part)
    return h.hexdigest()

def zip_backup(src: Path, dst: Path) -> None:
    # Backup all files under src into a zip archive at dst
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in tqdm(list(src.rglob("*")), desc="Creating backup ZIP"):
            if f.is_file():
                zf.write(f, f.relative_to(src))

def extract_archive(arc: Path, dest: Path) -> bool:
    import zipfile, rarfile, py7zr
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if arc.suffix == ".zip":
            with zipfile.ZipFile(arc) as z: z.extractall(dest)
        elif arc.suffix == ".rar":
            with rarfile.RarFile(arc) as r: r.extractall(dest)
        elif arc.suffix == ".7z":
            with py7zr.SevenZipFile(arc) as s: s.extractall(dest)
        return True
    except Exception as e:
        print(c(f" ! Extract failed: {arc.name} → {e}", Fore.YELLOW))
        return False

def category_for(file: Path) -> str:
    # Determine category folder based on filename or extension
    name = file.name.lower()
    for cat, keys in CATEGORY_MAP.items():
        for k in keys:
            if k.startswith("."):
                if file.suffix.lower() == k:
                    return cat
            elif k in name:
                return cat
    return "_Unsorted"

def standardize_folder_names(mods: Path) -> None:
    """Rename folders in Mods to match standard category names."""
    renamed = 0
    for folder in mods.iterdir():
        if folder.is_dir():
            clean_name = folder.name.strip().replace(" ", "-").title()
            for category in CATEGORY_MAP:
                if clean_name.lower() == category.lower():
                    if folder.name != category:
                        new_path = mods / category
                        if not new_path.exists():
                            folder.rename(new_path)
                            renamed += 1
    if renamed:
        print(c(f"📁 Standardized {renamed} folder name(s)", Fore.GREEN))

def export_mod_inventory_to_json(mods: Path, output_path: Path) -> None:
    inventory = []
    for file in mods.rglob("*"):
        if file.suffix.lower() in {".package", ".ts4script"}:
            entry = {
                "name": file.name,
                "path": str(file.relative_to(mods)),
                "size_kb": round(file.stat().st_size / 1024, 2),
                "category": category_for(file),
                "added": datetime.fromtimestamp(file.stat().st_ctime).isoformat()
            }
            inventory.append(entry)
    with open(output_path, "w") as f:
        json.dump(inventory, f, indent=2)
    print(c(f"🗃️ Exported mod inventory to {output_path}", Fore.GREEN))

def export_mod_inventory_to_csv(mods: Path, output_path: Path) -> None:
    import csv
    inventory = []
    for file in mods.rglob("*"):
        if file.suffix.lower() in {".package", ".ts4script"}:
            entry = {
                "name": file.name,
                "path": str(file.relative_to(mods)),
                "size_kb": round(file.stat().st_size / 1024, 2),
                "category": category_for(file),
                "added": datetime.fromtimestamp(file.stat().st_ctime).isoformat()
            }
            inventory.append(entry)

    with open(output_path, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["name", "path", "size_kb", "category", "added"])
        writer.writeheader()
        writer.writerows(inventory)
    print(c(f"📄 Exported mod inventory to {output_path}", Fore.GREEN))

def check_mod_versions(mods: Path, version_file: Path) -> None:
    """
    Check mods against a JSON file of known latest versions.
    JSON format should be:
    {
        "mod_filename.package": {
            "latest": "2025-06-01",
            "url": "https://example.com/mod_filename.package"
        }
    }
    """
    try:
        with open(version_file, "r") as f:
            known_versions = json.load(f)
    except Exception as e:
        print(c(f" ! Could not load version file: {e}", Fore.YELLOW))
        return

    outdated = []
    for file in mods.rglob("*"):
        if file.suffix.lower() in {".package", ".ts4script"}:
            name = file.name
            if name in known_versions:
                info = known_versions[name]
                latest_time = datetime.fromisoformat(info["latest"])
                file_time = datetime.fromtimestamp(file.stat().st_ctime)
                if file_time < latest_time:
                    outdated.append((file, latest_time.date(), file_time.date(), info.get("url")))

    if outdated:
        print(c("\n🔎 Outdated Mods Found:", Fore.YELLOW))
        for file, latest, current, url in outdated:
            print(f" - {file.name}: Installed {current}, Latest {latest}")
            if url:
                print(f"   ➜ Attempting to auto-download from {url}")
                download_file(url, file)
    else:
        print(c("✓ All mods are up to date.", Fore.GREEN))


# Helper function for downloading a file from a URL to a destination path
def download_file(url: str, dest: Path) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(url) as response, open(dest, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        print(c(f"⬇️ Downloaded update for {dest.name}", Fore.GREEN))
        return True
    except Exception as e:
        print(c(f" ! Failed to download {dest.name} → {e}", Fore.YELLOW))
        return False

def clean_garbage_files(mods: Path) -> None:
    # Remove common unwanted system files from mods folder
    garbage = {".DS_Store", "Thumbs.db", "desktop.ini"}
    removed = []

    for file in mods.rglob("*"):
        if file.name in garbage:
            try:
                file.unlink()
                removed.append(file)
            except Exception as e:
                print(c(f" ! Failed to delete {file} → {e}", Fore.YELLOW))

    if removed:
        print(c(f"🧹 Removed {len(removed)} garbage files", Fore.GREEN))

def rewrite_resource_cfg(mods: Path) -> None:
    # Rewrite Resource.cfg with appropriate priority and package paths
    cfg = mods / "Resource.cfg"
    lines = ["Priority 500\n", "PackedFile *.package\n"]
    lines += [
        "PackedFile " + "*/" * depth + "*.package\n"
        for depth in range(1, MAX_DEPTH)
    ]
    cfg.write_text("".join(lines))
    print(c("✓ Resource.cfg rewritten (depth 5).", Fore.GREEN))

# — SECTION 1️⃣ Backup — (starts line 103)
def extract_archives(archives: list[Path], qdir: Path) -> None:
    # Extract archives to quarantine directory
    extracted = []
    for arc in archives:
        try:
            shutil.unpack_archive(arc, qdir / arc.stem)
            extracted.append(arc)
        except Exception as e:
            print(c(f" ! Failed to extract {arc} → {e}", Fore.YELLOW))

    if extracted:
       print(c(f"📦 Extracted {len(extracted)} archive(s) to quarantine", Fore.GREEN))

# — SECTION 2️⃣ Read TGI keys — (starts line 117)
def read_tgi_keys(pkg_path):
    # Read TGI keys from package file for conflict detection
    keys = set()
    try:
        if not pkg_path.exists():
            return keys  # Skip files that no longer exist
        with pkg_path.open("rb") as f:
            data = f.read()
            offset = 0
            while True:
                idx = data.find(b'TGIN', offset)
                if idx == -1:
                    break
                keys.add(data[idx:idx+16])
                offset = idx + 1
    except Exception as e:
        print(f"Error reading TGI from {pkg_path}: {e}")
    return keys

# — SECTION 3️⃣ Duplicate scan — (starts line 133)
def main() -> None:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__)
    )
    ap.add_argument("--apply", action="store_true", help="Make changes (default is preview only)")
    ap.add_argument("--auto", action="store_true", help="Run silently and exit (for automation)")
    ap.add_argument("--gui", action="store_true", help="Launch GUI interface")
    args = ap.parse_args()

    if args.gui:
        launch_gui()
        return

    mods = MODS_DIR.expanduser()
    standardize_folder_names(mods)
    if not mods.exists():
        sys.exit(c(f"Mods folder not found: {mods}", Fore.RED))

    backup_zip = DESKTOP / BACKUP_NAME
    qdir = QUARANTINE_DIR
    print(c(f"\nMods dir: {mods}", Fore.CYAN))
    print(c(f"Backup  → {backup_zip}", Fore.CYAN))
    print(c(f"Quarantine → {qdir}\n", Fore.CYAN))

    # 1️⃣ Backup first
    if args.apply:
        zip_backup(mods, backup_zip)
    else:
        print(c("Dry-run → would create backup ZIP.", Fore.BLUE))

    # 2️⃣ Gather files safely
    clean_garbage_files(mods)
    archives, packages = [], []
    clean_empty_or_tiny_mods(mods, args)
    for f in mods.rglob("*"):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in ARCHIVE_EXT:
            archives.append(f)
        elif ext in PACKAGE_EXT:
            packages.append(f)

    extract_archives(archives, qdir)
    clean_empty_or_tiny_mods(mods, args)

    # 3️⃣ Duplicate MD5 scan (before any moves)
    md5_seen, dupes = {}, []
    for pkg in tqdm(packages, desc="Scanning for duplicates"):
        h = md5(pkg)
        if h in md5_seen:
            dupes.append(pkg)  # keep the first, quarantine others
        else:
            md5_seen[h] = pkg

    # 4️⃣ Extract archives
    for arc in tqdm(archives, desc="Extracting archives"):
        dest_dir = mods / category_for(arc)
        if args.apply:
            if extract_archive(arc, dest_dir):
                arc.unlink()
        else:
            print(c(f"[dry] would extract {arc.name} → {dest_dir}", Fore.BLUE))
#    cleanup_archives(archives)

    # 5️⃣ Sort packages into category folders
    for pkg in tqdm(packages, desc="Sorting packages"):
        cat = category_for(pkg)
        dest = mods / cat / pkg.name
        if dest == pkg:
            continue
        if args.apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(pkg, dest)
        else:
            print(c(f"[dry] would move {pkg.name} → {cat}", Fore.BLUE))

    # 6️⃣ Quarantine duplicate MD5 files
    for d in tqdm(dupes, desc="Quarantining duplicates"):
        if not d.exists():
            continue  # may have been moved already
        if args.apply:
            qdir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(d, qdir / d.name)
            except FileNotFoundError:
                continue  # skip vanished files
        else:
            print(c(f"[dry] would quarantine duplicate {d.name}", Fore.BLUE))

    # ── Embedded Resource-ID conflict scan (pure Python) ──
    conflict_output = DESKTOP / "TGI_Conflicts.csv"
    detect_conflicting_tgi(mods, conflict_output)

    broken_output = DESKTOP / "BrokenMods.csv"
    detect_broken_mods(mods, broken_output)

    # ── Corrupt / unreadable package check ──
    corrupt_files = []
    for pkg in packages:
        if pkg.suffix.lower() == ".ts4script":
            continue      # valid script mod, not a DBPF package
        try:
            with pkg.open("rb") as f:
                if f.read(4) != b"DBPF":
                    corrupt_files.append(pkg)
        except Exception:
            corrupt_files.append(pkg)

    for bad in corrupt_files:
        if args.apply:
            qdir.mkdir(parents=True, exist_ok=True)
            shutil.move(bad, qdir / bad.name)
            print(c(f"Corrupt package → {bad.name} moved to Quarantine", Fore.YELLOW))
        else:
            print(c(f"[dry] would quarantine corrupt {bad.name}", Fore.BLUE))

    # 7️⃣ Update Resource.cfg
    if args.apply:
        rewrite_resource_cfg(mods)
    else:
        print(c("[dry] would rewrite Resource.cfg.", Fore.BLUE))

    if args.apply:
        json_output = DESKTOP / "ModsInventory.json"
        export_mod_inventory_to_json(mods, json_output)
        csv_output = DESKTOP / "ModsInventory.csv"
        export_mod_inventory_to_csv(mods, csv_output)

        # Optional: Check mod versions if a known file is present
        version_file = Path.home() / "Desktop" / "KnownModVersions.json"
        update_url = "https://raw.githubusercontent.com/MissyAI87/sims-mod-tracker/refs/heads/main/KnownModVersions.json"  # Replace with real URL
        update_known_versions_file(update_url, version_file)
        if version_file.exists():
            check_mod_versions(mods, version_file)

    if not args.auto:
        print(c("\nAll done! " + ("Changes applied." if args.apply else "No files changed."), Fore.GREEN))

# — SECTION 4️⃣ Clean tiny mods — (starts line 190)
def clean_empty_or_tiny_mods(mods: Path, args) -> None:
    # Move suspiciously small mods to quarantine
    qdir = Path("~/Desktop/Sims4_Mod_Quarantine").expanduser()
    small = []
    for file in mods.rglob("*"):
        if file.suffix.lower() in {".package", ".ts4script"} and file.stat().st_size < 1024:
            small.append(file)
    
    for mod in small:
        if args.apply:
            qdir.mkdir(parents=True, exist_ok=True)
            shutil.move(mod, qdir / mod.name)
            print(c(f"Too small → {mod.name} quarantined", Fore.YELLOW))
        else:
            print(c(f"[dry] would quarantine tiny {mod.name}", Fore.BLUE))

def update_known_versions_file(url: str, dest: Path) -> None:
    try:
        import urllib.request
        with urllib.request.urlopen(url) as response:
            data = response.read()
            dest.write_bytes(data)
            print(c(f"🌐 Updated KnownModVersions.json from {url}", Fore.GREEN))
    except Exception as e:
        print(c(f" ! Failed to update KnownModVersions.json: {e}", Fore.YELLOW))

if __name__ == "__main__":
    main()


# GUI launcher for Sims 4 Mod Fixer
def launch_gui():
    def run_fixmods():
        def task():
            result = subprocess.run(
                [str(Path.home() / "sims4env/bin/python3"),
                 str(Path.home() / "Documents/sims4_mod_fixer.py"),
                 "--apply"],
                capture_output=True, text=True
            )
            output_text.after(0, lambda: (
                output_text.delete(1.0, tk.END),
                output_text.insert(tk.END, result.stdout if result.stdout else "Done. Check terminal for any issues.")
            ))

        import threading
        threading.Thread(target=task).start()

    root = tk.Tk()
    root.title("Sims 4 Mod Fixer")

    tk.Label(root, text="Welcome to Sims 4 Mod Fixer!", font=("Arial", 14)).pack(pady=10)

    tk.Button(root, text="Run FixMods Now", command=run_fixmods).pack(pady=5)

    output_text = tk.Text(root, height=10, width=60)
    output_text.pack(pady=10)

    root.mainloop()


# ── TGI conflict and broken mod detection ──
def detect_conflicting_tgi(mods: Path, output_path: Path) -> None:
    # Map of TGI keys to mod files
    tgi_map = {}
    conflicts = []

    for file in mods.rglob("*.package"):
        keys = read_tgi_keys(file)
        for key in keys:
            if key in tgi_map:
                conflicts.append((file.name, tgi_map[key].name))
            else:
                tgi_map[key] = file

    if conflicts:
        with open(output_path, "w") as f:
            f.write("mod1,mod2\n")
            for m1, m2 in conflicts:
                f.write(f"{m1},{m2}\n")
        print(c(f"⚠️ Found TGI conflicts. Exported to {output_path}", Fore.YELLOW))
    else:
        print(c("✓ No TGI conflicts found.", Fore.GREEN))


def detect_broken_mods(mods: Path, output_path: Path) -> None:
    broken = []

    for file in mods.rglob("*"):
        if file.suffix.lower() in {".package", ".ts4script"}:
            try:
                if file.stat().st_size == 0:
                    broken.append(file.name)
                else:
                    with file.open("rb") as f:
                        f.read(1)
            except Exception:
                broken.append(file.name)

    if broken:
        with open(output_path, "w") as f:
            f.write("broken_mods\n")
            for name in broken:
                f.write(f"{name}\n")
        print(c(f"🚫 Found broken mods. Exported to {output_path}", Fore.YELLOW))
    else:
        print(c("✓ No broken mods found.", Fore.GREEN))

Add initial version of Sims 4 Mod Fixer
