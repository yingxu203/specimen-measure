"""specimen-measure UI: a point-and-click front end for the batch
measurement pipeline, so anyone in the lab can run it without touching a
command line.

Launch with:
    streamlit run app.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw
from skimage import measure as sk_measure
from streamlit_image_coordinates import streamlit_image_coordinates

from specimen_measure.cli import DEFAULT_PATTERN, find_images, summarize_by_animal_and_view
from specimen_measure.contact_sheet import build_overlay_pdf
from specimen_measure.measure import get_rotated_crop, measure_file

st.set_page_config(page_title="specimen-measure", layout="wide")

ORIENT_OPTIONS = {
    "Heart (atria up, apex down)": "apex_down",
    "Other elongated organ/tumor (long axis vertical)": "vertical",
    "Other (long axis horizontal)": "horizontal",
}

for key, default in [
    ("df", None), ("overlay_paths", {}), ("image_path_by_name", {}),
    ("manual_overrides", {}), ("flip_by_name", {}), ("render_cache", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

st.title("specimen-measure")
st.caption(
    "Ruler-calibrated long-axis / short-axis / area measurement for excised organ or tumor "
    "specimen photos. Each overlay is rotated to a standard orientation for easy side-by-side "
    "comparison. Front and back photos of the same animal are always measured and summarized "
    "separately, never averaged together."
)

with st.expander("Settings", expanded=False):
    orient_label = st.selectbox("Specimen orientation convention", list(ORIENT_OPTIONS.keys()))
    orient_mode = ORIENT_OPTIONS[orient_label]
    use_genotype_colors = st.checkbox(
        "Color axis lines by genotype prefix (OX/OF/OM = red, WT/WF/WM = blue) -- heart-study "
        "convention; leave off for other specimen types",
        value=(orient_mode == "apex_down"),
    )

mode = st.radio("Where are your photos?", ["Upload photos", "Local folder path"], horizontal=True)

image_paths: list[Path] = []

if mode == "Upload photos":
    uploaded = st.file_uploader(
        "Drag and drop TIFF photos here (you can select many at once)",
        type=["tif", "tiff"], accept_multiple_files=True,
    )
    if uploaded:
        upload_dir = Path(tempfile.mkdtemp(prefix="specimen_measure_upload_"))
        for uf in uploaded:
            dest = upload_dir / uf.name
            dest.write_bytes(uf.getbuffer())
            image_paths.append(dest)
else:
    folder = st.text_input(
        "Folder path (searched recursively for *.tif files)",
        placeholder="/Users/you/path/to/your/photos",
    )
    if folder:
        folder_path = Path(folder).expanduser()
        if folder_path.is_dir():
            image_paths = find_images(folder_path, DEFAULT_PATTERN)
        else:
            st.error(f"Not a folder: {folder}")

if image_paths:
    st.write(f"Found **{len(image_paths)}** image(s).")
    if st.button("Run measurement", type="primary"):
        overlay_dir = Path(tempfile.mkdtemp(prefix="specimen_measure_overlays_"))
        rows = []
        overlay_paths: dict[str, Path] = {}
        path_by_name: dict[str, Path] = {}
        progress = st.progress(0.0, text="Starting...")
        for i, path in enumerate(image_paths):
            overlay_path = overlay_dir / f"{path.stem}_overlay.png"
            result = measure_file(
                path, overlay_path=overlay_path,
                orient_mode=orient_mode, use_genotype_colors=use_genotype_colors,
            )
            rows.append(result.to_row())
            path_by_name[path.name] = path
            if overlay_path.exists():
                overlay_paths[path.name] = overlay_path
            progress.progress((i + 1) / len(image_paths), text=path.name)
        progress.empty()
        st.session_state.df = pd.DataFrame(rows)
        st.session_state.overlay_paths = overlay_paths
        st.session_state.image_path_by_name = path_by_name
        st.session_state.manual_overrides = {}
        st.session_state.flip_by_name = {}
        st.session_state.render_cache = {}

df: pd.DataFrame | None = st.session_state.df
overlay_paths: dict[str, Path] = st.session_state.overlay_paths
path_by_name: dict[str, Path] = st.session_state.image_path_by_name


def _display_df() -> pd.DataFrame | None:
    """The measurements table with any manual overrides merged in as extra
    columns, recomputed live each rerun so it always reflects the current
    session state (manual overrides can change without re-running the batch).
    """
    if df is None:
        return None
    out = df.copy()
    overrides = st.session_state.manual_overrides
    out["long_axis_mm_manual"] = out["filename"].map(lambda f: overrides.get(f, {}).get("long"))
    out["short_axis_mm_manual"] = out["filename"].map(lambda f: overrides.get(f, {}).get("short"))
    out["final_long_axis_mm"] = out["long_axis_mm_manual"].combine_first(out["long_axis_mm"])
    out["final_short_axis_mm"] = out["short_axis_mm_manual"].combine_first(out["short_axis_mm"])
    return out


if df is not None:
    ok = df[df["ok"]]
    st.success(f"{len(ok)}/{len(df)} images measured successfully.")

    failed = df[~df["ok"]]
    if len(failed):
        with st.expander(f"{len(failed)} image(s) failed — click to see why"):
            st.dataframe(failed[["filename", "error"]], width="stretch")

    low_conf = ok[ok["low_confidence_calibration"]]
    if len(low_conf):
        st.warning(
            f"{len(low_conf)} image(s) have a low-confidence ruler calibration (fewer than 10 "
            f"ticks found, usually from a tilted/overexposed ruler) — their mm values may be off "
            f"by ~10-20%. Check the overlay and consider measuring these by hand: "
            + ", ".join(low_conf["filename"])
        )

    touching = ok[ok["touches_frame_edge"]]
    if len(touching):
        st.warning(
            f"{len(touching)} image(s) have a specimen mask touching the frame edge — "
            f"worth a visual check for possible cropping: " + ", ".join(touching["filename"])
        )

    low_orient = ok[ok["low_confidence_orientation"].fillna(False)]
    if len(low_orient):
        st.warning(
            f"{len(low_orient)} image(s) have a low-confidence apex/base orientation guess (the "
            f"atria/ventricle split was a close call) — mm values are unaffected, but the overlay "
            f"may show it upside down. Check the overlay below and use the flip checkbox if so: "
            + ", ".join(low_orient["filename"])
        )

    st.subheader("Measurements")
    display_df = _display_df()
    st.caption(
        "`final_long_axis_mm`/`final_short_axis_mm` use your manual measurement (below) when "
        "you've applied one for that image, otherwise the automatic value."
    )
    st.dataframe(display_df, width="stretch")
    st.download_button(
        "Download measurements.csv", display_df.to_csv(index=False).encode(),
        file_name="measurements.csv", mime="text/csv",
    )

    summary = summarize_by_animal_and_view(df)
    if len(summary):
        st.subheader("Summary by animal + view")
        st.caption("Front and back views are always summarized as separate rows, never pooled.")
        st.dataframe(summary, width="stretch")
        st.download_button(
            "Download summary_by_animal_and_view.csv", summary.to_csv(index=False).encode(),
            file_name="summary_by_animal_and_view.csv", mime="text/csv",
        )

    if overlay_paths:
        st.subheader("Overlay viewer + manual correction")
        choice = st.selectbox("Choose an image", sorted(overlay_paths.keys()))
        orig_path = path_by_name[choice]

        flip = st.checkbox(
            "Flip orientation (top/bottom) for this image",
            value=st.session_state.flip_by_name.get(choice, False),
            key=f"flip_cb_{choice}",
        )
        st.session_state.flip_by_name[choice] = flip

        cache_key = (choice, flip)
        if cache_key not in st.session_state.render_cache:
            tmp_dir = Path(tempfile.mkdtemp(prefix="specimen_measure_render_"))
            tmp_overlay = tmp_dir / f"{Path(choice).stem}_overlay.png"
            measure_file(
                orig_path, overlay_path=tmp_overlay, orient_mode=orient_mode,
                use_genotype_colors=use_genotype_colors, manual_flip=flip,
            )
            st.session_state.render_cache[cache_key] = str(tmp_overlay)
        display_path = st.session_state.render_cache[cache_key]
        st.image(display_path, width="stretch")

        with st.expander("Manual measurement (click two points on the image)"):
            st.caption(
                "Use this when the automatic outline/measurement isn't right for this image. "
                "Pick what you're measuring, click one end then the other on the plain image "
                "below, and apply it to override the automatic value for this row."
            )
            manual_which = st.radio(
                "Measuring", ["Length (L)", "Width (W)"], horizontal=True, key=f"manual_mode_{choice}",
            )
            which_key = "long" if manual_which.startswith("Length") else "short"

            try:
                crop, cal = get_rotated_crop(orig_path, orient_mode=orient_mode, manual_flip=flip)
                clean = Image.fromarray(crop.image).convert("RGB")
                draw = ImageDraw.Draw(clean)
                for contour in sk_measure.find_contours(crop.mask.astype(float), 0.5):
                    draw.line([(x, y) for y, x in contour], fill=(0, 255, 0), width=2)

                pts_key = f"manual_pts_{choice}_{which_key}_{flip}"
                last_key = f"manual_last_{choice}_{which_key}_{flip}"
                pts = st.session_state.setdefault(pts_key, [])
                for (px, py) in pts:
                    r = 6
                    draw.ellipse([px - r, py - r, px + r, py + r], outline=(255, 255, 0), width=3)
                if len(pts) == 2:
                    draw.line(pts, fill=(255, 255, 0), width=3)

                coords = streamlit_image_coordinates(clean, key=f"coords_{choice}_{which_key}_{flip}")
                if coords is not None and coords != st.session_state.get(last_key):
                    st.session_state[last_key] = coords
                    pts.append((coords["x"], coords["y"]))
                    if len(pts) > 2:
                        pts[:] = pts[-2:]

                col1, col2 = st.columns(2)
                if col1.button("Clear points", key=f"clear_{choice}_{which_key}"):
                    pts.clear()
                    st.rerun()

                if len(pts) == 2:
                    (x1, y1), (x2, y2) = pts
                    dist_px = float(np.hypot(x2 - x1, y2 - y1))
                    manual_mm = dist_px / cal.px_per_mm
                    st.write(f"Manual {manual_which} distance: **{manual_mm:.2f} mm**")
                    if col2.button(f"Apply as manual {manual_which}", key=f"apply_{choice}_{which_key}"):
                        overrides = st.session_state.manual_overrides.setdefault(choice, {})
                        overrides[which_key] = manual_mm
                        st.success(f"Applied. Row's final_{which_key}_axis_mm now uses this value.")
                else:
                    st.write(f"Click {2 - len(pts)} more point(s).")

                current_overrides = st.session_state.manual_overrides.get(choice, {})
                if current_overrides:
                    st.write("Manual overrides applied to this image:", current_overrides)
                    if st.button("Clear all manual overrides for this image", key=f"clear_override_{choice}"):
                        st.session_state.manual_overrides.pop(choice, None)
                        st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Can't build a manual-measurement canvas for this image: {exc}")

        col_zip, col_pdf = st.columns(2)

        zip_base = Path(tempfile.mkdtemp(prefix="specimen_measure_zip_")) / "overlays"
        zip_path = shutil.make_archive(str(zip_base), "zip", overlay_paths[choice].parent)
        with open(zip_path, "rb") as fh:
            col_zip.download_button(
                "Download all overlay images (.zip)", fh.read(),
                file_name="overlays.zip", mime="application/zip",
            )

        pdf_path = Path(tempfile.mkdtemp(prefix="specimen_measure_pdf_")) / "overlays_combined.pdf"
        build_overlay_pdf(list(overlay_paths.values()), pdf_path)
        with open(pdf_path, "rb") as fh:
            col_pdf.download_button(
                "Download all overlays as one scrollable PDF", fh.read(),
                file_name="overlays_combined.pdf", mime="application/pdf",
            )
