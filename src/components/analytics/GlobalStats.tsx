import { useSimulationStore } from "@/store/simulationStore";
import { Activity, Users, Coins, Calendar, Brain } from "lucide-react";
import { useState } from "react";

const ERA_DISPLAY: Record<string, { icon: string; label: string; color: string }> = {
  prehistoric: { icon: "🦴", label: "Prehistoric", color: "text-amber-700" },
  ancient:     { icon: "🏺", label: "Ancient",     color: "text-orange-600" },
  medieval:    { icon: "⚔️", label: "Medieval",    color: "text-red-600" },
  modern:      { icon: "🏭", label: "Modern",      color: "text-blue-600" },
};

const MODELS = [
  { id: "qwen2.5:1.5b", label: "Qwen 1.5B", icon: "🐉" },
  { id: "qwen3:4b", label: "Qwen 4B", icon: "🦙" },
  { id: "gemma3:4b", label: "Gemma 4B", icon: "💎" },
  { id: "deepseek-coder:1.3b", label: "DeepSeek 1.3B", icon: "⚡" },
  { id: "mixed",    label: "Mixed A/B/C/D", icon: "🧪" },
];

export function GlobalStats() {
  const {
    agents,
    tickCount,
    calendarDate,
    era,
    activeModel,
    targetTick,
    isRunning,
    toggleSimulation,
    setModel,
    setTargetTick,
    metrics,
    globalQuest,
  } = useSimulationStore();
  const [targetInput, setTargetInput] = useState("");

  const totalPop = Object.keys(agents).length;
  const totalWealth = Object.values(agents).reduce((acc, a) => acc + a.inventory.coin, 0);

  const eraInfo = ERA_DISPLAY[era] || ERA_DISPLAY.prehistoric;
  const currentModel = MODELS.find(m => m.id === activeModel) || { id: activeModel, label: activeModel, icon: "🧠" };
  const giniPct = `${(metrics.gini_coin * 100).toFixed(1)}%`;
  const densityPct = `${(metrics.social_density * 100).toFixed(1)}%`;
  const questProgress = globalQuest
    ? Math.min(100, Math.round((globalQuest.progress_amount / Math.max(1, globalQuest.target_amount)) * 100))
    : 0;
  const questTicksLeft = globalQuest ? Math.max(0, globalQuest.deadline_tick - tickCount) : 0;

  const handleSetTarget = () => {
    const val = parseInt(targetInput);
    if (!isNaN(val) && val > 0) {
      // Convert years to ticks (1 year = 360 ticks)
      setTargetTick(val * 360);
    }
  };

  return (
    <div className="flex flex-col gap-3 mb-4">
      {/* Top Row: Era + Calendar + Tick + Pop + GDP */}
      <div className="grid grid-cols-5 gap-2">
        {/* Era */}
        <div className="bg-white/40 ring-1 ring-black/5 rounded-xl p-2.5 flex flex-col justify-center">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-0.5">Era</div>
          <div className={`text-sm font-bold ${eraInfo.color}`}>
            {eraInfo.icon} {eraInfo.label}
          </div>
        </div>

        {/* Calendar */}
        <div className="bg-white/40 ring-1 ring-black/5 rounded-xl p-2.5 flex flex-col justify-center">
          <div className="flex items-center gap-1 mb-0.5 text-slate-400">
            <Calendar className="w-3 h-3" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">Date</span>
          </div>
          <div className="text-sm font-mono text-slate-800">{calendarDate}</div>
        </div>

        {/* Tick */}
        <div 
          className="bg-white/40 ring-1 ring-black/5 rounded-xl p-2.5 flex flex-col justify-center cursor-pointer hover:bg-white/60 transition-colors"
          onClick={toggleSimulation}
        >
          <div className="flex items-center gap-1 mb-0.5 text-slate-400">
            <Activity className={`w-3 h-3 ${isRunning ? "text-green-500 animate-pulse" : ""}`} />
            <span className="text-[10px] font-semibold uppercase tracking-wider">Tick</span>
          </div>
          <div className="text-sm font-mono text-slate-800">
            {String(tickCount).padStart(5, '0')}
            {targetTick > 0 && <span className="text-[10px] text-slate-400">/{targetTick}</span>}
          </div>
        </div>

        {/* Population */}
        <div className="bg-white/40 ring-1 ring-black/5 rounded-xl p-2.5 flex flex-col justify-center">
          <div className="flex items-center gap-1 mb-0.5 text-slate-400">
            <Users className="w-3 h-3" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">Pop</span>
          </div>
          <div className="text-sm font-mono text-slate-800">{totalPop}</div>
        </div>

        {/* GDP */}
        <div className="bg-white/40 ring-1 ring-black/5 rounded-xl p-2.5 flex flex-col justify-center">
          <div className="flex items-center gap-1 mb-0.5 text-slate-400">
            <Coins className="w-3 h-3" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">GDP</span>
          </div>
          <div className="text-sm font-mono text-slate-800">{totalWealth}</div>
        </div>
      </div>

      {/* Bottom Row: Info Badges */}
      <div className="grid grid-cols-3 gap-2">
        {/* Active Model Badge */}
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl p-2.5 flex items-center gap-2">
          <Brain className="w-4 h-4 text-purple-500 shrink-0" />          <div className="flex flex-col justify-center">
            <span className="text-[9px] font-bold text-purple-600/70 uppercase tracking-widest leading-none">LLM Brain</span>
            <span className="text-xs font-bold text-slate-700 mt-0.5">{currentModel.icon} {currentModel.label}</span>
          </div>
        </div>

        {/* Gini Metric */}
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-2.5 flex items-center gap-2">
          <Coins className="w-4 h-4 text-rose-500 shrink-0" />
          <div className="flex flex-col justify-center">
            <span className="text-[9px] font-bold text-rose-600/70 uppercase tracking-widest leading-none">Gini</span>
            <span className="text-xs font-bold text-slate-700 mt-0.5">{giniPct}</span>
          </div>
        </div>

        {/* Social Network Density */}
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-2.5 flex items-center gap-2">
          <Users className="w-4 h-4 text-emerald-500 shrink-0" />
          <div className="flex flex-col justify-center">
            <span className="text-[9px] font-bold text-emerald-600/70 uppercase tracking-widest leading-none">Net Density</span>
            <span className="text-xs font-bold text-slate-700 mt-0.5">{densityPct}</span>
          </div>
        </div>
      </div>

      {globalQuest && globalQuest.status === "active" && (
        <div className="bg-amber-500/10 border border-amber-500/25 rounded-xl p-2.5">
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-700">Global Quest</div>
            <div className="text-[10px] text-amber-800/80">{questTicksLeft} ticks left</div>
          </div>
          <div className="text-xs font-semibold text-slate-800 truncate">{globalQuest.title}</div>
          <svg className="mt-1 h-2 w-full rounded-full bg-amber-900/15 overflow-hidden" viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label="Quest progress">
            <rect x="0" y="0" width="100" height="8" rx="4" fill="transparent" />
            <rect x="0" y="0" width={questProgress} height="8" rx="4" fill="rgb(245 158 11)" />
          </svg>
          <div className="mt-1 text-[11px] text-slate-700">
            {globalQuest.progress_amount}/{globalQuest.target_amount} {globalQuest.resource} | Reward {globalQuest.reward_coin} coin
          </div>
        </div>
      )}
    </div>
  );
}
