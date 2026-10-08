import type { JobState } from "./types";

/** Human-readable progress line for a job status event. */
export function describeStatus(status: JobState["status"], attempts: number): string {
  switch (status) {
    case "queued":
      return attempts > 1 ? `Waiting to retry (attempt ${attempts})…` : "Queued…";
    case "running":
      return attempts > 1 ? `Working (attempt ${attempts})…` : "Searching issues and writing an answer…";
    case "succeeded":
      return "Done";
    case "failed":
      return "Failed";
  }
}

export function issueUrl(owner: string, name: string, number: number): string {
  return `https://github.com/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/issues/${number}`;
}

/** Seconds to wait from a Retry-After header, falling back to a default. */
export function retryAfterSeconds(header: string | null, fallback = 30): number {
  const parsed = header === null ? NaN : Number.parseInt(header, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

/** The text to show for a non-2xx API response; FastAPI errors carry {detail}. */
export function errorMessage(status: number, body: unknown, retryAfter: string | null): string {
  if (status === 401) return "Please log in to continue.";
  if (status === 429) return `The server is busy. Try again in ${retryAfterSeconds(retryAfter)}s.`;
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : ""))
      .filter(Boolean)
      .join("; ") || `Request failed (${status}).`;
  }
  return `Request failed (${status}).`;
}

/** How an assistant turn should be labelled in the transcript. */
export function outcomeNote(status: string): string | null {
  switch (status) {
    case "no_result":
      return "No relevant issues were found for this question.";
    case "rejected":
      return "The answer was withheld because it cited issues that were not retrieved.";
    default:
      return null;
  }
}
