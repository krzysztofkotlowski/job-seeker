import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { ThemeProvider, createTheme, CssBaseline } from "@mui/material";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Button from "@mui/material/Button";
import WorkOutlineIcon from "@mui/icons-material/WorkOutline";
import BackupIcon from "@mui/icons-material/Backup";
import { api } from "./api/client";
import { JobListPage } from "./pages/JobListPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ImportPage } from "./pages/ImportPage";
import { DashboardPage } from "./pages/DashboardPage";

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
  { label: "Import", to: "/import" },
];

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
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
              <Button
                size="small"
                startIcon={<BackupIcon />}
                onClick={async () => {
                  try {
                    const blob = await api.createBackup();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `jobseeker_backup_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}.sql`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (e) {
                    alert(e instanceof Error ? e.message : "Backup failed");
                  }
                }}
                sx={{ color: "inherit", opacity: 0.85, "&:hover": { opacity: 1 }, mr: 1 }}
              >
                Backup DB
              </Button>
              <Tab
                label="API Docs"
                component="a"
                href="/api/v1/docs"
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
