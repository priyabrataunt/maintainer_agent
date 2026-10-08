import { errorMessage } from "./format";
import type {
  FollowUp,
  JobAccepted,
  JobState,
  PendingAction,
  Repository,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
    credentials: "same-origin",
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(response.status, body, response.headers.get("Retry-After")));
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown, headers: Record<string, string> = {}) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), headers });

export const getMe = () => request<User>("/me");
export const logout = () => post<void>("/auth/logout");

export const listRepositories = () => request<Repository[]>("/repositories");
export const getRepository = (id: number) => request<Repository>(`/repositories/${id}`);
export const createRepository = (owner: string, name: string) =>
  post<Repository>("/repositories", { owner, name });
export const syncRepository = (id: number, idempotencyKey: string) =>
  post<JobAccepted>(`/repositories/${id}/sync`, undefined, { "Idempotency-Key": idempotencyKey });

export const startInvestigation = (repositoryId: number, question: string, idempotencyKey: string) =>
  post<JobAccepted>(
    "/investigations",
    { repository_id: repositoryId, question },
    { "Idempotency-Key": idempotencyKey },
  );
export const askFollowUp = (investigationId: number, question: string) =>
  post<FollowUp>(`/investigations/${investigationId}/messages`, { question });

export const listActions = (investigationId: number) =>
  request<PendingAction[]>(`/investigations/${investigationId}/actions`);
export const decideAction = (investigationId: number, actionId: number, approve: boolean) =>
  post<PendingAction>(`/investigations/${investigationId}/confirm`, {
    action_id: actionId,
    approve,
  });

/**
 * Follow a job's live status over Server-Sent Events. Calls `onStatus` for each change and
 * resolves with the final job state. The returned `cancel` closes the stream.
 */
export function followJob(
  jobId: string,
  onStatus: (status: JobState["status"], attempts: number) => void,
): { done: Promise<JobState>; cancel: () => void } {
  const source = new EventSource(`/api/jobs/${jobId}/events`);
  const done = new Promise<JobState>((resolve, reject) => {
    source.addEventListener("status", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      onStatus(data.status, data.attempts);
    });
    source.addEventListener("done", (e) => {
      source.close();
      resolve(JSON.parse((e as MessageEvent).data));
    });
    source.addEventListener("timeout", () => {
      source.close();
      reject(new ApiError(504, "This is taking longer than expected. Check back shortly."));
    });
    source.addEventListener("error", (e) => {
      const data = (e as MessageEvent).data;
      if (data) {
        // An application-level error event from the server (e.g. job not found).
        source.close();
        reject(new ApiError(404, JSON.parse(data).detail ?? "Job not found"));
      } else if (source.readyState === EventSource.CLOSED) {
        reject(new ApiError(0, "Lost connection to the server."));
      }
      // Otherwise the browser is retrying a dropped connection by itself.
    });
  });
  return { done, cancel: () => source.close() };
}
