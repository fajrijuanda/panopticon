"use client";

import { useMemo } from "react";
import { useSimulationStore } from "@/store/simulationStore";
import { Activity, Clock3, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";

const CATEGORY_CARD_STYLES: Record<string, string> = {
  ECONOMY: "border-amber-300 bg-amber-50",
  SOCIAL: "border-sky-300 bg-sky-50",
  SPATIAL: "border-cyan-300 bg-cyan-50",
  SYSTEM: "border-slate-300 bg-slate-100",
};

const CATEGORY_BADGE_STYLES: Record<string, string> = {
  ECONOMY: "border-amber-300 bg-amber-100 text-amber-900",
  SOCIAL: "border-sky-300 bg-sky-100 text-sky-900",
  SPATIAL: "border-cyan-300 bg-cyan-100 text-cyan-900",
  SYSTEM: "border-slate-300 bg-slate-200 text-slate-900",
};

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function ActivityTab() {
  const { agents, logs, selectedAgentId, setSelectedAgent, globalQuest } = useSimulationStore();
  const selectedAgent = selectedAgentId ? agents[selectedAgentId] : null;

  const activities = useMemo(() => {
    if (!selectedAgent) return [];

    const agentNamePattern = new RegExp(escapeRegExp(selectedAgent.name), "i");
    return [...logs]
      .filter((log) => {
        if (log.source_agent_id === selectedAgent.id) return true;
        if (log.participant_ids?.includes(selectedAgent.id)) return true;
        return agentNamePattern.test(log.message);
      })
      .sort((a, b) => b.tick - a.tick || b.timestamp - a.timestamp);
  }, [logs, selectedAgent]);

  const summary = useMemo(() => {
    const counts = { ECONOMY: 0, SOCIAL: 0, SPATIAL: 0, SYSTEM: 0 };
    for (const log of activities) {
      if (log.category in counts) {
        counts[log.category as keyof typeof counts] += 1;
      }
    }
    return counts;
  }, [activities]);

  if (!selectedAgent) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-slate-400 text-sm italic bg-white/30 rounded-xl border border-dashed border-slate-300 px-4 text-center">
        <Activity className="w-8 h-8 mb-2 opacity-50" />
        Select a citizen first to see their lifetime activity log.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-3">
      {globalQuest ? (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="font-bold uppercase tracking-wider text-[10px]">Global Quest</span>
            <span className="text-[10px] font-mono">Reward {globalQuest.reward_coin} coin</span>
          </div>
          <div className="font-semibold">{globalQuest.title}</div>
          <div className="text-[11px] mt-0.5">{globalQuest.description}</div>
          <div className="mt-1.5 text-[11px] font-mono">
            Progress: {globalQuest.progress_amount}/{globalQuest.target_amount} {globalQuest.resource}
          </div>
          <div className="mt-1 h-2 rounded bg-amber-100 overflow-hidden">
            <svg className="h-full w-full block" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">
              <rect
                x="0"
                y="0"
                width={Math.max(0, Math.min(100, (globalQuest.progress_amount / Math.max(1, globalQuest.target_amount)) * 100))}
                height="8"
                className="fill-amber-400"
                rx="4"
                ry="4"
              />
            </svg>
          </div>
          {Object.keys(globalQuest.contributors || {}).length > 0 ? (
            <div className="mt-2 text-[10px]">
              <div className="font-semibold mb-1">Top contributors</div>
              <div className="grid grid-cols-1 gap-1">
                {Object.entries(globalQuest.contributors)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 5)
                  .map(([agentId, amount]) => {
                    const citizenName = agents[agentId]?.name || agentId;
                    const pct = (amount / Math.max(1, globalQuest.target_amount)) * 100;
                    const estReward = Math.floor((amount / Math.max(1, globalQuest.target_amount)) * globalQuest.reward_coin);
                    return (
                      <div key={agentId} className="flex items-center justify-between rounded bg-white/60 border border-amber-200 px-2 py-1">
                        <span className="font-semibold truncate mr-2">{citizenName}</span>
                        <span className="font-mono">{amount} ({pct.toFixed(1)}%) ≈ {estReward} coin</span>
                      </div>
                    );
                  })}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="border-b border-white/20 pb-3">
        <div className="flex items-center gap-2 mb-2">
          <UserRound className="w-4 h-4 text-slate-500" />
          <span className="text-xs font-semibold tracking-wider text-slate-600 uppercase">
            {selectedAgent.name} Lifetime Activity
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs font-semibold">
          <div className="rounded border border-slate-300 bg-white px-2 py-1.5 text-slate-700 col-span-2">
            Total entries: {activities.length}
          </div>
          <div className="rounded border border-amber-300 bg-amber-50 px-2 py-1.5 text-amber-900">Economy: {summary.ECONOMY}</div>
          <div className="rounded border border-sky-300 bg-sky-50 px-2 py-1.5 text-sky-900">Social: {summary.SOCIAL}</div>
          <div className="rounded border border-cyan-300 bg-cyan-50 px-2 py-1.5 text-cyan-900">Spatial: {summary.SPATIAL}</div>
          <div className="rounded border border-slate-300 bg-slate-100 px-2 py-1.5 text-slate-900">System: {summary.SYSTEM}</div>
        </div>
      </div>

      {activities.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-xs italic px-3 text-center">
          No activity logs recorded for this citizen yet.
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-1 space-y-1.5 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-white/5">
          {activities.slice(0, 60).map((log) => (
            <div
              key={log.id}
              className={cn(
                "rounded border px-2.5 py-2 text-xs font-mono space-y-1.5 text-slate-800 shadow-sm",
                CATEGORY_CARD_STYLES[log.category] || "border-slate-300 bg-white"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <Clock3 className="w-3.5 h-3.5 text-slate-500" />
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">
                    [{log.calendar_date || String(log.tick).padStart(4, "0")}]
                  </span>
                </div>
                <span className={cn("text-[10px] font-bold uppercase tracking-wider rounded px-1.5 py-0.5 border", CATEGORY_BADGE_STYLES[log.category] || "border-slate-300 bg-slate-100 text-slate-900")}>
                  {log.category}
                </span>
              </div>
              <div className="text-slate-900 leading-5 whitespace-pre-wrap font-semibold">{log.message}</div>
              <div className="text-[10px] text-slate-600 flex items-center gap-2">
                <span>tick {log.tick}</span>
                {log.source_agent_id === selectedAgent.id ? <span className="text-emerald-700 font-semibold">source</span> : null}
                {log.participant_ids?.includes(selectedAgent.id) ? <span className="text-cyan-700 font-semibold">participant</span> : null}
                {(log.source_agent_id === selectedAgent.id || log.participant_ids?.includes(selectedAgent.id)) && (
                  <button
                    onClick={() => setSelectedAgent(selectedAgent.id)}
                    className="ml-auto rounded border border-slate-300 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-800 hover:bg-slate-100"
                  >
                    Focus
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
