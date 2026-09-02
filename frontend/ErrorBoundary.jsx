"use client";

import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error("RepoPilot UI error", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-[#08090b] px-6 text-white">
        <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-white/[0.025] p-6">
          <h1 className="text-sm font-semibold">Something went wrong</h1>
          <p className="mt-2 text-xs leading-5 text-white/35">
            RepoPilot could not render this workspace.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-5 rounded-lg bg-white px-3.5 py-2 text-xs font-semibold text-black"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
