"use client";

import { useEffect, useMemo, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Repo = {
  id: number;
  name: string;
  url: string;
  branch: string;
  status: string;
  created_at: string;
  updated_at?: string;
  last_indexed_commit?: string | null;
};

type Source = {
  file_path: string;
  start_line: number;
  end_line: number;
  content: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

type BusyState =
  | "connect"
  | "index"
  | "chat"
  | "load"
  | null;

function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    logo: "M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 0v9m0 0 8-4.5M12 12 4 7.5m8 0 8 4.5",
    repo: "M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9ZM8 9.5l4 2.25 4-2.25M8 14l4 2.25L16 14",
    index: "M12 3v12m0 0 4-4m-4 4-4-4M5 20h14",
    send: "M3 11.5 21 3l-5.5 18-4-7.5L3 11.5Zm8.5 2L21 3",
    file: "M6 3h8l4 4v14H6V3Zm8 0v5h4",
    external: "M14 5h5v5m-1-4-9 9",
    spark:
      "M12 3l1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Z",
  };

  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="icon"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name] || paths.spark} />
    </svg>
  );
}

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [url, setUrl] = useState("");
  const [question, setQuestion] = useState("");

  const [messages, setMessages] = useState<Message[]>([]);
  const [sources, setSources] = useState<Source[]>([]);

  const [busy, setBusy] = useState<BusyState>(null);

  const [activity, setActivity] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [activeSource, setActiveSource] =
    useState<Source | null>(null);

  const selected = useMemo(
    () => repos.find((r) => r.id === selectedId) || null,
    [repos, selectedId]
  );

  async function request(
    path: string,
    options?: RequestInit
  ) {
    const res = await fetch(`${API}${path}`, options);

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(
        data.detail || `Request failed (${res.status})`
      );
    }

    return data;
  }

  async function loadRepos() {
    setBusy("load");
    setError("");

    try {
      const data: Repo[] = await request("/repositories");

      setRepos(data);

      if (data.length > 0 && selectedId === null) {
        setSelectedId(data[0].id);
      }
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not load repositories."
      );
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    loadRepos();
  }, []);

  async function connect() {
    const repoUrl = url.trim();

    if (!repoUrl) return;

    setBusy("connect");
    setError("");
    setNotice("");
    setActivity("Connecting repository...");

    try {
      const repo: Repo = await request("/repositories", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          url: repoUrl,
          branch: "main",
        }),
      });

      setRepos((prev) => [
        repo,
        ...prev.filter((r) => r.id !== repo.id),
      ]);

      setSelectedId(repo.id);
      setUrl("");

      setNotice(`Connected ${repo.name}`);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not connect repository."
      );
    } finally {
      setBusy(null);
      setActivity("");
    }
  }

  async function indexRepo() {
    if (selectedId === null) return;

    setBusy("index");
    setError("");
    setNotice("");

    try {
      setActivity("Checking repository...");

      const data = await request(
        `/repositories/${selectedId}/index`,
        {
          method: "POST",
        }
      );

      setRepos((prev) =>
        prev.map((repo) =>
          repo.id === selectedId
            ? {
                ...repo,
                status: "indexed",
                last_indexed_commit:
                  data.commit ??
                  repo.last_indexed_commit,
              }
            : repo
        )
      );

      setNotice(
        data.chunks !== undefined
          ? `Repository indexed successfully. ${data.chunks} chunks processed.`
          : "Repository indexed successfully."
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Indexing failed."
      );
    } finally {
      setBusy(null);
      setActivity("");
    }
  }

  async function ask(text = question) {
    const message = text.trim();

    if (selectedId === null || !message) return;

    setQuestion("");
    setError("");
    setNotice("");
    setBusy("chat");

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: message,
      },
    ]);

    try {
      setActivity("Searching indexed code...");

      const data = await request("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          repository_id: selectedId,
          message,
        }),
      });

      const answerSources: Source[] = data.sources || [];

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            data.answer || "No answer returned.",
          sources: answerSources,
        },
      ]);

      setSources(answerSources);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "RepoPilot request failed."
      );
    } finally {
      setBusy(null);
      setActivity("");
    }
  }

  const suggestions = [
    "What does this project do?",
    "Explain the backend architecture.",
    "Where is repository indexing implemented?",
    "Find potential bugs or weak points.",
    "What vector database and embedding model does this project use?",
    "Explain how semantic search works.",
  ];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="logo" />
          </div>

          <div>
            <strong>RepoPilot</strong>
            <span>AI Codebase Intelligence</span>
          </div>
        </div>

        <div className="top-status">
          <span className="status-dot" />
          Local AI
          <span className="divider" />
          <span>Ollama + pgvector</span>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <div className="side-heading">
            <span>WORKSPACE</span>

            <button
              className="icon-button"
              onClick={loadRepos}
              disabled={busy !== null}
              title="Refresh repositories"
            >
              ↻
            </button>
          </div>

          <label className="field-label">
            GitHub repository
          </label>

          <div className="connect-box">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  connect();
                }
              }}
              placeholder="https://github.com/user/repo"
            />

            <button
              className="primary-button"
              onClick={connect}
              disabled={
                busy !== null || !url.trim()
              }
            >
              {busy === "connect" ? (
                <span className="spinner" />
              ) : (
                <Icon name="external" />
              )}
              Connect
            </button>
          </div>

          <div className="repo-list">
            <div className="list-title">
              Repositories
            </div>

            {repos.length === 0 ? (
              <div className="empty-repos">
                <Icon name="repo" />
                <p>No repositories yet</p>
                <span>
                  Connect a public GitHub repository
                  to begin.
                </span>
              </div>
            ) : (
              repos.map((repo) => (
                <button
                  key={repo.id}
                  className={`repo-item ${
                    selectedId === repo.id
                      ? "active"
                      : ""
                  }`}
                  onClick={() => {
                    setSelectedId(repo.id);
                    setMessages([]);
                    setSources([]);
                    setError("");
                    setNotice("");
                  }}
                >
                  <div className="repo-icon">
                    <Icon name="repo" />
                  </div>

                  <div className="repo-copy">
                    <b>{repo.name}</b>
                    <span>{repo.branch}</span>
                  </div>

                  <span
                    className={`repo-state ${repo.status}`}
                  >
                    {repo.status}
                  </span>
                </button>
              ))
            )}
          </div>

          <div className="sidebar-footer">
            <div className="stack-card">
              <div className="stack-icon">
                <Icon name="spark" />
              </div>

              <div>
                <b>Private by design</b>
                <span>
                  Models run locally through Ollama.
                </span>
              </div>
            </div>
          </div>
        </aside>

        <section className="main-panel">
          <div className="repo-header">
            <div>
              <div className="eyebrow">
                CODEBASE INTELLIGENCE
              </div>

              <h1>
                {selected?.name ||
                  "Connect a repository"}
              </h1>

              <p>
                {selected?.url ||
                  "Add a GitHub repository to start exploring its code with AI."}
              </p>
            </div>

            {selected && (
              <div className="repo-actions">
                <span
                  className={`pill ${selected.status}`}
                >
                  <span className="mini-dot" />
                  {selected.status}
                </span>

                <button
                  className="secondary-button"
                  onClick={indexRepo}
                  disabled={busy !== null}
                >
                  {busy === "index" ? (
                    <span className="spinner dark" />
                  ) : (
                    <Icon name="index" />
                  )}

                  {busy === "index"
                    ? "Indexing..."
                    : "Index repository"}
                </button>
              </div>
            )}
          </div>

          {(error || notice) && (
            <div
              className={`alert ${
                error ? "error" : "success"
              }`}
            >
              <span>{error || notice}</span>

              <button
                onClick={() => {
                  setError("");
                  setNotice("");
                }}
              >
                ×
              </button>
            </div>
          )}

          {activity && (
            <div className="activity-bar">
              <span className="activity-spinner" />
              <span>{activity}</span>
            </div>
          )}

          <div className="chat-area">
            {messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-icon">
                  <Icon name="spark" />
                </div>

                <div className="eyebrow">
                  REPOPILOT INTELLIGENCE
                </div>

                <h2>
                  Understand your codebase.
                  <br />
                  <span>
                    Ship with confidence.
                  </span>
                </h2>

                <p>
                  Ask questions about architecture,
                  implementation details, bugs, or
                  specific files. Answers are grounded
                  in indexed repository code.
                </p>

                <div className="suggestions">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => ask(suggestion)}
                      disabled={
                        selectedId === null ||
                        busy !== null
                      }
                    >
                      <span>{suggestion}</span>
                      <span>→</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="conversation">
                {messages.map((message, index) => (
                  <div
                    key={index}
                    className={`message ${message.role}`}
                  >
                    <div className="avatar">
                      {message.role === "assistant" ? (
                        <Icon name="spark" />
                      ) : (
                        "A"
                      )}
                    </div>

                    <div className="message-body">
                      <div className="message-name">
                        {message.role === "assistant"
                          ? "RepoPilot"
                          : "You"}
                      </div>

                      <div className="message-content">
                        {message.content}
                      </div>

                      {message.sources &&
                        message.sources.length > 0 && (
                          <div className="source-chips">
                            {message.sources
                              .slice(0, 5)
                              .map((source, index) => (
                                <button
                                  key={`${source.file_path}-${index}`}
                                  onClick={() =>
                                    setActiveSource(
                                      source
                                    )
                                  }
                                >
                                  <Icon name="file" />
                                  {source.file_path}:
                                  {source.start_line}
                                </button>
                              ))}
                          </div>
                        )}
                    </div>
                  </div>
                ))}

                {busy === "chat" && (
                  <div className="message assistant">
                    <div className="avatar">
                      <Icon name="spark" />
                    </div>

                    <div className="message-body">
                      <div className="message-name">
                        RepoPilot
                      </div>

                      <div className="typing">
                        <i />
                        <i />
                        <i />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="composer-wrap">
            <div className="composer">
              <textarea
                value={question}
                onChange={(e) =>
                  setQuestion(e.target.value)
                }
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey
                  ) {
                    e.preventDefault();
                    ask();
                  }
                }}
                placeholder={
                  selectedId !== null
                    ? "Ask anything about this codebase..."
                    : "Connect a repository first..."
                }
                disabled={
                  selectedId === null ||
                  busy !== null
                }
                rows={1}
              />

              <button
                className="send-button"
                onClick={() => ask()}
                disabled={
                  selectedId === null ||
                  !question.trim() ||
                  busy !== null
                }
              >
                {busy === "chat" ? (
                  <span className="spinner" />
                ) : (
                  <Icon name="send" />
                )}
              </button>
            </div>

            <div className="composer-hint">
              <span>
                Enter to send · Shift + Enter for
                new line
              </span>

              <span>
                Grounded answers · Local inference
              </span>
            </div>
          </div>
        </section>

        <aside className="sources-panel">
          <div className="sources-header">
            <div>
              <div className="eyebrow">CONTEXT</div>
              <h3>Sources</h3>
            </div>

            <span className="count">
              {sources.length}
            </span>
          </div>

          {sources.length === 0 ? (
            <div className="sources-empty">
              <Icon name="file" />

              <b>Relevant files appear here</b>

              <span>
                Ask RepoPilot a question to see the
                code used to ground its answer.
              </span>
            </div>
          ) : (
            <div className="source-list">
              {sources.map((source, index) => (
                <button
                  className="source-card"
                  key={`${source.file_path}-${index}`}
                  onClick={() =>
                    setActiveSource(source)
                  }
                >
                  <div className="source-top">
                    <Icon name="file" />
                    <span>{source.file_path}</span>
                  </div>

                  <span className="line-range">
                    Lines {source.start_line}–
                    {source.end_line}
                  </span>

                  <code>
                    {source.content
                      .slice(0, 150)
                      .replace(/\n/g, " ")}
                    {source.content.length > 150
                      ? "…"
                      : ""}
                  </code>
                </button>
              ))}
            </div>
          )}
        </aside>
      </div>

      {activeSource && (
        <div
          className="modal-backdrop"
          onClick={() => setActiveSource(null)}
        >
          <div
            className="source-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <div className="eyebrow">
                  SOURCE
                </div>

                <h3>{activeSource.file_path}</h3>

                <span>
                  Lines {activeSource.start_line}–
                  {activeSource.end_line}
                </span>
              </div>

              <button
                className="close-button"
                onClick={() =>
                  setActiveSource(null)
                }
              >
                ×
              </button>
            </div>

            <pre>
              <code>{activeSource.content}</code>
            </pre>
          </div>
        </div>
      )}
    </main>
  );
}