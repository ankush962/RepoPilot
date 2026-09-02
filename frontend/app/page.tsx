"use client";

import { useEffect, useMemo, useState } from "react";

type Repository = {
  id: number;
  name: string;
  url: string;
  branch?: string;
  status?: string;
  last_indexed_commit?: string | null;
};

type Source = {
  file_path?: string;
  start_line?: number;
  end_line?: number;
  content?: string;
  similarity?: number;
};

type ChatResponse = {
  answer?: string;
  response?: string;
  message?: string;
  content?: string;
  sources?: Source[];
  grounded?: boolean;
  [key: string]: unknown;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const QUICK_PROMPTS = [
  "What does this project do?",
  "Explain the backend architecture.",
  "Where is repository indexing implemented?",
  "Find potential bugs or weak points.",
  "What vector database and embedding model does this project use?",
  "Explain how semantic search works.",
];

function extractAnswer(data: ChatResponse | unknown): string {
  if (typeof data === "string") return data;

  if (!data || typeof data !== "object") {
    return "I couldn't generate a response.";
  }

  const obj = data as Record<string, unknown>;

  const candidates = [
    obj.answer,
    obj.response,
    obj.message,
    obj.content,
  ];

  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }

  // Prevent React from rendering "[object Object]".
  if (obj.answer && typeof obj.answer === "object") {
    const nested = obj.answer as Record<string, unknown>;

    for (const key of ["answer", "response", "message", "content", "text"]) {
      if (
        typeof nested[key] === "string" &&
        (nested[key] as string).trim()
      ) {
        return nested[key] as string;
      }
    }
  }

  return "The repository context was not sufficient to answer this question.";
}

