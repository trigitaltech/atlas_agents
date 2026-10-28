import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, Link } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  Bot,
  Compass,
  Database,
  Globe2,
  LayoutDashboard,
  Settings as SettingsIcon,
} from "lucide-react";
import Dashboard from "./pages/Dashboard";
import Agents from "./pages/Agents";
import Scrape from "./pages/Scrape";
import Jobs from "./pages/Jobs";
import Monitor from "./pages/Monitor";
import Results from "./pages/Results";
import Settings from "./pages/Settings";
import "./styles.css";
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000, refetchOnWindowFocus: true } },
});
const nav = [
  ["/", "Overview", LayoutDashboard],
  ["/agents", "Agent builder", Bot],
  ["/scrape", "Web intelligence", Globe2],
  ["/jobs", "Executions", Activity],
  ["/results", "Results", Database],
] as const;
function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <aside className="sidebar">
          <Link to="/" className="brand">
            <div className="brand-mark">
              <Compass size={25} />
            </div>
            <span>
              atlas<span className="brand-dot">.</span>
            </span>
          </Link>
          <div className="workspace-switch">
            <span className="workspace-avatar">W</span>
            <div>
              My workspace<small>Agent platform</small>
            </div>
            <span className="workspace-version">v1</span>
          </div>
          <div className="nav-label">WORKSPACE</div>
          <nav>
            {nav.map(([to, label, Icon]) => (
              <NavLink key={to} to={to} end={to === "/"}>
                <Icon size={18} />
                <span>{label}</span>
                {to === "/scrape" && <span className="nav-new">NEW</span>}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-note">
              <span className="sidebar-spark">✧</span>
              <h3>Built for the curious.</h3>
              <p>
                Turn questions into
                <br />
                structured knowledge.
              </p>
              <Link to="/scrape">
                Start exploring <ArrowUpRight size={14} />
              </Link>
            </div>
            <NavLink to="/settings" className="settings-link">
              <SettingsIcon size={18} />
              Settings
            </NavLink>
            <div className="profile">
              <div>W</div>
              <span>
                Workspace operator<small>Local environment</small>
              </span>
              <span className="profile-dot" />
            </div>
          </div>
        </aside>
        <div className="main-shell">
          <div className="topbar">
            <div>
              <span className="breadcrumb-icon">
                <Compass size={15} />
              </span>
              Workspace <span>/</span> Agent platform
            </div>
            <span className="topbar-tag">
              <i /> PRIVATE WORKSPACE
            </span>
            <Link
              to="/settings"
              className="mobile-settings"
              aria-label="Workspace settings"
            >
              <SettingsIcon size={17} />
            </Link>
          </div>
          <main>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/scrape" element={<Scrape />} />
              <Route path="/jobs" element={<Jobs />} />
              <Route path="/jobs/:id" element={<Monitor />} />
              <Route path="/results" element={<Results />} />
              <Route path="/results/:id" element={<Results />} />
              <Route path="/settings" element={<Settings />} />
              <Route
                path="*"
                element={
                  <div className="empty">
                    <h1>Page not found</h1>
                    <Link to="/">Return to workspace</Link>
                  </div>
                }
              />
            </Routes>
            <footer className="page-footer">
              <span>ATLAS / AGENT PLATFORM</span>
              <span>Thoughtful automation. Traceable intelligence.</span>
            </footer>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
