"use client";

import { useEffect } from "react";

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-[#08090b] text-white">
        <main className="flex min-h-screen items-center justify-center px-6">
          <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-white/[0.025] p-6">
            <div className="text-sm font-semibold">RepoPilot hit an unexpected error</div>
            <p className="mt-2 text-xs leading-5 text-white/35">
              The workspace could not render this screen. Your repository data is unchanged.
            </p>
            <button
              onClick={() => reset()}
              className="mt-5 rounded-lg bg-white px-3.5 py-2 text-xs font-semibold text-black hover:bg-white/90"
            >
              Reload workspace
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
