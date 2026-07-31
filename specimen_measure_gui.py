# -*- coding: utf-8 -*-
"""
specimen_measure_gui.py

Desktop pop-up window for the batch measurement tool, for anyone who would
rather not use the browser UI (app.py) or the command line. Matches the
look and workflow of the existing Echocardiography Segmenter tool: pick a
folder, check some boxes, hit Run, get a "done" popup.

Launch with:
    python3 specimen_measure_gui.py
"""

import sys
import threading
import tkinter as tk
import tkinter.ttk as ttk
from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox as msg

sys.path.insert(0, str(Path(__file__).parent))

from specimen_measure.cli import DEFAULT_PATTERN, run  # noqa: E402

window = tk.Tk()
window.title("specimen-measure")
window.geometry("900x260")

appTitle = tk.Label(window, text="specimen-measure", font=("calibri", 20, "bold"), fg="forest green")
appTitle.grid(column=3, row=0)

# ----------------------- Formatting -----------------------
offsetBlank = tk.Label(text="", width=4, height=2)
offsetBlank.grid(column=0, row=0)
for r in (2, 4, 6, 8, 10, 12):
    tk.Label(text="", width=1, height=1).grid(column=0, row=r)

# --------------------- Input directory ---------------------
inputDir = tk.StringVar(value="None Selected")


def selectInputClicked():
    chosen = filedialog.askdirectory()
    if chosen:
        inputDir.set(chosen)
        print(chosen + " selected as input")


tk.Label(window, text="Input Directory:", justify="right", width=20).grid(column=1, row=1)
inputDirDisp = tk.Label(window, textvariable=inputDir, font=("arial", 8), justify="center", bg="white", width=90)
inputDirDisp.grid(column=2, row=1, columnspan=3)
tk.Button(window, text="Select", command=selectInputClicked, justify="right", width=10).grid(column=5, row=1)

# --------------------- Output directory ---------------------
outputDir = tk.StringVar(value="None Selected (defaults to <input>/results)")


def selectOutputClicked():
    chosen = filedialog.askdirectory()
    if chosen:
        outputDir.set(chosen)
        print(chosen + " selected as output")


tk.Label(window, text="Output Directory:", justify="right", width=20).grid(column=1, row=3)
outputDirDisp = tk.Label(window, textvariable=outputDir, font=("arial", 8), justify="center", bg="white", width=90)
outputDirDisp.grid(column=2, row=3, columnspan=3)
tk.Button(window, text="Select", command=selectOutputClicked, justify="right", width=10).grid(column=5, row=3)

# --------------------- Specimen type ---------------------
SPECIMEN_TYPES = {
    "Heart (rotate, atria up/apex down, ventricle-only width)": "apex_down",
    "Other tissue/tumor (no rotation, simple center-to-edge)": "none",
}
specimenTypeLabel = tk.StringVar(value=list(SPECIMEN_TYPES.keys())[0])
tk.Label(window, text="Specimen type:", justify="right", width=20).grid(column=1, row=5)
specimenTypeMenu = ttk.Combobox(
    window, textvariable=specimenTypeLabel, values=list(SPECIMEN_TYPES.keys()),
    state="readonly", width=55,
)
specimenTypeMenu.grid(column=2, row=5, columnspan=3, sticky="w")

# ------------------------ Check boxes ------------------------------
saveOverlays = tk.BooleanVar(value=True)
tk.Checkbutton(window, text="Save overlay images + combined PDF", var=saveOverlays).grid(column=2, row=7)

useGenotypeColors = tk.BooleanVar(value=True)
tk.Checkbutton(window, text="Color axis lines by genotype (OX=red / WT=blue)", var=useGenotypeColors).grid(
    column=3, row=7,
)

statusText = tk.StringVar(value="")
statusLabel = tk.Label(window, textvariable=statusText, font=("arial", 10), fg="gray30")
statusLabel.grid(column=3, row=9)


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
        import subprocess
        subprocess.run(["open", str(output_path)], check=False)


def runButtonClicked():
    if inputDir.get() == "None Selected":
        msg.showinfo(message="Please select an input directory first.")
        return
    print("Running analysis...")
    runButton.configure(state="disabled")
    statusText.set("Running... this window will pop up again when done.")
    threading.Thread(target=_run_in_background, daemon=True).start()


runButton = tk.Button(window, text="Run", font=("Arial", 18), command=runButtonClicked)
runButton.grid(column=3, row=8)

# Main
window.mainloop()
