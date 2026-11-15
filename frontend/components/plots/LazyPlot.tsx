"use client";

import dynamic from "next/dynamic";

/** Plotly is heavy and touches `window`; load it lazily and only in the browser. */
const LazyPlot = dynamic(() => import("./PlotlyChart"), {
  ssr: false,
  loading: () => (
    <div
      role="status"
      className="flex h-[320px] w-full items-center justify-center rounded-sm border border-dashed border-[#1d2742] text-xs text-[#8a97b4]"
    >
      Loading plot…
    </div>
  ),
});

export default LazyPlot;
