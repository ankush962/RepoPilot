const { test, expect } = require("@playwright/test");

const workspace = {
  id: 1,
  name: "Default Workspace",
  slug: "default",
};

const repository = {
  id: 42,
  name: "demo-repository",
  url: "https://github.com/example/demo-repository",
  branch: "main",
  status: "indexed",
  last_indexed_commit: "1234567890abcdef1234567890abcdef12345678",
};

const dashboard = {
  repository: {
    name: repository.name,
    branch: repository.branch,
    status: "indexed",
    last_indexed_commit: repository.last_indexed_commit,
  },
  statistics: {
    files_indexed: 12,
    total_chunks: 48,
    embedded_chunks: 48,
    embedding_status: "complete",
  },
  health: {
    status: "healthy",
    index_ready: true,
    needs_update: false,
  },
  latest_job: {
    id: 7,
    status: "completed",
    progress: 100,
    stage: "complete",
    result_chunks: 48,
    result_vectors: 48,
  },
  indexing_history: [],
};

const explorerFiles = [
  "backend/app/main.py",
  "backend/app/services/indexer.py",
  "frontend/app/page.jsx",
];

const chatAnswer =
  "The repository uses a FastAPI backend and a Next.js frontend.";

const chatSource = {
  file_path: "backend/app/main.py",
  start_line: 1,
  end_line: 20,
  similarity: 0.91,
  content: "FastAPI application entry point.",
};

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

function streamResponse() {
  const encoder = new TextEncoder();

  const chunks = [
    `data: ${JSON.stringify({
      type: "token",
      content: chatAnswer,
    })}\n\n`,
    `data: ${JSON.stringify({
      type: "sources",
      sources: [chatSource],
    })}\n\n`,
    `data: ${JSON.stringify({
      type: "metrics",
      metrics: {
        sources: 1,
        top_similarity: 0.91,
        latency_seconds: 0.2,
        grounding: "grounded",
      },
    })}\n\n`,
    "data: [DONE]\n\n",
  ];

  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(
    ({
      workspace,
      repository,
      dashboard,
      explorerFiles,
      chatSource,
      chatAnswer,
    }) => {
      const originalFetch = window.fetch;

      window.fetch = async function (input, init) {
        const url =
          typeof input === "string"
            ? input
            : input instanceof Request
              ? input.url
              : String(input);

        const method =
          init?.method ||
          (input instanceof Request ? input.method : "GET");

        if (url.includes("/workspaces")) {
          return new Response(
            JSON.stringify([workspace]),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
              },
            },
          );
        }

        if (
          url.includes("/repositories") &&
          method === "GET" &&
          !url.includes("/dashboard") &&
          !url.includes("/files") &&
          !url.includes("/architecture") &&
          !url.includes("/git/")
        ) {
          return new Response(
            JSON.stringify([repository]),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
              },
            },
          );
        }

        if (url.includes(`/repositories/${repository.id}/dashboard`)) {
          return new Response(
            JSON.stringify(dashboard),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
              },
            },
          );
        }

        if (url.includes(`/repositories/${repository.id}/files`)) {
          return new Response(
            JSON.stringify({
              files: explorerFiles,
            }),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
              },
            },
          );
        }

        if (
          url.includes(
            `/repositories/${repository.id}/git/status`,
          )
        ) {
          return new Response(
            JSON.stringify({
              last_indexed_commit:
                repository.last_indexed_commit,
              remote_commit:
                repository.last_indexed_commit,
              needs_update: false,
            }),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
              },
            },
          );
        }

        if (
          url.includes(
            `/repositories/${repository.id}/architecture`,
          )
        ) {
          return new Response(
            JSON.stringify({
              summary: "Demo architecture",
              symbols: {
                files: 12,
                classes: 4,
                functions: 28,
                routes: 6,
              },
            }),
            {
              status: 200,
              headers: {
                "Content-Type": "application/json",
              },
            },
          );
        }

        if (url.includes("/chat/stream")) {
          const encoder = new TextEncoder();

          const chunks = [
            `data: ${JSON.stringify({
              type: "token",
              content: chatAnswer,
            })}\n\n`,
            `data: ${JSON.stringify({
              type: "sources",
              sources: [chatSource],
            })}\n\n`,
            `data: ${JSON.stringify({
              type: "metrics",
              metrics: {
                sources: 1,
                top_similarity: 0.91,
                latency_seconds: 0.2,
                grounding: "grounded",
              },
            })}\n\n`,
            "data: [DONE]\n\n",
          ];

          const body = new ReadableStream({
            start(controller) {
              for (const chunk of chunks) {
                controller.enqueue(
                  encoder.encode(chunk),
                );
              }
              controller.close();
            },
          });

          return new Response(body, {
            status: 200,
            headers: {
              "Content-Type": "text/event-stream",
              "Cache-Control": "no-cache",
            },
          });
        }

        return originalFetch.apply(this, arguments);
      };
    },
    {
      workspace,
      repository,
      dashboard,
      explorerFiles,
      chatSource,
      chatAnswer,
    },
  );
});

test("loads the RepoPilot workspace and repository", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByText("Repositories", { exact: true }),
  ).toBeVisible();

  await expect(
    page.getByRole("heading", {
      name: repository.name,
      exact: true,
    }),
  ).toBeVisible();

  await expect(
    page.getByText("Indexed", { exact: true }).first(),
  ).toBeVisible();
});

test("opens dashboard and explorer", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: repository.name,
      exact: true,
    }),
  ).toBeVisible();

  await expect(
    page.getByText("Repository dashboard", {
      exact: true,
    }),
  ).toBeVisible();

  await expect(
    page.getByText("Files indexed", {
      exact: true,
    }),
  ).toBeVisible();

  await expect(
    page.getByText("12", { exact: true }),
  ).toBeVisible();

  await expect(
    page.getByText("48", { exact: true }),
  ).toBeVisible();

  await expect(
    page.getByText("Healthy", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", {
    name: "Explorer",
  }).click();

  await expect(
    page.getByText("Codebase explorer", {
      exact: true,
    }),
  ).toBeVisible();

  await expect(
    page.getByText("backend/app/main.py", {
      exact: true,
    }),
  ).toBeVisible();

  await expect(
    page.getByText("frontend/app/page.jsx", {
      exact: true,
    }),
  ).toBeVisible();
});

test("submits a grounded codebase question", async ({
  page,
}) => {
  await page.goto("/");

  const question = page.getByPlaceholder(
    "Ask about your codebase…",
  );

  await expect(question).toBeVisible();

  await question.fill(
    "How is the application structured?",
  );

  await question.press("Enter");

  await expect(
    page.getByText(
      "How is the application structured?",
      { exact: true },
    ),
  ).toBeVisible();

  await expect(
    page.getByText(chatAnswer, {
      exact: true,
    }),
  ).toBeVisible();

  await expect(
    page.getByText("1 sources", {
      exact: true,
    }),
  ).toBeVisible();
});
