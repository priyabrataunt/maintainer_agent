import { issueUrl } from "@/lib/format";
import type { Repository, Source } from "@/lib/types";

export default function SourcesPanel({
  repo,
  sources,
}: {
  repo: Repository | null;
  sources: Source[];
}) {
  return (
    <section className="card" aria-labelledby="sources-title">
      <h2 id="sources-title">Sources</h2>
      {sources.length === 0 ? (
        <p className="muted">Issues cited in answers appear here.</p>
      ) : (
        <ul className="plain" data-testid="sources">
          {sources.map((s) => (
            <li key={s.issue_number}>
              {repo ? (
                <a href={issueUrl(repo.owner, repo.name, s.issue_number)} target="_blank" rel="noreferrer">
                  #{s.issue_number} {s.title}
                </a>
              ) : (
                <span>
                  #{s.issue_number} {s.title}
                </span>
              )}
              {s.state ? <span className="badge">{s.state}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
