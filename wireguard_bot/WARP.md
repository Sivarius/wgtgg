# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.
``

Project overview

A Telegram bot (aiogram) that manages WireGuard peers using simple JSON files for state. Core responsibilities:
- Handle Telegram commands (/add, /list, /remove, /edit, /info, /reload)
- Persist admins, peers, archive, and last allocated IP under config/
- Generate WireGuard client configs from config/template.conf and apply/remove peers via the wg CLI
- Daily jobs intended for notifications and auto-disabling expired peers via APScheduler

Common commands

Windows (PowerShell):
1) Python env and deps
- py -m venv .venv
- .\.venv\Scripts\Activate.ps1
- pip install aiogram apscheduler

2) Set Telegram Bot token and run
- $env:BOT_TOKEN = "{{TELEGRAM_BOT_TOKEN}}"
- python bot.py

Linux (bash):
1) Prereqs for full functionality
- Ensure wg CLI and systemd are available (WireGuard installed), and bash exists (wg_utils uses bash-specific process substitution)
2) Python env and deps
- python3 -m venv .venv
- source .venv/bin/activate
- pip install aiogram apscheduler
3) Set token and run
- export BOT_TOKEN="{{TELEGRAM_BOT_TOKEN}}"
- python3 bot.py

Tests/lint/build
- No test suite, linter config, or build tooling are present in this repository.

Architecture and data flow

Entry point: bot.py
- aiogram Bot/Dispatcher with command handlers:
  - /add name, dd.mm.yyyy: create a peer, allocate next IP, generate keys and client .conf, store in peers DB
  - /list: list active peers from JSON DB
  - /remove idN: move peer to archive and remove from wg
  - /edit idN dd.mm.yyyy: update expiry, possibly restore from archive and re-apply to wg
  - /info idN: show details
  - /reload: archive expired peers and (re)apply active peers to wg
- Admin auth: user ID must be in config/admins.json
- Scheduling: APScheduler (AsyncIOScheduler) intended to run daily jobs for notifications and auto-disable; wiring currently incomplete (see Gotchas)

Persistence: utils/json_db.py + JSON under config/
- Stores and retrieves Python dicts from JSON files (admins, peers, archive, last_ip)
- IDs are of the form idN and are derived from existing peers + archived peers
- last_ip.json tracks the last allocated address for incremental assignment

WireGuard integration: utils/wg_utils.py
- Allocates next IP from last_ip.json
- Generates private/public/preshared keys via wg and bash process substitution
- Renders client config from config/template.conf (%AD%, %PrK%, %PhK%) and writes to wg/clients/{id}.conf
- Applies/removes peers using wg set ... and restarts wg-quick@interface via systemctl
- Linux-specific: requires wg, bash, and systemd; will not function on Windows without WSL or a Linux host

Background jobs: utils/notifier.py, utils/disabler.py
- Intended to notify admins about expiring peers and to move expired peers to archive while removing them from wg
- Both operate over config/peers.json and config/archive.json

Gotchas and inconsistencies to be aware of

These issues must be addressed before the bot works end-to-end:
- File naming mismatch: code refers to config/archive.json but the repo contains config/archieve.json; standardize on archive.json
- Empty/invalid JSON: config/peers.json and config/archieve.json are empty files; initialize them as valid JSON (e.g., peers.json: {"peers": []}, archive.json: {"archive": []})
- Absolute log path: bot.py uses LOG_FILE = "/wireguard_bot/logs/bot.txt" (leading slash). On Windows and most setups this will fail; switch to a repo-relative path like logs/bot.txt
- Package/import drift:
  - utils/json_db.py uses Path without importing it and its API does not match how it’s called from bot.py (bot expects set/pop/replace_all/save, notifier/disabler expect load_json/save_json)
  - utils/notifier.py and utils/disabler.py import from wireguard_bot.utils..., but the repository is not structured as an installable package; use relative imports or make the project a package
  - bot.schedule_daily_jobs references disable_expired_peers and send_notifications without importing their names into the module namespace (currently only disabler and notifier are imported)
- Signature mismatches:
  - wg_utils.generate_client_config returns (client_id, conf_path) but bot.py expects (client_id, config_text, client_data) and writes its own file; reconcile to a single contract
  - wg_utils.apply_peer/remove_peer signatures differ from how bot.py calls them
- Linux-only commands: wg_utils relies on bash process substitution (<(echo ...)) and systemctl; these will fail on Windows without WSL or adaptations

Operational assumptions
- Run the bot from the repository root so relative paths to config/, logs/, and wg/ resolve correctly
- Ensure config/template.conf contains correct server-side values (Peer section should point to your server’s PublicKey and Endpoint)
- admins.json must list Telegram user IDs allowed to operate the bot

What to do first if bringing this up
1) Fix JSON files and naming under config/ (archive vs archieve; initialize peers/archive JSON)
2) Align json_db API and imports with actual usage across bot.py, notifier.py, disabler.py, and wg_utils.py
3) Decide the OS target (Linux recommended) and ensure wg and systemd are present; for Windows, develop logic paths that skip wg operations or use WSL
4) Update log file paths to be repo-relative
