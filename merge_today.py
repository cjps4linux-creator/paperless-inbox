import os
from pathlib import Path
import sys
import glob
import subprocess
from datetime import datetime

WATCH_DIR = os.path.expandvars(r'%USERPROFILE%\Downloads\paperless-inbox')
OUT_DIR = os.path.expandvars(r'%USERPROFILE%\Documents\Paperless')
# Path to the pdfcraft CLI used for merging. Override with PDFCRAFT_CLI.
# Default assumes pdfcraft is cloned as a sibling of this repository.
_PDFCRAFT_DEFAULT = Path(__file__).resolve().parent.parent / "pdfcraft" / "target" / "release" / "pdfcraft-cli.exe"
PDFCRAFT_CLI = os.environ.get("PDFCRAFT_CLI", str(_PDFCRAFT_DEFAULT))

os.makedirs(OUT_DIR, exist_ok=True)

today = datetime.now().strftime('%Y-%m-%d')
files = sorted(glob.glob(os.path.join(WATCH_DIR, f'{today}_*.pdf')))
files += sorted(glob.glob(os.path.join(WATCH_DIR, f'{today}_*.jpg')))
files += sorted(glob.glob(os.path.join(WATCH_DIR, f'{today}_*.jpeg')))
files += sorted(glob.glob(os.path.join(WATCH_DIR, f'{today}_*.png')))
files += sorted(glob.glob(os.path.join(WATCH_DIR, f'{today}_*.tif')))
files += sorted(glob.glob(os.path.join(WATCH_DIR, f'{today}_*.tiff')))
if not files:
    print('No files for', today)
    sys.exit(0)
out = os.path.join(OUT_DIR, f'Receipts-{today}.pdf')

if len(files) == 1:
    # just copy/rename to out
    try:
        import shutil
        shutil.copy2(files[0], out)
        print('Single file copied to', out)
        try:
            os.remove(files[0])
        except:
            pass
        sys.exit(0)
    except Exception as e:
        print('copy err', e)
        sys.exit(1)

try:
    cmd = [PDFCRAFT_CLI, 'combine'] + files + ['--out', out]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode == 0:
        print('Merged:', len(files), '->', out)
        for f in files:
            try:
                os.remove(f)
            except:
                pass
        sys.exit(0)
    else:
        print('combine failed:', r.stderr)
        sys.exit(1)
except Exception as e:
    print('err:', e)
    sys.exit(1)
