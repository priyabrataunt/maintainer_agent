import { describe, expect, it } from "vitest";
import { describeStatus, errorMessage, issueUrl, outcomeNote, retryAfterSeconds } from "./format";

describe("describeStatus", () => {
  it("explains each phase", () => {
    expect(describeStatus("queued", 0)).toBe("Queued…");
    expect(describeStatus("running", 1)).toContain("Searching issues");
    expect(describeStatus("succeeded", 1)).toBe("Done");
    expect(describeStatus("failed", 3)).toBe("Failed");
  });

  it("shows retries to the user", () => {
    expect(describeStatus("queued", 2)).toBe("Waiting to retry (attempt 2)…");
    expect(describeStatus("running", 2)).toBe("Working (attempt 2)…");
  });
});

describe("issueUrl", () => {
  it("builds a GitHub link and escapes path parts", () => {
    expect(issueUrl("octo", "demo", 5)).toBe("https://github.com/octo/demo/issues/5");
    expect(issueUrl("a b", "c/d", 1)).toBe("https://github.com/a%20b/c%2Fd/issues/1");
  });
});

describe("retryAfterSeconds", () => {
  it("parses a valid header", () => expect(retryAfterSeconds("45")).toBe(45));
  it("falls back for missing or bad values", () => {
    expect(retryAfterSeconds(null)).toBe(30);
    expect(retryAfterSeconds("soon")).toBe(30);
    expect(retryAfterSeconds("0")).toBe(30);
    expect(retryAfterSeconds("-5")).toBe(30);
  });
});

describe("errorMessage", () => {
  it("asks for login on 401", () => expect(errorMessage(401, null, null)).toMatch(/log in/i));
  it("tells the user how long to wait on 429", () =>
    expect(errorMessage(429, { detail: "Queue is full" }, "12")).toBe(
      "The server is busy. Try again in 12s.",
    ));
  it("uses the server's detail string", () =>
    expect(errorMessage(403, { detail: "You do not own or administer a/b" }, null)).toBe(
      "You do not own or administer a/b",
    ));
  it("flattens FastAPI validation errors", () =>
    expect(
      errorMessage(422, { detail: [{ msg: "String should have at least 1 character" }] }, null),
    ).toBe("String should have at least 1 character"));
  it("never shows raw objects", () => {
    expect(errorMessage(500, { detail: { weird: true } }, null)).toBe("Request failed (500).");
    expect(errorMessage(502, null, null)).toBe("Request failed (502).");
  });
});

describe("outcomeNote", () => {
  it("only annotates non-answers", () => {
    expect(outcomeNote("answered")).toBeNull();
    expect(outcomeNote("no_result")).toMatch(/No relevant issues/);
    expect(outcomeNote("rejected")).toMatch(/withheld/);
  });
});
