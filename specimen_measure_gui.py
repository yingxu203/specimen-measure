# -*- coding: utf-8 -*-
"""
specimen_measure_gui.py

Desktop pop-up window for the batch measurement tool, for anyone who would
rather not use the browser UI (app.py) or the command line.

Launch with:
    python3 specimen_measure_gui.py
"""

import subprocess
import sys
import threading
import tkinter as tk
import tkinter.ttk as ttk
from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox as msg

sys.path.insert(0, str(Path(__file__).parent))

from specimen_measure.cli import DEFAULT_PATTERN, run  # noqa: E402

APP_TITLE = "Ying's Measurement Tool for Specimen"

# A light, Finder-window-like background instead of Tk's default gray, with
# blue accents. Drawn by hand below (rather than relying on ttk's native
# macOS button/entry styling) because the bundled Tk build here (Anaconda's,
# not Apple's/python.org's) reports itself as the "aqua" platform but does
# not actually implement the rounded-corner or accent-color native widget
# theming -- so ttk widgets render as plain flat rectangles regardless of
# style options. Hand-drawn Canvas shapes render identically on any Tk build.
BG = "#FFFFFF"
ACCENT = "#0080FE"


def _rounded_rect_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


class RoundedButton(tk.Canvas):
    """A click-able rounded-rectangle button that always renders with real
    fill/border colors and soft corners, independent of the platform's
    native Tk button theming. White interior, blue text and outline.
    """

    def __init__(self, parent, text, command, width=110, height=34, radius=10,
                 fill="white", hover_fill="#EAF4FF", border=ACCENT,
                 disabled_fill="#F2F2F2", disabled_border="#CFCFCF",
                 text_color=ACCENT, font=("Arial", 13, "bold")):
        super().__init__(parent, width=width, height=height, bg=BG,
                          highlightthickness=0, bd=0, cursor="hand2")
        self._command = command
        self._fill = fill
        self._hover_fill = hover_fill
        self._border = border
        self._disabled_fill = disabled_fill
        self._disabled_border = disabled_border
        self._enabled = True
        self._shape = self.create_polygon(
            _rounded_rect_points(2, 2, width - 2, height - 2, radius),
            smooth=True, fill=fill, outline=border, width=1,
        )
        self._text_item = self.create_text(width / 2, height / 2, text=text,
                                            fill=text_color, font=font)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_click(self, _event):
        if self._enabled and self._command:
            self._command()

    def _on_enter(self, _event):
        if self._enabled:
            self.itemconfig(self._shape, fill=self._hover_fill)

    def _on_leave(self, _event):
        if self._enabled:
            self.itemconfig(self._shape, fill=self._fill)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        fill = self._fill if enabled else self._disabled_fill
        border = self._border if enabled else self._disabled_border
        self.itemconfig(self._shape, fill=fill, outline=border)
        self.configure(cursor="hand2" if enabled else "arrow")

    def set_text(self, text: str):
        self.itemconfig(self._text_item, text=text)


def _short_name(path: str, max_len: int = 28) -> str:
    name = Path(path).name or path
    if len(name) > max_len:
        name = name[: max_len - 1] + "…"
    return name


window = tk.Tk()
window.title(APP_TITLE)
window.geometry("900x340")
window.configure(bg=BG)

# 'clam' is a fully Tk-drawn (non-native) ttk theme, which is what lets us
# force the Combobox's field to plain white below -- the native 'aqua'
# theme ignores fieldbackground on readonly comboboxes and always shows its
# own grey/tan "readonly" tint instead.
style = ttk.Style()
style.theme_use("clam")
style.configure("TCombobox", fieldbackground="white", background="white",
                 foreground="black", bordercolor=ACCENT, arrowcolor=ACCENT)
style.map("TCombobox", fieldbackground=[("readonly", "white")],
          background=[("readonly", "white")])


def _widen_dropdown_popup(combo: ttk.Combobox):
    """The popdown listbox defaults to the (narrow) entry width, clipping
    long option text. Widen just the popup list to fit the longest option,
    leaving the closed box's own width untouched.
    """
    try:
        popdown = combo.tk.eval(f"ttk::combobox::PopdownWindow {combo}")
        longest = max((len(v) for v in combo["values"]), default=0)
        combo.tk.call(f"{popdown}.f.l", "configure", "-width", longest)
    except tk.TclError:
        pass


