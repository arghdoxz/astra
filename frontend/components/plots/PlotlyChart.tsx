"use client";

// Internal: the only module that imports plotly.js. Always loaded through ./LazyPlot (next/dynamic, ssr:false).
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";

const Plot = createPlotlyComponent(Plotly);
export default Plot;
