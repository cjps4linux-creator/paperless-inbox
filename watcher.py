import os
import time
import shutil
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_DIR = os.path.expandvars(r'%USERPROFILE%\Downloads\paperless-inbox')
OUT_DIR = os.path.expandvars(r'%USERPROFILE%\Documents\Paperless')
PDFCRAFT_CLI = r'C:\Users\user\Projects\pdfcraft\target\release\pdfcraft-cli.exe'

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
