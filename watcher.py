import os
from pathlib import Path
import time
import shutil
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_DIR = os.path.expandvars(r'%USERPROFILE%\Downloads\paperless-inbox')
OUT_DIR = os.path.expandvars(r'%USERPROFILE%\Documents\Paperless')
# Path to the pdfcraft CLI used for merging. Override with PDFCRAFT_CLI.
# Default assumes pdfcraft is cloned as a sibling of this repository.
_PDFCRAFT_DEFAULT = Path(__file__).resolve().parent.parent / "pdfcraft" / "target" / "release" / "pdfcraft-cli.exe"
PDFCRAFT_CLI = os.environ.get("PDFCRAFT_CLI", str(_PDFCRAFT_DEFAULT))

os.makedirs(WATCH_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

class Handler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        ext = os.path.splitext(path)[1].lower()
        if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'):
            return
        # wait for write to finish
        time.sleep(2)
        try:
            dt = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            name = f'{dt}_{os.path.basename(path)}'
            dest = os.path.join(WATCH_DIR, name)
            # Never overwrite an existing receipt: two files with the same
            # basename arriving within the same second would otherwise
            # silently destroy the first one.
            if os.path.exists(dest):
                stem, ext = os.path.splitext(dest)
                counter = 1
                while os.path.exists(f'{stem}_{counter}{ext}'):
                    counter += 1
                dest = f'{stem}_{counter}{ext}'
            shutil.move(path, dest)
            print('Queued:', dest)
        except Exception as e:
            print('Err:', e)

if __name__ == '__main__':
    print('Watching', WATCH_DIR, '->', OUT_DIR)
    obs = Observer()
    obs.schedule(Handler(), WATCH_DIR, recursive=False)
    obs.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()
