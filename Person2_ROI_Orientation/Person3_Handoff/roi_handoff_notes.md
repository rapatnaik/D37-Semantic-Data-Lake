# Person 2 → Person 3 handoff (PNG-only)

## Scope
- 22 images/ROI/orientation records inventoried; 21 in MATLAB study list.
- 17 passed metadata-only transformed-frame checks; 5 flagged for investigation.
- 22 approximate PNG-based ROI overlays created.
- **No native-resolution LIF data processed. No full-resolution crops created. No fibrosis measurements made.**

## Files
- `roi_coordinates.csv`: original four ROI coordinate pairs (native transformed-image coordinates).
- `roi_validation.csv`: structural and bounds flags; **not** native image verification.
- `roi_geometry.csv`: ROI area and coverage computed from original coordinates/calibration.
- `orientation_metadata.csv`: sample rotation angles.
- `roi_transform_manifest.csv`: MATLAB transform sequence and crop conventions.
- `preview_overlay_index.csv`: preview source and overlay paths.
- `manual_roi_review.csv`: manual sign-off template, **pending by default**.
- `figures/`: area, coverage, orientation plots and approximate overlays.

## Required actions for Person 3
1. Load the original native `.lif` microscopy image and confirm its series/channel interpretation.
2. Reproduce the original MATLAB transform order: vertical flip; -90° bilinear rotation; -orientation angle bilinear rotation with crop mode; apply original ROI coordinates using MATLAB 1-based conventions.
3. Validate ROI bounds in the native transformed image, especially all flagged records. **Do not silently clip or rescale native ROI coordinates.**
4. Establish whether each segmentation mask is in the raw-image, transformed-image, or already-cropped coordinate frame before alignment. Do not automatically transform masks without verifying their frame.
5. Calculate fibrosis only from suitable native quantitative pixels and correctly aligned masks, never from 8-bit display PNG previews.
6. Review overlays and fill in `manual_roi_review.csv` as part of the joint QC sign-off.

## Limits
- Preview PNG images were downsampled and intensity-scaled for display; rotation on PNGs is not pixel-identical to MATLAB on native images.
- The metadata bounds check assumes final rotated frame dimensions are those after the -90° rotation; confirm using native processing and MATLAB reference outputs.
- Study inclusion is taken from `fibrosisAnalysis.m`; the extra inventory sample remains recorded but excluded from study-aligned summaries.
- The MATLAB script may be configured to process only one sample in its loop; verify before bulk use.

## Flagged samples
- `191017_1_overview`: outside_transformed_bounds
- `191125_1_overview`: outside_transformed_bounds
- `200219_1_overview`: outside_transformed_bounds
- `200318_1_overview`: outside_transformed_bounds
- `200318_2_overview`: outside_transformed_bounds
