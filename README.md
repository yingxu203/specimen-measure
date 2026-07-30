# heart-measure

Batch morphometry for photographed whole-heart specimens: automatically finds
the cm/mm ruler in each photo, segments the heart from the background, and
reports the long-axis (apex-to-base) length, short-axis (transverse) length,
and cross-sectional area in millimeters/mm², calibrated per-image from the
ruler rather than an assumed camera distance.

Built for a set of mouse heart specimen photos (front/back views on a dark
background with a printed ruler along one edge), but the calibration and
segmentation approach generalizes to any similar setup. Usable either as a
command-line batch tool or through a point-and-click browser UI (see
[UI](#ui-for-non-coders)) — no coding required for day-to-day use.

![example overlay on a synthetic test image](docs/example_overlay.png)

*(Synthetic illustrative example — real specimen photos are not included in
this repo; see [Usage](#usage) to run against your own images.)*

## How it works

For each image:

1. **Calibration** ([`heart_measure/calibration.py`](heart_measure/calibration.py)) — finds which edge of
   the frame the bright ruler panel is on, samples a narrow strip just inside
   its edge, and locates the regularly-spaced tick marks in that strip's
   brightness profile. The spacing between ticks (assumed to be 1 mm
   apart) gives pixels-per-mm for *that specific photo* — no fixed
   "pixels per cm" assumption baked in, so it's robust to photos taken at
   slightly different zoom/crop.
2. **Segmentation** ([`heart_measure/segmentation.py`](heart_measure/segmentation.py)) — thresholds the
   HSV "value" channel (max of R, G, B) rather than plain grayscale
   brightness, because deep red tissue (atria, vessels) can have low mean
   brightness but still stands out clearly from a near-black background in
   at least one color channel. Otsu thresholding + morphological
   cleanup + largest-connected-component selection isolates the heart.
3. **Measurement** ([`heart_measure/segmentation.py`](heart_measure/segmentation.py)`compute_axes`) —
   long/short axis length is a true caliper-style measurement: every
   foreground pixel is projected onto the shape's principal-axis directions,
   and the min/max of that projection is taken, so the reported length
   reaches exactly to the segmented shape's real boundary (not an
   ellipse-of-equivalent-moments approximation, which can over- or
   under-shoot on notched/asymmetric shapes like a heart with an auricle).
   Area is simply the segmented pixel count, converted with the same
   per-image scale.
4. **Display rotation** ([`heart_measure/rotate.py`](heart_measure/rotate.py)) — for the overlay image
   only (not the underlying measurement, which is rotation-invariant), the
   specimen crop is rotated so the long axis is horizontal — parallel to the
   bottom edge — and tightly cropped, so overlays are easy to flip through
   and compare regardless of how the heart happened to sit in the original
   photo.
5. **Overlay drawing** ([`heart_measure/measure.py`](heart_measure/measure.py)) — the rotated crop gets
   the heart outline (green), long axis line labeled **L** and short axis
   line labeled **W** (colored **red `#FF2C2C`** for OX/OF/OM animals,
   **blue `#0000FF`** for WT/WF/WM animals, based on the genotype parsed from
   the filename), and a text label with the long/short/area/scale values.

## Install

```bash
pip install -r requirements.txt
```

(Python 3.10+. No GPU or compiled dependencies — numpy/scipy/scikit-image/pillow/pandas/tifffile/streamlit only.)

## UI (for non-coders)

```bash
streamlit run app.py
```

or, on macOS, just double-click [`run_app.command`](run_app.command) in Finder — it installs
dependencies if needed and opens the app in your browser. No command line
required.

In the app you can either drag-and-drop photos or point it at a local folder
path, run the measurement, browse results in a table, flip through the
rotated/color-coded overlay images, and download the CSVs — everything the
CLI produces, with no code.

## Usage (command line)

```bash
python -m heart_measure.cli --input-dir "/path/to/your/photos" --output-dir ./results
```

This searches `--input-dir` recursively for `*.tif` files and writes to `--output-dir`:

- `measurements.csv` — one row per image (see schema below)
- `summary_by_animal_and_view.csv` — mean ± std long/short axis/area grouped
  by (genotype, treatment, animal ID, **view**) — front and back photos of
  the same animal are always kept in separate rows, never averaged together,
  since a front-view photo and a back-view photo of the same heart aren't
  directly comparable measurements
- `overlays/*.png` — each specimen crop, rotated so the long axis is
  horizontal, with the detected heart outline (green) and long/short axis
  lines (labeled **L**/**W**, colored by genotype — red for OX/OF/OM, blue
  for WT/WF/WM) drawn on it, plus the measured values as text

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--pattern` | `*.tif` | glob pattern for image files |
| `--ruler-side` | `auto` | `left`/`right`/`auto` — which edge of the frame the ruler is on |
| `--no-overlays` | off | skip writing overlay PNGs (faster, smaller output) |

## Output schema (`measurements.csv`)

| Column | Meaning |
|---|---|
| `filename` | source file name |
| `ok` | whether measurement succeeded |
| `error` | failure reason, if `ok` is false |
| `long_axis_mm`, `short_axis_mm` | heart long/short axis length in mm |
| `area_mm2` | segmented area in mm² |
| `px_per_mm` | calibrated scale for this image |
| `n_ruler_ticks` | number of ruler ticks the calibration found (see below) |
| `touches_frame_edge` | heart mask touches the image border — possible crop/clipping, worth a visual check |
| `low_confidence_calibration` | fewer than 10 ruler ticks were found; scale may be off by ~10-20%, worth a visual check or a manual re-measure |
| `genotype`, `treatment`, `animal_id`, `view`, `replicate`, `cohort`, `is_sv_variant`, `notes` | best-effort fields parsed from the filename (see below); `None`/blank if not present |

## Calibration confidence

Ruler tick detection is very reliable when the ruler panel spans the full
frame height (typically 11-14 ticks detected). Some photos have the ruler
photographed at a slight tilt, with a rounded/cropped corner, or overexposed
— the calibration still runs (it restricts tick-finding to the actual
ruler sub-region) but on fewer ticks, and cross-checking against sibling
photos of the same animal shows the resulting scale can be off by 10-20%.
These rows are flagged `low_confidence_calibration = True` rather than
silently trusted — the overlay PNG also stamps `[LOW-CONFIDENCE
CALIBRATION]` on the image itself. Treat these as "measure this one by hand"
candidates, not as ready-to-use numbers.

## Filename metadata parsing

Real lab filenames accumulate inconsistency over time (extra spaces, typos in
casing, free-text notes). `heart_measure/metadata.py` extracts genotype,
treatment, animal ID, view (front/back), replicate number, and free-text
notes (e.g. "NO RA", "NOT ALIGNED") with a set of best-effort regexes — every
field is `None` if its pattern doesn't match, rather than raising, so one odd
filename never aborts a batch run. Check `measurements.csv` for blank fields
after a run on a new naming convention and extend the patterns in
`metadata.py` as needed.

## Limitations

- Assumes a dark, low-texture-relative-to-tissue background and a ruler
  that is visibly brighter than the specimen area. A different photography
  setup (different background color, ruler style, or lighting) will likely
  need threshold tuning in `segmentation.py`/`calibration.py`.
- Assumes ruler ticks are 1 mm apart (i.e. the finest gradation on the
  ruler). If your ruler's finest visible gradation is different, the
  reported `px_per_mm` will be scaled incorrectly.
- The long/short axis measurement reaches to the edges of whatever tissue
  survived dissection/segmentation (e.g. a torn auricle changes the
  outline) — it isn't a judgment call about what "should" count as part of
  the heart. Always spot-check overlays against your own judgment.
- Not validated on anything other than the mouse heart photo setup this was
  built for.

## Roadmap

Built-in statistical analysis/comparison across genotype and treatment
groups (beyond the simple per-animal summary CSV) is planned as a follow-up,
once the measurement pipeline and UI are stable.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

Tests run entirely against a synthetic generated image
(`tests/synthetic.py`) with a known scale and heart size — no real specimen
photos are (or should be) checked into this repo.

## License

MIT — see [LICENSE](LICENSE).
