# sims4-mod-fixer
A Python script to clean, organize, and update Sims 4 mods automatically.
# Sims 4 Mod Fixer 🛠️

A handy utility script to manage and clean your Sims 4 Mods folder on macOS.

## Features

- **Backup**: ZIPs your entire Mods folder before making changes.
- **Garbage Clean**: Removes system files like `.DS_Store`, `Thumbs.db`, etc.
- **Tiny Mod Quarantine**: Moves suspiciously small mods (< 1 KB) into quarantine.
- **Duplicate Detection**: Detects identical files by MD5 and quarantines extras.
- **Archive Handling**: Extracts `.zip`, `.rar`, `.7z` archives into proper category folders.
- **Categorization**: Automatically moves mods into subfolders (Kitchen, Bathroom, Scripts, etc.).
- **Corrupt Detection**: Identifies unreadable `.package` or `.ts4script` files and quarantines them.
- **Resource.cfg Update**: Rewrites `Resource.cfg` to maintain mod load order.
- **Mod Inventory Export**: Writes mod metadata into JSON and CSV files (e.g. `ModsInventory.json`, `ModsInventory.csv`).
- **TGI Conflict & Broken Mod Reports**: Generates conflict summaries and broken file lists.
- **Mod Version Checker (Optional)**: Compares installation timestamps against a `KnownModVersions.json` file, and auto-downloads updates if a URL is provided.
- **Optional GUI**: Run from a simple tkinter window by using `--gui`.

## How to Use

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MissyAI87/sims4-mod-fixer.git
   cd sims4-mod-fixer
