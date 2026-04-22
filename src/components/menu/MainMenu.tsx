"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { Hexagon, Play, Trash2, FolderOpen, Map, Brain, Target, Users } from "lucide-react";
import { useSimulationStore } from "@/store/simulationStore";
import { ErrorModal } from "@/components/layout/ErrorModal";

interface SaveEntry {
  filename: string;
  display_name?: string;
  model: string;
  tick: number;
  era: string;
  has_image?: boolean;
  has_excel?: boolean;
  updated_at?: string;
}

const MODELS = [
  { id: "qwen2.5:1.5b", label: "Qwen 1.5B (A)", icon: "🐉" },
  { id: "qwen3:4b", label: "Qwen 4B (B)", icon: "🦙" },
  { id: "gemma3:4b", label: "Gemma 4B (C)", icon: "💎" },
  { id: "deepseek-coder:1.3b", label: "DeepSeek 1.3B (D)", icon: "⚡" },
  { id: "mixed",    label: "Mixed A/B/C/D (25%)",   icon: "🧪" },
];

export function MainMenu({ onStartGame }: { onStartGame: () => void }) {
  const syncState = useSimulationStore((s) => s.syncState);
  const [saves, setSaves] = useState<SaveEntry[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("qwen2.5:1.5b");
  const [targetTicks, setTargetTicks] = useState<string>("");
  const [citizenCount, setCitizenCount] = useState(30);
  const [fertility, setFertility] = useState(50);
  const [abundance, setAbundance] = useState(50);
  const [water, setWater] = useState(50);
  const [loading, setLoading] = useState(false);
  const [errorModal, setErrorModal] = useState({
    isOpen: false,
    title: "",
    message: "",
    errorCode: "",
    suggestion: "",
  });
  const [tab, setTab] = useState<"new" | "load">("new");

  function refreshSaves() {
    fetch("http://localhost:8000/saves").then(r => r.json()).then(d => {
      const normalized: SaveEntry[] = (d.saves || []).map((item: SaveEntry | string) => {
        if (typeof item === "string") {
          return {
            filename: item,
            display_name: item.replace(/\.json$/i, ""),
            model: "-",
            tick: 0,
            era: "-",
          };
        }
        return item;
      });
      setSaves(normalized);
    }).catch(() => {});
  }

  useEffect(() => {
    refreshSaves();
  }, []);

  const handleNewGame = async () => {
    setLoading(true);
    try {
      const parsedTargetTicks = Number.parseInt(targetTicks || "0", 10);
      const targetTick = Number.isFinite(parsedTargetTicks) && parsedTargetTicks > 0 ? parsedTargetTicks : 0;
      const mapPreset = "realistic"; // Always use realistic island
      const res = await fetch(`http://localhost:8000/new_game/${mapPreset}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fertility,
          abundance,
          water,
          model: selectedModel,
          target_tick: targetTick,
          citizen_count: citizenCount,
        })
      });

      if (!res.ok) {
        const errorCode = `HTTP ${res.status}`;
        setErrorModal({
          isOpen: true,
          title: "Game Creation Failed",
          message: "Unable to create new game. Please check your settings and try again.",
          errorCode,
          suggestion: "Is the backend server running? Try restarting it at localhost:8000",
        });
        setLoading(false);
        return;
      }

      const payload = await res.json();
      if (payload?.status !== "ok") {
        setErrorModal({
          isOpen: true,
          title: "Game Creation Rejected",
          message: payload?.message || "The backend rejected the new game request.",
          errorCode: "BACKEND_ERROR",
          suggestion: "Check the server logs for more details about what went wrong.",
        });
        setLoading(false);
        return;
      }

      // Prevent stale menu-era state (often qwen default) from flashing in telemetry.
      syncState({
        active_model: payload.active_model || selectedModel,
        target_tick: payload.target_tick ?? targetTick,
      });

      onStartGame();
    } catch (e) {
      console.error(e);
      setErrorModal({
        isOpen: true,
        title: "Connection Error",
        message: "Failed to connect to the backend server.",
        errorCode: "NETWORK_ERROR",
        suggestion: "Ensure the backend is running on localhost:8000. You may need to restart the server.",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleLoadGame = async (filename: string) => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/load/${filename}`, { method: "POST" });
      if (res.ok) {
        onStartGame();
      } else {
        const errorCode = `HTTP ${res.status}`;
        setErrorModal({
          isOpen: true,
          title: "Failed to Load Game",
          message: `Could not load save file "${filename}". The file may be corrupted or incompatible.`,
          errorCode,
          suggestion: "Try deleting the save and creating a new game, or restart the backend server.",
        });
      }
    } catch (e) {
      console.error(e);
      setErrorModal({
        isOpen: true,
        title: "Connection Error",
        message: "Failed to connect to the backend server when loading game.",
        errorCode: "NETWORK_ERROR",
        suggestion: "Ensure the backend is running on localhost:8000. You may need to restart the server.",
      });
    }
    setLoading(false);
  };

  const handleDeleteSave = async (filename: string) => {
    if (!confirm(`Delete save "${filename}"?`)) return;
    try {
      const res = await fetch(`http://localhost:8000/saves/${filename}`, { method: "DELETE" });
      if (!res.ok) {
        setErrorModal({
          isOpen: true,
          title: "Failed to Delete Save",
          message: `Could not delete save file "${filename}".`,
          errorCode: `HTTP ${res.status}`,
          suggestion: "Check that the file exists and try again.",
        });
      } else {
        refreshSaves();
      }
    } catch (e) {
      console.error(e);
      setErrorModal({
        isOpen: true,
        title: "Connection Error",
        message: "Failed to connect to the backend server when deleting save.",
        errorCode: "NETWORK_ERROR",
        suggestion: "Ensure the backend is running on localhost:8000.",
      });
    }
  };

  return (
    <>
    <div className="w-screen h-screen bg-linear-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center overflow-hidden relative">
      {/* Animated background */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-cyan-500 rounded-full blur-[120px] animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-purple-500 rounded-full blur-[120px] animate-pulse [animation-delay:1s]" />
      </div>

      <div className="relative z-10 w-full max-w-3xl mx-4">
        {/* Title */}
        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-4 mb-4">
            <div className="w-16 h-16 rounded-2xl bg-linear-to-br from-cyan-500 to-purple-600 flex items-center justify-center shadow-2xl shadow-cyan-500/20">
              <Image src="/panopticon-icon.svg" alt="Panopticon Icon" width={36} height={36} className="w-9 h-9" priority />
            </div>
          </div>
          <h1 className="text-5xl font-black tracking-widest uppercase bg-clip-text text-transparent bg-linear-to-r from-cyan-400 to-purple-400">
            Panopticon
          </h1>
          <p className="text-sm text-slate-400 font-mono tracking-[0.3em] uppercase mt-2">
            Autonomous LLM Civilization Engine
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex justify-center gap-2 mb-6">
          <button
            onClick={() => setTab("new")}
            className={`px-6 py-2 rounded-lg font-bold text-sm uppercase tracking-wider transition-all ${
              tab === "new" ? "bg-cyan-500 text-white shadow-lg shadow-cyan-500/30" : "bg-white/5 text-slate-400 hover:bg-white/10"
            }`}
          >
            <Map className="w-4 h-4 inline mr-2" />New Game
          </button>
          <button
            onClick={() => { setTab("load"); refreshSaves(); }}
            className={`px-6 py-2 rounded-lg font-bold text-sm uppercase tracking-wider transition-all ${
              tab === "load" ? "bg-purple-500 text-white shadow-lg shadow-purple-500/30" : "bg-white/5 text-slate-400 hover:bg-white/10"
            }`}
          >
            <FolderOpen className="w-4 h-4 inline mr-2" />Load Game ({saves.length})
          </button>
        </div>

        {/* New Game Tab */}
        {tab === "new" && (
          <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 space-y-6">

            {/* Model Selection */}
            <div>
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                <Brain className="w-4 h-4" /> LLM Brain
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {MODELS.map(m => (
                  <button
                    key={m.id}
                    onClick={() => setSelectedModel(m.id)}
                    className={`p-3 rounded-xl border-2 text-center transition-all ${
                      selectedModel === m.id
                        ? "border-purple-400 bg-purple-500/10"
                        : "border-white/10 bg-white/5 hover:border-white/20"
                    }`}
                  >
                    <div className="text-2xl">{m.icon}</div>
                    <div className="text-white font-bold text-xs mt-1">{m.label}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Population Count */}
            <div className="bg-black/20 p-4 rounded-xl border border-white/5 space-y-3">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                <Users className="w-4 h-4" /> Population
              </h3>
              <p className="text-[10px] text-slate-400">
                Set the initial number of citizens (1–40). Mixed mode distributes citizens equally across model slots A/B/C/D.
              </p>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min="1"
                  max="40"
                  value={citizenCount}
                  onChange={e => setCitizenCount(parseInt(e.target.value))}
                  className="flex-1 accent-emerald-500"
                  title="Citizen count"
                  aria-label="Citizen count"
                />
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    min="1"
                    max="40"
                    value={citizenCount}
                    onChange={e => {
                      const v = parseInt(e.target.value);
                      if (!isNaN(v)) setCitizenCount(Math.max(1, Math.min(40, v)));
                    }}
                    className="w-16 bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-center text-sm text-white font-mono focus:outline-none focus:border-emerald-400"
                  />
                  <span className="text-[10px] text-slate-500 font-mono">/40</span>
                </div>
              </div>
            </div>

            {/* Environment Parameters */}
            <div className="space-y-4 bg-black/20 p-4 rounded-xl border border-white/5">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                <Hexagon className="w-4 h-4" /> Environment Settings
              </h3>
              
              <div className="space-y-3">
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between text-[10px] uppercase font-bold text-slate-300">
                    <span>🌾 Soil Fertility</span>
                    <span className="text-cyan-400">{fertility}%</span>
                  </div>
                  <input type="range" min="10" max="100" value={fertility} onChange={e => setFertility(parseInt(e.target.value))} className="w-full accent-cyan-500" title="Soil fertility" aria-label="Soil fertility" />
                </div>
                
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between text-[10px] uppercase font-bold text-slate-300">
                    <span>💎 Resource Abundance</span>
                    <span className="text-purple-400">{abundance}%</span>
                  </div>
                  <input type="range" min="10" max="100" value={abundance} onChange={e => setAbundance(parseInt(e.target.value))} className="w-full accent-purple-500" title="Resource abundance" aria-label="Resource abundance" />
                </div>

                <div className="flex flex-col gap-1">
                  <div className="flex justify-between text-[10px] uppercase font-bold text-slate-300">
                    <span>💧 Water Availability</span>
                    <span className="text-blue-400">{water}%</span>
                  </div>
                  <input type="range" min="10" max="100" value={water} onChange={e => setWater(parseInt(e.target.value))} className="w-full accent-blue-500" title="Water availability" aria-label="Water availability" />
                </div>

              </div>
            </div>

            {/* Target Ticks */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-slate-400">
                <Target className="w-4 h-4" />
                <span className="text-xs font-bold uppercase tracking-widest">Auto-stop Ticks</span>
              </div>
              <input
                type="number"
                placeholder="∞ (unlimited)"
                value={targetTicks}
                onChange={(e) => setTargetTicks(e.target.value)}
                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-sm text-white font-mono placeholder-slate-500 focus:outline-none focus:border-cyan-400"
              />
            </div>

            {/* Start Button */}
            <button
              onClick={handleNewGame}
              disabled={loading}
              className="w-full py-4 bg-linear-to-r from-cyan-500 to-purple-600 text-white font-black text-lg uppercase tracking-widest rounded-xl shadow-2xl shadow-cyan-500/20 hover:shadow-cyan-500/40 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
            >
              <Play className="w-6 h-6" />
              {loading ? "Creating World..." : "Start Civilization"}
            </button>
          </div>
        )}

        {/* Load Game Tab */}
        {tab === "load" && (
          <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
            {saves.length === 0 ? (
              <div className="text-center py-12 text-slate-500">
                <FolderOpen className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">No saved games found.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-100 overflow-y-auto pr-2">
                {saves.map(s => (
                  <div key={s.filename} className="flex items-center justify-between p-3 bg-white/5 rounded-xl border border-white/10 hover:bg-white/10 transition-colors">
                    <div className="flex-1">
                      <div className="text-white font-mono text-sm">{s.display_name || s.filename}</div>
                      <div className="text-slate-400 text-[10px] mt-0.5">
                        Model: {s.model} · Tick: {s.tick} · Era: {s.era}
                      </div>
                      {(s.has_image || s.has_excel) && (
                        <div className="text-slate-500 text-[10px] mt-0.5">
                          {s.has_image ? "PNG" : "-"} · {s.has_excel ? "Excel" : "-"}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleLoadGame(s.filename)}
                        className="p-2 text-cyan-400 hover:bg-cyan-500/20 rounded-lg transition-colors"
                        title="Load Game"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDeleteSave(s.filename)}
                        className="p-2 text-rose-400 hover:bg-rose-500/20 rounded-lg transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>

      <ErrorModal
        isOpen={errorModal.isOpen}
        title={errorModal.title}
        message={errorModal.message}
        errorCode={errorModal.errorCode}
        suggestion={errorModal.suggestion}
        onClose={() => setErrorModal({ ...errorModal, isOpen: false })}
      />
      </>
    );
}
