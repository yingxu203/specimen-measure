"""heart-measure UI: a point-and-click front end for the batch measurement
pipeline, so anyone in the lab can run it without touching a command line.

Launch with:
    streamlit run app.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from heart_measure.cli import DEFAULT_PATTERN, find_images, summarize_by_animal_and_view
from heart_measure.measure import measure_file

st.set_page_config(page_title="heart-measure", layout="wide")

if "df" not in st.session_state:
    st.session_state.df = None
if "overlay_paths" not in st.session_state:
    st.session_state.overlay_paths = {}

st.title("heart-measure")
st.caption(
    "Ruler-calibrated long-axis / short-axis / area measurement for heart specimen photos. "
    "Long axis (**L**) and short axis (**W**) are colored by genotype — "
    "**red** for OX/OF/OM animals, **blue** for WT/WF/WM animals. "
    "Each overlay is rotated so the long axis is horizontal, for easy side-by-side comparison. "
    "Front and back photos of the same animal are always measured and summarized separately, never averaged together."
)

mode = st.radio("Where are your photos?", ["Upload photos", "Local folder path"], horizontal=True)

image_paths: list[Path] = []

if mode == "Upload photos":
    uploaded = st.file_uploader(
        "Drag and drop TIFF photos here (you can select many at once)",
        type=["tif", "tiff"], accept_multiple_files=True,
    )
    if uploaded:
        upload_dir = Path(tempfile.mkdtemp(prefix="heart_measure_upload_"))
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
        overlay_dir = Path(tempfile.mkdtemp(prefix="heart_measure_overlays_"))
        rows = []
        overlay_paths: dict[str, Path] = {}
        progress = st.progress(0.0, text="Starting...")
        for i, path in enumerate(image_paths):
            overlay_path = overlay_dir / f"{path.stem}_overlay.png"
            result = measure_file(path, overlay_path=overlay_path)
            rows.append(result.to_row())
            if overlay_path.exists():
                overlay_paths[path.name] = overlay_path
            progress.progress((i + 1) / len(image_paths), text=path.name)
        progress.empty()
        st.session_state.df = pd.DataFrame(rows)
        st.session_state.overlay_paths = overlay_paths

df: pd.DataFrame | None = st.session_state.df
overlay_paths: dict[str, Path] = st.session_state.overlay_paths

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
            f"{len(touching)} image(s) have a heart mask touching the frame edge — "
            f"worth a visual check for possible cropping: " + ", ".join(touching["filename"])
        )

    st.subheader("Measurements")
    st.dataframe(df, width="stretch")
    st.download_button(
        "Download measurements.csv", df.to_csv(index=False).encode(),
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
        st.subheader("Overlay viewer")
        choice = st.selectbox("Choose an image", sorted(overlay_paths.keys()))
        st.image(str(overlay_paths[choice]), width="stretch")

        zip_base = Path(tempfile.mkdtemp(prefix="heart_measure_zip_")) / "overlays"
        zip_path = shutil.make_archive(str(zip_base), "zip", overlay_paths[choice].parent)
        with open(zip_path, "rb") as fh:
            st.download_button(
                "Download all overlay images (.zip)", fh.read(),
                file_name="overlays.zip", mime="application/zip",
            )
