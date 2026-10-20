import os
import glob
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

OUT_DIR = os.path.expandvars(r'%USERPROFILE%\Documents\Paperless')
PDFCRAFT_CLI = r'C:\Users\user\Projects\pdfcraft\target\release\pdfcraft-cli.exe'
os.makedirs(OUT_DIR, exist_ok=True)

class App:
    def __init__(self, root):
        root.title('Paperless Inbox')
        root.geometry('700x500')
        root.resizable(False, False)
        self.root = root
        self.files = []
        frm = ttk.Frame(root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text='Receipts/Invoices').pack(anchor='w')
        self.listbox = tk.Listbox(frm, height=15)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text='Add Files', command=self.add).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text='Add Folder', command=self.add_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text='Remove Selected', command=self.remove).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text='Clear', command=self.clear).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text='Merge to PDF', command=self.merge).pack(side=tk.RIGHT, padx=2)
        ttk.Label(frm, text=f'Output: {OUT_DIR}').pack(anchor='w', pady=5)
    
    def add(self):
        files = filedialog.askopenfilenames(filetypes=[('Docs', '*.pdf;*.jpg;*.jpeg;*.png;*.tif;*.tiff'), ('All', '*.*')])
        for f in files:
            if f not in self.files:
                self.files.append(f); self.listbox.insert(tk.END, os.path.basename(f))
    
    def add_folder(self):
        d = filedialog.askdirectory()
        if not d: return
        exts = ('*.pdf','*.jpg','*.jpeg','*.png','*.tif','*.tiff')
        for e in exts:
            for f in glob.glob(os.path.join(d, e)):
                if f not in self.files:
                    self.files.append(f); self.listbox.insert(tk.END, os.path.basename(f))
    
    def remove(self):
        sel = list(self.listbox.curselection())
        sel.reverse()
        for i in sel:
            self.listbox.delete(i)
            del self.files[i]
    
    def clear(self):
        self.listbox.delete(0, tk.END)
        self.files.clear()
    
    def merge(self):
        if not self.files:
            messagebox.showerror('Error', 'No files selected')
            return
        today = datetime.now().strftime('%Y-%m-%d')
        out = os.path.join(OUT_DIR, f'Receipts-{today}.pdf')
        try:
            cmd = [PDFCRAFT_CLI, 'combine'] + self.files + ['--out', out]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                messagebox.showinfo('Done', f'Merged {len(self.files)} files to\n{out}')
                self.clear()
            else:
                messagebox.showerror('Error', r.stderr or 'Merge failed')
        except Exception as e:
            messagebox.showerror('Error', str(e))

if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
