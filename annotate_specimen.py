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

Already-annotated images are automatically skipped on repeat runs, so you
can stop and resume this process across multiple sessions.
"""

import csv
import os
import sys

import matplotlib.pyplot as plt
from matplotlib import image as mpimg
from matplotlib.patches import Polygon

OUTPUT_DIR = "annotation_reference"
# v3: the frame is now a hand-traced polygon (true area) instead of a
# 2-corner bounding box (v2, area only approximate) -- a different file so
# the two schemas (variable-length polygon vs. fixed rectangle) never mix.
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "reference_annotations_v3_polygon_frame.csv")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")

FIELDNAMES = [
    "filename",
    "frame_points_px", "frame_area_px",
    "length_x1", "length_y1", "length_x2", "length_y2", "length_px",
    "width_x1", "width_y1", "width_x2", "width_y2", "width_px",
]

MIN_FRAME_POINTS = 3


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

        self.fig, self.ax = plt.subplots(figsize=(8, 8))
        self.cid_click = self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.cid_key = self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.redraw()
        plt.show()

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
        self.ax.clear()
        self.ax.imshow(self.image)

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
        if self.stage == "frame":
            n = len(self.frame_points)
            need = "" if n >= MIN_FRAME_POINTS else f" (need {MIN_FRAME_POINTS - n} more)"
            return (f"click OUTLINE points (green), {n} so far{need}  |  "
                    f"'n' = finish outline  |  'u' = undo  |  'q' = save+next")
        if self.stage == "length":
            return f"click point {len(self.length_points) + 1}/2 for LENGTH (red)  |  'u' = undo  |  'q' = save+next"
        if self.stage == "width":
            return f"click point {len(self.width_points) + 1}/2 for WIDTH (blue)  |  'u' = undo  |  'q' = save+next"
        return "done -- press 'q' to save"

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

    print(f"\nDone this session. Reference annotations saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
