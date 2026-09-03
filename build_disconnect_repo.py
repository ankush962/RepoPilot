#!/usr/bin/env python3
from pathlib import Path

ROOT = Path.home() / "Desktop" / "ai-engineer-copilot"
FRONTEND = ROOT / "frontend" / "app" / "page.jsx"
BACKEND = ROOT / "backend" / "app" / "api" / "repositories.py"

if not FRONTEND.exists():
    raise SystemExit(f"Frontend file not found: {FRONTEND}")
if not BACKEND.exists():
    raise SystemExit(f"Backend file not found: {BACKEND}")

# ---------- backend ----------
b = BACKEND.read_text()

if '@router.delete("/{repository_id}"' not in b:
    anchor = '''@router.get("/{repository_id}", response_model=RepositoryResponse, dependencies=[Depends(require_auth)])
'''
    if anchor not in b:
        raise SystemExit("Could not find repository get_repository anchor in backend/app/api/repositories.py")

    endpoint = '''@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_auth)])
def disconnect_repository(
    repository_id: int,
    db: Session = Depends(get_db),
    owner_username: str | None = Depends(require_auth),
):
    repo = db.get(Repository, repository_id)

    if not repo or repo.owner_username != (owner_username or "anonymous"):
        raise HTTPException(404, "Repository not found")

    active_job = (
        db.query(IndexJob)
        .filter(
            IndexJob.repository_id == repository_id,
            IndexJob.status.in_(["queued", "running"]),
        )
        .first()
    )
    if active_job:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Repository is currently indexing. Wait for indexing to finish before disconnecting it.",
        )

    db.query(IndexJob).filter(
        IndexJob.repository_id == repository_id
    ).delete(synchronize_session=False)

    db.query(CodeChunk).filter(
        CodeChunk.repository_id == repository_id
    ).delete(synchronize_session=False)

    db.delete(repo)
    db.commit()

'''
    b = b.replace(anchor, endpoint + anchor, 1)
    BACKEND.write_text(b)

# ---------- frontend ----------
f = FRONTEND.read_text()

old_api = '''const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\\/$/, "");'''
new_api = '''const API_BASE = "/api";'''
if old_api in f:
    f = f.replace(old_api, new_api, 1)

old_state = '''  const [connectingRepo, setConnectingRepo] = useState(false);
  const [repoError, setRepoError] = useState("");
'''
new_state = '''  const [connectingRepo, setConnectingRepo] = useState(false);
  const [repoError, setRepoError] = useState("");

  const [disconnectTarget, setDisconnectTarget] = useState(null);
  const [disconnectingRepo, setDisconnectingRepo] = useState(false);
  const [disconnectError, setDisconnectError] = useState("");
'''
if old_state not in f:
    raise SystemExit("Could not find repository connection state block")
f = f.replace(old_state, new_state, 1)

anchor = '''  async function indexRepository() {
'''
if "async function disconnectRepository" not in f:
    if anchor not in f:
        raise SystemExit("Could not find indexRepository anchor")

    handler = '''  async function disconnectRepository() {
    const repo = disconnectTarget;

    if (!repo?.id || disconnectingRepo) return;

    setDisconnectingRepo(true);
    setDisconnectError("");

    try {
      if (asking) {
        requestController?.abort();
      }

      const response = await fetch(
        `${API_BASE}/repositories/${repo.id}`,
        {
          method: "DELETE",
          credentials: "include",
          cache: "no-store",
        },
      );

      let data = {};
      try {
        data = await response.json();
      } catch {}

      if (!response.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Unable to disconnect repository.",
        );
      }

      const remaining = repositories.filter(
        (item) => item.id !== repo.id,
      );

      setRepositories(remaining);
      setSelectedRepo((current) =>
        current?.id === repo.id
          ? remaining[0] || null
          : current,
      );

      setDisconnectTarget(null);
      setDisconnectError("");
      shouldAutoScrollRef.current = true;

      if (typeof window !== "undefined") {
        window.localStorage.removeItem(historyKey(repo.id));
        window.sessionStorage.removeItem(
          `repopilot-chat-scroll-${repo.id}`,
        );
      }

      setMessages([]);
      setQuestion("");
      setExpandedSource(null);
      setShowSources({});
      setSourceViewer(null);
      setExplorerFiles([]);
      setExplorerOpenFile(null);
      setExplorerSearch("");
      setDashboard(null);
      setDashboardError("");
      setArchitecture(null);
      setArchitectureError("");
      setGitStatus(null);
      setGitComparison(null);
      setGitCommitSha("");
      setGitCommitInfo(null);
      setPrNumber("");
      setPrResult(null);
      setPrError("");
      setIndexMessage("");
      setChatError("");
      setSuggestedQuestions([
        "What does this project do?",
        "Explain the architecture.",
        "Find potential bugs.",
      ]);
      switchSurface("chat");
    } catch (error) {
      setDisconnectError(
        getErrorMessage(
          error,
          "Unable to disconnect repository.",
        ),
      );
    } finally {
      setDisconnectingRepo(false);
    }
  }

'''
    f = f.replace(anchor, handler + anchor, 1)

