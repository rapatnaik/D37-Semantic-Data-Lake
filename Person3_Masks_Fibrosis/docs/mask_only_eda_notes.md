# Mask-only EDA: methods and limitations

- Original TIFF masks were read without alteration.
- All available masks were matched to sample IDs and expected ROI crop dimensions.
- Coverage was calculated as nonzero pixels divided by total mask pixels.
- This is a descriptive stored-value measurement, not fibrosis percentage.
- Two masks use 0/255 encoding: 191007_1_overview and 200219_1_overview.
- The original MATLAB script selects manual-mask pixels using mask == 1.
  It therefore does not select the 255-valued pixels in those two files.
- Nonzero interpretation of the 0/255 masks remains provisional.
- Connected components use 8-neighbor connectivity; no size filtering was applied.
- Component areas are reported in pixels, not physical units.
- Matching crop dimensions does not establish anatomical alignment.
- Native microscopy alignment and WGA thresholding have not been performed.
- All 13 available masks belong to HF samples according to the supplied study mapping.
- Missing masks, including donor masks, do not indicate zero fibrosis.
- No healthy-versus-HF fibrosis comparison can be made from these masks alone.
