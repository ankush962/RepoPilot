"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const QUICK_PROMPTS = [
  ["Project overview", "What does this project do?", "✦"],
  ["Backend architecture", "Explain the backend architecture.", "⌘"],
  ["Indexing flow", "Where is repository indexing implemented?", "↗"],
  ["Find weak points", "Find potential bugs or weak points.", "◇"],
  ["Semantic search", "How does semantic search work?", "◎"],
  ["Embeddings", "How are embeddings generated and stored?", "∿"],
];

function Icon({ name, className = "" }) {
  const common = {
    className: `h-4 w-4 ${className}`,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.8",
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };

  const paths = {
    plus: (
      <>
        <path d="M12 5v14" />
        <path d="M5 12h14" />
      </>
    ),

    close: (
      <>
        <path d="M6 6l12 12" />
        <path d="M18 6 6 18" />
      </>
    ),

    refresh: (
      <>
        <path d="M20 11a8 8 0 0 0-14.7-4L4 9" />
        <path d="M4 4v5h5" />
        <path d="M4 13a8 8 0 0 0 14.7 4L20 15" />
        <path d="M20 20v-5h-5" />
      </>
    ),

    external: (
      <>
        <path d="M14 4h6v6" />
        <path d="M20 4l-9 9" />
        <path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" />
      </>
    ),

    arrow: (
      <>
        <path d="M5 12h13" />
        <path d="m13 6 6 6-6 6" />
      </>
    ),

    chevron: <path d="m6 9 6 6 6-6" />,

    stop: <rect x="7" y="7" width="10" height="10" rx="1.5" />,
  };

  return <svg {...common}>{paths[name]}</svg>;
}

function formatAnswer(text) {
  return String(text)
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/\*\*Answer:\*\*\s*/i, "")
    .trim();
}

