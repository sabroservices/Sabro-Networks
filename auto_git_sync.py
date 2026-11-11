#!/usr/bin/env python3
"""
Real-time Automatic Git Sync Watcher for Sabro Networks.
Monitors directory changes, automatically commits, and pushes to GitHub (origin main),
which automatically triggers cloud deployment on Render.
"""
import os
import time
import subprocess
from datetime import datetime

WATCH_DIR = os.path.dirname(os.path.abspath(__file__))
POLL_INTERVAL_SECONDS = 3
DEBOUNCE_SECONDS = 5

# Files and directories to ignore during change detection
IGNORED_PATTERNS = [
    ".git", "__pycache__", ".pytest_cache", "sabro_isp.db",
    "sabro_isp.db-wal", "sabro_isp.db-shm", "sabro_isp.db-journal",
    ".idea", ".vscode", "scratch", "tmp", "temp", ".log",
    "static/uploads/pfp/pfp_"
]

def find_git_exe():
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Programs", "Git", "cmd", "git.exe"),
        "git"
    ]
    for c in candidates:
        if os.path.isabs(c) and os.path.exists(c):
            return c
    return "git"

GIT_BIN = find_git_exe()

def run_git(args):
    try:
        res = subprocess.run(
            [GIT_BIN] + args,
            cwd=WATCH_DIR,
            capture_output=True,
            text=True,
            timeout=45
        )
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def has_git_changes():
    success, out, _ = run_git(["status", "--porcelain"])
    if not success or not out:
        return False, []

    changed_files = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        filename = parts[1] if len(parts) > 1 else parts[0]
        if any(ignored in filename for ignored in IGNORED_PATTERNS):
            continue
        changed_files.append(filename)
    return len(changed_files) > 0, changed_files

def main():
    print("=" * 65)
    print("  Sabro Networks - Continuous Real-Time GitHub & Render Sync")
    print(f"  Watching directory: {WATCH_DIR}")
    print(f"  Git Executable:     {GIT_BIN}")
    print("=" * 65)
    print("[*] Monitoring for code changes... (Press Ctrl+C to stop)\n")

    last_change_time = None

    while True:
        try:
            has_changes, changed_files = has_git_changes()

            if has_changes:
                if last_change_time is None:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Detected changes in {len(changed_files)} file(s):")
                    for f in changed_files[:5]:
                        print(f"   -> {f}")
                    if len(changed_files) > 5:
                        print(f"   -> ... and {len(changed_files) - 5} more")
                    print(f"[*] Waiting {DEBOUNCE_SECONDS}s to finish edits before pushing...")
                    last_change_time = time.time()
                elif time.time() - last_change_time >= DEBOUNCE_SECONDS:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    summary = f"auto-sync: update ({len(changed_files)} file(s) at {timestamp})"

                    print(f"\n[*] Committing changes: '{summary}'...")
                    run_git(["add", "."])
                    c_ok, c_out, c_err = run_git(["commit", "-m", summary])

                    if c_ok or "nothing to commit" not in (c_out + c_err):
                        print("[*] Syncing & pushing to GitHub (origin main)...")
                        p_ok, p_out, p_err = run_git(["push", "origin", "main"])
                        if not p_ok:
                            run_git(["pull", "--rebase", "origin", "main"])
                            p_ok, p_out, p_err = run_git(["push", "origin", "main"])

                        if p_ok:
                            print(f"[SUCCESS] Pushed to GitHub at {timestamp}!")
                            print("          -> Render is automatically deploying your changes now!\n")
                        else:
                            print(f"[WARNING] Push failed: {p_err or p_out}")
                            print("          Will retry automatically.\n")

                    last_change_time = None
            else:
                last_change_time = None

            time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n[*] Real-time auto-sync stopped.")
            break
        except Exception as e:
            print(f"[ERROR] Exception in watcher loop: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
