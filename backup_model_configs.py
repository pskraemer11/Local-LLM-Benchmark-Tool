"""
Backup/Restore utility for LM Studio per-model configs.

Usage:
    python backup_model_configs.py backup          # Create timestamped backup
    python backup_model_configs.py list             # List available backups
    python backup_model_configs.py restore <name>   # Restore from backup
    python backup_model_configs.py restore --latest # Restore newest backup
"""
import shutil, sys, os, glob
from datetime import datetime

CONFIG_DIR = os.path.expanduser(r'~\.lmstudio\.internal\user-concrete-model-default-config')
BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups', 'lmstudio-configs')

def backup():
    if not os.path.isdir(CONFIG_DIR):
        print(f"[ERROR] Config directory not found: {CONFIG_DIR}")
        return False
    ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    dst = os.path.join(BACKUP_DIR, ts)
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(CONFIG_DIR):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, CONFIG_DIR)
            dst_file = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src, dst_file)
    count = sum(len(files) for _, _, files in os.walk(dst))
    print(f"[OK] Backup saved: {dst} ({count} files)")
    return True

def list_backups():
    if not os.path.isdir(BACKUP_DIR):
        print("[INFO] No backups found.")
        return
    backups = sorted(os.listdir(BACKUP_DIR), reverse=True)
    for b in backups:
        count = sum(len(files) for _, _, files in os.walk(os.path.join(BACKUP_DIR, b)))
        print(f"  {b}  ({count} files)")

def restore(name=None):
    if not os.path.isdir(BACKUP_DIR):
        print("[ERROR] No backups directory.")
        return False
    if name == '--latest' or name is None:
        backups = sorted(os.listdir(BACKUP_DIR), reverse=True)
        if not backups:
            print("[ERROR] No backups found.")
            return False
        name = backups[0]
    src = os.path.join(BACKUP_DIR, name)
    if not os.path.isdir(src):
        print(f"[ERROR] Backup not found: {name}")
        return False
    for root, dirs, files in os.walk(src):
        for f in files:
            src_file = os.path.join(root, f)
            rel = os.path.relpath(src_file, src)
            dst = os.path.join(CONFIG_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src_file, dst)
    count = sum(len(files) for _, _, files in os.walk(src))
    print(f"[OK] Restored {count} files from: {name}")
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'backup':
        sys.exit(0 if backup() else 1)
    elif cmd == 'list':
        list_backups()
    elif cmd == 'restore':
        name = sys.argv[2] if len(sys.argv) > 2 else '--latest'
        sys.exit(0 if restore(name) else 1)
    else:
        print(f"[ERROR] Unknown command: {cmd}")
        sys.exit(1)
