# WORK_PLAN

## Current Objective
The user requested uploading the current project version to GitHub and rewriting the `README.md` to be a comprehensive, objective, and detailed instruction manual. The new manual must explain how to use the software, detailing every part and button. It must avoid useless adjectives and icons/emojis.

## Diagnosis / Analysis
1. The current `README.md` contains emojis and marketing-style descriptions (e.g., "Spotlight", "Magically masks").
2. The user needs a technical, dry, and precise manual explaining UI elements (e.g., Start, Stop, Auto Search, Delay, Save Dir, bin/win settings, Tagger IP inputs).
3. The project currently has multiple modes: 1TDC, 2TDC, and Virtual Host WLAN D-TDC. All need to be documented objectively.
4. Git commit and push is required post-documentation.

## Proposed Code Changes
1. **`README.md`**: Completely rewrite.
   - Remove all emojis.
   - Use a structured, objective tone.
   - Add a detailed "User Interface Manual" section for both single/dual machines and the Virtual Host setup.
   - Explain buttons: `Connect Devices`, `START/STOP`, `Auto Search`, `Bin`, `Window`, `Save Params`.
2. **Git**:
   - `git add README.md`
   - `git commit -m "docs: rewrite README as an objective detailed instruction manual"`
   - `git push`
