# Local typography assets

Inter (body and tabular numerals) and Manrope (headings) are bundled for offline use. No font request is sent to Google or another CDN at runtime.

Sources downloaded 14 November 2026:

- Manrope variable font: https://github.com/google/fonts/blob/main/ofl/manrope/Manrope%5Bwght%5D.ttf
- Inter variable font: https://github.com/google/fonts/blob/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf

Original glyph coverage, names and variable axes are retained; the TrueType files were losslessly packaged as WOFF using the already available FontTools tool. FontTools is not a project runtime dependency. Each font's SIL Open Font License 1.1 and author notice are retained alongside the assets. These assets are separately licensed from the MIT application code.
