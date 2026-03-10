import { lazy, Suspense, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  useLocation,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme, CssBaseline, useTheme, useMediaQuery } from "@mui/material";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Divider from "@mui/material/Divider";
import WorkOutlineIcon from "@mui/icons-material/WorkOutline";
import SettingsIcon from "@mui/icons-material/Settings";
import LoginIcon from "@mui/icons-material/Login";
import LogoutIcon from "@mui/icons-material/Logout";
import MenuIcon from "@mui/icons-material/Menu";
import DashboardIcon from "@mui/icons-material/Dashboard";
import PsychologyIcon from "@mui/icons-material/Psychology";
import DescriptionIcon from "@mui/icons-material/Description";
import CircularProgress from "@mui/material/CircularProgress";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/useAuth";
import { ToastProvider } from "./contexts/ToastContext";
import { SettingsModal } from "./components/SettingsModal";

const JobListPage = lazy(() =>
  import("./pages/JobListPage").then((m) => ({ default: m.JobListPage })),
);
const JobDetailPage = lazy(() =>
  import("./pages/JobDetailPage").then((m) => ({ default: m.JobDetailPage })),
);
const SkillsPage = lazy(() =>
  import("./pages/SkillsPage").then((m) => ({ default: m.SkillsPage })),
);
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const ResumeAnalysisPage = lazy(() =>
  import("./pages/ResumeAnalysisPage").then((m) => ({
    default: m.ResumeAnalysisPage,
  })),
);

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#818cf8" },
    secondary: { main: "#38bdf8" },
  },
  typography: {
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: {
      styleOverrides: { root: { textTransform: "none", fontWeight: 600 } },
    },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 500, minHeight: 48 },
      },
    },
  },
});

const NAV_ITEMS = [
  { label: "Jobs", to: "/jobs", icon: WorkOutlineIcon },
  { label: "Dashboard", to: "/dashboard", icon: DashboardIcon },
  { label: "Skills", to: "/skills", icon: PsychologyIcon },
  { label: "Resume", to: "/resume", icon: DescriptionIcon },
];

function AppContentInner() {
  const auth = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const location = useLocation();

  const closeDrawer = () => setDrawerOpen(false);

  return (
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        <AppBar position="sticky" elevation={1}>
          <Toolbar sx={{ maxWidth: 1200, width: "100%", mx: "auto", px: 2 }}>
            {isMobile ? (
              <IconButton
                color="inherit"
                onClick={() => setDrawerOpen(true)}
                aria-label="Open menu"
                sx={{ mr: 1 }}
              >
                <MenuIcon />
              </IconButton>
            ) : null}
            <WorkOutlineIcon sx={{ color: "primary.main", mr: 1 }} />
            <Typography variant="h6" fontWeight={700} sx={{ mr: isMobile ? 0 : 4, flexGrow: isMobile ? 1 : 0 }}>
              Job Seeker
            </Typography>
            {!isMobile && (
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
            )}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.5,
                flexShrink: 0,
              }}
            >
              {auth?.config?.enabled ? (
                auth?.authenticated ? (
                  <Button
                    size="small"
                    startIcon={<LogoutIcon />}
                    onClick={() => auth.logout()}
                    sx={{
                      color: "inherit",
                      opacity: 0.85,
                      "&:hover": { opacity: 1 },
                    }}
                  >
                    Logout
                  </Button>
                ) : (
                  <Button
                    size="small"
                    startIcon={<LoginIcon />}
                    onClick={() => auth.login()}
                    sx={{
                      color: "inherit",
                      opacity: 0.85,
                      "&:hover": { opacity: 1 },
                    }}
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
              <Tooltip title="Settings (Import, AI Config, API Docs)">
                <IconButton
                  color="inherit"
                  onClick={() => setSettingsOpen(true)}
                  sx={{ opacity: 0.85, "&:hover": { opacity: 1 } }}
                  aria-label="Settings"
                >
                  <SettingsIcon />
                </IconButton>
              </Tooltip>
            </Box>
          </Toolbar>
        </AppBar>

        <Drawer
          anchor="left"
          open={drawerOpen}
          onClose={closeDrawer}
          PaperProps={{
            sx: { width: 280 },
          }}
        >
          <Box sx={{ py: 2, px: 2 }}>
            <Typography variant="h6" fontWeight={700} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <WorkOutlineIcon color="primary" />
              Job Seeker
            </Typography>
          </Box>
          <Divider />
          <List>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.to || location.pathname.startsWith(item.to + "/");
              return (
                <ListItem key={item.to} disablePadding>
                  <ListItemButton
                    component={NavLink}
                    to={item.to}
                    onClick={closeDrawer}
                    selected={isActive}
                    sx={{
                      "&.Mui-selected": {
                        bgcolor: "action.selected",
                        color: "primary.main",
                        fontWeight: 600,
                      },
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 40 }}>
                      <Icon color={isActive ? "primary" : "inherit"} fontSize="small" />
                    </ListItemIcon>
                    <ListItemText primary={item.label} />
                  </ListItemButton>
                </ListItem>
              );
            })}
          </List>
          <Divider />
          <List>
            <ListItem disablePadding>
              <ListItemButton onClick={() => { setSettingsOpen(true); closeDrawer(); }}>
                <ListItemIcon sx={{ minWidth: 40 }}>
                  <SettingsIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Settings" />
              </ListItemButton>
            </ListItem>
          </List>
        </Drawer>

        <Box sx={{ maxWidth: 1200, mx: "auto", px: 2, py: 3 }}>
          <Suspense
            fallback={
              <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
                <CircularProgress />
              </Box>
            }
          >
            <Routes>
              <Route path="/" element={<Navigate to="/jobs" replace />} />
              <Route path="/jobs" element={<JobListPage />} />
              <Route path="/jobs/:id" element={<JobDetailPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/resume" element={<ResumeAnalysisPage />} />
            </Routes>
            <SettingsModal
              open={settingsOpen}
              onClose={() => setSettingsOpen(false)}
            />
          </Suspense>
        </Box>
      </Box>
  );
}

function AppContent() {
  return (
    <BrowserRouter>
      <AppContentInner />
    </BrowserRouter>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 30_000,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline enableColorScheme />
        <ToastProvider>
          <AuthProvider>
            <AppContent />
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
