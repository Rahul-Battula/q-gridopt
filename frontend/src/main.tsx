import "@fontsource/plus-jakarta-sans/400.css";
import "@fontsource/plus-jakarta-sans/500.css";
import "@fontsource/plus-jakarta-sans/600.css";
import "@fontsource/plus-jakarta-sans/700.css";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, lazy } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { Layout } from "./components/Layout";
import { ScenarioProvider } from "./components/ScenarioContext";

// Each page is its own bundle chunk, downloaded the first time the page is opened.
const Overview = lazy(() => import("./pages/Overview").then((m) => ({ default: m.Overview })));
const Quantum = lazy(() => import("./pages/Quantum").then((m) => ({ default: m.Quantum })));
const Hardware = lazy(() => import("./pages/Hardware").then((m) => ({ default: m.Hardware })));
const Runs = lazy(() => import("./pages/Runs").then((m) => ({ default: m.Runs })));
const RunDetail = lazy(() => import("./pages/RunDetail").then((m) => ({ default: m.RunDetail })));
const Grover = lazy(() => import("./pages/Grover").then((m) => ({ default: m.Grover })));
const Benchmark = lazy(() => import("./pages/Benchmark").then((m) => ({ default: m.Benchmark })));

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "quantum", element: <Quantum /> },
      { path: "hardware", element: <Hardware /> },
      { path: "runs", element: <Runs /> },
      { path: "runs/:runId", element: <RunDetail /> },
      { path: "benchmark", element: <Benchmark /> },
      { path: "grover", element: <Grover /> },
    ],
  },
]);

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ScenarioProvider>
        <RouterProvider router={router} />
      </ScenarioProvider>
    </QueryClientProvider>
  </StrictMode>,
);
