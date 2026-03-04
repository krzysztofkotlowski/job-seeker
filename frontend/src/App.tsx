import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { ThemeProvider, createTheme, CssBaseline } from "@mui/material";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import WorkOutlineIcon from "@mui/icons-material/WorkOutline";
import { JobListPage } from "./pages/JobListPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ImportPage } from "./pages/ImportPage";
import { DashboardPage } from "./pages/DashboardPage";

const theme = createTheme({
  palette: {
    primary: { main: "#4f46e5" },
    secondary: { main: "#0ea5e9" },
    background: { default: "#f8fafc" },
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
  { label: "Import", to: "/import" },
];

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
          <AppBar position="sticky" elevation={1} sx={{ bgcolor: "white", color: "text.primary" }}>
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
              <Tab
                label="API Docs"
                component="a"
                href="/api/docs"
                target="_blank"
                rel="noopener noreferrer"
                sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}
              />
            </Toolbar>
          </AppBar>

          <Box sx={{ maxWidth: 1200, mx: "auto", px: 2, py: 3 }}>
            <Routes>
              <Route path="/" element={<Navigate to="/jobs" replace />} />
              <Route path="/jobs" element={<JobListPage />} />
              <Route path="/jobs/:id" element={<JobDetailPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/import" element={<ImportPage />} />
            </Routes>
          </Box>
        </Box>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
