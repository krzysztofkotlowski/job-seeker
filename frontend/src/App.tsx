import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { ThemeProvider, createTheme, CssBaseline } from "@mui/material";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import WorkOutlineIcon from "@mui/icons-material/WorkOutline";
import LoginIcon from "@mui/icons-material/Login";
import LogoutIcon from "@mui/icons-material/Logout";
import CircularProgress from "@mui/material/CircularProgress";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/useAuth";
import { ToastProvider } from "./contexts/ToastContext";

const JobListPage = lazy(() => import("./pages/JobListPage").then((m) => ({ default: m.JobListPage })));
const JobDetailPage = lazy(() => import("./pages/JobDetailPage").then((m) => ({ default: m.JobDetailPage })));
const SkillsPage = lazy(() => import("./pages/SkillsPage").then((m) => ({ default: m.SkillsPage })));
const ImportPage = lazy(() => import("./pages/ImportPage").then((m) => ({ default: m.ImportPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const ResumeAnalysisPage = lazy(() => import("./pages/ResumeAnalysisPage").then((m) => ({ default: m.ResumeAnalysisPage })));

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#818cf8" },
    secondary: { main: "#38bdf8" },
  },
  typography: {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: { styleOverrides: { root: { textTransform: "none", fontWeight: 600 } } },
    MuiTab: { styleOverrides: { root: { textTransform: "none", fontWeight: 500, minHeight: 48 } } },
  },
});

const NAV_ITEMS = [
  { label: "Jobs", to: "/jobs" },
  { label: "Dashboard", to: "/dashboard" },
  { label: "Skills", to: "/skills" },
  { label: "Resume", to: "/resume" },
  { label: "Import", to: "/import" },
];

function AppContent() {
  const auth = useAuth();
  return (
    <BrowserRouter>
        <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
          <AppBar position="sticky" elevation={1}>
            <Toolbar sx={{ maxWidth: 1200, width: "100%", mx: "auto", px: 2 }}>
              <WorkOutlineIcon sx={{ color: "primary.main", mr: 1 }} />
              <Typography variant="h6" fontWeight={700} sx={{ mr: 4 }}>
                Job Seeker
              </Typography>
              <Tabs value={false} sx={{ flexGrow: 1 }}>
                {NAV_ITEMS.map((item) => (
                  <Tab
                    key={item.to}
                    label={item.label}
                    component={NavLink}
                    to={item.to}
                    sx={{
                      "&.active": { color: "primary.main", fontWeight: 700 },
                    }}
                  />
                ))}
              </Tabs>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
                {auth?.config?.enabled ? (
                  auth?.authenticated ? (
                    <Button
                      size="small"
                      startIcon={<LogoutIcon />}
                      onClick={() => auth.logout()}
                      sx={{ color: "inherit", opacity: 0.85, "&:hover": { opacity: 1 } }}
                    >
                      Logout
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      startIcon={<LoginIcon />}
                      onClick={() => auth.login()}
                      sx={{ color: "inherit", opacity: 0.85, "&:hover": { opacity: 1 } }}
                    >
                      Login
                    </Button>
                  )
                ) : auth?.config !== null ? (
                  <Tooltip title="Authentication not configured">
                    <span>
                      <Button
                        size="small"
                        startIcon={<LoginIcon />}
                        disabled
                        sx={{ color: "inherit", opacity: 0.5 }}
                      >
                        Login
                      </Button>
                    </span>
                  </Tooltip>
                ) : null}
                <Tab
                  label="API Docs"
                  component="a"
                  href="/api/v1/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}
                />
              </Box>
            </Toolbar>
          </AppBar>

          <Box sx={{ maxWidth: 1200, mx: "auto", px: 2, py: 3 }}>
            <Suspense fallback={
              <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
                <CircularProgress />
              </Box>
            }>
            <Routes>
              <Route path="/" element={<Navigate to="/jobs" replace />} />
              <Route path="/jobs" element={<JobListPage />} />
              <Route path="/jobs/:id" element={<JobDetailPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/resume" element={<ResumeAnalysisPage />} />
              <Route path="/import" element={<ImportPage />} />
            </Routes>
            </Suspense>
          </Box>
        </Box>
      </BrowserRouter>
  );
}

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline enableColorScheme />
      <ToastProvider>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App;
