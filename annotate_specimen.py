# -*- coding: utf-8 -*-
"""
annotate_specimen.py

Interactive tool for recording ground-truth frame/length/width annotations
on specimen photos (or their rendered overlays), used as reference to check
and fix the automatic measurement pipeline -- or, per-image, to manually
re-frame a specimen the automatic segmentation got wrong and mark its
length/width from scratch.

For each image in a folder, this tool lets you:
  1. Click 2 opposite corners marking the tissue's FRAME (bounding box)
  2. Click 2 points marking where LENGTH should be measured
  3. Click 2 points marking where WIDTH should be measured
  4. Save all three as pixel coordinates (+ pixel distances) to a reference CSV

USAGE:
    python annotate_specimen.py "/path/to/image/folder"
    python annotate_specimen.py "/path/to/image/folder" specific_file.png

CONTROLS (while annotating):
    - Left-click on the image to add a point. The first 2 clicks mark
      opposite corners of the FRAME (drawn in green); the next 2 mark the
      LENGTH line (drawn in red); the last 2 mark the WIDTH line (drawn in
      blue).
    - Press 'u' to undo the last point (steps back across stage boundaries
      if needed).
    - Press 'q' to save and move to the next image (needs all 6 points).
    - Close the window / press 'q' with fewer than 6 points to SKIP (not saved).

Already-annotated images are automatically skipped on repeat runs, so you
can stop and resume this process across multiple sessions.
"""

import csv
import os
import sys

import matplotlib.pyplot as plt
from matplotlib import image as mpimg
from matplotlib.patches import Rectangle

OUTPUT_DIR = "annotation_reference"
# A separate file from the original reference_annotations.csv: that file's
# header has 11 columns (no frame), and this version writes 17 (frame added)
# -- appending the new format under the old header would misalign the CSV.
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "reference_annotations_v2_with_frame.csv")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")

FIELDNAMES = [
    "filename",
    "frame_x1", "frame_y1", "frame_x2", "frame_y2",
    "frame_width_px", "frame_height_px",
    "length_x1", "length_y1", "length_x2", "length_y2", "length_px",
    "width_x1", "width_y1", "width_x2", "width_y2", "width_px",
]

N_POINTS = 6  # 2 frame corners + 2 length endpoints + 2 width endpoints


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
    """Interactive matplotlib clicker: 2 points for the frame (bounding box),
    then 2 for length, then 2 for width."""

    def __init__(self, image, title):
        self.image = image
        self.title = title
        self.points = []  # up to 6: [frame_p1, frame_p2, len_p1, len_p2, wid_p1, wid_p2]
        self.finished = False

        self.fig, self.ax = plt.subplots(figsize=(8, 8))
        self.cid_click = self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.cid_key = self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.redraw()
        plt.show()

    def on_click(self, event):
        if event.inaxes != self.ax or len(self.points) >= N_POINTS:
            return
        self.points.append((event.xdata, event.ydata))
        self.redraw()

    def on_key(self, event):
        if event.key == "u":
            if self.points:
                self.points.pop()
                self.redraw()
        elif event.key == "q":
            if len(self.points) >= N_POINTS:
                self.finished = True
            plt.close(self.fig)

    def redraw(self):
        self.ax.clear()
        self.ax.imshow(self.image)

        if len(self.points) >= 1:
            self.ax.plot(*self.points[0], "o", color="limegreen", markersize=8)
        if len(self.points) >= 2:
            (x1, y1), (x2, y2) = self.points[0], self.points[1]
            self.ax.add_patch(Rectangle(
                (min(x1, x2), min(y1, y2)), abs(x2 - x1), abs(y2 - y1),
                fill=False, edgecolor="limegreen", linewidth=2, label="frame",
            ))
        if len(self.points) >= 3:
            self.ax.plot(*self.points[2], "o", color="red", markersize=8)
        if len(self.points) >= 4:
            xs = [self.points[2][0], self.points[3][0]]
            ys = [self.points[2][1], self.points[3][1]]
            self.ax.plot(xs, ys, "o-", color="red", markersize=8, linewidth=2, label="length")
        if len(self.points) >= 5:
            self.ax.plot(*self.points[4], "o", color="deepskyblue", markersize=8)
        if len(self.points) >= 6:
            xs = [self.points[4][0], self.points[5][0]]
            ys = [self.points[4][1], self.points[5][1]]
            self.ax.plot(xs, ys, "o-", color="deepskyblue", markersize=8, linewidth=2, label="width")

        if len(self.points) < 2:
            step = f"click point {len(self.points) + 1}/2 for FRAME (green, opposite corners)"
        elif len(self.points) < 4:
            step = f"click point {len(self.points) - 1}/2 for LENGTH (red)"
        elif len(self.points) < 6:
            step = f"click point {len(self.points) - 3}/2 for WIDTH (blue)"
        else:
            step = "done -- press 'q' to save"

        self.ax.set_title(
            f"{self.title}\n{step}  |  'u' = undo  |  'q' = save+next (need all 6 points)",
            fontsize=10,
        )
        self.fig.canvas.draw()

    def get_row(self, filename):
        if not self.finished:
            return None
        (fx1, fy1), (fx2, fy2) = self.points[0], self.points[1]
        (lx1, ly1), (lx2, ly2) = self.points[2], self.points[3]
        (wx1, wy1), (wx2, wy2) = self.points[4], self.points[5]
        length_px = ((lx2 - lx1) ** 2 + (ly2 - ly1) ** 2) ** 0.5
        width_px = ((wx2 - wx1) ** 2 + (wy2 - wy1) ** 2) ** 0.5
        return {
            "filename": filename,
            "frame_x1": fx1, "frame_y1": fy1, "frame_x2": fx2, "frame_y2": fy2,
            "frame_width_px": abs(fx2 - fx1), "frame_height_px": abs(fy2 - fy1),
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