function formatAnswer(text: string) {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export default function Home() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);

  const [loadingRepos, setLoadingRepos] = useState(true);
  const [indexing, setIndexing] = useState(false);
  const [indexMessage, setIndexMessage] = useState("");

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<
    {
      role: "user" | "assistant";
      content: string;
      sources?: Source[];
    }[]
  >([]);

  const [asking, setAsking] = useState(false);

  const [showNewRepo, setShowNewRepo] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [repoBranch, setRepoBranch] = useState("main");
  const [connectingRepo, setConnectingRepo] = useState(false);
  const [repoError, setRepoError] = useState("");

  const indexed = selectedRepo?.status === "indexed";

  const statusLabel = useMemo(() => {
    if (indexing) return "Indexing";
    if (selectedRepo?.status === "error") return "Error";
    if (indexed) return "Indexed";
    return "Ready";
  }, [indexing, indexed, selectedRepo]);

  useEffect(() => {
    loadRepositories();
  }, []);

  async function loadRepositories() {
    try {
      setLoadingRepos(true);

      const response = await fetch(`${API_BASE}/repositories`);

      if (!response.ok) {
        throw new Error("Unable to load repositories.");
      }

      const data = await response.json();
      const repos = Array.isArray(data) ? data : [];

      setRepositories(repos);

      if (repos.length > 0) {
        setSelectedRepo(repos[0]);
      }
    } catch {
      setRepositories([]);
    } finally {
      setLoadingRepos(false);
    }
  }

  async function refreshRepository(repoId: number) {
    try {
      const response = await fetch(
        `${API_BASE}/repositories/${repoId}`
      );

      if (!response.ok) return;

      const repo = await response.json();

      setRepositories((current) =>
        current.map((item) =>
          item.id === repo.id ? repo : item
        )
      );

      setSelectedRepo(repo);
    } catch {
      // Keep existing UI state.
    }
  }

  async function indexRepository() {
    if (!selectedRepo || indexing) return;

    setIndexing(true);
    setIndexMessage("");

    try {
      const response = await fetch(
        `${API_BASE}/repositories/${selectedRepo.id}/index`,
        {
          method: "POST",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Repository indexing failed."
        );
      }

      await refreshRepository(selectedRepo.id);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Repository indexing failed.";

      setIndexMessage(message);
    } finally {
      setIndexing(false);
    }
  }

  async function askQuestion(value?: string) {
    const prompt = (value ?? question).trim();

    if (!prompt || !selectedRepo || asking) return;

    setQuestion("");
    setAsking(true);

    setMessages((current) => [
      ...current,
      {
        role: "user",
        content: prompt,
      },
    ]);

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          repository_id: selectedRepo.id,
          message: prompt,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Unable to answer the question."
        );
      }

      const answer = formatAnswer(extractAnswer(data));

      const sources = Array.isArray(data?.sources)
        ? data.sources
        : [];

      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: answer,
          sources,
        },
      ]);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Something went wrong.";

      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: message,
        },
      ]);
    } finally {
      setAsking(false);
    }
  }


  async function connectRepository() {
  const url = repoUrl.trim();

  if (!url || connectingRepo) return;

  setConnectingRepo(true);
  setRepoError("");

  try {
    const response = await fetch(`${API_BASE}/repositories`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url,
        branch: repoBranch.trim() || "main",
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        typeof data?.detail === "string"
          ? data.detail
          : "Unable to connect repository."
      );
    }

    setRepositories((current) => {
      const exists = current.some((repo) => repo.id === data.id);
      return exists
        ? current.map((repo) => (repo.id === data.id ? data : repo))
        : [data, ...current];
    });

    setSelectedRepo(data);
    setRepoUrl("");
    setRepoBranch("main");
    setShowNewRepo(false);

  } catch (error) {
    setRepoError(
      error instanceof Error
        ? error.message
        : "Unable to connect repository."
    );
  } finally {
    setConnectingRepo(false);
  }
}

  function handleKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      askQuestion();
    }
  }

  return (
    <main className="min-h-screen bg-[#08090b] text-white">


      {showNewRepo && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
    <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#101114] p-6 shadow-2xl">

      <div className="mb-6 flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">
            Connect repository
          </h2>

          <p className="mt-1 text-xs text-white/40">
            Add a GitHub repository to your workspace.
          </p>
        </div>

        <button
          onClick={() => setShowNewRepo(false)}
          className="rounded-lg px-2 py-1 text-white/40 transition hover:bg-white/[0.06] hover:text-white"
        >
          ×
        </button>
      </div>

      <div className="space-y-4">

        <div>
          <label className="mb-2 block text-[11px] font-medium text-white/50">
            Repository URL
          </label>

          <input
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                connectRepository();
              }
            }}
            placeholder="https://github.com/username/repository"
            className="w-full rounded-xl border border-white/[0.08] bg-white/[0.025] px-3 py-3 text-sm text-white outline-none placeholder:text-white/20 focus:border-white/[0.18]"
            autoFocus
          />
        </div>

        <div>
          <label className="mb-2 block text-[11px] font-medium text-white/50">
            Branch
          </label>

          <input
            value={repoBranch}
            onChange={(e) => setRepoBranch(e.target.value)}
            placeholder="main"
            className="w-full rounded-xl border border-white/[0.08] bg-white/[0.025] px-3 py-3 text-sm text-white outline-none placeholder:text-white/20 focus:border-white/[0.18]"
          />
        </div>

        {repoError && (
          <div className="rounded-xl border border-red-400/10 bg-red-400/[0.06] px-3 py-2.5 text-xs text-red-300">
            {repoError}
          </div>
        )}

        <button
          onClick={connectRepository}
          disabled={!repoUrl.trim() || connectingRepo}
          className="w-full rounded-xl bg-white px-4 py-3 text-sm font-medium text-black transition hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {connectingRepo ? "Connecting..." : "Connect repository"}
        </button>

      </div>
    </div>
  </div>
)}
      <div className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="hidden w-[260px] shrink-0 border-r border-white/[0.07] bg-[#0b0c0f] px-5 py-6 lg:block">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-sm font-bold text-black">
              RP
            </div>

            <div>
              <div className="text-[15px] font-semibold tracking-tight">
                RepoPilot
              </div>
              <div className="text-[11px] text-white/40">
                AI Code Intelligence
              </div>
            </div>
          </div>

          <div className="mt-10">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35">
                Workspace
              </span>

              <button
                onClick={loadRepositories}
                className="rounded-md p-1.5 text-white/40 transition hover:bg-white/[0.06] hover:text-white"
                aria-label="Refresh repositories"
              >
                ↻
              </button>
            </div>

            <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
              <div className="mb-1 text-[11px] text-white/40">
                GitHub repository
              </div>

              <div className="truncate text-sm text-white/85">
                {selectedRepo?.name || "No repository"}
              </div>

              <div className="mt-1 text-[11px] text-white/30">
                {selectedRepo?.branch || "main"}
              </div>
            </div>
          </div>

          <div className="mt-7">
            <div className="mb-3 flex items-center justify-between">
  <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35">
    Repositories
  </div>

  <button
    onClick={() => {
      setRepoError("");
      setShowNewRepo(true);
    }}
    className="flex h-6 w-6 items-center justify-center rounded-md border border-white/[0.08] bg-white/[0.025] text-sm text-white/45 transition hover:border-white/[0.15] hover:bg-white/[0.07] hover:text-white"
    title="Connect repository"
  >
    +
  </button>
