"""Pure pytest suite for paperless-inbox (app.py / watcher.py / merge_today.py).

Why this file is written the way it is
--------------------------------------
All three source modules perform work *at import time*:

* ``app.py``       -- ``os.makedirs(OUT_DIR, exist_ok=True)`` at module scope,
  with ``OUT_DIR = %USERPROFILE%\\Documents\\Paperless`` -> a plain import
  creates a folder inside the real user profile.
* ``watcher.py``   -- creates ``%USERPROFILE%\\Downloads\\paperless-inbox`` and
  ``%USERPROFILE%\\Documents\\Paperless`` at module scope.
* ``merge_today.py`` -- is a *script*: it globs the watch folder at module
  scope and calls ``sys.exit()`` (0 or 1) depending on what it finds.

So none of them may be imported at module scope in a test file.  Every test
here:

1. redirects ``USERPROFILE`` to ``tmp_path`` (monkeypatch.setenv),
2. chdirs into ``tmp_path`` (monkeypatch.chdir) so that even on POSIX, where
   ``os.path.expandvars`` does not understand ``%VAR%`` syntax and therefore
   yields a *relative* path, every path still resolves inside ``tmp_path``,
3. replaces ``os.makedirs`` with a *guarded* version that refuses to create
   anything outside ``tmp_path`` (monkeypatch.setattr) and records what it
   created,
4. loads the module under test with
   ``importlib.util.spec_from_file_location`` **inside the test body**, so the
   import-time side effects happen exactly once and under our control.

``tkinter`` is replaced by a stub module tree (see ``_install_tkinter_stub``)
so that no real Tk window can ever be created, on any platform, and so the
suite also runs on headless Linux CI images.

Nothing in this file shells out to pdfcraft: ``subprocess.run`` is monkey-
patched everywhere and the captured argv is what gets asserted.
"""

from __future__ import annotations

import contextlib
import datetime as datetime_module
import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# 2026-01-15 13:45:30 -- frozen clock so date-derived names are deterministic.
FROZEN = datetime_module.datetime(2026, 1, 15, 13, 45, 30)
FROZEN_DATE = "2026-01-15"
FROZEN_STAMP = "2026-01-15_13-45-30"

WATCH_DIR_PATTERN = r"%USERPROFILE%\Downloads\paperless-inbox"
OUT_DIR_PATTERN = r"%USERPROFILE%\Documents\Paperless"

SUPPORTED_EXTS = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff")


# --------------------------------------------------------------------------
# harness helpers
# --------------------------------------------------------------------------
class FrozenDatetime(datetime_module.datetime):
    """``datetime`` subclass whose ``now()`` never moves."""

    @classmethod
    def now(cls, tz=None):  # noqa: ARG003 - mirrors datetime.now signature
        return cls(FROZEN.year, FROZEN.month, FROZEN.day, 13, 45, 30)


