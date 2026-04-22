"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { GlassPanel } from "@/components/layout/GlassPanel";
import { SpatialGrid } from "@/components/map/SpatialGrid";
import { GlobalStats } from "@/components/analytics/GlobalStats";
import { TelemetryPanel } from "@/components/analytics/TelemetryPanel";
import { ActivityTab } from "@/components/analytics/ActivityTab";
import { RelationshipTab } from "@/components/analytics/RelationshipTab";
import { RankingTab } from "@/components/analytics/RankingTab";
import { LogViewer } from "@/components/terminal/LogViewer";
import { ErrorModal } from "@/components/layout/ErrorModal";
import { SaveModal } from "@/components/layout/SaveModal";
import { useSimulationStore } from "@/store/simulationStore";
import { Download, RotateCcw, Play, Pause, LogOut, ChevronLeft, ChevronRight, Activity, Maximize2, X } from "lucide-react";
import { MainMenu } from "@/components/menu/MainMenu";
import { socket } from "@/lib/socket";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const SESSION_MODE_KEY = "panopticon_app_mode";

// Toast notification types
interface Toast {
  id: string;
  category: "ECONOMY" | "SOCIAL" | "SPATIAL" | "SYSTEM";
  icon: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
  timestamp: number;
}

const TOAST_CATEGORY_STYLES: Record<Toast["category"], string> = {
  ECONOMY: "border-amber-300/70 bg-amber-500 text-amber-50",
  SOCIAL: "border-sky-300/70 bg-sky-500 text-sky-50",
  SPATIAL: "border-cyan-300/70 bg-cyan-500 text-cyan-50",
  SYSTEM: "border-slate-300/70 bg-slate-600 text-slate-50",
};

const TOAST_CATEGORY_ICONS: Record<Toast["category"], string> = {
  ECONOMY: "💰",
  SOCIAL: "💬",
  SPATIAL: "🧭",
  SYSTEM: "⚙️",
};

