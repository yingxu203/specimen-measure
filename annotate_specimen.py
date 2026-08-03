# -*- coding: utf-8 -*-
"""
annotate_specimen.py

Interactive tool for recording ground-truth outline/length/width
annotations on specimen photos (or their rendered overlays), used as
reference to check and fix the automatic measurement pipeline -- or,
per-image, to manually re-trace a specimen the automatic segmentation got
wrong and mark its length/width from scratch.

For each image in a folder, this tool lets you:
  1. Click as many points as you like tracing the tissue's true OUTLINE
     (drawn in green) -- not just a bounding box, so the resulting area is
     the actual traced polygon's area, not an approximation.
  2. Click 2 points marking where LENGTH should be measured
  3. Click 2 points marking where WIDTH should be measured
  4. Save all three as pixel coordinates (+ pixel distances/area) to a
     reference CSV

USAGE:
    python annotate_specimen.py "/path/to/image/folder"
    python annotate_specimen.py "/path/to/image/folder" specific_file.png

CONTROLS (while annotating):
    - Left-click on the image to add a point.
    - Stage 1 (OUTLINE, green): click every point around the tissue's true
      edge, in order around the shape (as many as you need for an accurate
      trace -- at least 3). Press 'n' when done tracing to move on.
    - Stage 2 (LENGTH, red): click 2 points.
    - Stage 3 (WIDTH, blue): click 2 points -- moves on automatically.
    - Press 'u' to undo the last point (steps back across stage boundaries
      if the current stage has nothing left to undo).
    - Press 'q' to save and move to the next image (needs the outline
      closed and both length/width drawn).
    - Close the window / press 'q' before finishing to SKIP (not saved).
    - Scroll the mouse wheel / trackpad to zoom in/out, centered on the
      cursor -- the heart is often small in the full photo, zoom in for
      precise clicks.
    - Arrow keys pan the view once zoomed in. Press 'r' to reset back to
      the full image.

Already-annotated images are automatically skipped on repeat runs, so you
can stop and resume this process across multiple sessions.
"""

import csv
import os
import sys

import tkinter as tk
from tkinter import messagebox

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import image as mpimg
from matplotlib.patches import Polygon

# Matplotlib binds the left/right arrow keys to its own toolbar back/forward
# view-history navigation by default, which would fight with our own
# arrow-key panning below (both would respond to the same keypress).
plt.rcParams["keymap.back"] = []
plt.rcParams["keymap.forward"] = []

OUTPUT_DIR = "annotation_reference"
# v3: the frame is now a hand-traced polygon (true area) instead of a
# 2-corner bounding box (v2, area only approximate) -- a different file so
# the two schemas (variable-length polygon vs. fixed rectangle) never mix.
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "reference_annotations_v3_polygon_frame.csv")
OUTPUT_XLSX = os.path.join(OUTPUT_DIR, "reference_annotations_v3_polygon_frame.xlsx")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")

FIELDNAMES = [
    "filename",
    "frame_points_px", "frame_area_px",
    "length_x1", "length_y1", "length_x2", "length_y2", "length_px",
    "width_x1", "width_y1", "width_x2", "width_y2", "width_px",
]

MIN_FRAME_POINTS = 3
ZOOM_SCALE = 1.3
PAN_FRACTION = 0.15