</div> 

            {loadingRepos ? (
              <div className="rounded-lg px-3 py-2 text-xs text-white/30">
                Loading workspace
              </div>
            ) : repositories.length === 0 ? (
              <div className="rounded-lg px-3 py-2 text-xs text-white/30">
                No repositories connected
              </div>
            ) : (
              <div className="space-y-1">
                {repositories.map((repo) => (
                  <button
                    key={repo.id}
                    onClick={() => setSelectedRepo(repo)}
                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                      selectedRepo?.id === repo.id
                        ? "bg-white/[0.07] text-white"
                        : "text-white/50 hover:bg-white/[0.04] hover:text-white/80"
                    }`}
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-white/30" />

                    <span className="min-w-0 flex-1 truncate">
                      {repo.name}
                    </span>

                    {repo.status === "indexed" && (
                      <span className="text-[10px] text-white/30">
                        indexed
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="absolute bottom-6 left-5 right-5 lg:w-[220px]">
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
              <div className="flex items-center gap-2 text-[11px] text-white/45">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" />
                Private by design
              </div>

              <div className="mt-1 text-[10px] text-white/25">
                Models run locally through Ollama.
              </div>
            </div>
          </div>
        </aside>

        {/* Main */}
        <section className="flex min-w-0 flex-1 flex-col">
          {/* Top bar */}
          <header className="flex h-16 items-center justify-between border-b border-white/[0.07] px-5 lg:px-8">
            <div className="flex items-center gap-3 lg:hidden">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-xs font-bold text-black">
                RP
              </div>

              <div className="text-sm font-semibold">
                RepoPilot
              </div>
            </div>

            <div className="hidden lg:block" />

            <div className="flex items-center gap-2">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  statusLabel === "Error"
                    ? "bg-red-400"
                    : statusLabel === "Indexing"
                    ? "bg-amber-400"
                    : "bg-emerald-400"
                }`}
              />

              <span className="text-[11px] text-white/40">
                {statusLabel}
              </span>
            </div>
          </header>

          {/* Workspace content */}
          <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-5 py-8 lg:px-8">
            {/* Repository card */}
            <div className="rounded-2xl border border-white/[0.07] bg-white/[0.018] p-5">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/30">
                    Codebase intelligence
                  </div>

                  <h1 className="truncate text-xl font-semibold tracking-tight">
                    {selectedRepo?.name || "No repository selected"}
                  </h1>

                  {selectedRepo?.url && (
                    <a
                      href={selectedRepo.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block truncate text-xs text-white/35 transition hover:text-white/60"
                    >
                      {selectedRepo.url} ↗
                    </a>
                  )}
                </div>

                <div className="flex shrink-0 items-center gap-3">
                  <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.025] px-3 py-2">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        indexed
                          ? "bg-emerald-400"
                          : indexing
                          ? "bg-amber-400"
                          : "bg-white/25"
                      }`}
                    />

                    <span className="text-xs text-white/50">
                      {indexing
                        ? "Indexing"
                        : indexed
                        ? "Indexed"
                        : "Not indexed"}
                    </span>
                  </div>

                  <button
                    onClick={indexRepository}
                    disabled={!selectedRepo || indexing}
                    className="rounded-lg bg-white px-4 py-2 text-xs font-medium text-black transition hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {indexing ? "Indexing…" : "Index repository"}
                  </button>
                </div>
              </div>

              {indexing && (
                <div className="mt-4 flex items-center gap-2 border-t border-white/[0.05] pt-3 text-[11px] text-white/35">
                  <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border border-white/20 border-t-white/70" />
                  <span>Updating repository intelligence</span>
                </div>
              )}

              {indexMessage && (
                <div className="mt-3 rounded-lg border border-red-400/10 bg-red-400/[0.04] px-3 py-2 text-xs text-red-300/80">
                  {indexMessage}
                </div>
              )}
            </div>

            {/* Chat */}
            <div className="mt-8 flex flex-1 flex-col">
              <div className="mb-7">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/30">
                  RepoPilot intelligence
                </div>

                <h2 className="text-2xl font-semibold tracking-tight">
                  Understand your codebase.
                  <br />
                  <span className="text-white/35">
                    Ship with confidence.
                  </span>
                </h2>

                <p className="mt-3 max-w-xl text-sm leading-6 text-white/40">
                  Ask questions about architecture, implementation
                  details, bugs, or specific files. Answers are
                  grounded in indexed repository code.
                </p>
              </div>

              {messages.length === 0 && (
                <div className="grid gap-2 sm:grid-cols-2">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => askQuestion(prompt)}
                      disabled={!selectedRepo || asking}
                      className="group rounded-xl border border-white/[0.06] bg-white/[0.018] px-4 py-3 text-left text-xs text-white/45 transition hover:border-white/[0.11] hover:bg-white/[0.035] hover:text-white/75 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <span>{prompt}</span>
                      <span className="ml-2 text-white/20 transition group-hover:text-white/50">
                        →
                      </span>
                    </button>
                  ))}
                </div>
              )}

              <div className="mt-7 space-y-6">
                {messages.map((message, index) => (
                  <div
                    key={`${message.role}-${index}`}
                    className="flex gap-3"
                  >
                    <div
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[10px] font-semibold ${
                        message.role === "user"
                          ? "bg-white/[0.08] text-white/70"
                          : "bg-white text-black"
                      }`}
                    >
                      {message.role === "user" ? "A" : "RP"}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="mb-1 text-[11px] font-medium text-white/35">
                        {message.role === "user"
                          ? "You"
                          : "RepoPilot"}
                      </div>

                      <div className="whitespace-pre-wrap text-sm leading-7 text-white/75">
                        {message.content}
                      </div>

                      {message.sources &&
                        message.sources.length > 0 && (
                          <div className="mt-4 flex flex-wrap gap-2">
                            {message.sources.slice(0, 5).map(
                              (source, sourceIndex) => (
                                <div
                                  key={`${source.file_path}-${sourceIndex}`}
                                  className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-[10px] text-white/35"
                                >
                                  {source.file_path}
                                  {typeof source.start_line ===
                                    "number" &&
                                    `:${source.start_line}`}
                                </div>
                              )
                            )}
                          </div>
                        )}
                    </div>
                  </div>
                ))}

                {asking && (
                  <div className="flex gap-3">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white text-[10px] font-semibold text-black">
                      RP
                    </div>

                    <div>
                      <div className="mb-2 text-[11px] font-medium text-white/35">
                        RepoPilot
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/30" />
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/20 [animation-delay:150ms]" />
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/10 [animation-delay:300ms]" />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Composer */}
              <div className="mt-auto pt-10">
                <div className="rounded-2xl border border-white/[0.08] bg-[#0d0f12] p-2 shadow-2xl shadow-black/20">
                  <textarea
                    value={question}
                    onChange={(event) =>
                      setQuestion(event.target.value)
                    }
                    onKeyDown={handleKeyDown}
                    disabled={!selectedRepo || asking}
                    placeholder={
                      selectedRepo
                        ? "Ask anything about your codebase…"
                        : "Connect a repository to begin…"
                    }
                    rows={2}
                    className="w-full resize-none bg-transparent px-3 py-2 text-sm leading-6 text-white outline-none placeholder:text-white/20 disabled:cursor-not-allowed"
                  />

                  <div className="flex items-center justify-between px-2 pb-1">
                    <span className="text-[10px] text-white/25">
                      Enter to send · Shift + Enter for new line
                    </span>

                    <button
                      onClick={() => askQuestion()}
                      disabled={
                        !question.trim() ||
                        !selectedRepo ||
                        asking
                      }
                      className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-black transition hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-20"
                      aria-label="Send question"
                    >
                      ↑
                    </button>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-center gap-2 text-[10px] text-white/20">
                  <span>● Grounded answers</span>
                  <span>·</span>
                  <span>Local inference</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
