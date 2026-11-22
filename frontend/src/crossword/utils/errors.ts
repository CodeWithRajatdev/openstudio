/** Translate technical/HTTP error text into plain user-friendly messages. */
export function toPlainLanguageError(err: unknown, fallback = "Something went wrong. Please try again."): string {
  const raw = err instanceof Error ? err.message : typeof err === "string" ? err : "";
  const cleaned = raw.trim();
  if (!cleaned) return fallback;

  if (/Failed to fetch|NetworkError|Load failed/i.test(cleaned)) {
    return "Could not reach the Woodpecker Studio backend server. Make sure the backend is running and try again.";
  }
  if (/^HTTP\s+\d+$/i.test(cleaned)) {
    return fallback;
  }
  // Strip noisy leading "HTTP 4xx:" or python class prefixes if any
  return cleaned.replace(/^HTTP\s*\d+\s*[:-]\s*/i, "").replace(/^[A-Za-z]+Error:\s*/, "");
}