def polygon_area_px(points):
    """Shoelace formula. `points` is a list of (x, y) pixel coordinates,
    assumed to trace the outline in order (open, not pre-closed)."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def already_annotated(filename):
    if not os.path.exists(OUTPUT_CSV):
        return False
    with open(OUTPUT_CSV, newline="") as f:
        return any(row["filename"] == filename for row in csv.DictReader(f))


def append_row(row):
    is_new = not os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
    # Keep an Excel version in sync too, same as the main measurement
    # results -- rewritten in full each time since there's no cheap
    # "append a row" for .xlsx like there is for a text CSV.
    pd.read_csv(OUTPUT_CSV).to_excel(OUTPUT_XLSX, index=False)


class LineAnnotator:
    """Interactive matplotlib clicker: an outline trace (any number of
    points), then 2 points for length, then 2 for width."""

    def __init__(self, image, title):
        self.image = image
        self.title = title
        self.stage = "frame"  # "frame" -> "length" -> "width" -> "done"
        self.frame_points = []
        self.length_points = []
        self.width_points = []
        self.finished = False
        self._view_initialized = False  # False until the user has zoomed/panned

        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        self.cid_click = self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.cid_key = self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.cid_scroll = self.fig.canvas.mpl_connect("scroll_event", self.on_scroll)
        self.redraw()
        plt.show()

    def on_scroll(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        factor = 1 / ZOOM_SCALE if event.button == "up" else ZOOM_SCALE
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        x, y = event.xdata, event.ydata
        new_w = (xlim[1] - xlim[0]) * factor
        new_h = (ylim[1] - ylim[0]) * factor
        relx = (x - xlim[0]) / (xlim[1] - xlim[0])
        rely = (y - ylim[0]) / (ylim[1] - ylim[0])
        self.ax.set_xlim(x - new_w * relx, x + new_w * (1 - relx))
        self.ax.set_ylim(y - new_h * rely, y + new_h * (1 - rely))
        self._view_initialized = True
        self.fig.canvas.draw()

    def _pan(self, direction):
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        dx = (xlim[1] - xlim[0]) * PAN_FRACTION
        dy = (ylim[1] - ylim[0]) * PAN_FRACTION
        if direction == "left":
            self.ax.set_xlim(xlim[0] - dx, xlim[1] - dx)
        elif direction == "right":
            self.ax.set_xlim(xlim[0] + dx, xlim[1] + dx)
        elif direction == "up":
            self.ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
        elif direction == "down":
            self.ax.set_ylim(ylim[0] + dy, ylim[1] + dy)
        self._view_initialized = True

    def on_click(self, event):
        if event.inaxes != self.ax or self.stage == "done":
            return
        point = (event.xdata, event.ydata)
        if self.stage == "frame":
            self.frame_points.append(point)
        elif self.stage == "length":
            if len(self.length_points) < 2:
                self.length_points.append(point)
            if len(self.length_points) == 2:
                self.stage = "width"
        elif self.stage == "width":
            if len(self.width_points) < 2:
                self.width_points.append(point)
            if len(self.width_points) == 2:
                self.stage = "done"
        self.redraw()

    def on_key(self, event):
        if event.key == "u":
            self._undo()
        elif event.key == "n" and self.stage == "frame" and len(self.frame_points) >= MIN_FRAME_POINTS:
            self.stage = "length"
        elif event.key == "r":
            self._view_initialized = False  # redraw() below falls back to the full image
        elif event.key in ("left", "right", "up", "down"):
            self._pan(event.key)
        elif event.key == "q":
            if self.stage == "done":
                self.finished = True
            plt.close(self.fig)
        self.redraw()

    def _undo(self):
        if self.stage == "frame":
            if self.frame_points:
                self.frame_points.pop()
        elif self.stage == "length":
            if self.length_points:
                self.length_points.pop()
            else:
                self.stage = "frame"
        elif self.stage == "width":
            if self.width_points:
                self.width_points.pop()
            else:
                self.stage = "length"
        elif self.stage == "done":
            self.stage = "width"
            if self.width_points:
                self.width_points.pop()

    def redraw(self):
        # ax.clear() below wipes the current zoom/pan too, so save and
        # restore it around every redraw (points get added, undone, etc. --
        # a wiped view on every click would make zooming pointless).
        xlim = self.ax.get_xlim() if self._view_initialized else None
        ylim = self.ax.get_ylim() if self._view_initialized else None

        self.ax.clear()
        self.ax.imshow(self.image)
        if xlim is not None:
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        if self.frame_points:
            xs = [p[0] for p in self.frame_points]
            ys = [p[1] for p in self.frame_points]
            if self.stage == "frame":
                self.ax.plot(xs, ys, "o-", color="limegreen", markersize=5, linewidth=2)
            else:
                self.ax.add_patch(Polygon(
                    self.frame_points, closed=True, fill=True,
                    facecolor="limegreen", alpha=0.15, edgecolor="limegreen", linewidth=2,
                ))
                self.ax.plot(xs, ys, "o", color="limegreen", markersize=5)

        if len(self.length_points) >= 1:
            self.ax.plot(*self.length_points[0], "o", color="red", markersize=8)
        if len(self.length_points) >= 2:
            xs = [p[0] for p in self.length_points]
            ys = [p[1] for p in self.length_points]
            self.ax.plot(xs, ys, "o-", color="red", markersize=8, linewidth=2, label="length")

        if len(self.width_points) >= 1:
            self.ax.plot(*self.width_points[0], "o", color="deepskyblue", markersize=8)
        if len(self.width_points) >= 2:
            xs = [p[0] for p in self.width_points]
            ys = [p[1] for p in self.width_points]
            self.ax.plot(xs, ys, "o-", color="deepskyblue", markersize=8, linewidth=2, label="width")

        self.ax.set_title(f"{self.title}\n{self._status_text()}", fontsize=10)
        self.fig.canvas.draw()

    def _status_text(self):
        zoom_hint = "  |  scroll = zoom, arrows = pan, 'r' = reset view"
        if self.stage == "frame":
            n = len(self.frame_points)
            need = "" if n >= MIN_FRAME_POINTS else f" (need {MIN_FRAME_POINTS - n} more)"
            return (f"click OUTLINE points (green), {n} so far{need}  |  "
                    f"'n' = finish outline  |  'u' = undo  |  'q' = save+next{zoom_hint}")
        if self.stage == "length":
            return (f"click point {len(self.length_points) + 1}/2 for LENGTH (red)  |  "
                    f"'u' = undo  |  'q' = save+next{zoom_hint}")
        if self.stage == "width":
            return (f"click point {len(self.width_points) + 1}/2 for WIDTH (blue)  |  "
                    f"'u' = undo  |  'q' = save+next{zoom_hint}")
        return f"done -- press 'q' to save{zoom_hint}"

    def get_row(self, filename):
        if not self.finished:
            return None
        (lx1, ly1), (lx2, ly2) = self.length_points
        (wx1, wy1), (wx2, wy2) = self.width_points
        length_px = ((lx2 - lx1) ** 2 + (ly2 - ly1) ** 2) ** 0.5
        width_px = ((wx2 - wx1) ** 2 + (wy2 - wy1) ** 2) ** 0.5
        frame_points_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in self.frame_points)
        return {
            "filename": filename,
            "frame_points_px": frame_points_str,
            "frame_area_px": polygon_area_px(self.frame_points),
            "length_x1": lx1, "length_y1": ly1, "length_x2": lx2, "length_y2": ly2,
            "length_px": length_px,
            "width_x1": wx1, "width_y1": wy1, "width_x2": wx2, "width_y2": wy2,
            "width_px": width_px,
        }


def main():
    if len(sys.argv) < 2:
        print('Usage: python annotate_specimen.py "<path_to_image_folder>" [optional_specific_filename]')
        return

    input_dir = sys.argv[1]
    target_file = sys.argv[2] if len(sys.argv) > 2 else None

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(IMAGE_EXTENSIONS))

    if target_file:
        if target_file not in files:
            print(f"ERROR: '{target_file}' not found in {input_dir}")
            return
        files = [target_file]
        print(f"Annotating single file: {target_file}")

    annotated_count = 0
    for file in files:
        if not target_file and already_annotated(file):
            print(f"Skipping {file} (already annotated)")
            continue

        image = mpimg.imread(os.path.join(input_dir, file))

        print(f"\n=== {file} ===")
        annotator = LineAnnotator(image, file)
        row = annotator.get_row(file)

        if row is None:
            print(f"  Skipped {file} (annotation incomplete or window closed early)")
            continue

        append_row(row)
        annotated_count += 1
        print(f"  Saved. ({annotated_count} annotated this session)")

    print(f"\nDone this session. Reference annotations saved to:\n  {OUTPUT_CSV}\n  {OUTPUT_XLSX}")
    _show_completion_popup(annotated_count)


def _show_completion_popup(annotated_count):
    root = tk.Tk()
    root.withdraw()
    if annotated_count:
        message = (
            f"{annotated_count} image(s) annotated this session.\n\n"
            f"Results saved to:\n{os.path.abspath(OUTPUT_CSV)}\n{os.path.abspath(OUTPUT_XLSX)}"
        )
    else:
        message = "No new annotations were saved this session."
    messagebox.showinfo("Annotation Complete", message)
    root.destroy()


if __name__ == "__main__":
    main()