export default function DashboardPage() {
  const { syncState, isRunning, toggleSimulation, setRunningStatus, logs } = useSimulationStore();
  const dashboardRef = useRef<HTMLElement>(null);
  const toastTimersRef = useRef<Map<string, number>>(new Map());
  const [speed, setSpeed] = useState<number>(1);
  const [appMode, setAppMode] = useState<"menu" | "simulation">("menu");
  const [bootstrapping, setBootstrapping] = useState(true);
  const [showExitModal, setShowExitModal] = useState(false);
  const [fullscreenPanel, setFullscreenPanel] = useState<"zoneB" | "zoneC" | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveDefaultName, setSaveDefaultName] = useState("");
  const [saveErrorModal, setSaveErrorModal] = useState({
    isOpen: false,
    title: "",
    message: "",
    errorCode: "",
    suggestion: "",
  });
  const [rightPanelTab, setRightPanelTab] = useState<"telemetry" | "activity" | "relationships" | "ranking">("telemetry");
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [lastLogCount, setLastLogCount] = useState(0);

  const persistAppMode = (mode: "menu" | "simulation") => {
    try {
      window.localStorage.setItem(SESSION_MODE_KEY, mode);
    } catch {
      // Ignore storage failures; backend state still determines the real session.
    }
  };

  const pushToast = (toast: Omit<Toast, "timestamp">) => {
    const nextToast: Toast = {
      ...toast,
      timestamp: Date.now(),
    };

    setToasts((prev) => [...prev, nextToast]);

    const timeoutId = window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== nextToast.id));
      toastTimersRef.current.delete(nextToast.id);
    }, 5000);

    toastTimersRef.current.set(nextToast.id, timeoutId);
  };

  useEffect(() => {
    return () => {
      for (const timeoutId of toastTimersRef.current.values()) {
        window.clearTimeout(timeoutId);
      }
      toastTimersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    // Connect to python backend
    socket.connect();

    socket.on("connect", () => {
      console.log("Connected to Panopticon Engine");
    });

    socket.on("init_state", (data) => {
      syncState(data);
      if (data?.terrain?.length) {
        setAppMode("simulation");
        persistAppMode("simulation");
      }
      setBootstrapping(false);
    });

    socket.on("sync_state", (data) => {
      syncState(data);
    });

    socket.on("simulation_complete", (data) => {
      setRunningStatus(false);
      alert(
        `✅ Simulation complete!\n` +
        `Model: ${data.model}\n` +
        `Tick: ${data.tick}\n` +
        `Auto JSON: ${data.auto_save_file || "-"}\n` +
        `Auto Excel: ${data.auto_excel_file || "-"}\n` +
        `Logs saved: ${data.log_count ?? 0}`
      );
    });

    return () => {
      socket.disconnect();
      socket.off("connect");
      socket.off("init_state");
      socket.off("sync_state");
      socket.off("simulation_complete");
    };
  }, [syncState]);

  useEffect(() => {
    const hydrateFromBackend = async () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 3000);
      try {
        const res = await fetch(`${BACKEND_URL}/state`, { signal: controller.signal });
        if (!res.ok) {
          setBootstrapping(false);
          return;
        }

        const state = await res.json();
        if (state?.has_map) {
          setAppMode("simulation");
          persistAppMode("simulation");
          setRunningStatus(Boolean(state.is_running));
        } else {
          persistAppMode("menu");
        }
      } catch (error) {
        // Backend may not be running yet during initial page load; keep UI responsive.
        const message = error instanceof Error ? error.message : String(error);
        if (process.env.NODE_ENV !== "production" && message !== "Failed to fetch") {
          console.warn("Hydration skipped:", message);
        }
      } finally {
        window.clearTimeout(timeout);
        setBootstrapping(false);
      }
    };

    try {
      const savedMode = window.localStorage.getItem(SESSION_MODE_KEY);
      if (savedMode === "simulation") {
        setAppMode("simulation");
      }
    } catch {
      // Ignore storage access issues.
    }

    hydrateFromBackend();
  }, [setRunningStatus]);

  // Toast notification system - trigger on new logs
  useEffect(() => {
    if (!logs || logs.length === 0) {
      setLastLogCount(0);
      return;
    }

    if (logs.length > lastLogCount) {
      const newLogs = logs.slice(lastLogCount);
      
      newLogs.forEach((log, index) => {
        const category = (log.category as Toast["category"]) || "SYSTEM";
        const newToast: Toast = {
          id: `${log.id}-${Date.now()}`,
          category,
          icon: TOAST_CATEGORY_ICONS[category] || "⚙️",
          message: log.message,
          type: "info",
        };
        
        pushToast(newToast);
      });

      setLastLogCount(logs.length);
    }
  }, [logs, lastLogCount]);

  const handleToggleSimulation = async () => {
    try {
      const endpoint = isRunning ? `${BACKEND_URL}/stop` : `${BACKEND_URL}/start`;
      const res = await fetch(endpoint, { method: "POST" });
      if (res.ok) {
        toggleSimulation();
      }
    } catch (e) {
      console.error("Failed to toggle engine", e);
    }
  };

  const handleSave = async () => {
    if (isSaving) return;
    setSaveDefaultName(`paper_${new Date().toISOString().replace(/[:.]/g, "-")}`);
    setShowSaveModal(true);
  };

  const handleConfirmSave = async (saveName: string) => {
    if (isSaving || !saveName) return;

    setShowSaveModal(false);
    setIsSaving(true);
    try {
      let screenshotDataUrl: string | null = null;

      // Capture screenshot when possible; fallback to state-only save on CSS parser limitations.
      if (dashboardRef.current) {
        try {
          const html2canvas = (await import("html2canvas")).default;
          const canvas = await html2canvas(dashboardRef.current, { scale: 2 });
          screenshotDataUrl = canvas.toDataURL("image/png");
        } catch (captureError) {
          console.warn("Screenshot capture failed, saving without screenshot", captureError);
        }
      }

      const res = await fetch(`${BACKEND_URL}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          save_name: saveName.trim(),
          screenshot_data_url: screenshotDataUrl,
          export_excel: true,
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const payload = await res.json();
      pushToast({
        id: `save-${Date.now()}`,
        category: "SYSTEM",
        icon: screenshotDataUrl ? "💾" : "📁",
        message: screenshotDataUrl
          ? `Save berhasil: ${payload.save_name}`
          : `Save berhasil tanpa screenshot: ${payload.save_name}`,
        type: "success",
      });
      setShowSaveModal(false);
    } catch(e) {
      console.error("Failed to save snapshot", e);
      setSaveErrorModal({
        isOpen: true,
        title: "Save Gagal",
        message: "Snapshot tidak berhasil disimpan ke backend.",
        errorCode: e instanceof Error ? e.message : "SAVE_ERROR",
        suggestion: "Pastikan backend masih berjalan dan folder save dapat ditulis. Coba ulangi setelah itu.",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleRestart = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/restart`, { method: "POST" });
      if (res.ok) {
        setRunningStatus(false);
        setSpeed(1);
      }
    } catch(e) {
      console.error("Failed to restart engine", e);
    }
  };

  const handleSpeed = async (newSpeed: number) => {
    try {
      const res = await fetch(`${BACKEND_URL}/speed/${newSpeed}`, { method: "POST" });
      if (res.ok) {
        setSpeed(newSpeed);
      }
    } catch(e) {
      console.error("Failed to set speed", e);
    }
  };

  const handleExitSaveAndQuit = async () => {
    try {
      await fetch(`${BACKEND_URL}/stop`, { method: "POST" });
      await fetch(`${BACKEND_URL}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setRunningStatus(false);
      setShowExitModal(false);
      setAppMode("menu");
      persistAppMode("menu");
    } catch (e) {
      console.error("Failed to save and exit", e);
    }
  };

  const handleExitWithoutSaving = async () => {
    try {
      await fetch(`${BACKEND_URL}/stop`, { method: "POST" });
      setRunningStatus(false);
      setShowExitModal(false);
      setAppMode("menu");
      persistAppMode("menu");
    } catch (e) {
      console.error("Failed to exit", e);
    }
  };

  if (bootstrapping) {
    return null;
  }

  if (appMode === "menu") {
    return <MainMenu onStartGame={() => setAppMode("simulation")} />;
  }

  const renderZoneBContent = (showFullscreenButton: boolean) => (
    <div className="flex flex-col h-full overflow-hidden gap-2">
      {showFullscreenButton ? (
        <div className="flex justify-end shrink-0">
          <button
            onClick={() => setFullscreenPanel("zoneB")}
            className="flex items-center gap-1 px-2 py-1 rounded border border-slate-200 bg-white/70 text-[10px] font-bold uppercase tracking-wider text-slate-600 hover:bg-white"
            title="Fullscreen Zone B"
          >
            <Maximize2 className="w-3.5 h-3.5" /> Fullscreen
          </button>
        </div>
      ) : null}

      <div className="flex gap-2 border-b border-white/20 pb-2 shrink-0 flex-wrap">
        <button
          onClick={() => setRightPanelTab("telemetry")}
          className={`px-2 sm:px-3 py-1 sm:py-1.5 text-[10px] sm:text-xs font-bold rounded uppercase tracking-wider transition-colors whitespace-nowrap ${
            rightPanelTab === "telemetry"
              ? "bg-cyan-500 text-white shadow-md"
              : "bg-white/10 text-slate-400 hover:bg-white/20"
          }`}
        >
          👤 Telemetry
        </button>
        <button
          onClick={() => setRightPanelTab("activity")}
          className={`px-2 sm:px-3 py-1 sm:py-1.5 text-[10px] sm:text-xs font-bold rounded uppercase tracking-wider transition-colors whitespace-nowrap flex items-center gap-1 ${
            rightPanelTab === "activity"
              ? "bg-emerald-500 text-white shadow-md"
              : "bg-white/10 text-slate-400 hover:bg-white/20"
          }`}
        >
          <Activity className="w-3.5 h-3.5" /> Activity
        </button>
        <button
          onClick={() => setRightPanelTab("relationships")}
          className={`px-2 sm:px-3 py-1 sm:py-1.5 text-[10px] sm:text-xs font-bold rounded uppercase tracking-wider transition-colors whitespace-nowrap ${
            rightPanelTab === "relationships"
              ? "bg-indigo-600 text-white shadow-md"
              : "bg-white/10 text-slate-400 hover:bg-white/20"
          }`}
        >
          💞 Relationships
        </button>
        <button
          onClick={() => setRightPanelTab("ranking")}
          className={`px-2 sm:px-3 py-1 sm:py-1.5 text-[10px] sm:text-xs font-bold rounded uppercase tracking-wider transition-colors whitespace-nowrap ${
            rightPanelTab === "ranking"
              ? "bg-amber-500 text-white shadow-md"
              : "bg-white/10 text-slate-400 hover:bg-white/20"
          }`}
        >
          🏆 Ranking
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {rightPanelTab === "telemetry" ? (
          <div className="h-full overflow-y-auto custom-scrollbar pr-2">
            <TelemetryPanel />
          </div>
        ) : rightPanelTab === "activity" ? (
          <div className="h-full overflow-y-auto custom-scrollbar pr-2">
            <ActivityTab />
          </div>
        ) : rightPanelTab === "ranking" ? (
          <div className="h-full overflow-y-auto custom-scrollbar pr-2">
            <RankingTab />
          </div>
        ) : (
          <div className="h-full overflow-hidden">
            <RelationshipTab />
          </div>
        )}
      </div>
    </div>
  );

  const renderZoneCContent = (showFullscreenButton: boolean) => (
    <div className="flex flex-col h-full overflow-hidden gap-2">
      {showFullscreenButton ? (
        <div className="flex justify-end shrink-0">
          <button
            onClick={() => setFullscreenPanel("zoneC")}
            className="flex items-center gap-1 px-2 py-1 rounded border border-slate-200 bg-white/70 text-[10px] font-bold uppercase tracking-wider text-slate-600 hover:bg-white"
            title="Fullscreen Zone C"
          >
            <Maximize2 className="w-3.5 h-3.5" /> Fullscreen
          </button>
        </div>
      ) : null}
      <div className="flex-1 min-h-0 overflow-hidden">
        <LogViewer />
      </div>
    </div>
  );

  return (
    <>
    <main ref={dashboardRef} className="w-screen h-screen overflow-hidden p-2 sm:p-4 md:p-6 flex flex-col gap-3 sm:gap-4 md:gap-6 bg-[#f8fafc]">
      
      {/* Header bar */}
      <header className="flex items-center justify-between z-10 shrink-0 gap-2 sm:gap-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="w-8 sm:w-10 h-8 sm:h-10 rounded-xl bg-linear-to-br from-slate-800 to-slate-900 flex items-center justify-center shadow-lg border border-slate-700">
            <Image src="/panopticon-icon.svg" alt="Panopticon Icon" width={24} height={24} className="w-5 sm:w-6 h-5 sm:h-6" priority />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-lg sm:text-xl font-bold tracking-widest text-slate-800 uppercase shadow-white drop-shadow-sm">Panopticon</h1>
            <p className="text-[9px] sm:text-[10px] text-slate-500 font-mono tracking-widest uppercase">Autonomous Agent Observer</p>
          </div>
        </div>
        <div className="flex items-center gap-1 sm:gap-4 flex-wrap justify-end">
          <button
            onClick={handleSave}
            title="Save Snapshot"
            disabled={isSaving}
            className="flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 bg-white border border-slate-200 rounded-md shadow-sm text-[10px] sm:text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors whitespace-nowrap"
          >
            <Download className="w-3 sm:w-4 h-3 sm:h-4" /> <span className="hidden sm:inline">{isSaving ? "Saving..." : "Save"}</span><span className="sm:hidden">{isSaving ? "…" : "💾"}</span>
          </button>
          <button
            onClick={handleRestart}
            title="Restart Simulation"
            className="flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 bg-white border border-slate-200 rounded-md shadow-sm text-[10px] sm:text-xs font-semibold text-rose-600 hover:bg-rose-50 transition-colors whitespace-nowrap"
          >
            <RotateCcw className="w-3 sm:w-4 h-3 sm:h-4" /> <span className="hidden sm:inline">Restart</span><span className="sm:hidden">↻</span>
          </button>
          
          <div className="h-6 w-px bg-slate-200 hidden sm:block"></div>

          <div className="flex bg-white border border-slate-200 rounded-md shadow-sm overflow-hidden">
            {[1, 2, 3].map(multiplier => (
              <button
                key={multiplier}
                onClick={() => handleSpeed(multiplier)}
                className={`flex items-center justify-center px-1.5 sm:px-3 py-1 sm:py-1.5 text-[9px] sm:text-xs font-bold border-r border-slate-200 last:border-0 transition-colors ${
                  speed === multiplier
                    ? 'bg-sky-500 text-white'
                    : 'bg-white text-slate-500 hover:bg-slate-50'
                }`}
                title={`${multiplier}x Speed`}
              >
                {multiplier}x
              </button>
            ))}
          </div>

          <button
            onClick={handleToggleSimulation}
            className={`flex items-center gap-1 sm:gap-2 px-2 sm:px-4 py-1 sm:py-1.5 rounded-md shadow-sm border transition-colors text-[10px] sm:text-xs font-bold uppercase tracking-wider whitespace-nowrap ${
              isRunning 
                ? 'bg-amber-100 border-amber-200 text-amber-700 hover:bg-amber-200' 
                : 'bg-emerald-100 border-emerald-200 text-emerald-700 hover:bg-emerald-200'
            }`}
          >
            {isRunning ? <Pause className="w-3 sm:w-4 h-3 sm:h-4" /> : <Play className="w-3 sm:w-4 h-3 sm:h-4" />}
            <span className="hidden sm:inline">
              {isRunning ? "Pause" : "Play"}
            </span>
          </button>

          <div className="h-6 w-px bg-slate-200 hidden sm:block"></div>

          <button
            onClick={() => setShowExitModal(true)}
            title="Exit to Main Menu"
            className="flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 bg-white border border-slate-200 rounded-md shadow-sm text-[10px] sm:text-xs font-semibold text-slate-500 hover:bg-slate-100 transition-colors whitespace-nowrap"
          >
            <LogOut className="w-3 sm:w-4 h-3 sm:h-4" /> <span className="hidden sm:inline">Exit</span><span className="sm:hidden">←</span>
          </button>

          <button
            onClick={() => setRightPanelCollapsed(!rightPanelCollapsed)}
            title={rightPanelCollapsed ? "Expand panels" : "Collapse panels"}
            className="flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 bg-white border border-slate-200 rounded-md shadow-sm text-[10px] sm:text-xs font-semibold text-slate-500 hover:bg-slate-100 transition-colors whitespace-nowrap"
          >
            {rightPanelCollapsed ? <ChevronLeft className="w-3 sm:w-4 h-3 sm:h-4" /> : <ChevronRight className="w-3 sm:w-4 h-3 sm:h-4" />}
            <span className="hidden sm:inline">Panels</span>
            <span className="sm:hidden">◫</span>
          </button>
        </div>
      </header>

      {/* Main Grid Layout - Fullscreen map with collapsible right panel */}
      <div className="flex-1 min-h-0 flex flex-row gap-3 sm:gap-4 md:gap-6 relative z-10">
        
        {/* Main: Zone A (Map) - Full width when panel is collapsed */}
        <div className={`flex flex-col shrink-0 min-h-0 transition-all duration-300 ${rightPanelCollapsed ? 'w-full' : 'w-full lg:w-2/3'}`}>
          <GlassPanel title="Zone A: Spatial Mapping" className="flex-1 shadow-2xl isolate">
            <SpatialGrid />
          </GlassPanel>
        </div>

        {/* Collapsible Right Panel */}
        <div className={`flex flex-col shrink-0 gap-3 sm:gap-4 md:gap-6 min-h-0 transition-all duration-300 overflow-hidden ${
          rightPanelCollapsed ? 'w-0' : 'w-full lg:w-1/3 lg:min-w-80'
        }`}>

          {/* Sticky Stats (outside Zone B) */}
          {!rightPanelCollapsed && (
            <GlassPanel title="Live Stats" className="shrink-0 shadow-lg">
              <GlobalStats />
            </GlassPanel>
          )}

          {/* Top Right: Zone B - Hidden when collapsed */}
          {!rightPanelCollapsed && (
            <GlassPanel title="Zone B: Telemetry & Analytics" className="flex-3 shadow-lg min-h-0">
              {renderZoneBContent(true)}
            </GlassPanel>
          )}

          {/* Bottom Right: Zone C - Hidden when collapsed */}
          {!rightPanelCollapsed && (
            <GlassPanel title="Zone C: Memory Stream" className="flex-2 shadow-lg min-h-0">
              {renderZoneCContent(true)}
            </GlassPanel>
          )}

        </div>
      </div>

      {fullscreenPanel && (
        <div className="fixed inset-0 z-9999 flex items-center justify-center bg-black/55 backdrop-blur-sm">
          <div className="w-[min(1240px,96vw)] h-[92vh] rounded-2xl bg-white border border-slate-200 shadow-2xl overflow-hidden flex flex-col">
            <div className="px-5 py-3 border-b border-slate-200 bg-slate-50/90 flex items-center justify-between">
              <h2 className="text-sm font-semibold tracking-wider uppercase text-slate-800">
                {fullscreenPanel === "zoneB" ? "Zone B: Telemetry & Analytics" : "Zone C: Memory Stream"}
              </h2>
              <button
                onClick={() => setFullscreenPanel(null)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded border border-slate-300 text-xs font-semibold text-slate-600 hover:bg-white"
                title="Close fullscreen"
              >
                <X className="w-3.5 h-3.5" /> Close
              </button>
            </div>
            <div className="flex-1 min-h-0 p-4 bg-slate-50/40">
              <div className="h-full rounded-xl border border-slate-200 bg-white/70 p-3 overflow-hidden">
                {fullscreenPanel === "zoneB" ? renderZoneBContent(false) : renderZoneCContent(false)}
              </div>
            </div>
          </div>
        </div>
      )}

      <SaveModal
        isOpen={showSaveModal}
        defaultName={saveDefaultName}
        isSaving={isSaving}
        onClose={() => setShowSaveModal(false)}
        onConfirm={handleConfirmSave}
      />

      <ErrorModal
        isOpen={saveErrorModal.isOpen}
        title={saveErrorModal.title}
        message={saveErrorModal.message}
        errorCode={saveErrorModal.errorCode}
        suggestion={saveErrorModal.suggestion}
        onClose={() => setSaveErrorModal((prev) => ({ ...prev, isOpen: false }))}
      />

    </main>

      {/* Toast Notification Container - Top-right corner, stacking down */}
      <div className="fixed top-20 right-6 z-9999 flex flex-col gap-2 pointer-events-none max-w-xs">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`px-4 py-3 rounded-lg border shadow-lg text-sm font-medium pointer-events-auto animate-in slide-in-from-right fade-in transition-all ${
              toast.type === "error"
                ? "border-rose-300/70 bg-rose-500 text-rose-50"
                : toast.type === "warning"
                ? "border-amber-300/70 bg-amber-500 text-amber-50"
                : toast.type === "success"
                ? "border-emerald-300/70 bg-emerald-500 text-emerald-50"
                : TOAST_CATEGORY_STYLES[toast.category]
            }`}
          >
            <div className="flex items-start gap-2">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-wider font-bold opacity-90">{toast.category}</div>
                <div className="whitespace-pre-wrap wrap-break-word">{toast.message}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Exit Confirmation Modal */}
      {showExitModal && (
        <div className="fixed inset-0 z-9999 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full mx-4 border border-slate-200">
            <h2 className="text-lg font-bold text-slate-800 mb-2">Exit to Main Menu</h2>
            <p className="text-sm text-slate-500 mb-6">Do you want to save your progress before exiting?</p>
            <div className="flex flex-col gap-3">
              <button
                onClick={handleExitSaveAndQuit}
                className="w-full px-4 py-2.5 bg-emerald-500 text-white rounded-lg font-semibold text-sm hover:bg-emerald-600 transition-colors shadow-sm"
              >
                💾 Save & Exit
              </button>
              <button
                onClick={handleExitWithoutSaving}
                className="w-full px-4 py-2.5 bg-rose-500 text-white rounded-lg font-semibold text-sm hover:bg-rose-600 transition-colors shadow-sm"
              >
                🚪 Exit Without Saving
              </button>
              <button
                onClick={() => setShowExitModal(false)}
                className="w-full px-4 py-2.5 bg-slate-100 text-slate-600 rounded-lg font-semibold text-sm hover:bg-slate-200 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
