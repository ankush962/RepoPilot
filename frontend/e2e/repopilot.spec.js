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

test.beforeEach(async ({ page }) => {
  await page.route("**/workspaces*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([workspace]),
    });
  });

  await page.route("**/repositories*", async (route) => {
    const request = route.request();

    if (request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([repository]),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(repository),
    });
  });

  await page.route(
    `**/repositories/${repository.id}/dashboard`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(dashboard),
      });
    },
  );

  await page.route(
    `**/repositories/${repository.id}/files`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          files: explorerFiles,
        }),
      });
    },
  );

  await page.route(
    `**/repositories/${repository.id}/git/status`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          last_indexed_commit: repository.last_indexed_commit,
          remote_commit: repository.last_indexed_commit,
          needs_update: false,
        }),
      });
    },
  );

  await page.route(
    `**/repositories/${repository.id}/architecture`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          summary: "Demo architecture",
          symbols: {
            files: 12,
            classes: 4,
            functions: 28,
            routes: 6,
          },
        }),
      });
    },
  );

  await page.route("**/chat/stream", async (route) => {
    const body = [
      "data: ",
      JSON.stringify({
        type: "token",
        content:
          "The repository uses a FastAPI backend and a Next.js frontend.",
      }),
      "\n\n",
      "data: ",
      JSON.stringify({
        type: "sources",
        sources: [
          {
            file_path: "backend/app/main.py",
            start_line: 1,
            end_line: 20,
            similarity: 0.91,
            content: "FastAPI application entry point.",
          },
        ],
      }),
      "\n\n",
      "data: ",
      JSON.stringify({
        type: "metrics",
        metrics: {
          sources: 1,
          top_similarity: 0.91,
          latency_seconds: 0.2,
          grounding: "grounded",
        },
      }),
      "\n\n",
      "data: [DONE]\n\n",
    ].join("");

    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });
});

test("loads the RepoPilot workspace and repository", async ({ page }) => {
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

  await expect(page.getByText("12", { exact: true })).toBeVisible();
  await expect(page.getByText("48", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Healthy", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Explorer" }).click();

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

test("submits a grounded codebase question", async ({ page }) => {
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
    page.getByText(
      "The repository uses a FastAPI backend and a Next.js frontend.",
      { exact: true },
    ),
  ).toBeVisible();

  await expect(
    page.getByText("1 sources", { exact: true }),
  ).toBeVisible();
});
