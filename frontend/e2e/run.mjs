// Browser end-to-end test. Real: Next.js, FastAPI, Postgres, Redis, RQ worker, SSE, cookies.
// Faked: the LLM and GitHub (see fakes.py). Usage: node e2e/run.mjs <jwt> <repoId>
import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";

const [jwt, repoId] = process.argv.slice(2);
const BASE = "http://localhost:3000";
const failures = [];
let checks = 0;

function check(name, ok, detail = "") {
  checks += 1;
  if (!ok) failures.push(`${name}${detail ? ` -> ${detail}` : ""}`);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : detail ? `  (${detail})` : ""}`);
}

const seed = (...args) =>
  execFileSync("uv", ["run", "python", "frontend/e2e/seed.py", ...args], { cwd: "..", stdio: "pipe" });

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const context = await browser.newContext();
const page = await context.newPage();
const consoleErrors = [];
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
page.on("pageerror", (e) => consoleErrors.push(String(e)));

try {
  // --- logged out ---
  await page.goto(BASE);
  await page.getByRole("link", { name: "Log in with GitHub" }).first().waitFor();
  check("logged out: home offers GitHub login", true);
  await page.goto(`${BASE}/repos`);
  await page.getByText("Log in to see your repositories.").waitFor();
  check("logged out: /repos asks to log in", true);
  const loginHref = await page.getByRole("link", { name: "Log in with GitHub" }).first().getAttribute("href");
  check("login button points at the proxied backend route", loginHref === "/api/auth/login", loginHref);

  // --- log in with a genuinely signed cookie ---
  await context.addCookies([
    { name: "access_token", value: jwt, domain: "localhost", path: "/", httpOnly: true, sameSite: "Lax" },
  ]);
  await page.goto(`${BASE}/repos`);
  await page.getByTestId("login").waitFor();
  check("logged in: user bar shows the login", (await page.getByTestId("login").innerText()) === "e2e-octocat");
  await page.getByTestId(`repo-${repoId}`).waitFor();
  check("repo list shows the seeded repository", (await page.getByTestId(`repo-${repoId}`).innerText()).includes("e2e/demo"));

  // --- add a repository (and a duplicate) ---
  await page.getByLabel("Owner").fill("e2e");
  await page.getByLabel("Name").fill("added-by-ui");
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByText("e2e/added-by-ui").waitFor();
  check("adding a repository lists it", true);
  await page.getByLabel("Owner").fill("e2e");
  await page.getByLabel("Name").fill("added-by-ui");
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByRole("alert").getByText("Repository already exists").waitFor();
  check("duplicate repository shows the server's message", true);

  // --- sync job with live status ---
  await page.getByTestId(`repo-${repoId}`).getByRole("button", { name: "Sync" }).click();
  await page.getByTestId(`repo-${repoId}`).getByText(/Synced 2 issues/).waitFor({ timeout: 30000 });
  check("sync job runs on the worker and reports its result", true);

  // --- chat: first question, with SSE progress captured ---
  await page.getByTestId(`repo-${repoId}`).getByRole("link", { name: "Ask questions" }).click();
  await page.getByRole("heading", { name: "e2e/demo" }).waitFor();
  await page.evaluate(() => {
    window.__progress = [];
    const el = document.querySelector('[data-testid="progress"]');
    new MutationObserver(() => el.textContent && window.__progress.push(el.textContent))
      .observe(el, { childList: true, characterData: true, subtree: true });
  });
  check("ask button is disabled while the box is empty", await page.getByRole("button", { name: "Ask" }).isDisabled());
  await page.getByLabel("Your question").fill("why does the app crash on startup");
  await page.getByRole("button", { name: "Ask" }).click();
  await page.getByTestId("turn-assistant").first().waitFor({ timeout: 30000 });
  const answer = await page.getByTestId("turn-assistant").first().innerText();
  check("assistant answer cites the right issue", answer.includes("[#1]"), answer);
  const progress = await page.evaluate(() => window.__progress);
  console.log(`      progress seen: ${JSON.stringify([...new Set(progress)])}`);
  // "Queued…" is set by the page itself; this phrase can only arrive via the SSE stream.
  check("live status from the server arrived over SSE through the proxy",
    progress.includes("Searching issues and writing an answer…"), JSON.stringify(progress));
  const sources = page.getByTestId("sources");
  await sources.waitFor();
  check("sources panel lists the cited issue", (await sources.innerText()).includes("#1 Crash on startup"));
  const href = await sources.getByRole("link").first().getAttribute("href");
  check("source links to the GitHub issue", href === "https://github.com/e2e/demo/issues/1", href);
  check("follow-up label replaces the first-question label",
    await page.getByLabel("Ask a follow-up").isVisible());

  // --- follow-up (synchronous endpoint) ---
  await page.getByLabel("Ask a follow-up").fill("what about the dark theme request");
  await page.getByRole("button", { name: "Ask" }).click();
  await page.getByTestId("turn-assistant").nth(1).waitFor({ timeout: 30000 });
  check("follow-up answer cites the second issue",
    (await page.getByTestId("turn-assistant").nth(1).innerText()).includes("[#2]"));
  check("sources panel accumulates", (await sources.innerText()).includes("#2 Add dark mode"));
  check("follow-up sources carry their state badge too", (await sources.innerText()).includes("closed"));

  // --- proposed changes: approve and reject ---
  seed("action", "close_issue", "1");
  seed("action", "add_label", "2");
  await page.getByLabel("Ask a follow-up").fill("anything else about the crash on startup");
  await page.getByRole("button", { name: "Ask" }).click();
  const actions = page.getByTestId("actions");
  await actions.waitFor({ timeout: 30000 });
  check("proposed changes appear with approve/reject", (await actions.getByRole("button", { name: "Approve" }).count()) === 2);
  await actions.getByRole("listitem").filter({ hasText: "close_issue" }).getByRole("button", { name: "Approve" }).click();
  await actions.getByRole("listitem").filter({ hasText: "close_issue" }).getByText("confirmed").waitFor();
  check("approving runs the action and shows 'confirmed'", true);
  await actions.getByRole("listitem").filter({ hasText: "add_label" }).getByRole("button", { name: "Reject" }).click();
  await actions.getByRole("listitem").filter({ hasText: "add_label" }).getByText("rejected").waitFor();
  check("rejecting shows 'rejected' and removes the buttons",
    (await actions.getByRole("button", { name: "Approve" }).count()) === 0);

  await page.screenshot({ path: "/tmp/e2e-chat.png", fullPage: true });

  // --- layout: phone width and dark mode ---
  await page.setViewportSize({ width: 375, height: 800 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check("chat page has no horizontal scroll at phone width", overflow <= 0, `${overflow}px overflow`);
  await page.screenshot({ path: "/tmp/e2e-chat-mobile.png", fullPage: true });
  await page.goto(`${BASE}/repos`);
  await page.getByTestId(`repo-${repoId}`).waitFor();
  const reposOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check("repo list has no horizontal scroll at phone width", reposOverflow <= 0, `${reposOverflow}px overflow`);
  await page.setViewportSize({ width: 1280, height: 800 });
  const lightBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.emulateMedia({ colorScheme: "dark" });
  const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check("dark mode changes the page colours", lightBg !== darkBg, `${lightBg} vs ${darkBg}`);
  await page.screenshot({ path: "/tmp/e2e-dark.png", fullPage: true });
  await page.emulateMedia({ colorScheme: "light" });

  // --- logout ---
  await page.getByRole("button", { name: "Log out" }).click();
  await page.getByRole("link", { name: "Log in with GitHub" }).first().waitFor();
  check("logging out returns to the login state", true);
  await page.goto(`${BASE}/repos`);
  await page.getByText("Log in to see your repositories.").waitFor();
  check("after logout the browser no longer holds a session cookie",
    !(await context.cookies()).some((c) => c.name === "access_token"));

  const relevant = consoleErrors.filter((e) => !/401|Failed to load resource/.test(e));
  check("no unexpected browser console errors", relevant.length === 0, relevant.join(" | "));
} catch (e) {
  failures.push(`script error: ${e.message}`);
  console.log(`ERROR ${e.message}`);
  await page.screenshot({ path: "/tmp/e2e-failure.png", fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}

console.log(`\n${checks - failures.length}/${checks} checks passed`);
process.exit(failures.length ? 1 : 0);