class FakeCompleted:
    """Stand-in for ``subprocess.CompletedProcess``."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeListbox:
    """Minimal stand-in for ``tkinter.Listbox`` (no window, no display)."""

    END = "end"

    def __init__(self):
        self.items = []
        self.selection = ()

    def insert(self, _index, text):
        self.items.append(text)

    def delete(self, index, index2=None):
        if index2 is None:
            del self.items[index]
            return
        if index2 == self.END:
            del self.items[index:]
            return
        del self.items[index : index2 + 1]

    def curselection(self):
        return self.selection


class FakeApp:
    """Minimal stand-in for ``app.App`` -- only the attributes the methods use."""

    def __init__(self, files=()):
        self.files = list(files)
        self.listbox = FakeListbox()
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1
        self.files.clear()
        self.listbox.items.clear()


def _resolve(root, path):
    """Absolute path of *path* as seen from *root* (handles relative paths)."""
    text = os.fspath(path)
    if os.path.isabs(text):
        return os.path.abspath(text)
    return os.path.abspath(os.path.join(root, text))


def _is_within(root, target):
    try:
        return os.path.commonpath([root, target]) == root
    except ValueError:  # different drives on Windows
        return False


def _install_guarded_makedirs(monkeypatch, tmp_path):
    """Replace ``os.makedirs`` with a version confined to ``tmp_path``.

    Returns the list that records every directory actually created.
    """
    real_makedirs = os.makedirs
    root = os.path.abspath(str(tmp_path))
    created = []

    def guarded(path, *args, **kwargs):
        target = _resolve(root, path)
        if not _is_within(root, target):
            raise AssertionError(f"refusing to create {path!r} outside tmp_path")
        created.append(target)
        return real_makedirs(target, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", guarded)
    return created


def _freeze_clock(monkeypatch):
    """Pin ``datetime.datetime.now()`` for every module loaded afterwards."""
    monkeypatch.setattr(datetime_module, "datetime", FrozenDatetime)


def _install_tkinter_stub(monkeypatch):
    """Install a fake ``tkinter`` package tree so no Tk window can be made."""
    dialogs = {"error": [], "info": []}

    tk = types.ModuleType("tkinter")
    tk.BOTH = "both"
    tk.END = FakeListbox.END
    tk.LEFT = "left"
    tk.RIGHT = "right"
    tk.X = "x"
    tk.W = "w"
    tk.N = "n"
    tk.S = "s"
    tk.Y = "y"
    tk.Tk = object  # never instantiated by the code under test

    ttk = types.ModuleType("tkinter.ttk")

    class _Widget:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    for widget in ("Frame", "Label", "Button", "Entry"):
        setattr(ttk, widget, _Widget)

    filedialog = types.ModuleType("tkinter.filedialog")
    filedialog.askopenfilenames = lambda **kwargs: ()
    filedialog.askdirectory = lambda **kwargs: ""

    messagebox = types.ModuleType("tkinter.messagebox")

    def showerror(title="", message=""):
        dialogs["error"].append((title, message))

    def showinfo(title="", message=""):
        dialogs["info"].append((title, message))

    messagebox.showerror = showerror
    messagebox.showinfo = showinfo

    tk.ttk = ttk
    tk.filedialog = filedialog
    tk.messagebox = messagebox

    for name, module in (
        ("tkinter", tk),
        ("tkinter.ttk", ttk),
        ("tkinter.filedialog", filedialog),
        ("tkinter.messagebox", messagebox),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    return dialogs


@contextlib.contextmanager
def _no_bytecode():
    """Suppress ``.pyc`` writes while a module is being executed.

    ``spec_from_file_location`` uses the normal import machinery, which would
    otherwise drop ``__pycache__/*.pyc`` next to the source files in the
    repository.  Keeping the suite hermetic means it leaves nothing behind
    outside ``tmp_path``.
    """
    original = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = original


def _load_module(name, path):
    """Import *path* under *name* without registering it in ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with _no_bytecode():
        spec.loader.exec_module(module)
    return module


def _load_script(name, path):
    """Import a top-level script, capturing the ``SystemExit`` it raises.

    ``merge_today.py`` calls ``sys.exit()`` at module scope; the raised
    ``SystemExit`` is swallowed here and surfaced as ``module.exit_code``
    (``None`` when the script fell off the end without calling ``sys.exit``).
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    module.exit_code = None
    try:
        with _no_bytecode():
            spec.loader.exec_module(module)
    except SystemExit as exc:
        module.exit_code = exc.code
    return module


def _prepare_env(monkeypatch, tmp_path):
    """Point every ``%USERPROFILE%``-derived path at ``tmp_path``.

    Returns the list recording the directories created while importing.
    """
    created = _install_guarded_makedirs(monkeypatch, tmp_path)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("PDFCRAFT_CLI", raising=False)
    monkeypatch.chdir(tmp_path)
    return created


# --------------------------------------------------------------------------
# app.py
# --------------------------------------------------------------------------
@pytest.fixture
def app_env(monkeypatch, tmp_path):
    """Load ``app.py`` under full control of its import-time side effects."""
    created = _prepare_env(monkeypatch, tmp_path)
    _freeze_clock(monkeypatch)
    dialogs = _install_tkinter_stub(monkeypatch)

    runs = []
    result = FakeCompleted(returncode=0)

    def fake_run(cmd, **kwargs):
        runs.append((list(cmd), kwargs))
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    module = _load_module("paperless_app_under_test", REPO_ROOT / "app.py")

    return types.SimpleNamespace(
        module=module,
        runs=runs,
        result=result,
        dialogs=dialogs,
        created=created,
        tmp_path=tmp_path,
    )


@pytest.mark.parametrize(
    "count",
    [1, 2, 3, 5],
)
def test_merge_builds_combine_command(app_env, count):
    """``App.merge`` builds ``[CLI, 'combine', *files, '--out', out]``."""
    files = [f"C:/receipts/file{index}.pdf" for index in range(count)]
    gui = FakeApp(files)

    app_env.module.App.merge(gui)

    assert len(app_env.runs) == 1
    cmd, kwargs = app_env.runs[0]

    # argv[0] is the pdfcraft CLI, argv[1] is the sub-command.
    assert cmd[0] == app_env.module.PDFCRAFT_CLI
    assert cmd[1] == "combine"

    # The selected files follow, in selection order, untouched.
    assert cmd[2 : 2 + count] == files

    # '--out' is the second-to-last token, the output path the last one.
    assert cmd[-2] == "--out"
    assert cmd[-1] == os.path.join(app_env.module.OUT_DIR, f"Receipts-{FROZEN_DATE}.pdf")

    # Output file name format: Receipts-<YYYY-MM-DD>.pdf
    assert os.path.basename(cmd[-1]) == f"Receipts-{FROZEN_DATE}.pdf"

    # pdfcraft is invoked in capture mode with a timeout.
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 600


def test_merge_preserves_selection_order(app_env):
    """File order in the argv is exactly the order the user selected."""
    files = ["C:/receipts/zeta.pdf", "C:/receipts/alpha.pdf", "C:/receipts/mid.jpg"]
    gui = FakeApp(files)

    app_env.module.App.merge(gui)

    cmd = app_env.runs[0][0]
    assert cmd[2:5] == files


def test_merge_with_no_files_shows_error_and_does_not_run_pdfcraft(app_env):
    """The only guard rail is ``if not self.files`` -> 'No files selected'."""
    gui = FakeApp([])

    app_env.module.App.merge(gui)

    assert app_env.dialogs["error"] == [("Error", "No files selected")]
    assert app_env.dialogs["info"] == []
    assert app_env.runs == []
    assert gui.clear_calls == 0


def test_merge_with_a_single_file_still_invokes_pdfcraft(app_env):
    """KNOWN BEHAVIOUR: there is no 'fewer than two files' branch.

    ``app.py`` only rejects an *empty* selection, so a one-file selection is
    handed to pdfcraft.  ``merge_today.py`` instead copies a single file
    straight to the output.  The two entry points disagree here.
    """
    gui = FakeApp(["C:/receipts/only.pdf"])

    app_env.module.App.merge(gui)

    assert len(app_env.runs) == 1
    cmd = app_env.runs[0][0]
    assert cmd[2:3] == ["C:/receipts/only.pdf"]
    assert cmd[-2] == "--out"


def test_merge_success_shows_info_and_clears_the_list(app_env):
    """A zero exit code clears the selection and reports the output path."""
    gui = FakeApp(["C:/receipts/a.pdf", "C:/receipts/b.pdf"])

    app_env.module.App.merge(gui)

    assert len(app_env.dialogs["info"]) == 1
    title, message = app_env.dialogs["info"][0]
    assert title == "Done"
    assert "Merged 2 files to" in message
    assert f"Receipts-{FROZEN_DATE}.pdf" in message
    assert gui.clear_calls == 1
    assert gui.files == []


def test_merge_failure_reports_stderr_and_keeps_the_selection(app_env):
    """A non-zero exit code surfaces stderr and does not clear the list."""
    app_env.result.returncode = 1
    app_env.result.stderr = "pdfcraft exploded"
    gui = FakeApp(["C:/receipts/a.pdf"])

    app_env.module.App.merge(gui)

    assert app_env.dialogs["error"] == [("Error", "pdfcraft exploded")]
    assert app_env.dialogs["info"] == []
    assert gui.clear_calls == 0
    assert gui.files == ["C:/receipts/a.pdf"]


def test_merge_failure_without_stderr_shows_generic_message(app_env):
    """Empty stderr falls back to the generic 'Merge failed' text."""
    app_env.result.returncode = 2
    app_env.result.stderr = ""
    gui = FakeApp(["C:/receipts/a.pdf"])

    app_env.module.App.merge(gui)

    assert app_env.dialogs["error"] == [("Error", "Merge failed")]


def test_merge_swallows_exceptions_from_subprocess(app_env, monkeypatch):
    """An exploding ``subprocess.run`` becomes an error dialog, not a crash."""

    def boom(cmd, **kwargs):
        raise OSError("pdfcraft missing")

    monkeypatch.setattr(subprocess, "run", boom)
    gui = FakeApp(["C:/receipts/a.pdf"])

    app_env.module.App.merge(gui)

    assert app_env.dialogs["error"] == [("Error", "pdfcraft missing")]
    assert gui.clear_calls == 0


def test_merge_output_goes_to_out_dir(app_env, tmp_path):
    """The output path is built from ``OUT_DIR`` (``Documents/Paperless``)."""
    gui = FakeApp(["C:/receipts/a.pdf"])

    app_env.module.App.merge(gui)

    out = app_env.runs[0][0][-1]
    assert os.path.dirname(out) == app_env.module.OUT_DIR
    assert "Documents" in out
    assert "Paperless" in out
    # OUT_DIR was redirected into tmp_path, so the real profile is untouched.
    assert _is_within(os.path.abspath(str(tmp_path)), os.path.abspath(out))


@pytest.mark.parametrize(
    "ext",
    [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"],
)
def test_add_folder_keeps_supported_extensions(app_env, tmp_path, ext):
    """``add_folder`` only picks up the six receipt extensions."""
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / f"scan{ext}").write_text("data", encoding="utf-8")
    (folder / "notes.txt").write_text("data", encoding="utf-8")
    (folder / "archive.zip").write_text("data", encoding="utf-8")

    gui = FakeApp()
    app_env.module.filedialog.askdirectory = lambda **kwargs: str(folder)

    app_env.module.App.add_folder(gui)

    assert gui.files == [str(folder / f"scan{ext}")]
    assert gui.listbox.items == [f"scan{ext}"]


def test_add_folder_excludes_unsupported_extensions(app_env, tmp_path):
    """Non-receipt files are filtered out by the extension glob."""
    folder = tmp_path / "receipts"
    folder.mkdir()
    for name in ("a.pdf", "b.txt", "c.exe", "d.docx", "e"):
        (folder / name).write_text("data", encoding="utf-8")

    gui = FakeApp()
    app_env.module.filedialog.askdirectory = lambda **kwargs: str(folder)

    app_env.module.App.add_folder(gui)

    assert gui.files == [str(folder / "a.pdf")]


def test_add_folder_skips_duplicates(app_env, tmp_path):
    """A file already in the list is not added twice."""
    folder = tmp_path / "receipts"
    folder.mkdir()
    (folder / "a.pdf").write_text("data", encoding="utf-8")

    gui = FakeApp([str(folder / "a.pdf")])
    app_env.module.filedialog.askdirectory = lambda **kwargs: str(folder)

    app_env.module.App.add_folder(gui)

    assert gui.files == [str(folder / "a.pdf")]
    assert gui.listbox.items == []


def test_add_folder_groups_by_extension_tuple_order(app_env, tmp_path):
    """Files are grouped per extension in the order of the ``exts`` tuple.

    ``exts = ('*.pdf', '*.jpg', '*.jpeg', '*.png', '*.tif', '*.tiff')`` and
    each group is globbed separately, so the resulting order follows the
    extension groups -- it is *not* a plain alphabetical sort of the folder.
    (Within a single group the order comes from ``glob`` and is not
    guaranteed, so only the grouping is asserted here.)
    """
    folder = tmp_path / "receipts"
    folder.mkdir()
    for name in ("z.pdf", "a.jpg", "m.png", "b.pdf"):
        (folder / name).write_text("data", encoding="utf-8")

    gui = FakeApp()
    app_env.module.filedialog.askdirectory = lambda **kwargs: str(folder)

    app_env.module.App.add_folder(gui)

    assert [os.path.splitext(path)[1] for path in gui.files] == [
        ".pdf",
        ".pdf",
        ".jpg",
        ".png",
    ]
    assert sorted(os.path.basename(path) for path in gui.files) == [
        "a.jpg",
        "b.pdf",
        "m.png",
        "z.pdf",
    ]


def test_add_folder_ignores_cancelled_dialog(app_env):
    """An empty directory choice adds nothing."""
    gui = FakeApp()
    app_env.module.filedialog.askdirectory = lambda **kwargs: ""

    app_env.module.App.add_folder(gui)

    assert gui.files == []
    assert gui.listbox.items == []


def test_add_deduplicates_and_lists_base_names(app_env):
    """``add`` appends new files only and shows base names in the listbox."""
    gui = FakeApp(["C:/receipts/a.pdf"])
    app_env.module.filedialog.askopenfilenames = lambda **kwargs: (
        "C:/receipts/a.pdf",
        "C:/receipts/b.pdf",
    )

    app_env.module.App.add(gui)

    assert gui.files == ["C:/receipts/a.pdf", "C:/receipts/b.pdf"]
    assert gui.listbox.items == ["b.pdf"]


def test_remove_deletes_the_selected_entries(app_env):
    """``remove`` drops the selected rows from the list and the file list."""
    gui = FakeApp(["a.pdf", "b.pdf", "c.pdf"])
    gui.listbox.items = ["a.pdf", "b.pdf", "c.pdf"]
    gui.listbox.selection = (0, 2)

    app_env.module.App.remove(gui)

    assert gui.files == ["b.pdf"]
    assert gui.listbox.items == ["b.pdf"]


def test_clear_empties_the_selection(app_env):
    """``clear`` empties both the listbox and the file list."""
    gui = FakeApp(["a.pdf", "b.pdf"])
    gui.listbox.items = ["a.pdf", "b.pdf"]

    app_env.module.App.clear(gui)

    assert gui.files == []
    assert gui.listbox.items == []


def test_app_import_creates_only_directories_inside_tmp_path(app_env, tmp_path):
    """The import-time ``os.makedirs`` is contained by the tmp_path guard."""
    root = os.path.abspath(str(tmp_path))
    assert app_env.created, "app.py should create its OUT_DIR at import time"
    for path in app_env.created:
        assert _is_within(root, path)
    assert _is_within(root, os.path.abspath(app_env.module.OUT_DIR))


def test_app_import_does_not_need_a_real_tk_display(monkeypatch, tmp_path):
    """app.py imports cleanly with the *real* tkinter, without a window.

    ``import tkinter`` neither opens a display connection nor creates a
    widget, so this stays a pure import check.
    """
    pytest.importorskip("tkinter")
    _prepare_env(monkeypatch, tmp_path)
    _freeze_clock(monkeypatch)

    module = _load_module("paperless_app_real_tk", REPO_ROOT / "app.py")

    assert hasattr(module, "App")
    assert module.OUT_DIR.endswith("Paperless")
    assert module.PDFCRAFT_CLI


def test_guarded_makedirs_refuses_paths_outside_tmp_path(monkeypatch, tmp_path):
    """The guard used by this suite actually blocks escapes."""
    _install_guarded_makedirs(monkeypatch, tmp_path)

    # The escape target has to be absolute on every platform, so it is
    # derived from tmp_path's parent rather than hard-coded as "C:/..." —
    # a "C:/..." path is *relative* on POSIX and would be joined onto the
    # tmp root instead of escaping it.
    outside = tmp_path.parent / "escaped-outside-tmp-path"
    with pytest.raises(AssertionError):
        os.makedirs(outside)

    inside = tmp_path / "ok"
    os.makedirs(inside)
    assert inside.is_dir()


# --------------------------------------------------------------------------
# watcher.py
# --------------------------------------------------------------------------
@pytest.fixture
def watcher_env(monkeypatch, tmp_path):
    """Load ``watcher.py`` with the watch folder pointed at ``tmp_path``."""
    _prepare_env(monkeypatch, tmp_path)
    _freeze_clock(monkeypatch)

    module = _load_module("paperless_watcher_under_test", REPO_ROOT / "watcher.py")

    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    module.WATCH_DIR = str(watch_dir)

    class _TimeStub:
        """The handler sleeps 2s; the stub keeps the tests fast."""

        def __init__(self):
            self.slept = []

        def sleep(self, seconds):
            self.slept.append(seconds)

        @staticmethod
        def time():
            return 0.0

    time_stub = _TimeStub()
    monkeypatch.setattr(module, "time", time_stub)

    return types.SimpleNamespace(
        module=module,
        watch_dir=watch_dir,
        time_stub=time_stub,
        tmp_path=tmp_path,
    )


def _event(path, is_directory=False):
    return types.SimpleNamespace(src_path=str(path), is_directory=is_directory)


@pytest.mark.parametrize(
    "ext",
    SUPPORTED_EXTS,
)
def test_on_created_moves_supported_files(watcher_env, ext):
    """A dropped receipt is renamed with a timestamp and moved into place."""
    src = watcher_env.watch_dir / f"scan{ext}"
    src.write_text("payload", encoding="utf-8")

    watcher_env.module.Handler().on_created(_event(src))

    dest = watcher_env.watch_dir / f"{FROZEN_STAMP}_scan{ext}"
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "payload"
    assert not src.exists()


@pytest.mark.parametrize(
    "ext",
    [".txt", ".exe", ".docx", ".zip", ".mp4", ""],
)
def test_on_created_ignores_unsupported_extensions(watcher_env, ext):
    """Files that are not receipts are left completely alone."""
    src = watcher_env.watch_dir / f"notes{ext}"
    src.write_text("payload", encoding="utf-8")

    watcher_env.module.Handler().on_created(_event(src))

    assert src.is_file()
    assert list(watcher_env.watch_dir.iterdir()) == [src]


def test_on_created_ignores_directory_events(watcher_env):
    """Directory events are dropped before any path handling.

    The directory is deliberately named with a *supported* extension: without
    the ``event.is_directory`` guard it would pass the extension filter and
    be renamed/moved like a receipt.
    """
    folder = watcher_env.watch_dir / "batch.pdf"
    folder.mkdir()
    (folder / "inner.txt").write_text("data", encoding="utf-8")

    watcher_env.module.Handler().on_created(_event(folder, is_directory=True))

    assert folder.is_dir()
    assert (folder / "inner.txt").is_file()
    assert list(watcher_env.watch_dir.iterdir()) == [folder]


def test_on_created_matches_extension_case_insensitively(watcher_env):
    """The extension is lower-cased before it is compared."""
    src = watcher_env.watch_dir / "SCAN.PDF"
    src.write_text("payload", encoding="utf-8")

    watcher_env.module.Handler().on_created(_event(src))

    assert (watcher_env.watch_dir / f"{FROZEN_STAMP}_SCAN.PDF").is_file()


def test_on_created_waits_two_seconds_before_moving(watcher_env):
    """The handler pauses to let the writer finish before moving the file."""
    src = watcher_env.watch_dir / "scan.pdf"
    src.write_text("payload", encoding="utf-8")

    watcher_env.module.Handler().on_created(_event(src))

    assert watcher_env.time_stub.slept == [2]


def test_on_created_keeps_both_files_on_destination_collision(watcher_env, tmp_path):
    """Two drops that share a base name and land in one second.

    The destination name is ``<timestamp>_<basename>``.  Two receipts with the
    same base name that arrive within the same second would map to the same
    destination, so the watcher must disambiguate rather than overwrite —
    otherwise the first receipt's content is silently lost.
    """
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "scan.pdf"
    first.write_text("FIRST", encoding="utf-8")
    second = second_dir / "scan.pdf"
    second.write_text("SECOND", encoding="utf-8")

    handler = watcher_env.module.Handler()
    handler.on_created(_event(first))
    handler.on_created(_event(second))

    dest = watcher_env.watch_dir / f"{FROZEN_STAMP}_scan.pdf"
    assert dest.read_text(encoding="utf-8") == "FIRST"

    # The second receipt must be preserved under a distinct name.
    kept = [p for p in watcher_env.watch_dir.iterdir() if p.name != dest.name]
    assert len(kept) == 1, f"expected one additional receipt, found {kept}"
    assert kept[0].read_text(encoding="utf-8") == "SECOND"
    assert not first.exists()
    assert not second.exists()


def test_on_created_reports_errors_instead_of_raising(watcher_env, monkeypatch):
    """A failing move is reported on stdout, not raised to the observer."""

    def boom(src, dest):
        raise OSError("locked")

    monkeypatch.setattr(watcher_env.module.shutil, "move", boom)
    src = watcher_env.watch_dir / "scan.pdf"
    src.write_text("payload", encoding="utf-8")

    watcher_env.module.Handler().on_created(_event(src))

    assert src.is_file()


def test_watcher_import_creates_only_directories_inside_tmp_path(monkeypatch, tmp_path):
    """Importing the watcher only creates directories under ``tmp_path``."""
    _prepare_env(monkeypatch, tmp_path)
    _freeze_clock(monkeypatch)

    module = _load_module("paperless_watcher_guard", REPO_ROOT / "watcher.py")

    root = os.path.abspath(str(tmp_path))
    for path in (module.WATCH_DIR, module.OUT_DIR):
        assert _is_within(root, os.path.abspath(path))


# --------------------------------------------------------------------------
# merge_today.py
# --------------------------------------------------------------------------
@pytest.fixture
def merge_today_env(monkeypatch, tmp_path):
    """Prepare an isolated run of the ``merge_today.py`` script."""
    _prepare_env(monkeypatch, tmp_path)
    _freeze_clock(monkeypatch)

    # Same expansion the script performs itself, so the paths line up on
    # Windows (absolute) and on POSIX (relative to the tmp_path cwd).
    watch_dir = os.path.expandvars(WATCH_DIR_PATTERN)
    out_dir = os.path.expandvars(OUT_DIR_PATTERN)
    os.makedirs(watch_dir, exist_ok=True)

    runs = []
    result = FakeCompleted(returncode=0)

    def fake_run(cmd, **kwargs):
        runs.append((list(cmd), kwargs))
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    def run(seed=()):
        for name, content in seed:
            path = os.path.join(watch_dir, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
        return _load_script("paperless_merge_today_under_test", REPO_ROOT / "merge_today.py")

    return types.SimpleNamespace(
        run=run,
        watch_dir=watch_dir,
        out_dir=out_dir,
        runs=runs,
        result=result,
        tmp_path=tmp_path,
    )


def test_merge_today_exits_zero_when_there_is_nothing_to_do(merge_today_env, capsys):
    """An empty watch folder prints a message and exits 0 without pdfcraft."""
    module = merge_today_env.run()

    assert module.exit_code == 0
    assert merge_today_env.runs == []
    assert f"No files for {FROZEN_DATE}" in capsys.readouterr().out


def test_merge_today_copies_a_single_file_and_removes_the_source(merge_today_env, capsys):
    """One file is copied straight to the output, never sent to pdfcraft."""
    module = merge_today_env.run([(f"{FROZEN_DATE}_scan.pdf", "ONLY")])

    out = os.path.join(merge_today_env.out_dir, f"Receipts-{FROZEN_DATE}.pdf")
    assert module.exit_code == 0
    assert merge_today_env.runs == []
    assert os.path.isfile(out)
    with open(out, encoding="utf-8") as handle:
        assert handle.read() == "ONLY"
    assert not os.path.exists(os.path.join(merge_today_env.watch_dir, f"{FROZEN_DATE}_scan.pdf"))
    assert "Single file copied to" in capsys.readouterr().out


def test_merge_today_single_file_copy_preserves_the_original_timestamp(merge_today_env):
    """The single-file branch uses ``shutil.copy2``, so the mtime survives.

    ``shutil.copy`` would stamp the output with the current time instead.
    """
    source = os.path.join(merge_today_env.watch_dir, f"{FROZEN_DATE}_scan.pdf")
    with open(source, "w", encoding="utf-8") as handle:
        handle.write("ONLY")

    # Rewind the source's mtime before the script copies it.
    stamp = 1_600_000_000
    os.utime(source, (stamp, stamp))

    merge_today_env.run()

    out = os.path.join(merge_today_env.out_dir, f"Receipts-{FROZEN_DATE}.pdf")
    assert int(os.path.getmtime(out)) == stamp


def test_merge_today_combines_multiple_files_in_extension_group_order(merge_today_env):
    """Files are grouped per extension (pdf, jpg, jpeg, png, tif, tiff).

    The groups are concatenated in the fixed extension order and each group
    is sorted on its own -- the result is *not* a global alphabetical sort.
    """
    merge_today_env.run(
        [
            (f"{FROZEN_DATE}_z.pdf", "PDF"),
            (f"{FROZEN_DATE}_a.pdf", "PDF"),
            (f"{FROZEN_DATE}_c.jpg", "JPG"),
            (f"{FROZEN_DATE}_c.png", "PNG"),
        ]
    )

    assert len(merge_today_env.runs) == 1
    cmd = merge_today_env.runs[0][0]
    assert cmd[1] == "combine"
    assert [os.path.basename(path) for path in cmd[2:-2]] == [
        f"{FROZEN_DATE}_a.pdf",
        f"{FROZEN_DATE}_z.pdf",
        f"{FROZEN_DATE}_c.jpg",
        f"{FROZEN_DATE}_c.png",
    ]
    assert cmd[-2] == "--out"
    assert os.path.basename(cmd[-1]) == f"Receipts-{FROZEN_DATE}.pdf"


def test_merge_today_removes_the_sources_after_a_successful_merge(merge_today_env, capsys):
    """A successful combine deletes the merged source files."""
    module = merge_today_env.run(
        [
            (f"{FROZEN_DATE}_a.pdf", "A"),
            (f"{FROZEN_DATE}_b.pdf", "B"),
        ]
    )

    assert module.exit_code == 0
    assert "Merged: 2 ->" in capsys.readouterr().out
    remaining = os.listdir(merge_today_env.watch_dir)
    assert remaining == []


def test_merge_today_keeps_the_sources_when_the_merge_fails(merge_today_env, capsys):
    """A failing pdfcraft leaves the receipts in the watch folder."""
    merge_today_env.result.returncode = 1
    merge_today_env.result.stderr = "pdfcraft exploded"

    module = merge_today_env.run(
        [
            (f"{FROZEN_DATE}_a.pdf", "A"),
            (f"{FROZEN_DATE}_b.pdf", "B"),
        ]
    )

    out = capsys.readouterr().out
    assert "combine failed: pdfcraft exploded" in out
    assert sorted(os.listdir(merge_today_env.watch_dir)) == [
        f"{FROZEN_DATE}_a.pdf",
        f"{FROZEN_DATE}_b.pdf",
    ]
    # The script must exit non-zero so the .bat wrapper reports the failure.
    assert module.exit_code == 1


def test_merge_today_ignores_files_from_other_days(merge_today_env):
    """Only files prefixed with today's date are picked up."""
    module = merge_today_env.run(
        [
            ("1999-01-01_old.pdf", "OLD"),
            (f"{FROZEN_DATE}_today.pdf", "TODAY"),
        ]
    )

    assert [os.path.basename(path) for path in module.files] == [f"{FROZEN_DATE}_today.pdf"]


def test_merge_today_honours_the_pdfcraft_cli_environment_variable(monkeypatch, tmp_path):
    """``PDFCRAFT_CLI`` from the environment overrides the default path."""
    _prepare_env(monkeypatch, tmp_path)
    _freeze_clock(monkeypatch)
    monkeypatch.setenv("PDFCRAFT_CLI", "C:/fake/pdfcraft-cli.exe")

    runs = []

    def fake_run(cmd, **kwargs):
        runs.append((list(cmd), kwargs))
        return FakeCompleted(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    watch_dir = os.path.expandvars(WATCH_DIR_PATTERN)
    os.makedirs(watch_dir, exist_ok=True)
    for name in (f"{FROZEN_DATE}_a.pdf", f"{FROZEN_DATE}_b.pdf"):
        with open(os.path.join(watch_dir, name), "w", encoding="utf-8") as handle:
            handle.write("X")

    module = _load_script("paperless_merge_today_env_cli", REPO_ROOT / "merge_today.py")

    assert module.PDFCRAFT_CLI == "C:/fake/pdfcraft-cli.exe"
    assert runs[0][0][0] == "C:/fake/pdfcraft-cli.exe"


def test_merge_today_output_name_follows_the_dated_convention(merge_today_env):
    """The merged file is always ``Receipts-<YYYY-MM-DD>.pdf``."""
    merge_today_env.run(
        [
            (f"{FROZEN_DATE}_a.pdf", "A"),
            (f"{FROZEN_DATE}_b.pdf", "B"),
        ]
    )

    out = merge_today_env.runs[0][0][-1]
    assert os.path.basename(out) == f"Receipts-{FROZEN_DATE}.pdf"
    assert os.path.dirname(out) == merge_today_env.out_dir
