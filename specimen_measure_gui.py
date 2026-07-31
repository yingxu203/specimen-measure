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
# a blue accent for the title text.
BG = "#FFFFFF"
ACCENT = "#0080FE"

window = tk.Tk()
window.title(APP_TITLE)
window.geometry("900x340")
window.configure(bg=BG)

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
        print(chosen + " selected as input")


row1 = _row(form)
tk.Label(row1, text="Input Directory:", justify="right", width=16, bg=BG).pack(side="left")
ttk.Entry(row1, textvariable=inputDir, justify="center", width=68, state="readonly").pack(
    side="left", padx=6)
ttk.Button(row1, text="Select", command=selectInputClicked, width=10).pack(side="left")

# --------------------- Output directory ---------------------
outputDir = tk.StringVar(value="None Selected (defaults to <input>/results)")


def selectOutputClicked():
    chosen = filedialog.askdirectory()
    if chosen:
        outputDir.set(chosen)
        print(chosen + " selected as output")


row2 = _row(form)
tk.Label(row2, text="Output Directory:", justify="right", width=16, bg=BG).pack(side="left")
ttk.Entry(row2, textvariable=outputDir, justify="center", width=68, state="readonly").pack(
    side="left", padx=6)
ttk.Button(row2, text="Select", command=selectOutputClicked, width=10).pack(side="left")

# --------------------- Specimen type ---------------------
SPECIMEN_TYPES = {
    "Heart (rotate, atria up/apex down, ventricle-only width)": "apex_down",
    "Other tissue/tumor (no rotation, simple center-to-edge)": "none",
}
specimenTypeLabel = tk.StringVar(value=list(SPECIMEN_TYPES.keys())[0])

row3 = _row(form)
tk.Label(row3, text="Specimen type:", justify="right", width=16, bg=BG).pack(side="left")
specimenTypeMenu = ttk.Combobox(
    row3, textvariable=specimenTypeLabel, values=list(SPECIMEN_TYPES.keys()),
    state="readonly", width=58,
)
specimenTypeMenu.pack(side="left", padx=6)

# ------------------------ Check boxes ------------------------------
row4 = tk.Frame(form, bg=BG)
row4.pack(pady=(10, 0))

saveOverlays = tk.BooleanVar(value=True)
tk.Checkbutton(row4, text="Save overlay images + combined PDF", var=saveOverlays, bg=BG,
               activebackground=BG).pack(side="left", padx=10)

useGenotypeColors = tk.BooleanVar(value=True)
tk.Checkbutton(row4, text="Color axis lines by genotype (OX=red / WT=blue)", var=useGenotypeColors,
               bg=BG, activebackground=BG).pack(side="left", padx=10)

statusText = tk.StringVar(value="")
tk.Label(main, textvariable=statusText, font=("arial", 10), fg="gray30", bg=BG).pack(pady=(10, 0))


# ----------------------- Run button ----------------------------
def _run_in_background():
    input_path = Path(inputDir.get())
    output_path = Path(outputDir.get()) if outputDir.get() != "None Selected (defaults to <input>/results)" \
        else input_path / "results"
    orient_mode = SPECIMEN_TYPES[specimenTypeLabel.get()]

    try:
        df = run(
            input_dir=input_path,
            output_dir=output_path,
            pattern=DEFAULT_PATTERN,
            ruler_side="auto",
            overlays=saveOverlays.get(),
            orient_mode=orient_mode,
            use_genotype_colors=useGenotypeColors.get(),
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
    runButton.configure(state="normal")
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
    print("Running analysis...")
    runButton.configure(state="disabled")
    statusText.set("Running... this window will pop up again when done.")
    threading.Thread(target=_run_in_background, daemon=True).start()


runFrame = tk.Frame(main, bg=BG)
runFrame.pack(pady=(14, 0))  # centered by default
# "Accent.TButton" is a built-in native style on macOS (Tk 8.6.10+) that
# renders as a real rounded, filled-blue system button -- plain tk.Button
# ignores custom bg colors under macOS's native (Aqua) button rendering, so
# a manually-colored button would just stay gray.
try:
    runButton = ttk.Button(runFrame, text="Run", width=12, command=runButtonClicked,
                            style="Accent.TButton")
except tk.TclError:
    runButton = ttk.Button(runFrame, text="Run", width=12, command=runButtonClicked)
runButton.pack(ipady=4)


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
ttk.Button(
    manualFrame, text="Manual Annotation (for images not captured well)...",
    command=manualAnnotateClicked,
).pack()

# Main
window.mainloop()
