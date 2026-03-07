import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import IconButton from "@mui/material/IconButton";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import CloseIcon from "@mui/icons-material/Close";
import SettingsIcon from "@mui/icons-material/Settings";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { ImportContent } from "./ImportContent";
import { AIConfigContent } from "./AIConfigContent";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
}

const API_DOCS_URL = "/api/v1/docs";

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const [tab, setTab] = useState(0);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 2,
          height: "85vh",
          maxHeight: 880,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
      }}
    >
      <Box sx={{ flexShrink: 0 }}>
        <DialogTitle
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: 1,
            borderColor: "divider",
            py: 1.5,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <SettingsIcon color="primary" fontSize="small" />
            <span>Settings</span>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Link
              href={API_DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.5,
                fontSize: "0.875rem",
                color: "text.secondary",
                textDecoration: "none",
                "&:hover": { color: "primary.main" },
              }}
            >
              API Docs
              <OpenInNewIcon sx={{ fontSize: 16 }} />
            </Link>
            <IconButton size="small" onClick={onClose} aria-label="Close">
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{ borderBottom: 1, borderColor: "divider", px: 2 }}
        >
          <Tab label="Import" />
          <Tab label="AI Config" />
        </Tabs>
      </Box>
      <DialogContent
        sx={{
          flex: 1,
          p: 0,
          minHeight: 0,
          overflow: tab === 1 ? "hidden" : "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box
          sx={{
            p: 3,
            flex: tab === 1 ? 1 : undefined,
            minHeight: tab === 1 ? 0 : undefined,
            overflow: tab === 1 ? "hidden" : undefined,
            display: tab === 1 ? "flex" : "block",
            flexDirection: tab === 1 ? "column" : undefined,
          }}
        >
          {tab === 0 && <ImportContent />}
          {tab === 1 && <AIConfigContent />}
        </Box>
      </DialogContent>
    </Dialog>
  );
}
