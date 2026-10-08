// Chart colours mirror the CSS theme tokens in index.css.
export const C = {
  solar: "#D9980B",
  wind: "#3E8E41",
  gas: "#C2570C",
  battery: "#7A5FA8",
  unserved: "#B3261E",
  demand: "#14172E",
  quantum: "#5B3FD8",
  noisy: "#0AA5C2",
  ibm: "#1F5FBF",
  classical: "#8A877D",
  ok: "#2E7D4F",
  bad: "#B3261E",
  grid: "#E0E3F0",
  axis: "#565B7A",
  panel: "#FFFFFF",
  line: "#C7CCE6",
};

export const FONT_MONO = "Plus Jakarta Sans, sans-serif";

export const axisProps = {
  stroke: "transparent",
  tick: { fill: C.axis, fontSize: 11, fontFamily: FONT_MONO },
  tickLine: false,
  axisLine: false,
};

export const tooltipProps = {
  contentStyle: {
    background: "#FFFFFF",
    border: "1px solid #C7CCE6",
    borderRadius: 6,
    fontFamily: FONT_MONO,
    fontSize: 12,
    boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
    padding: "10px 12px",
  },
  labelStyle: { color: "#14172E", marginBottom: 4 },
  itemStyle: { padding: 0 },
  cursor: { fill: "rgba(91,63,216,0.06)" },
};

export const legendProps = {
  wrapperStyle: { fontSize: 11, fontFamily: FONT_MONO, paddingTop: 6 },
  iconType: "circle" as const,
  iconSize: 8,
};
