export type User = { id: number; github_id: number; login: string; avatar_url: string | null };

export type Repository = { id: number; owner: string; name: string; description: string | null };

export type Source = { issue_number: number; title: string; state?: string };

export type JobState = {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  attempts: number;
  result: Record<string, unknown> | null;
  error: string | null;
};

export type JobAccepted = { job_id: string; status: string; deduplicated: boolean };

export type InvestigationResult = {
  investigation_id: number;
  status: "answered" | "no_result" | "rejected";
  answer: string;
  sources: Source[];
};

export type FollowUp = {
  id: number;
  status: "answered" | "no_result" | "rejected";
  answer: string;
  citations: Source[];
};

export type PendingAction = {
  id: number;
  tool_name: string;
  args: Record<string, unknown>;
  status: "pending" | "confirmed" | "rejected" | "failed";
  result: string | null;
};