old_repo_row = '''            repositories.map((repo) => (
              <button
                key={repo.id}
                type="button"
                onClick={() =>
                  selectRepository(repo)
                }
                className={`group flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left transition ${
                  selectedRepo?.id ===
                  repo.id
                    ? "bg-white/[0.075] text-white"
                    : "text-white/45 hover:bg-white/[0.04] hover:text-white/80"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot(
                    repo.status,
                  )}`}
                />

                <span className="min-w-0 flex-1 truncate text-[12px]">
                  {repo.name}
                </span>

                {repo.status ===
                  "indexed" && (
                  <span className="text-[9px] text-emerald-400/45">
                    ready
                  </span>
                )}
              </button>
            ))
'''
new_repo_row = '''            repositories.map((repo) => (
              <div
                key={repo.id}
                className={`group flex items-center gap-1 rounded-lg transition ${
                  selectedRepo?.id === repo.id
                    ? "bg-white/[0.075]"
                    : "hover:bg-white/[0.04]"
                }`}
              >
                <button
                  type="button"
                  onClick={() => selectRepository(repo)}
                  className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-3 py-2.5 text-left ${
                    selectedRepo?.id === repo.id
                      ? "text-white"
                      : "text-white/45 hover:text-white/80"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot(
                      repo.status,
                    )}`}
                  />

                  <span className="min-w-0 flex-1 truncate text-[12px]">
                    {repo.name}
                  </span>

                  {repo.status === "indexed" && (
                    <span className="text-[9px] text-emerald-400/45">
                      ready
                    </span>
                  )}
                </button>

                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setDisconnectError("");
                    setDisconnectTarget(repo);
                  }}
                  disabled={disconnectingRepo}
                  className="mr-1 hidden shrink-0 rounded-md px-2 py-1.5 text-[9px] text-white/20 transition hover:bg-red-400/[0.08] hover:text-red-300 disabled:opacity-30 group-hover:block"
                  aria-label={`Disconnect ${repo.name}`}
                  title={`Disconnect ${repo.name}`}
                >
                  Disconnect
                </button>
              </div>
            ))
'''
if old_repo_row not in f:
    raise SystemExit("Could not find repository list block")
f = f.replace(old_repo_row, new_repo_row, 1)

old_url_block = '''                  {selectedRepo?.url && (
                    <a
                      href={selectedRepo.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 flex max-w-xl items-center gap-1 truncate text-[10px] text-white/25 hover:text-white/50"
                    >
                      <span className="truncate">
                        {selectedRepo.url}
                      </span>

                      <Icon
                        name="external"
                        className="h-3 w-3 shrink-0"
                      />
                    </a>
                  )}
'''
new_url_block = '''                  <div className="mt-1 flex min-w-0 items-center gap-3">
                    {selectedRepo?.url && (
                      <a
                        href={selectedRepo.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex min-w-0 max-w-xl items-center gap-1 truncate text-[10px] text-white/25 hover:text-white/50"
                      >
                        <span className="truncate">
                          {selectedRepo.url}
                        </span>

                        <Icon
                          name="external"
                          className="h-3 w-3 shrink-0"
                        />
                      </a>
                    )}

                    {selectedRepo && (
                      <button
                        type="button"
                        onClick={() => {
                          setDisconnectError("");
                          setDisconnectTarget(selectedRepo);
                        }}
                        className="shrink-0 text-[9px] text-white/25 transition hover:text-red-300"
                      >
                        Disconnect
                      </button>
                    )}
                  </div>
'''
if old_url_block not in f:
    raise SystemExit("Could not find repository header URL block")
f = f.replace(old_url_block, new_url_block, 1)

modal_anchor = '''      {mobileSidebar && (
'''
if "Disconnect repository?" not in f:
    if modal_anchor not in f:
        raise SystemExit("Could not find modal insertion anchor")

    modal = '''      {disconnectTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 px-4 backdrop-blur-sm">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-white/[0.09] bg-[#101114]">
            <div className="border-b border-white/[0.06] px-5 py-4">
              <div className="text-sm font-semibold">
                Disconnect repository?
              </div>

              <div className="mt-2 text-[10px] leading-5 text-white/35">
                This removes <span className="text-white/60">{disconnectTarget.name}</span>{" "}
                from this workspace and deletes its indexed data.
                The GitHub repository itself will not be changed.
              </div>
            </div>

            {disconnectError && (
              <div className="mx-5 mt-4 rounded-xl border border-red-400/10 bg-red-400/[0.05] px-3 py-2.5 text-[10px] text-red-300/80">
                {disconnectError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 px-5 py-4">
              <button
                type="button"
                onClick={() => {
                  if (!disconnectingRepo) {
                    setDisconnectTarget(null);
                    setDisconnectError("");
                  }
                }}
                disabled={disconnectingRepo}
                className="rounded-lg border border-white/[0.07] px-3 py-2 text-[10px] text-white/40 hover:bg-white/[0.05] hover:text-white disabled:opacity-30"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={disconnectRepository}
                disabled={disconnectingRepo}
                className="flex items-center gap-2 rounded-lg bg-red-400 px-3 py-2 text-[10px] font-semibold text-black hover:bg-red-300 disabled:opacity-50"
              >
                {disconnectingRepo && (
                  <span className="h-3 w-3 animate-spin rounded-full border border-black/20 border-t-black" />
                )}
                {disconnectingRepo
                  ? "Disconnecting…"
                  : "Disconnect repository"}
              </button>
            </div>
          </div>
        </div>
      )}

'''
    f = f.replace(modal_anchor, modal + modal_anchor, 1)

FRONTEND.write_text(f)
print("RepoPilot disconnect feature patched successfully.")
print(FRONTEND)
print(BACKEND)