main = tk.Frame(window, bg=BG)
main.pack(fill="both", expand=True, padx=20, pady=16)

appTitle = tk.Label(main, text=APP_TITLE, font=("calibri", 20, "bold"), fg=ACCENT, bg=BG)
appTitle.pack(pady=(0, 16))  # centered by default (no fill/side given)

form = tk.Frame(main, bg=BG)
form.pack()


def _row(parent):
    r = tk.Frame(parent, bg=BG)
    r.pack(fill="x", pady=5)
    return r


# --------------------- Input directory ---------------------
inputDir = tk.StringVar(value="None Selected")


def selectInputClicked():
    chosen = filedialog.askdirectory()
    if chosen:
        inputDir.set(chosen)
        inputSelectButton.set_text(f"Selected: {_short_name(chosen)}")
        print(chosen + " selected as input")


DIRECTORY_BUTTON_WIDTH = 220

row1 = _row(form)
tk.Label(row1, text="Input Directory:", justify="right", width=16, bg=BG).pack(side="left")
inputSelectButton = RoundedButton(row1, text="Select Folder...", command=selectInputClicked,
                                   width=DIRECTORY_BUTTON_WIDTH, height=32)
inputSelectButton.pack(side="left", padx=6)

# --------------------- Output directory ---------------------
outputDir = tk.StringVar(value="None Selected (defaults to <input>/results)")


def selectOutputClicked():
    chosen = filedialog.askdirectory()
    if chosen:
        outputDir.set(chosen)
        outputSelectButton.set_text(f"Selected: {_short_name(chosen)}")
        print(chosen + " selected as output")


row2 = _row(form)
tk.Label(row2, text="Output Directory:", justify="right", width=16, bg=BG).pack(side="left")
outputSelectButton = RoundedButton(row2, text="Select Folder... (optional)", command=selectOutputClicked,
                                    width=DIRECTORY_BUTTON_WIDTH, height=32)
outputSelectButton.pack(side="left", padx=6)

# --------------------- Specimen type ---------------------
SPECIMEN_TYPES = {
    "Heart (rotate, atria up/apex down, ventricle-only width)": "apex_down",
    "Other tissue/tumor (no rotation, simple center-to-edge)": "none",
}
specimenTypeLabel = tk.StringVar(value="")  # empty until the user picks one

row3 = _row(form)
tk.Label(row3, text="Specimen type:", justify="right", width=16, bg=BG).pack(side="left")
specimenTypeFrame = tk.Frame(row3, width=DIRECTORY_BUTTON_WIDTH, height=32, bg=BG)
specimenTypeFrame.pack_propagate(False)
specimenTypeFrame.pack(side="left", padx=6)
specimenTypeMenu = ttk.Combobox(
    specimenTypeFrame, textvariable=specimenTypeLabel, values=list(SPECIMEN_TYPES.keys()),
    state="readonly",
)
specimenTypeMenu.pack(fill="both", expand=True)
_widen_dropdown_popup(specimenTypeMenu)

# ------------------------ Check boxes ------------------------------
row4 = tk.Frame(form, bg=BG)
row4.pack(pady=(10, 0))

saveOverlays = tk.BooleanVar(value=True)
tk.Checkbutton(row4, text="Save overlay images + combined PDF", var=saveOverlays, bg=BG,
               activebackground=BG).pack(side="left", padx=10)

useGenotypeColors = tk.BooleanVar(value=True)
tk.Checkbutton(row4, text="Color axis lines by genotype", var=useGenotypeColors,
               bg=BG, activebackground=BG).pack(side="left", padx=10)

# Genotype group names -- default to this study's OX/WT convention, but any
# other filename convention can be typed in here instead (matched against
# the filename, case-insensitive); the red/blue colors stay the same either
# way, they are just applied to whichever two group names are given here.
def _make_entry(parent, var):
    return tk.Entry(parent, textvariable=var, width=10, bg="white", fg="black",
                     relief="flat", bd=0, highlightthickness=1,
                     highlightbackground=ACCENT, highlightcolor=ACCENT)


