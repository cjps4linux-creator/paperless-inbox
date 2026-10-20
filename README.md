<h1 align="center">Paperless Inbox</h1>

<p align="center"><b>Drop receipts and invoices in. Get a clean, dated PDF out. Local only.</b></p>

<p align="center">
  <a href="https://github.com/cjps4linux-creator/paperless-inbox/actions/workflows/ci.yml"><img src="https://github.com/cjps4linux-creator/paperless-inbox/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/license-MIT-0a7563" alt="License: MIT">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776ab" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-8a5800" alt="Platforms">
  <img src="https://img.shields.io/badge/no_account-no_telemetry-0a7563" alt="No account, no telemetry">
</p>

---

## What it does

A local drop-to-archive inbox for receipts and invoices.

- **Drop folder** — copy files into `Downloads/paperless-inbox/`
- **Watcher** — timestamps each drop as it arrives
- **Batch merge** — one dated PDF per day of receipts
- **GUI** — add files or a whole folder, remove entries, merge on demand

Output lands in `Documents/Paperless/Receipts-YYYY-MM-DD.pdf`.

## Requirements

- Python 3.11+
- [`pdfcraft-cli`](https://github.com/storytold/pdfcraft) — the PDF engine this
  tool shells out to for merging

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Configure

`app.py` expects the PdfCraft CLI at a fixed path. Edit the constant at the top
of the file to match your install:

```python
PDFCRAFT_CLI = r'C:\path\to\pdfcraft-cli.exe'
```

## Run

```bash
python app.py
```

Or double-click `Paperless-GUI.bat` / `Paperless-Inbox-GUI.exe` on the Desktop.

### CLI workflow

1. Copy receipts into `Downloads/paperless-inbox/`
2. Run `Merge-Today.bat` to merge today's batch
3. `Start-Watcher.bat` runs the arrival-timestamping watcher

## Licence

MIT — see [LICENSE](LICENSE).

---

## Credits

Built by **Conrad CJ Wilson** — [GitHub](https://github.com/cjps4linux-creator) · [LinkedIn](https://linkedin.com/in/conradcjwilson)

`conradcjwilson0@gmail.com`
