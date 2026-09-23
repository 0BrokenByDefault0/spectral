/**
 * Hands the analysis from the upload screen to the results screen.
 *
 * sessionStorage rather than a store: the result is one object, it belongs to one tab,
 * and it should survive a refresh of /results without re-uploading the audio. It does
 * not need to outlive the tab, so it is not localStorage.
 */

import type { AnalysisResult } from "./types";

const KEY = "voxchain:result";
const NAME_KEY = "voxchain:filename";

export function storeResult(result: AnalysisResult, filename: string): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(result));
    sessionStorage.setItem(NAME_KEY, filename);
  } catch {
    // Private mode, or a profile too large to store. The results screen will send the
    // user back to upload rather than showing half an analysis.
  }
}

export function loadResult(): { result: AnalysisResult; filename: string } | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    return {
      result: JSON.parse(raw) as AnalysisResult,
      filename: sessionStorage.getItem(NAME_KEY) ?? "your recording",
    };
  } catch {
    return null;
  }
}

export function clearResult(): void {
  try {
    sessionStorage.removeItem(KEY);
    sessionStorage.removeItem(NAME_KEY);
  } catch {
    /* nothing to clear */
  }
}