function getErrorMessage(error, fallback) {
  if (error?.name === "AbortError") {
    return "Request cancelled.";
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

function statusText(status) {
  if (status === "indexed") return "Indexed";
  if (status === "indexing") return "Indexing";
  if (status === "error") return "Error";
  return "Not indexed";
}

function statusDot(status) {
  if (status === "indexed") return "bg-emerald-400";
  if (status === "indexing") return "bg-amber-400 animate-pulse";
  if (status === "error") return "bg-red-400";
  return "bg-white/20";
}

function fileType(path = "") {
  const ext = path.split(".").pop()?.toUpperCase();
  return ext && ext.length <= 6 ? ext : "CODE";
}

function SourceCard({ source, expanded, onToggle, onOpen }) {
  const path = source?.file_path || "Unknown file";

  const similarity =
    typeof source?.similarity === "number"
      ? `${Math.round(source.similarity * 100)}%`
      : null;

  const startLine = source?.start_line ?? "?";
  const endLine = source?.end_line ?? "?";

  const why =
    typeof source?.similarity === "number"
      ? source.similarity >= 0.7
        ? "Strong semantic match for this question."
        : source.similarity >= 0.5
          ? "Relevant repository evidence selected for this answer."
          : "Supporting evidence with a weaker semantic match."
      : "Repository evidence used to support this answer.";

  return (
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.018]">
      <div className="flex items-stretch">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2.5 text-left transition hover:bg-white/[0.035]"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/[0.05] text-[8px] font-semibold text-white/35">
            {fileType(path)}
          </span>

          <span className="min-w-0 flex-1">
            <span className="block truncate text-[11px] font-medium text-white/65">
              {path}
            </span>

            <span className="mt-0.5 block text-[9px] text-white/25">
              Lines {startLine}–{endLine}
              {similarity ? ` · ${similarity} match` : ""}
            </span>
          </span>

          <span className="text-[9px] text-white/20">
            {expanded ? "Hide" : "Preview"}
          </span>
        </button>

        <button
          type="button"
          onClick={() => onOpen(source)}
          className="shrink-0 border-l border-white/[0.06] px-3 text-[9px] font-medium text-white/30 transition hover:bg-white/[0.04] hover:text-white/70"
        >
          Open
        </button>
      </div>

      {expanded && (
        <div className="border-t border-white/[0.05]">
          {source?.content && (
            <pre className="max-h-64 overflow-auto bg-black/30 p-3 text-[10px] leading-5 text-white/50">
              <code>{source.content}</code>
            </pre>
          )}

          <div className="border-t border-white/[0.05] px-3 py-2.5">
            <div className="text-[9px] font-semibold uppercase tracking-[0.15em] text-white/20">
              Why this source?
            </div>

            <div className="mt-1 text-[10px] leading-5 text-white/30">
              {why}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MessageMetrics({ metrics }) {
  if (!metrics) return null;

  const parts = [];

  if (typeof metrics.sources === "number") {
    parts.push(`${metrics.sources} sources`);
  }

  if (typeof metrics.top_similarity === "number") {
    parts.push(`${Math.round(metrics.top_similarity * 100)}% top match`);
  }

  if (typeof metrics.latency_seconds === "number") {
    parts.push(`${metrics.latency_seconds.toFixed(1)}s`);
  }

  if (metrics.grounding) {
    parts.push(metrics.grounding);
  }

  if (!parts.length) return null;

  return (
    <div className="mt-3 text-[9px] text-white/20">
      {parts.join("  ·  ")}
    </div>
  );
}

function historyKey(repoId) {
  return `repopilot-conversation-${repoId}`;
}

function loadConversationHistory(repoId) {
  if (!repoId || typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(historyKey(repoId));

    if (!raw) return [];

    const parsed = JSON.parse(raw);

    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveConversationHistory(repoId, messages) {
  if (!repoId || typeof window === "undefined") return;

  try {
    window.localStorage.setItem(
      historyKey(repoId),
      JSON.stringify(messages),
    );
  } catch {}
}

function buildSuggestedQuestions(prompt, answer) {
  const text = `${prompt} ${answer}`.toLowerCase();

  if (text.includes("architecture") || text.includes("request flow")) {
    return [
      "Which files are the core architectural components?",
      "How does a request move through the backend?",
      "What part of the architecture is most complex?",
    ];
  }

  if (
    text.includes("bug") ||
    text.includes("error") ||
    text.includes("weakness")
  ) {
    return [
      "Which issue is the highest priority?",
      "How would you fix the most serious issue?",
      "Are there tests covering this behavior?",
    ];
  }

  if (
    text.includes("index") ||
    text.includes("embedding") ||
    text.includes("vector")
  ) {
    return [
      "How does incremental indexing work?",
      "Where are embeddings generated?",
      "How does retrieval rank the chunks?",
    ];
  }

  if (
    text.includes("workspace") ||
    text.includes("member") ||
    text.includes("team")
  ) {
    return [
      "Who has access to this workspace?",
      "How are repository permissions enforced?",
      "How do workspace roles work?",
    ];
  }

  return [
    "What are the most important files in this project?",
    "What potential risks should I investigate?",
    "How could this codebase be improved?",
  ];
}

function isNearBottom(element) {
  const threshold = 120;

  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <
    threshold
  );
}

function RepositoryDashboard({ dashboard, loading, error, onRefresh }) {
  if (loading && !dashboard) {
    return (
      <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.018] p-4">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 animate-pulse rounded-full bg-white/40" />
          <span className="text-[10px] text-white/30">
            Loading repository dashboard...
          </span>
        </div>
      </div>
    );
  }

  if (error && !dashboard) {
    return (
      <div className="mt-4 rounded-2xl border border-red-400/10 bg-red-400/[0.03] p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[10px] text-red-300/70">{error}</span>

          <button
            type="button"
            onClick={onRefresh}
            className="rounded-lg border border-red-300/10 px-3 py-1.5 text-[9px] text-red-200 hover:bg-red-300/[0.06]"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!dashboard) return null;

  const repository = dashboard.repository || {};
  const statistics = dashboard.statistics || {};
  const health = dashboard.health || {};
  const latestJob = dashboard.latest_job || null;

  const history = Array.isArray(dashboard.indexing_history)
    ? dashboard.indexing_history
    : [];

  const healthLabel =
    {
      healthy: "Healthy",
      outdated: "Outdated",
      indexing: "Indexing",
      empty: "Empty",
      error: "Error",
    }[health.status] || "Unknown";

  const healthClass =
    health.status === "healthy"
      ? "text-emerald-300 bg-emerald-400/[0.07] border-emerald-400/10"
      : health.status === "error"
        ? "text-red-300 bg-red-400/[0.07] border-red-400/10"
        : "text-amber-300 bg-amber-400/[0.07] border-amber-400/10";

  const formatDate = (value) => {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  };

  const shortCommit = repository.last_indexed_commit
    ? repository.last_indexed_commit.slice(0, 12)
    : "—";

  return (
    <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.018]">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3 sm:px-5">
        <div>
          <div className="text-[11px] font-semibold text-white/70">
            Repository dashboard
          </div>

          <div className="mt-0.5 text-[9px] text-white/25">
            {repository.name || "Repository"}
            {repository.branch ? ` · ${repository.branch}` : ""}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div
            className={`rounded-full border px-2 py-1 text-[9px] ${healthClass}`}
          >
            {healthLabel}
          </div>

          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="rounded-lg border border-white/[0.07] p-1.5 text-white/35 hover:bg-white/[0.05] hover:text-white disabled:opacity-30"
          >
            <Icon
              name="refresh"
              className={loading ? "animate-spin" : ""}
            />
          </button>
        </div>
      </div>

      <div className="grid gap-2 p-4 sm:grid-cols-2 lg:grid-cols-4 sm:p-5">
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
          <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
            Files indexed
          </div>
          <div className="mt-2 text-xl font-semibold text-white/85">
            {statistics.files_indexed ?? 0}
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
          <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
            Total chunks
          </div>
          <div className="mt-2 text-xl font-semibold text-white/85">
            {statistics.total_chunks ?? 0}
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
          <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
            Embeddings
          </div>

          <div className="mt-2 text-xl font-semibold text-white/85">
            {statistics.embedded_chunks ?? 0}
            <span className="ml-1 text-xs font-normal text-white/25">
              / {statistics.total_chunks ?? 0}
            </span>
          </div>

          <div className="mt-1 text-[9px] text-white/25">
            {statistics.embedding_status || "not_started"}
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
          <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
            Last indexed commit
          </div>

          <div className="mt-2 font-mono text-sm text-white/70">
            {shortCommit}
          </div>
        </div>
      </div>

      <div className="grid gap-4 border-t border-white/[0.06] p-4 sm:p-5 lg:grid-cols-2">
        <div>
          <div className="mb-2 text-[9px] font-semibold uppercase tracking-[0.15em] text-white/25">
            Repository health
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-white/55">Index ready</span>
              <span
                className={
                  health.index_ready
                    ? "text-[10px] text-emerald-300/70"
                    : "text-[10px] text-amber-300/70"
                }
              >
                {health.index_ready ? "Yes" : "No"}
              </span>
            </div>

            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-white/55">Needs update</span>
              <span
                className={
                  health.needs_update
                    ? "text-[10px] text-amber-300/70"
                    : "text-[10px] text-emerald-300/70"
                }
              >
                {health.needs_update ? "Yes" : "No"}
              </span>
            </div>

            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-white/55">
                Repository status
              </span>
              <span className="text-[10px] text-white/35">
                {repository.status || "unknown"}
              </span>
            </div>
          </div>
        </div>

        <div>
          <div className="mb-2 text-[9px] font-semibold uppercase tracking-[0.15em] text-white/25">
            Latest indexing job
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
            {latestJob ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-white/55">
                    Job #{latestJob.id}
                  </span>

                  <span className="text-[10px] text-white/35">
                    {latestJob.status}
                  </span>
                </div>

                <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.05]">
                  <div
                    className="h-full rounded-full bg-white/35"
                    style={{
                      width: `${Math.max(
                        0,
                        Math.min(100, latestJob.progress ?? 0),
                      )}%`,
                    }}
                  />
                </div>

                <div className="mt-2 text-[9px] text-white/25">
                  {latestJob.stage || "—"} ·{" "}
                  {latestJob.result_chunks ?? 0} chunks ·{" "}
                  {latestJob.result_vectors ?? 0} vectors
                </div>
              </>
            ) : (
              <div className="text-[10px] text-white/25">
                No indexing jobs yet.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-white/[0.06] px-4 py-4 sm:px-5">
        <div className="mb-2 text-[9px] font-semibold uppercase tracking-[0.15em] text-white/25">
          Indexing history
        </div>

        {history.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/[0.06] px-3 py-4 text-[10px] text-white/25">
            No indexing history.
          </div>
        ) : (
          <div className="space-y-1.5">
            {history.map((job) => (
              <div
                key={job.id}
                className="flex flex-col gap-2 rounded-xl border border-white/[0.05] bg-white/[0.015] px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <div className="text-[10px] text-white/50">
                    Job #{job.id} · {job.stage || job.status}
                  </div>

                  <div className="mt-0.5 text-[9px] text-white/20">
                    {formatDate(job.created_at)}
                  </div>
                </div>

                <div className="flex items-center gap-3 text-[9px] text-white/25">
                  <span>{job.result_chunks ?? 0} chunks</span>
                  <span>{job.result_vectors ?? 0} vectors</span>
                  <span
                    className={
                      job.status === "completed"
                        ? "text-emerald-300/60"
                        : job.status === "failed"
                          ? "text-red-300/60"
                          : "text-amber-300/60"
                    }
                  >
                    {job.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ExplorerFileViewer({ repositoryId, filePath, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadFile() {
      setLoading(true);
      setError("");

      try {
        const params = new URLSearchParams({
          path: filePath,
        });

        const response = await fetch(
          `${API_BASE}/repositories/${repositoryId}/files/source?${params.toString()}`,
          {
            credentials: "include",
            cache: "no-store",
          },
        );

        let result = {};

        try {
          result = await response.json();
        } catch {}

        if (!response.ok) {
          throw new Error(
            typeof result?.detail === "string"
              ? result.detail
              : "Unable to load source file.",
          );
        }

        if (!cancelled) {
          setData(result);
        }
      } catch (error) {
        if (!cancelled) {
          setError(
            getErrorMessage(error, "Unable to load source file."),
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadFile();

    return () => {
      cancelled = true;
    };
  }, [repositoryId, filePath]);

  if (loading) {
    return (
      <div className="flex h-full min-h-[360px] items-center justify-center">
        <div className="text-[10px] text-white/25">
          Loading {filePath}...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-5">
        <div className="text-[10px] text-red-300/70">{error}</div>

        <button
          type="button"
          onClick={onClose}
          className="mt-3 rounded-lg border border-white/[0.07] px-3 py-1.5 text-[9px] text-white/40 hover:bg-white/[0.05] hover:text-white"
        >
          Close
        </button>
      </div>
    );
  }

  const content = data?.content || "";

  return (
    <div className="flex h-full min-h-[360px] flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-4 py-2.5">
        <div className="min-w-0">
          <div className="truncate font-mono text-[10px] text-white/55">
            {filePath}
          </div>
          <div className="mt-0.5 text-[9px] text-white/20">
            {data?.total_lines ?? 0} lines
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-white/[0.07] px-2.5 py-1.5 text-[9px] text-white/35 hover:bg-white/[0.05] hover:text-white"
        >
          Close
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-[#090a0c]">
        <div className="min-w-max p-4 font-mono text-[11px] leading-6">
          {content.split("\n").map((line, index) => (
            <div key={index} className="flex">
              <span className="w-14 shrink-0 select-none pr-4 text-right text-white/15">
                {index + 1}
              </span>

              <code className="whitespace-pre text-white/45">
                {line || " "}
              </code>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [workspaces, setWorkspaces] = useState([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState(null);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);
  const [workspaceError, setWorkspaceError] = useState("");

  const [repositories, setRepositories] = useState([]);
  const [selectedRepo, setSelectedRepo] = useState(null);

  const [loadingRepos, setLoadingRepos] = useState(true);
  const [repoLoadError, setRepoLoadError] = useState("");

  const [indexing, setIndexing] = useState(false);
  const [indexMessage, setIndexMessage] = useState("");
  const [indexStage, setIndexStage] = useState("Preparing repository...");

  const [showNewRepo, setShowNewRepo] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [repoBranch, setRepoBranch] = useState("main");
  const [connectingRepo, setConnectingRepo] = useState(false);
  const [repoError, setRepoError] = useState("");

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [chatStage, setChatStage] = useState(
    "Searching indexed code...",
  );
  const [chatError, setChatError] = useState("");

  const [messages, setMessages] = useState([]);

  const [suggestedQuestions, setSuggestedQuestions] = useState([
    "What is the main architecture of this project?",
    "Where is the most important backend logic?",
    "What potential bugs should I investigate?",
  ]);

  const [mobileSidebar, setMobileSidebar] = useState(false);

  const [expandedSource, setExpandedSource] = useState(null);
  const [showSources, setShowSources] = useState({});

  const [sourceViewer, setSourceViewer] = useState(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState("");

  const [showExplorer, setShowExplorer] = useState(false);
  const [explorerFiles, setExplorerFiles] = useState([]);
  const [explorerSearch, setExplorerSearch] = useState("");
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [explorerError, setExplorerError] = useState("");
  const [explorerOpenFile, setExplorerOpenFile] = useState(null);

  const [dashboard, setDashboard] = useState(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [dashboardError, setDashboardError] = useState("");
  const [showDashboard, setShowDashboard] = useState(true);

  const [gitStatus, setGitStatus] = useState(null);
  const [gitChecking, setGitChecking] = useState(false);
  const [showGitTools, setShowGitTools] = useState(true);
  const [gitBase, setGitBase] = useState("main");
  const [gitTarget, setGitTarget] = useState("");
  const [gitComparison, setGitComparison] = useState(null);
  const [gitCommitSha, setGitCommitSha] = useState("");
  const [gitCommitLoading, setGitCommitLoading] = useState(false);
  const [gitCommitInfo, setGitCommitInfo] = useState(null);

  const [showArchitecture, setShowArchitecture] = useState(false);
  const [architecture, setArchitecture] = useState(null);
  const [architectureLoading, setArchitectureLoading] = useState(false);
  const [architectureError, setArchitectureError] = useState("");

  const [prNumber, setPrNumber] = useState("");
  const [prLoading, setPrLoading] = useState(false);
  const [prResult, setPrResult] = useState(null);
  const [prError, setPrError] = useState("");

  const [requestController, setRequestController] = useState(null);

  const chatScrollRef = useRef(null);
  const questionRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);
  const historyLoadedRef = useRef(false);

  const indexed = selectedRepo?.status === "indexed";

  const filteredExplorerFiles = useMemo(() => {
    const query = explorerSearch.trim().toLowerCase();

    if (!query) {
      return explorerFiles;
    }

    return explorerFiles.filter((file) =>
      file.toLowerCase().includes(query),
    );
  }, [explorerFiles, explorerSearch]);

  const statusLabel = useMemo(() => {
    if (indexing) return "Indexing";
    if (selectedRepo?.status === "error") return "Error";
    if (indexed) return "Indexed";
    return "Ready";
  }, [indexing, indexed, selectedRepo]);

  const loadWorkspaces = useCallback(async () => {
    setLoadingWorkspaces(true);
    setWorkspaceError("");

    try {
      const response = await fetch(`${API_BASE}/workspaces`, {
        credentials: "include",
        cache: "no-store",
      });

      let data = {};

      try {
        data = await response.json();
      } catch {}

      if (!response.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Unable to load workspaces.",
        );
      }

      const items = Array.isArray(data)
        ? data
        : Array.isArray(data?.workspaces)
          ? data.workspaces
          : [];

      setWorkspaces(items);

      setSelectedWorkspace((current) => {
        if (!items.length) {
          return null;
        }

        return (
          items.find(
            (workspace) => workspace.id === current?.id,
          ) || items[0]
        );
      });
    } catch (error) {
      setWorkspaceError(
        getErrorMessage(error, "Unable to load workspaces."),
      );
      setWorkspaces([]);
      setSelectedWorkspace(null);
    } finally {
      setLoadingWorkspaces(false);
    }
  }, []);

  const loadRepositories = useCallback(async () => {
    try {
      setLoadingRepos(true);
      setRepoLoadError("");

      const params = new URLSearchParams();

      if (selectedWorkspace?.id) {
        params.set(
          "workspace_id",
          String(selectedWorkspace.id),
        );
      }

      const query = params.toString();

      const response = await fetch(
        `${API_BASE}/repositories${
          query ? `?${query}` : ""
        }`,
        {
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
            : "Unable to load repositories.",
        );
      }

      const repos = Array.isArray(data) ? data : [];

      setRepositories(repos);

      setSelectedRepo((current) => {
        if (!repos.length) {
          return null;
        }

        return (
          repos.find(
            (repo) => repo.id === current?.id,
          ) || repos[0]
        );
      });
    } catch (error) {
      setRepoLoadError(
        getErrorMessage(error, "Unable to load repositories."),
      );
      setRepositories([]);
      setSelectedRepo(null);
    } finally {
      setLoadingRepos(false);
    }
  }, [selectedWorkspace?.id]);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  useEffect(() => {
    loadRepositories();
  }, [loadRepositories]);

  async function loadDashboard(repoId) {
    if (!repoId) {
      setDashboard(null);
      return;
    }

    try {
      setLoadingDashboard(true);
      setDashboardError("");

      const response = await fetch(
        `${API_BASE}/repositories/${repoId}/dashboard`,
        {
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
            : "Unable to load repository dashboard.",
        );
      }

      setDashboard(data);
    } catch (error) {
      setDashboard(null);
      setDashboardError(
        getErrorMessage(
          error,
          "Unable to load repository dashboard.",
        ),
      );
    } finally {
      setLoadingDashboard(false);
    }
  }

  async function loadExplorerFiles(repoId) {
    if (!repoId) {
      setExplorerFiles([]);
      return;
    }

    setExplorerLoading(true);
    setExplorerError("");

    try {
      const response = await fetch(
        `${API_BASE}/repositories/${repoId}/files`,
        {
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
            : "Unable to load repository files.",
        );
      }

      setExplorerFiles(
        Array.isArray(data?.files) ? data.files : [],
      );
    } catch (error) {
      setExplorerError(
        getErrorMessage(
          error,
          "Unable to load repository files.",
        ),
      );
    } finally {
      setExplorerLoading(false);
    }
  }

  async function loadArchitecture(repoId) {
    if (!repoId) {
      setArchitecture(null);
      return;
    }

    setArchitectureLoading(true);
    setArchitectureError("");

    try {
      const response = await fetch(
        `${API_BASE}/repositories/${repoId}/architecture`,
        {
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
            : "Unable to load architecture analysis.",
        );
      }

      setArchitecture(data);
    } catch (error) {
      setArchitecture(null);
      setArchitectureError(
        getErrorMessage(
          error,
          "Unable to load architecture analysis.",
        ),
      );
    } finally {
      setArchitectureLoading(false);
    }
  }

  async function checkGitStatus(repoId) {
    if (!repoId) return;

    setGitChecking(true);

    try {
      const response = await fetch(
        `${API_BASE}/repositories/${repoId}/git/status`,
        {
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
            : "Unable to check Git status.",
        );
      }

      setGitStatus(data);
    } catch (error) {
      setGitStatus({
        error: getErrorMessage(
          error,
          "Unable to check Git status.",
        ),
      });
    } finally {
      setGitChecking(false);
    }
  }

  async function refreshRepository(repoId) {
    try {
      const response = await fetch(
        `${API_BASE}/repositories/${repoId}`,
        {
          credentials: "include",
          cache: "no-store",
        },
      );

      if (!response.ok) return;

      const repo = await response.json();

      setRepositories((current) =>
        current.map((item) =>
          item.id === repo.id ? repo : item,
        ),
      );

      setSelectedRepo(repo);
    } catch {}
  }

  useEffect(() => {
    if (!selectedRepo?.id) {
      setDashboard(null);
      setGitStatus(null);
      return;
    }

    loadDashboard(selectedRepo.id);
    checkGitStatus(selectedRepo.id);

    const interval = window.setInterval(() => {
      checkGitStatus(selectedRepo.id);
      loadDashboard(selectedRepo.id);
    }, 60000);

    return () => {
      window.clearInterval(interval);
    };
  }, [selectedRepo?.id]);

  useEffect(() => {
    if (showExplorer && selectedRepo?.id) {
      loadExplorerFiles(selectedRepo.id);
    }
  }, [showExplorer, selectedRepo?.id]);

  useEffect(() => {
    if (
      showArchitecture &&
      selectedRepo?.id &&
      !architecture
    ) {
      loadArchitecture(selectedRepo.id);
    }
  }, [showArchitecture, selectedRepo?.id, architecture]);

  useEffect(() => {
    shouldAutoScrollRef.current = true;

    if (!selectedRepo?.id) {
      setMessages([]);
      historyLoadedRef.current = false;
      return;
    }

    const history = loadConversationHistory(
      selectedRepo.id,
    );

    setMessages(history);
    historyLoadedRef.current = true;

    requestAnimationFrame(() => {
      const element = chatScrollRef.current;

      if (element) {
        element.scrollTop = element.scrollHeight;
      }
    });
  }, [selectedRepo?.id]);

  useEffect(() => {
    if (
      !selectedRepo?.id ||
      !historyLoadedRef.current
    ) {
      return;
    }

    saveConversationHistory(
      selectedRepo.id,
      messages,
    );
  }, [selectedRepo?.id, messages]);

  useEffect(() => {
    if (indexed && !asking) {
      questionRef.current?.focus();
    }
  }, [indexed, asking, selectedRepo?.id]);

  function selectWorkspace(workspace) {
    if (!workspace) return;

    if (asking) {
      requestController?.abort();
      setRequestController(null);
      setAsking(false);
    }

    setSelectedWorkspace(workspace);
    setSelectedRepo(null);

    setMessages([]);
    setArchitecture(null);
    setArchitectureError("");

    setGitStatus(null);
    setGitComparison(null);
    setGitCommitSha("");
    setGitCommitInfo(null);

    setPrNumber("");
    setPrResult(null);
    setPrError("");

    setExpandedSource(null);
    setShowSources({});
    setSourceViewer(null);

    setExplorerFiles([]);
    setExplorerOpenFile(null);
    setExplorerSearch("");

    setDashboard(null);
    setDashboardError("");

    setChatError("");
    setIndexMessage("");
    setSuggestedQuestions([
      "What does this project do?",
      "Explain the architecture.",
      "Find potential bugs.",
    ]);
  }

  function selectRepository(repo) {
    if (asking) {
      requestController?.abort();
      setRequestController(null);
      setAsking(false);
    }

    shouldAutoScrollRef.current = true;

    setSelectedRepo(repo);

    setExpandedSource(null);
    setShowSources({});
    setIndexMessage("");
    setChatError("");

    setExplorerSearch("");
    setExplorerOpenFile(null);
    setSourceViewer(null);

    setGitComparison(null);
    setGitCommitSha("");
    setGitCommitInfo(null);

    setPrNumber("");
    setPrResult(null);
    setPrError("");

    setArchitecture(null);
    setArchitectureError("");
    setShowArchitecture(false);

    setSuggestedQuestions([
      "What does this project do?",
      "Explain the architecture.",
      "Find potential bugs.",
    ]);

    setMobileSidebar(false);
  }

  async function connectRepository() {
    const url = repoUrl.trim();

    if (!url || connectingRepo) return;

    setConnectingRepo(true);
    setRepoError("");

    try {
      const params = new URLSearchParams();

      if (selectedWorkspace?.id) {
        params.set(
          "workspace_id",
          String(selectedWorkspace.id),
        );
      }

      const query = params.toString();

      const response = await fetch(
        `${API_BASE}/repositories${
          query ? `?${query}` : ""
        }`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            url,
            branch: repoBranch.trim() || "main",
          }),
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
            : "Unable to connect repository.",
        );
      }

      const repo = data;

      setRepositories((current) => {
        const exists = current.some(
          (item) => item.id === repo.id,
        );

        return exists
          ? current.map((item) =>
              item.id === repo.id ? repo : item,
            )
          : [repo, ...current];
      });

      setSelectedRepo(repo);

      setRepoUrl("");
      setRepoBranch("main");
      setShowNewRepo(false);

      setMessages([]);
      setExpandedSource(null);
      setShowSources({});
    } catch (error) {
      setRepoError(
        getErrorMessage(
          error,
          "Unable to connect repository.",
        ),
      );
    } finally {
      setConnectingRepo(false);
    }
  }

  async function indexRepository() {
    if (!selectedRepo || indexing) return;

    const repoId = selectedRepo.id;

    setIndexing(true);
    setIndexMessage("");
    setIndexStage("Starting indexing...");

    try {
      const response = await fetch(
        `${API_BASE}/repositories/${repoId}/index`,
        {
          method: "POST",
          credentials: "include",
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
            : "Repository indexing failed.",
        );
      }

      const jobId = data?.id || data?.job_id;

      if (!jobId) {
        throw new Error(
          "Indexing started but no job ID was returned.",
        );
      }

      setIndexStage("Indexing repository...");

      let finished = false;

      while (!finished) {
        await new Promise((resolve) =>
          setTimeout(resolve, 1000),
        );

        const jobResponse = await fetch(
          `${API_BASE}/repositories/${repoId}/jobs/${jobId}`,
          {
            credentials: "include",
            cache: "no-store",
          },
        );

        let job = {};

        try {
          job = await jobResponse.json();
        } catch {}

        if (!jobResponse.ok) {
          throw new Error(
            typeof job?.detail === "string"
              ? job.detail
              : "Unable to check indexing progress.",
          );
        }

        const jobStatus = String(
          job?.status || "",
        ).toLowerCase();

        if (
          jobStatus === "queued" ||
          jobStatus === "pending"
        ) {
          setIndexStage(
            "Waiting for indexing worker...",
          );
        } else if (
          jobStatus === "running" ||
          jobStatus === "processing"
        ) {
          setIndexStage("Indexing repository...");
        } else if (
          jobStatus === "completed" ||
          jobStatus === "complete" ||
          jobStatus === "success" ||
          jobStatus === "indexed"
        ) {
          finished = true;
          setIndexStage("Finalizing index...");
        } else if (
          jobStatus === "failed" ||
          jobStatus === "error"
        ) {
          throw new Error(
            job?.error ||
              job?.message ||
              "Repository indexing failed.",
          );
        }
      }

      await refreshRepository(repoId);
      await loadDashboard(repoId);
      await checkGitStatus(repoId);
    } catch (error) {
      const message = getErrorMessage(
        error,
        "Repository indexing failed.",
      );

      setIndexMessage(message);

      setSelectedRepo((current) =>
        current
          ? {
              ...current,
              status: "error",
            }
          : current,
      );
    } finally {
      setIndexing(false);
    }
  }

  function cancelQuestion() {
    requestController?.abort();
  }

  async function askQuestion(value) {
    const prompt = (value ?? question).trim();

    if (
      !prompt ||
      !selectedRepo ||
      !indexed ||
      asking
    ) {
      return;
    }

    setQuestion("");
    setChatError("");
    setAsking(true);
    setChatStage("Searching indexed code...");
    setSuggestedQuestions([]);

    shouldAutoScrollRef.current = true;

    const controller = new AbortController();
    setRequestController(controller);

    const userMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: prompt,
    };

    const assistantId = crypto.randomUUID();

    const assistantMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: [],
      metrics: null,
    };

    setMessages((current) => [
      ...current,
      userMessage,
      assistantMessage,
    ]);

    requestAnimationFrame(() => {
      const element = chatScrollRef.current;

      if (
        element &&
        shouldAutoScrollRef.current
      ) {
        element.scrollTop = element.scrollHeight;
      }
    });

    const answerStageTimer =
      window.setTimeout(() => {
        setChatStage(
          "Generating grounded answer...",
        );
      }, 1400);

    const finalStageTimer =
      window.setTimeout(() => {
        setChatStage("Writing response...");
      }, 5000);

    const commitMatch = prompt.match(
      /\bcommit\s+([0-9a-f]{7,64})\b/i,
    );

    const commitSha = commitMatch
      ? commitMatch[1]
      : null;

    try {
      const response = await fetch(
        `${API_BASE}/chat/stream`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          signal: controller.signal,
          body: JSON.stringify({
            repository_id: selectedRepo.id,
            message: prompt,
            commit_sha: commitSha,
          }),
        },
      );

      if (!response.ok) {
        let data = {};

        try {
          data = await response.json();
        } catch {}

        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Unable to answer the question.",
        );
      }

      if (!response.body) {
        throw new Error(
          "Streaming response body is unavailable.",
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";
      let answer = "";
      let sources = [];
      let metrics = null;
      let streamFinished = false;

      while (!streamFinished) {
        const { value, done } =
          await reader.read();

        if (done) break;

        buffer += decoder.decode(value, {
          stream: true,
        });

        const events = buffer.split(
          "\n\n",
        );

        buffer = events.pop() || "";

        for (const event of events) {
          const lines = event
            .split("\n")
            .filter((line) =>
              line.startsWith("data:"),
            );

          for (const line of lines) {
            const payload = line
              .slice(5)
              .trim();

            if (!payload) continue;

            if (payload === "[DONE]") {
              streamFinished = true;
              break;
            }

            let data;

            try {
              data = JSON.parse(payload);
            } catch {
              continue;
            }

            if (data?.type === "token") {
              answer += data.content || "";
              setChatStage("Writing response...");

              setMessages((current) =>
                current.map((message) =>
                  message.id === assistantId
                    ? {
                        ...message,
                        content:
                          formatAnswer(answer),
                      }
                    : message,
                ),
              );
            }

            if (data?.type === "sources") {
              sources = Array.isArray(
                data.sources,
              )
                ? data.sources
                : [];

              setMessages((current) =>
                current.map((message) =>
                  message.id === assistantId
                    ? {
                        ...message,
                        sources,
                      }
                    : message,
                ),
              );
            }

            if (data?.type === "metrics") {
              metrics =
                data.metrics || null;

              setMessages((current) =>
                current.map((message) =>
                  message.id === assistantId
                    ? {
                        ...message,
                        metrics,
                      }
                    : message,
                ),
              );
            }

            if (data?.type === "error") {
              throw new Error(
                data.message ||
                  data.detail ||
                  "Unable to answer the question.",
              );
            }
          }

          if (streamFinished) break;
        }
      }

      const cleanedAnswer =
        formatAnswer(answer);

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content:
                  cleanedAnswer ||
                  "The indexed repository context is insufficient to determine this.",
                sources,
                metrics,
              }
            : message,
        ),
      );

      setSuggestedQuestions(
        buildSuggestedQuestions(
          prompt,
          cleanedAnswer,
        ),
      );
    } catch (error) {
      const message = getErrorMessage(
        error,
        "Something went wrong.",
      );

      if (error?.name === "AbortError") {
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  content: answer
                    ? formatAnswer(answer)
                    : "Generation cancelled.",
                  cancelled: true,
                  prompt,
                }
              : item,
          ),
        );
      } else {
        setChatError(message);

        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  content: message,
                  error: true,
                  prompt,
                }
              : item,
          ),
        );
      }
    } finally {
      window.clearTimeout(
        answerStageTimer,
      );
      window.clearTimeout(
        finalStageTimer,
      );

      setRequestController(null);
      setAsking(false);
    }
  }

  async function compareBranches() {
    if (
      !selectedRepo?.id ||
      !gitBase.trim() ||
      !gitTarget.trim()
    ) {
      return;
    }

    try {
      setGitComparison(null);

      const params =
        new URLSearchParams({
          base: gitBase.trim(),
          target: gitTarget.trim(),
        });

      const response = await fetch(
        `${API_BASE}/repositories/${selectedRepo.id}/git/compare?${params.toString()}`,
        {
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
            : "Unable to compare branches.",
        );
      }

      setGitComparison(data);
    } catch (error) {
      setGitComparison({
        error: getErrorMessage(
          error,
          "Unable to compare branches.",
        ),
      });
    }
  }

  async function loadCommitInfo() {
    const sha = gitCommitSha.trim();

    if (!selectedRepo?.id || !sha) {
      return;
    }

    try {
      setGitCommitLoading(true);
      setGitCommitInfo(null);

      const response = await fetch(
        `${API_BASE}/repositories/${selectedRepo.id}/git/commit/${encodeURIComponent(
          sha,
        )}`,
        {
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
            : "Unable to load commit.",
        );
      }

      setGitCommitInfo(data);
    } catch (error) {
      setGitCommitInfo({
        error: getErrorMessage(
          error,
          "Unable to load commit.",
        ),
      });
    } finally {
      setGitCommitLoading(false);
    }
  }

  function askAboutCommit() {
    const sha = gitCommitSha.trim();

    if (!sha) return;

    setQuestion(
      `What changed in commit ${sha}?`,
    );

    setShowGitTools(false);

    requestAnimationFrame(() =>
      questionRef.current?.focus(),
    );
  }

  async function analyzePullRequest() {
    if (
      !selectedRepo?.id ||
      !prNumber.trim() ||
      prLoading
    ) {
      return;
    }

    const number = prNumber.trim();

    if (!/^\d+$/.test(number)) {
      setPrError(
        "Pull request number must be numeric.",
      );
      return;
    }

    setPrLoading(true);
    setPrError("");
    setPrResult(null);

    try {
      const response = await fetch(
        `${API_BASE}/repositories/${selectedRepo.id}/git/pr/${encodeURIComponent(
          number,
        )}/analyze`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            base_branch:
              selectedRepo.branch ||
              "main",
          }),
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
            : "Unable to analyze pull request.",
        );
      }

      setPrResult(data);
    } catch (error) {
      setPrError(
        getErrorMessage(
          error,
          "Unable to analyze pull request.",
        ),
      );
    } finally {
      setPrLoading(false);
    }
  }

  function handleChatScroll() {
    const element =
      chatScrollRef.current;

    if (!element) return;

    shouldAutoScrollRef.current =
      isNearBottom(element);
  }

  function scrollToLatest() {
    const element =
      chatScrollRef.current;

    if (!element) return;

    shouldAutoScrollRef.current = true;

    element.scrollTo({
      top: element.scrollHeight,
      behavior: "smooth",
    });
  }

  function handleKeyDown(event) {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();
      askQuestion();
    }

    if (
      event.key === "Escape" &&
      asking
    ) {
      event.preventDefault();
      cancelQuestion();
    }
  }

  function retryQuestion(prompt) {
    if (!prompt || asking) return;

    setMessages((current) => {
      const index =
        current.findIndex(
          (message) =>
            message.role ===
              "assistant" &&
            message.error &&
            message.prompt ===
              prompt,
        );

      return index === -1
        ? current
        : current.filter(
            (_, itemIndex) =>
              itemIndex !== index,
          );
    });

    askQuestion(prompt);
  }

  function closeNewRepository() {
    if (connectingRepo) return;

    setShowNewRepo(false);
    setRepoError("");
    setRepoUrl("");
    setRepoBranch("main");
  }

  async function openSource(source) {
    if (
      !selectedRepo?.id ||
      !source?.file_path
    ) {
      return;
    }

    setSourceLoading(true);
    setSourceError("");
    setSourceViewer(null);

    try {
      const params =
        new URLSearchParams({
          path: source.file_path,
          start_line: String(
            source.start_line ?? 1,
          ),
          end_line: String(
            source.end_line ??
              source.start_line ??
              1,
          ),
        });

      const response = await fetch(
        `${API_BASE}/repositories/${selectedRepo.id}/files/source/range?${params.toString()}`,
        {
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
            : "Unable to open source.",
        );
      }

      setSourceViewer({
        ...data,
        similarity:
          typeof source.similarity ===
          "number"
            ? source.similarity
            : null,
      });
    } catch (error) {
      setSourceError(
        getErrorMessage(
          error,
          "Unable to open source.",
        ),
      );
    } finally {
      setSourceLoading(false);
    }
  }

  const sidebar = (
    <aside className="flex h-full w-[270px] shrink-0 flex-col border-r border-white/[0.07] bg-[#0b0c0f]">
      <div className="px-5 pt-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-xs font-black text-black">
            RP
          </div>

          <div>
            <div className="text-[14px] font-semibold tracking-tight">
              RepoPilot
            </div>

            <div className="text-[10px] text-white/30">
              AI code intelligence
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8 px-4">
        <div className="mb-2 px-1 text-[9px] font-semibold uppercase tracking-[0.18em] text-white/25">
          Workspace
        </div>

        <div className="relative">
          <select
            value={
              selectedWorkspace?.id ?? ""
            }
            onChange={(event) => {
              const workspace =
                workspaces.find(
                  (item) =>
                    String(item.id) ===
                    event.target.value,
                );

              if (workspace) {
                selectWorkspace(
                  workspace,
                );
              }
            }}
            disabled={
              loadingWorkspaces ||
              workspaces.length === 0
            }
            className="w-full appearance-none rounded-xl border border-white/[0.07] bg-white/[0.025] px-3 py-2.5 pr-8 text-[10px] font-medium text-white/65 outline-none hover:bg-white/[0.05] focus:border-white/[0.15] disabled:opacity-40"
            aria-label="Select workspace"
          >
            {workspaces.length === 0 ? (
              <option
                value=""
                className="bg-[#101114]"
              >
                {loadingWorkspaces
                  ? "Loading workspace..."
                  : "No workspace"}
              </option>
            ) : (
              workspaces.map(
                (workspace) => (
                  <option
                    key={workspace.id}
                    value={workspace.id}
                    className="bg-[#101114] text-white"
                  >
                    {workspace.name ||
                      workspace.slug ||
                      `Workspace ${workspace.id}`}
                  </option>
                ),
              )
            )}
          </select>

          <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-white/25">
            <Icon
              name="chevron"
              className="h-3 w-3"
            />
          </span>
        </div>

        {workspaceError && (
          <div className="mt-2 rounded-lg border border-red-400/10 bg-red-400/[0.04] px-3 py-2 text-[9px] text-red-300/70">
            {workspaceError}
          </div>
        )}

        <div className="mt-3 rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
          <div className="flex items-center gap-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${statusDot(
                selectedRepo?.status,
              )}`}
            />

            <span className="text-[10px] text-white/35">
              {statusText(
                selectedRepo?.status,
              )}
            </span>
          </div>

          <div className="mt-2 truncate text-[13px] font-medium text-white/85">
            {selectedRepo?.name ||
              "No repository"}
          </div>

          <div className="mt-1 truncate text-[10px] text-white/20">
            {selectedRepo?.branch ||
              "main"}
          </div>
        </div>
      </div>

      <div className="mt-7 min-h-0 flex-1 px-4">
        <div className="mb-2 flex items-center justify-between px-1">
          <span className="text-[9px] font-semibold uppercase tracking-[0.18em] text-white/25">
            Repositories
          </span>

          <button
            type="button"
            onClick={() => {
              setRepoError("");
              setShowNewRepo(true);
            }}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-white/[0.08] bg-white/[0.025] text-white/40 hover:bg-white/[0.07] hover:text-white"
          >
            <Icon
              name="plus"
              className="h-3.5 w-3.5"
            />
          </button>
        </div>

        {repoLoadError && (
          <div className="mb-2 rounded-lg border border-red-400/10 bg-red-400/[0.04] px-3 py-2 text-[10px] text-red-300/75">
            {repoLoadError}

            <button
              type="button"
              onClick={loadRepositories}
              className="ml-2 underline underline-offset-2 hover:text-red-200"
            >
              Retry
            </button>
          </div>
        )}

        <div className="max-h-[calc(100vh-360px)] space-y-1 overflow-y-auto pr-1">
          {loadingRepos ? (
            <>
              <div className="h-10 animate-pulse rounded-lg bg-white/[0.035]" />
              <div className="h-10 animate-pulse rounded-lg bg-white/[0.025]" />
            </>
          ) : repositories.length === 0 ? (
            <div className="rounded-xl border border-dashed border-white/[0.07] px-3 py-4">
              <div className="text-xs text-white/30">
                No repositories in this workspace.
              </div>

              <button
                type="button"
                onClick={() =>
                  setShowNewRepo(true)
                }
                className="mt-2 text-[10px] text-white/55 hover:text-white"
              >
                Connect one
              </button>
            </div>
          ) : (
            repositories.map((repo) => (
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
          )}
        </div>
      </div>

      <div className="px-4 pb-5">
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
          <div className="flex items-center gap-2 text-[10px] text-white/40">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" />
            Local-first
          </div>

          <div className="mt-1 text-[9px] text-white/20">
            Inference through Ollama
          </div>
        </div>
      </div>
    </aside>
  );

  return (
    <main className="min-h-screen bg-[#08090b] text-white">
      {sourceViewer && (
        <div className="fixed inset-0 z-[70] bg-black/75 backdrop-blur-sm">
          <div className="flex h-full w-full items-center justify-center p-4">
            <div className="flex h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/[0.09] bg-[#0d0f12]">
              <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-[12px] font-semibold text-white/75">
                    {
                      sourceViewer.file_path
                    }
                  </div>

                  <div className="mt-0.5 text-[9px] text-white/25">
                    Lines{" "}
                    {
                      sourceViewer.start_line
                    }
                    –
                    {
                      sourceViewer.end_line
                    }
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() =>
                    setSourceViewer(
                      null,
                    )
                  }
                  className="rounded-lg border border-white/[0.07] px-3 py-1.5 text-[9px] text-white/40 hover:bg-white/[0.05] hover:text-white"
                >
                  Close
                </button>
              </div>

              {sourceLoading ? (
                <div className="flex flex-1 items-center justify-center">
                  <div className="text-[10px] text-white/25">
                    Loading source...
                  </div>
                </div>
              ) : sourceError ? (
                <div className="p-5 text-[10px] text-red-300/70">
                  {sourceError}
                </div>
              ) : (
                <div className="min-h-0 flex-1 overflow-auto bg-[#090a0c]">
                  <div className="min-w-max p-4 font-mono text-[11px] leading-6">
                    {(
                      sourceViewer.content ||
                      ""
                    )
                      .split("\n")
                      .map(
                        (
                          line,
                          index,
                        ) => {
                          const lineNumber =
                            (sourceViewer.start_line ??
                              1) +
                            index;

                          return (
                            <div
                              key={`${lineNumber}-${index}`}
                              className="flex bg-white/[0.045]"
                            >
                              <span className="w-14 shrink-0 select-none pr-4 text-right text-white/40">
                                {
                                  lineNumber
                                }
                              </span>

                              <code className="whitespace-pre text-white/75">
                                {line || " "}
                              </code>
                            </div>
                          );
                        },
                      )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {showNewRepo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4 backdrop-blur-sm">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-white/[0.09] bg-[#101114]">
            <div className="flex items-start justify-between border-b border-white/[0.06] px-5 py-4">
              <div>
                <div className="text-sm font-semibold">
                  Connect repository
                </div>

                <div className="mt-1 text-[10px] text-white/30">
                  Add a repository to{" "}
                  {selectedWorkspace?.name ||
                    "this workspace"}.
                </div>
              </div>

              <button
                type="button"
                onClick={closeNewRepository}
                disabled={
                  connectingRepo
                }
                className="rounded-lg p-1.5 text-white/35 hover:bg-white/[0.06] hover:text-white disabled:opacity-30"
              >
                <Icon
                  name="close"
                  className="h-4 w-4"
                />
              </button>
            </div>

            <form
              className="space-y-4 p-5"
              onSubmit={(event) => {
                event.preventDefault();
                connectRepository();
              }}
            >
              <label className="block">
                <span className="mb-1.5 block text-[10px] font-medium text-white/45">
                  Repository URL
                </span>

                <input
                  value={repoUrl}
                  onChange={(event) =>
                    setRepoUrl(
                      event.target.value,
                    )
                  }
                  placeholder="https://github.com/username/repository"
                  className="w-full rounded-xl border border-white/[0.08] bg-white/[0.025] px-3 py-2.5 text-sm text-white outline-none placeholder:text-white/20 focus:border-white/[0.2]"
                  autoFocus
                />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[10px] font-medium text-white/45">
                  Branch
                </span>

                <input
                  value={repoBranch}
                  onChange={(event) =>
                    setRepoBranch(
                      event.target.value,
                    )
                  }
                  placeholder="main"
                  className="w-full rounded-xl border border-white/[0.08] bg-white/[0.025] px-3 py-2.5 text-sm text-white outline-none placeholder:text-white/20 focus:border-white/[0.2]"
                />
              </label>

              {repoError && (
                <div className="rounded-xl border border-red-400/10 bg-red-400/[0.06] px-3 py-2.5 text-xs text-red-300">
                  {repoError}
                </div>
              )}

              <button
                type="submit"
                disabled={
                  !repoUrl.trim() ||
                  connectingRepo ||
                  !selectedWorkspace
                }
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-xs font-semibold text-black hover:bg-white/90 disabled:opacity-40"
              >
                {connectingRepo && (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border border-black/20 border-t-black" />
                )}

                {connectingRepo
                  ? "Connecting…"
                  : "Connect repository"}
              </button>
            </form>
          </div>
        </div>
      )}

      {mobileSidebar && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            onClick={() =>
              setMobileSidebar(false)
            }
            aria-label="Close repositories"
          />

          <div className="relative h-full w-[280px] shadow-2xl">
            {sidebar}
          </div>
        </div>
      )}

      <div className="flex min-h-screen">
        <div className="hidden lg:block">
          {sidebar}
        </div>

        <section className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-white/[0.07] bg-[#08090b]/90 px-4 backdrop-blur-xl lg:px-7">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                onClick={() =>
                  setMobileSidebar(true)
                }
                className="rounded-lg border border-white/[0.07] p-2 text-white/50 hover:bg-white/[0.05] lg:hidden"
                aria-label="Open repositories"
              >
                <span className="block h-3.5 w-4 border-y border-white/50 py-1">
                  <span className="block border-t border-white/50" />
                </span>
              </button>

              <div className="hidden min-w-0 sm:block">
                <div className="truncate text-[10px] text-white/20">
                  {selectedWorkspace?.name ||
                    "Workspace"}
                </div>

                <div className="truncate text-xs font-medium text-white/45">
                  {selectedRepo?.name ||
                    "RepoPilot"}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 rounded-full border border-white/[0.06] bg-white/[0.025] px-2.5 py-1.5">
              <span
                className={`h-1.5 w-1.5 rounded-full ${statusDot(
                  selectedRepo?.status,
                )}`}
              />

              <span className="text-[10px] text-white/40">
                {statusLabel}
              </span>
            </div>
          </header>

          <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
            <div className="rounded-2xl border border-white/[0.07] bg-white/[0.018]">
              <div className="flex flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-2 w-2 rounded-full ${statusDot(
                        selectedRepo?.status,
                      )}`}
                    />

                    <h1 className="truncate text-sm font-semibold tracking-tight">
                      {selectedRepo?.name ||
                        "No repository selected"}
                    </h1>
                  </div>

                  {selectedRepo?.url && (
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
                </div>

                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setShowDashboard(
                        (current) =>
                          !current,
                      )
                    }
                    className="rounded-lg border border-white/[0.08] px-3.5 py-2 text-[10px] font-medium text-white/50 hover:bg-white/[0.05] hover:text-white"
                  >
                    {showDashboard
                      ? "Hide dashboard"
                      : "Dashboard"}
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      setShowExplorer(
                        (current) =>
                          !current,
                      )
                    }
                    className="rounded-lg border border-white/[0.08] px-3.5 py-2 text-[10px] font-medium text-white/50 hover:bg-white/[0.05] hover:text-white"
                  >
                    {showExplorer
                      ? "Hide explorer"
                      : "Explorer"}
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      setShowArchitecture(
                        (current) =>
                          !current,
                      )
                    }
                    className={`rounded-lg border px-3.5 py-2 text-[10px] font-medium ${
                      showArchitecture
                        ? "border-white/[0.14] bg-white/[0.07] text-white/80"
                        : "border-white/[0.08] text-white/50 hover:bg-white/[0.05]"
                    }`}
                  >
                    {showArchitecture
                      ? "Hide architecture"
                      : "Architecture"}
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      setShowGitTools(
                        (current) =>
                          !current,
                      )
                    }
                    className={`rounded-lg border px-3.5 py-2 text-[10px] font-medium ${
                      showGitTools
                        ? "border-white/[0.14] bg-white/[0.07] text-white/80"
                        : "border-white/[0.08] text-white/50 hover:bg-white/[0.05]"
                    }`}
                  >
                    Git
                  </button>

                  <button
                    type="button"
                    onClick={
                      indexRepository
                    }
                    disabled={
                      !selectedRepo ||
                      indexing
                    }
                    className="rounded-lg bg-white px-3.5 py-2 text-[10px] font-semibold text-black hover:bg-white/90 disabled:opacity-35"
                  >
                    {indexing
                      ? "Indexing…"
                      : indexed
                        ? "Re-index"
                        : "Index repository"}
                  </button>
                </div>
              </div>

              {indexing && (
                <div className="border-t border-white/[0.06] px-4 py-3 sm:px-5">
                  <div className="flex items-center gap-2.5">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />

                    <span className="text-[10px] text-white/55">
                      {indexStage}
                    </span>
                  </div>
                </div>
              )}

              {indexMessage && (
                <div className="border-t border-red-400/10 bg-red-400/[0.03] px-4 py-2.5 text-[10px] text-red-300/80 sm:px-5">
                  {indexMessage}
                </div>
              )}
            </div>

            {showDashboard &&
              selectedRepo && (
                <RepositoryDashboard
                  dashboard={dashboard}
                  loading={
                    loadingDashboard
                  }
                  error={dashboardError}
                  onRefresh={() =>
                    selectedRepo?.id &&
                    loadDashboard(
                      selectedRepo.id,
                    )
                  }
                />
              )}

            {showArchitecture &&
              selectedRepo && (
                <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.018]">
                  <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3 sm:px-5">
                    <div>
                      <div className="text-[11px] font-semibold text-white/70">
                        Architecture intelligence
                      </div>

                      <div className="mt-0.5 text-[9px] text-white/25">
                        Repository structure and dependency analysis
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        selectedRepo?.id &&
                        loadArchitecture(
                          selectedRepo.id,
                        )
                      }
                      disabled={
                        architectureLoading
                      }
                      className="rounded-lg border border-white/[0.07] p-1.5 text-white/35 hover:bg-white/[0.05]"
                    >
                      <Icon
                        name="refresh"
                        className={
                          architectureLoading
                            ? "animate-spin"
                            : ""
                        }
                      />
                    </button>
                  </div>

                  <div className="p-4 sm:p-5">
                    {architectureLoading &&
                      !architecture && (
                        <div className="text-[10px] text-white/25">
                          Loading architecture analysis...
                        </div>
                      )}

                    {architectureError && (
                      <div className="rounded-xl border border-red-400/10 bg-red-400/[0.04] p-3 text-[10px] text-red-300/70">
                        {architectureError}
                      </div>
                    )}

                    {architecture &&
                      !architectureError && (
                        <div className="space-y-4">
                          <div className="rounded-xl border border-white/[0.06] bg-black/20 p-4">
                            <ReactMarkdown
                              remarkPlugins={[
                                remarkGfm,
                              ]}
                              components={{
                                p: ({
                                  children,
                                }) => (
                                  <p className="mb-4 last:mb-0 text-[11px] leading-6 text-white/50">
                                    {children}
                                  </p>
                                ),
                                h2: ({
                                  children,
                                }) => (
                                  <h2 className="mb-3 mt-5 text-sm font-semibold text-white">
                                    {children}
                                  </h2>
                                ),
                                h3: ({
                                  children,
                                }) => (
                                  <h3 className="mb-2 mt-4 text-xs font-semibold text-white/80">
                                    {children}
                                  </h3>
                                ),
                                ul: ({
                                  children,
                                }) => (
                                  <ul className="mb-4 list-disc space-y-1.5 pl-5 text-[11px] text-white/45">
                                    {children}
                                  </ul>
                                ),
                                ol: ({
                                  children,
                                }) => (
                                  <ol className="mb-4 list-decimal space-y-1.5 pl-5 text-[11px] text-white/45">
                                    {children}
                                  </ol>
                                ),
                              }}
                            >
                              {architecture.summary ||
                                "No architecture summary available."}
                            </ReactMarkdown>
                          </div>

                          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                            <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
                              <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
                                Code files
                              </div>
                              <div className="mt-2 text-xl font-semibold text-white/85">
                                {
                                  architecture
                                    .statistics
                                    ?.total_code_files ??
                                  0
                                }
                              </div>
                            </div>

                            <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
                              <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
                                Functions
                              </div>
                              <div className="mt-2 text-xl font-semibold text-white/85">
                                {
                                  architecture
                                    .statistics
                                    ?.symbols
                                    ?.functions ??
                                  0
                                }
                              </div>
                            </div>

                            <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
                              <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
                                Classes
                              </div>
                              <div className="mt-2 text-xl font-semibold text-white/85">
                                {
                                  architecture
                                    .statistics
                                    ?.symbols
                                    ?.classes ??
                                  0
                                }
                              </div>
                            </div>

                            <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
                              <div className="text-[9px] uppercase tracking-[0.15em] text-white/20">
                                Routes
                              </div>
                              <div className="mt-2 text-xl font-semibold text-white/85">
                                {
                                  architecture
                                    .statistics
                                    ?.symbols
                                    ?.routes ??
                                  0
                                }
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                  </div>
                </div>
              )}

            {showGitTools &&
              selectedRepo && (
                <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.018]">
                  <div className="border-b border-white/[0.06] px-4 py-3 sm:px-5">
                    <div className="text-[11px] font-semibold text-white/70">
                      Git integration
                    </div>

                    <div className="mt-0.5 text-[9px] text-white/25">
                      {selectedRepo.branch ||
                        "main"}
                    </div>
                  </div>

                  <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-2">
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-[9px] font-semibold uppercase tracking-[0.15em] text-white/20">
                          Remote status
                        </div>

                        {gitStatus &&
                          !gitStatus.error && (
                            <span
                              className={`rounded-full border px-2 py-1 text-[9px] ${
                                gitStatus.needs_update
                                  ? "border-amber-400/10 bg-amber-400/[0.07] text-amber-300"
                                  : "border-emerald-400/10 bg-emerald-400/[0.07] text-emerald-300"
                              }`}
                            >
                              {gitStatus.needs_update
                                ? "Update available"
                                : "Up to date"}
                            </span>
                          )}
                      </div>

                      {gitStatus?.error ? (
                        <div className="mt-3 text-[9px] text-red-300/70">
                          {gitStatus.error}
                        </div>
                      ) : (
                        <div className="mt-3 space-y-2">
                          <div>
                            <div className="text-[9px] text-white/20">
                              Indexed commit
                            </div>

                            <div className="mt-1 break-all font-mono text-[10px] text-white/45">
                              {gitStatus?.last_indexed_commit ||
                                selectedRepo.last_indexed_commit ||
                                "—"}
                            </div>
                          </div>

                          <div>
                            <div className="text-[9px] text-white/20">
                              Remote commit
                            </div>

                            <div className="mt-1 break-all font-mono text-[10px] text-white/45">
                              {gitStatus?.remote_commit ||
                                "—"}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.018] p-3">
                      <div className="text-[9px] font-semibold uppercase tracking-[0.15em] text-white/20">
                        Automatic sync
                      </div>

                      <div className="mt-2 text-[11px] text-white/55">
                        RepoPilot checks the remote branch automatically.
                      </div>

                      <div className="mt-1 text-[9px] leading-5 text-white/25">
                        Remote changes can trigger repository re-indexing.
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-white/[0.06] p-4 sm:p-5">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.15em] text-white/20">
                      Compare branches
                    </div>

                    <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                      <input
                        value={gitBase}
                        onChange={(event) =>
                          setGitBase(
                            event.target.value,
                          )
                        }
                        placeholder="main"
                        className="rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2 text-[10px] text-white/70"
                      />

                      <input
                        value={gitTarget}
                        onChange={(event) =>
                          setGitTarget(
                            event.target.value,
                          )
                        }
                        placeholder="feature/test"
                        className="rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2 text-[10px] text-white/70"
                      />

                      <button
                        type="button"
                        onClick={
                          compareBranches
                        }
                        disabled={
                          !gitBase.trim() ||
                          !gitTarget.trim()
                        }
                        className="rounded-lg bg-white px-4 py-2 text-[10px] font-semibold text-black disabled:opacity-30"
                      >
                        Compare
                      </button>
                    </div>

                    {gitComparison && (
                      <div className="mt-3 rounded-xl border border-white/[0.06] bg-black/20 p-3">
                        {gitComparison.error ? (
                          <div className="text-[9px] text-red-300/70">
                            {
                              gitComparison.error
                            }
                          </div>
                        ) : (
                          <>
                            <div className="flex flex-wrap gap-3 text-[10px] text-white/45">
                              <span>
                                {
                                  gitComparison.files_changed
                                }{" "}
                                files
                              </span>

                              <span>
                                {
                                  gitComparison.commits_count
                                }{" "}
                                commits
                              </span>
                            </div>

                            <div className="mt-3 space-y-1">
                              {(
                                gitComparison.files ||
                                []
                              )
                                .slice(0, 20)
                                .map(
                                  (
                                    file,
                                    index,
                                  ) => (
                                    <div
                                      key={`${file.new_path}-${index}`}
                                      className="font-mono text-[9px] text-white/35"
                                    >
                                      <span className="mr-2 text-white/20">
                                        {
                                          file.change_type
                                        }
                                      </span>

                                      {
                                        file.new_path ||
                                        file.old_path
                                      }
                                    </div>
                                  ),
                                )}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="border-t border-white/[0.06] p-4 sm:p-5">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.15em] text-white/20">
                      Commit tools
                    </div>

                    <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
                      <input
                        value={
                          gitCommitSha
                        }
                        onChange={(event) =>
                          setGitCommitSha(
                            event.target.value,
                          )
                        }
                        placeholder="commit SHA"
                        className="rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2 text-[10px] text-white/70"
                      />

                      <button
                        type="button"
                        onClick={
                          loadCommitInfo
                        }
                        disabled={
                          gitCommitLoading ||
                          !gitCommitSha.trim()
                        }
                        className="rounded-lg border border-white/[0.08] px-3 py-2 text-[10px] text-white/50 hover:bg-white/[0.05] disabled:opacity-30"
                      >
                        {gitCommitLoading
                          ? "Loading…"
                          : "Inspect"}
                      </button>

                      <button
                        type="button"
                        onClick={
                          askAboutCommit
                        }
                        disabled={
                          !gitCommitSha.trim()
                        }
                        className="rounded-lg bg-white px-3 py-2 text-[10px] font-semibold text-black disabled:opacity-30"
                      >
                        Ask AI
                      </button>
                    </div>

                    {gitCommitInfo && (
                      <div className="mt-3 rounded-xl border border-white/[0.06] bg-black/20 p-3">
                        {gitCommitInfo.error ? (
                          <div className="text-[9px] text-red-300/70">
                            {
                              gitCommitInfo.error
                            }
                          </div>
                        ) : (
                          <>
                            <div className="font-mono text-[10px] text-white/50">
                              {
                                gitCommitInfo.short_sha
                              }
                            </div>

                            <div className="mt-1 text-[11px] text-white/65">
                              {
                                gitCommitInfo.message
                              }
                            </div>

                            <div className="mt-2 text-[9px] text-white/25">
                              Author:{" "}
                              {
                                gitCommitInfo.author ||
                                "—"
                              }
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="border-t border-white/[0.06] p-4 sm:p-5">
                    <div className="text-[9px] font-semibold uppercase tracking-[0.15em] text-white/20">
                      PR Assistant
                    </div>

                    <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto]">
                      <input
                        value={prNumber}
                        onChange={(event) =>
                          setPrNumber(
                            event.target.value,
                          )
                        }
                        placeholder="Pull request number"
                        inputMode="numeric"
                        className="rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2 text-[10px] text-white/70"
                      />

                      <button
                        type="button"
                        onClick={
                          analyzePullRequest
                        }
                        disabled={
                          prLoading ||
                          !prNumber.trim()
                        }
                        className="rounded-lg bg-white px-4 py-2 text-[10px] font-semibold text-black disabled:opacity-30"
                      >
                        {prLoading
                          ? "Analyzing…"
                          : "Analyze PR"}
                      </button>
                    </div>

                    {prError && (
                      <div className="mt-3 rounded-xl border border-red-400/10 bg-red-400/[0.04] px-3 py-2 text-[9px] text-red-300/70">
                        {prError}
                      </div>
                    )}

                    {prResult && (
                      <div className="mt-3 rounded-xl border border-white/[0.06] bg-black/20 p-3">
                        <div className="text-[10px] text-white/55">
                          PR #{prResult.pull_request}
                        </div>

                        <div className="mt-2 text-[10px] leading-5 text-white/40">
                          {prResult.review
                            ?.summary ||
                            "No PR summary generated."}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

            {showExplorer &&
              selectedRepo && (
                <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.018]">
                  <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3 sm:px-5">
                    <div>
                      <div className="text-[11px] font-semibold text-white/70">
                        Codebase explorer
                      </div>

                      <div className="mt-0.5 text-[9px] text-white/25">
                        {
                          explorerFiles.length
                        }{" "}
                        files
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        loadExplorerFiles(
                          selectedRepo.id,
                        )
                      }
                      disabled={
                        explorerLoading
                      }
                      className="rounded-lg border border-white/[0.07] p-1.5 text-white/35 hover:bg-white/[0.05]"
                    >
                      <Icon
                        name="refresh"
                        className={
                          explorerLoading
                            ? "animate-spin"
                            : ""
                        }
                      />
                    </button>
                  </div>

                  <div className="grid min-h-[360px] lg:grid-cols-[280px_1fr]">
                    <div className="border-b border-white/[0.06] lg:border-b-0 lg:border-r">
                      <div className="p-3">
                        <input
                          value={
                            explorerSearch
                          }
                          onChange={(event) =>
                            setExplorerSearch(
                              event.target.value,
                            )
                          }
                          placeholder="Search files..."
                          className="w-full rounded-lg border border-white/[0.08] bg-white/[0.025] px-3 py-2 text-[10px] text-white/70 placeholder:text-white/20"
                        />
                      </div>

                      {explorerError && (
                        <div className="mx-3 mb-3 rounded-lg border border-red-400/10 bg-red-400/[0.04] px-3 py-2 text-[9px] text-red-300/70">
                          {
                            explorerError
                          }
                        </div>
                      )}

                      <div className="max-h-[420px] overflow-y-auto px-2 pb-3">
                        {explorerLoading ? (
                          <div className="space-y-1">
                            {Array.from(
                              { length: 8 },
                              (_, index) => (
                                <div
                                  key={index}
                                  className="h-8 animate-pulse rounded-lg bg-white/[0.025]"
                                />
                              ),
                            )}
                          </div>
                        ) : filteredExplorerFiles.length ===
                          0 ? (
                          <div className="px-2 py-6 text-[10px] text-white/25">
                            No files found.
                          </div>
                        ) : (
                          filteredExplorerFiles.map(
                            (file) => (
                              <button
                                key={file}
                                type="button"
                                onClick={() =>
                                  setExplorerOpenFile(
                                    file,
                                  )
                                }
                                className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left ${
                                  explorerOpenFile ===
                                  file
                                    ? "bg-white/[0.07] text-white"
                                    : "text-white/40 hover:bg-white/[0.035]"
                                }`}
                              >
                                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white/[0.04] text-[7px] font-semibold text-white/25">
                                  {fileType(
                                    file,
                                  )}
                                </span>

                                <span className="truncate text-[10px]">
                                  {file}
                                </span>
                              </button>
                            ),
                          )
                        )}
                      </div>
                    </div>

                    <div className="min-w-0">
                      {!explorerOpenFile ? (
                        <div className="flex h-full min-h-[360px] items-center justify-center p-6 text-center">
                          <div>
                            <div className="text-[11px] text-white/35">
                              Select a file
                            </div>

                            <div className="mt-1 text-[9px] text-white/15">
                              Browse repository source here.
                            </div>
                          </div>
                        </div>
                      ) : (
                        <ExplorerFileViewer
                          repositoryId={
                            selectedRepo.id
                          }
                          filePath={
                            explorerOpenFile
                          }
                          onClose={() =>
                            setExplorerOpenFile(
                              null,
                            )
                          }
                        />
                      )}
                    </div>
                  </div>
                </div>
              )}

            <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col">
              {messages.length === 0 ? (
                <div className="flex flex-1 flex-col justify-center py-10 lg:py-14">
                  <div>
                    <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.025] px-2.5 py-1 text-[9px] font-medium uppercase tracking-[0.16em] text-white/25">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" />
                      Codebase intelligence
                    </div>

                    <h2 className="max-w-2xl text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
                      Ask your codebase.
                    </h2>

                    <p className="mt-3 max-w-xl text-sm leading-6 text-white/30">
                      Architecture, implementation,
                      bugs and files — grounded in
                      your indexed repository.
                    </p>
                  </div>

                  <div className="mt-8 grid gap-2 sm:grid-cols-2">
                    {QUICK_PROMPTS.map(
                      ([label, prompt, icon]) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() =>
                            askQuestion(
                              prompt,
                            )
                          }
                          disabled={
                            !selectedRepo ||
                            !indexed ||
                            asking
                          }
                          className="group flex min-h-[68px] items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.018] p-3.5 text-left disabled:opacity-25"
                        >
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/[0.07] bg-white/[0.025] text-[11px] text-white/35">
                            {icon}
                          </span>

                          <span className="min-w-0">
                            <span className="block text-[11px] font-medium text-white/55">
                              {label}
                            </span>

                            <span className="mt-1 block text-[10px] leading-4 text-white/20">
                              {prompt}
                            </span>
                          </span>

                          <Icon
                            name="arrow"
                            className="ml-auto mt-1 h-3.5 w-3.5 text-white/10"
                          />
                        </button>
                      ),
                    )}
                  </div>

                  {!selectedRepo &&
                    !loadingRepos && (
                      <div className="mt-5 rounded-xl border border-white/[0.06] bg-white/[0.018] px-4 py-3 text-[10px] text-white/30">
                        Select a workspace and
                        connect a repository to
                        start.
                      </div>
                    )}

                  {selectedRepo &&
                    !indexed &&
                    !indexing && (
                      <div className="mt-5 flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.018] px-4 py-3">
                        <span className="text-[10px] text-white/35">
                          Index this repository to
                          unlock chat.
                        </span>

                        <button
                          type="button"
                          onClick={
                            indexRepository
                          }
                          className="rounded-lg border border-white/[0.08] px-3 py-1.5 text-[10px] text-white/60 hover:bg-white/[0.05]"
                        >
                          Index
                        </button>
                      </div>
                    )}
                </div>
              ) : (
                <div
                  ref={chatScrollRef}
                  onScroll={
                    handleChatScroll
                  }
                  className="min-h-0 flex-1 overflow-y-auto overscroll-contain py-8"
                >
                  <div className="space-y-8">
                    {messages.map(
                      (message) => (
                        <div
                          key={message.id}
                        >
                          {message.role ===
                          "user" ? (
                            <div className="flex justify-end">
                              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-white/[0.07] px-4 py-3 text-sm leading-6 text-white/80">
                                {
                                  message.content
                                }
                              </div>
                            </div>
                          ) : (
                            <div className="flex gap-3">
                              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-[9px] font-black text-black">
                                RP
                              </div>

                              <div className="min-w-0 flex-1 pt-0.5">
                                <div
                                  className={`max-w-3xl text-sm leading-7 ${
                                    message.error
                                      ? "text-red-300/75"
                                      : message.cancelled
                                        ? "text-white/30"
                                        : "text-white/72"
                                  }`}
                                >
                                  {message.error ||
                                  message.cancelled ? (
                                    <div>
                                      {
                                        message.content
                                      }

                                      {message.error &&
                                        message.prompt && (
                                          <button
                                            type="button"
                                            onClick={() =>
                                              retryQuestion(
                                                message.prompt,
                                              )
                                            }
                                            className="ml-3 rounded-lg border border-white/[0.07] px-3 py-1.5 text-[10px] text-white/45"
                                          >
                                            Retry
                                          </button>
                                        )}
                                    </div>
                                  ) : (
                                    <div className="markdown-content">
                                      <ReactMarkdown
                                        remarkPlugins={[
                                          remarkGfm,
                                        ]}
                                        components={{
                                          p: ({
                                            children,
                                          }) => (
                                            <p className="mb-4 last:mb-0">
                                              {
                                                children
                                              }
                                            </p>
                                          ),
                                          strong:
                                            ({
                                              children,
                                            }) => (
                                              <strong className="font-semibold text-white">
                                                {
                                                  children
                                                }
                                              </strong>
                                            ),
                                          ul: ({
                                            children,
                                          }) => (
                                            <ul className="mb-4 list-disc space-y-1.5 pl-5">
                                              {
                                                children
                                              }
                                            </ul>
                                          ),
                                          ol: ({
                                            children,
                                          }) => (
                                            <ol className="mb-4 list-decimal space-y-1.5 pl-5">
                                              {
                                                children
                                              }
                                            </ol>
                                          ),
                                          h2: ({
                                            children,
                                          }) => (
                                            <h2 className="mb-3 mt-5 text-base font-semibold text-white">
                                              {
                                                children
                                              }
                                            </h2>
                                          ),
                                          h3: ({
                                            children,
                                          }) => (
                                            <h3 className="mb-2 mt-4 text-sm font-semibold text-white">
                                              {
                                                children
                                              }
                                            </h3>
                                          ),
                                          code: ({
                                            inline,
                                            children,
                                            className,
                                          }) =>
                                            inline ? (
                                              <code className="rounded-md bg-white/[0.07] px-1.5 py-0.5 text-[12px] text-white/80">
                                                {
                                                  children
                                                }
                                              </code>
                                            ) : (
                                              <code
                                                className={
                                                  className
                                                }
                                              >
                                                {
                                                  children
                                                }
                                              </code>
                                            ),
                                          pre: ({
                                            children,
                                          }) => (
                                            <pre className="group relative mb-4 overflow-x-auto rounded-xl border border-white/[0.07] bg-black/35 p-4 text-[12px] leading-6 text-white/65">
                                              {
                                                children
                                              }
                                            </pre>
                                          ),
                                        }}
                                      >
                                        {
                                          message.content
                                        }
                                      </ReactMarkdown>
                                    </div>
                                  )}
                                </div>

                                {message.sources
                                  ?.length >
                                  0 && (
                                  <div className="mt-5 max-w-3xl">
                                    <button
                                      type="button"
                                      onClick={() =>
                                        setShowSources(
                                          (
                                            current,
                                          ) => ({
                                            ...current,
                                            [message.id]:
                                              !current[
                                                message
                                                  .id
                                              ],
                                          }),
                                        )
                                      }
                                      className="flex items-center gap-2 px-1 py-1 text-[9px] font-semibold uppercase tracking-[0.15em] text-white/25"
                                    >
                                      {
                                        message
                                          .sources
                                          .length
                                      }{" "}
                                      sources

                                      <Icon
                                        name="chevron"
                                        className={`h-3 w-3 ${
                                          showSources[
                                            message
                                              .id
                                          ]
                                            ? "rotate-180"
                                            : ""
                                        }`}
                                      />
                                    </button>

                                    {showSources[
                                      message.id
                                    ] && (
                                      <div className="mt-2 space-y-1.5">
                                        {message.sources
                                          .slice(
                                            0,
                                            6,
                                          )
                                          .map(
                                            (
                                              source,
                                              sourceIndex,
                                            ) => {
                                              const sourceKey = `${message.id}-${source.file_path}-${source.start_line}-${sourceIndex}`;

                                              return (
                                                <SourceCard
                                                  key={
                                                    sourceKey
                                                  }
                                                  source={
                                                    source
                                                  }
                                                  expanded={
                                                    expandedSource ===
                                                    sourceKey
                                                  }
                                                  onToggle={() =>
                                                    setExpandedSource(
                                                      (
                                                        current,
                                                      ) =>
                                                        current ===
                                                        sourceKey
                                                          ? null
                                                          : sourceKey,
                                                    )
                                                  }
                                                  onOpen={
                                                    openSource
                                                  }
                                                />
                                              );
                                            },
                                          )}
                                      </div>
                                    )}
                                  </div>
                                )}

                                <MessageMetrics
                                  metrics={
                                    message.metrics
                                  }
                                />

                                {message.id ===
                                  messages[
                                    messages.length -
                                      1
                                  ]?.id &&
                                  !message.error &&
                                  !message.cancelled &&
                                  !asking &&
                                  suggestedQuestions.length >
                                    0 && (
                                    <div className="mt-4 max-w-3xl">
                                      <div className="mb-2 text-[9px] font-semibold uppercase tracking-[0.15em] text-white/20">
                                        Continue exploring
                                      </div>

                                      <div className="flex flex-wrap gap-2">
                                        {suggestedQuestions.map(
                                          (
                                            suggestion,
                                          ) => (
                                            <button
                                              key={
                                                suggestion
                                              }
                                              type="button"
                                              onClick={() =>
                                                askQuestion(
                                                  suggestion,
                                                )
                                              }
                                              className="rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2 text-[10px] text-white/40"
                                            >
                                              {
                                                suggestion
                                              }
                                            </button>
                                          ),
                                        )}
                                      </div>
                                    </div>
                                  )}
                              </div>
                            </div>
                          )}
                        </div>
                      ),
                    )}

                    {asking && (
                      <div className="ml-10 flex items-center gap-3">
                        <div className="flex items-center gap-1">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/45" />
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/25" />
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/15" />
                        </div>

                        <span className="text-[10px] text-white/25">
                          {chatStage}
                        </span>

                        <button
                          type="button"
                          onClick={
                            cancelQuestion
                          }
                          className="rounded-md border border-white/[0.07] px-2 py-1 text-[9px] text-white/35"
                        >
                          Stop
                        </button>
                      </div>
                    )}

                    {chatError && (
                      <div className="rounded-xl border border-red-400/10 bg-red-400/[0.035] px-3 py-2 text-[10px] text-red-300/70">
                        {chatError}
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="shrink-0 bg-[#08090b] pt-5">
                <div
                  className={`rounded-2xl border bg-[#0d0f12]/95 p-2 ${
                    asking
                      ? "border-white/[0.13]"
                      : "border-white/[0.08]"
                  }`}
                >
                  <textarea
                    ref={questionRef}
                    value={question}
                    onChange={(event) =>
                      setQuestion(
                        event.target.value,
                      )
                    }
                    onKeyDown={
                      handleKeyDown
                    }
                    disabled={
                      !selectedRepo ||
                      !indexed ||
                      asking
                    }
                    placeholder={
                      !selectedRepo
                        ? "Connect a repository to begin…"
                        : !indexed
                          ? "Index the repository to start asking…"
                          : "Ask about your codebase…"
                    }
                    rows={2}
                    maxLength={4000}
                    className="w-full bg-transparent px-3 py-2 text-sm leading-6 text-white outline-none placeholder:text-white/20 disabled:cursor-not-allowed"
                  />

                  <div className="flex items-center justify-between px-2 pb-1">
                    <span className="hidden text-[9px] text-white/20 sm:block">
                      Enter to send · Shift +
                      Enter for a new line ·
                      Esc to stop
                    </span>

                    <span className="text-[9px] text-white/20 sm:hidden">
                      Enter to send
                    </span>

                    <div className="flex items-center gap-2">
                      {messages.length >
                        0 &&
                        !asking && (
                          <button
                            type="button"
                            onClick={
                              scrollToLatest
                            }
                            className="rounded-lg border border-white/[0.07] px-2 py-1 text-[9px] text-white/30"
                          >
                            Latest
                          </button>
                        )}

                      {asking ? (
                        <button
                          type="button"
                          onClick={
                            cancelQuestion
                          }
                          className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.05]"
                        >
                          <Icon
                            name="stop"
                            className="h-3.5 w-3.5"
                          />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() =>
                            askQuestion()
                          }
                          disabled={
                            !question.trim() ||
                            !selectedRepo ||
                            !indexed
                          }
                          className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-black disabled:opacity-20"
                        >
                          <Icon
                            name="arrow"
                            className="h-3.5 w-3.5"
                          />
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-center gap-2 py-2 text-[9px] text-white/15">
                  <span>Grounded</span>
                  <span>·</span>
                  <span>Local</span>
                  <span>·</span>
                  <span>Private</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