row5 = tk.Frame(form, bg=BG)
row5.pack(pady=(6, 0))
tk.Label(row5, text="Group 1 name (red):", bg=BG).pack(side="left", padx=(0, 4))
genotypeLabelA = tk.StringVar(value="OX")
_make_entry(row5, genotypeLabelA).pack(side="left", padx=(0, 16))
tk.Label(row5, text="Group 2 name (blue):", bg=BG).pack(side="left", padx=(0, 4))
genotypeLabelB = tk.StringVar(value="WT")
_make_entry(row5, genotypeLabelB).pack(side="left")

statusText = tk.StringVar(value="")
tk.Label(main, textvariable=statusText, font=("arial", 10), fg="gray30", bg=BG).pack(pady=(10, 0))


# ----------------------- Run button ----------------------------
def _run_in_background():
    input_path = Path(inputDir.get())
    output_path = Path(outputDir.get()) if outputDir.get() != "None Selected (defaults to <input>/results)" \
        else input_path / "results"
    orient_mode = SPECIMEN_TYPES[specimenTypeLabel.get()]
    label_a, label_b = genotypeLabelA.get().strip(), genotypeLabelB.get().strip()

    try:
        df = run(
            input_dir=input_path,
            output_dir=output_path,
            pattern=DEFAULT_PATTERN,
            ruler_side="auto",
            overlays=saveOverlays.get(),
            orient_mode=orient_mode,
            use_genotype_colors=useGenotypeColors.get(),
            genotype_labels=(label_a, label_b) if label_a and label_b else None,
        )
    except SystemExit as exc:
        window.after(0, lambda: _finish(error=str(exc)))
        return
    except Exception as exc:  # noqa: BLE001 - surface any failure to the user, do not crash the GUI
        window.after(0, lambda: _finish(error=f"Unexpected error: {exc}"))
        return

    ok = int(df["ok"].sum())
    total = len(df)
    low_cal = int(df["low_confidence_calibration"].fillna(False).sum())
    low_orient = int(df["low_confidence_orientation"].fillna(False).sum())
    summary = (
        f"{ok}/{total} images measured successfully.\n"
        f"{low_cal} low-confidence calibration, {low_orient} low-confidence orientation.\n"
        f"Results saved to:\n{output_path}"
    )
    window.after(0, lambda: _finish(summary=summary, output_path=output_path))


def _finish(summary: str | None = None, error: str | None = None, output_path: Path | None = None):
    runButton.set_enabled(True)
    statusText.set("")
    if error:
        msg.showinfo(message=f"There was an issue with this run:\n{error}")
        return
    msg.showinfo(message=f"Analysis Complete!\n\n{summary}")
    if output_path is not None:
        subprocess.run(["open", str(output_path)], check=False)


def runButtonClicked():
    if inputDir.get() == "None Selected":
        msg.showinfo(message="Please select an input directory first.")
        return
    if specimenTypeLabel.get() not in SPECIMEN_TYPES:
        msg.showinfo(message="Please choose a specimen type first.")
        return
    print("Running analysis...")
    runButton.set_enabled(False)
    statusText.set("Running... this window will pop up again when done.")
    threading.Thread(target=_run_in_background, daemon=True).start()


runFrame = tk.Frame(main, bg=BG)
runFrame.pack(pady=(14, 0))  # centered by default
runButton = RoundedButton(runFrame, text="Run", command=runButtonClicked, width=140, height=42,
                           radius=12, font=("Arial", 16, "bold"))
runButton.pack()


# ----------------------- Manual annotation ----------------------------
def manualAnnotateClicked():
    """Opens the click-to-annotate tool (annotate_specimen.py) for images
    the automatic measurement did not capture well. Runs as a separate
    process (it has its own matplotlib window/event loop) so this window
    stays open and usable.
    """
    default_dir = (
        str(Path(outputDir.get()) / "overlays")
        if outputDir.get() != "None Selected (defaults to <input>/results)"
        else (inputDir.get() if inputDir.get() != "None Selected" else None)
    )
    chosen = filedialog.askdirectory(
        title="Choose the folder of images to manually annotate",
        initialdir=default_dir,
    )
    if not chosen:
        return
    script = Path(__file__).parent / "annotate_specimen.py"
    subprocess.Popen([sys.executable, str(script), chosen])


manualFrame = tk.Frame(main, bg=BG)
manualFrame.pack(pady=(8, 0))
RoundedButton(
    manualFrame, text="Manual Annotation (for images not captured well)...",
    command=manualAnnotateClicked, width=420, height=32, font=("Arial", 12),
).pack()

# Main
window.mainloop()
