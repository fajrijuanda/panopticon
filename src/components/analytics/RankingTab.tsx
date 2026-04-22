"use client";

import { useMemo } from "react";
import { Crown, Medal, Trophy, UserRound } from "lucide-react";
import { useSimulationStore } from "@/store/simulationStore";
import { cn } from "@/lib/utils";

const SOCIAL_CLASS_BONUS: Record<string, number> = {
  nomad: 0,
  peasant: 8,
  citizen: 16,
  noble: 26,
  royalty: 38,
};

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value));
}

function rankBadge(rank: number) {
  if (rank === 1) return { icon: Trophy, color: "text-amber-500", bg: "bg-amber-50 border-amber-200" };
  if (rank === 2) return { icon: Medal, color: "text-slate-500", bg: "bg-slate-50 border-slate-200" };
  if (rank === 3) return { icon: Medal, color: "text-orange-600", bg: "bg-orange-50 border-orange-200" };
  return { icon: UserRound, color: "text-slate-400", bg: "bg-white border-slate-200" };
}

export function RankingTab() {
  const { agents, setSelectedAgent } = useSimulationStore();

  const ranked = useMemo(() => {
    const alive = Object.values(agents).filter((a) => a.is_alive);

    const rows = alive.map((agent) => {
      const vitalScore = (
        clamp(agent.vitals.energy) * 0.24 +
        clamp(agent.vitals.hunger) * 0.2 +
        clamp(agent.vitals.hydration) * 0.2 +
        clamp(agent.vitals.social) * 0.18 +
        clamp(agent.vitals.happiness) * 0.18
      );

      const wealthRaw =
        agent.inventory.coin * 1.8 +
        agent.inventory.tools * 2.0 +
        agent.inventory.stone * 0.6 +
        agent.inventory.wood * 0.45 +
        agent.inventory.food * 0.7 +
        agent.inventory.meat * 0.85 +
        agent.inventory.crop * 0.6 +
        agent.inventory.fruit * 0.6 +
        agent.inventory.herb * 0.6 +
        (agent.inventory.has_boat ? 20 : 0) +
        (agent.inventory.has_cart ? 16 : 0) +
        (agent.inventory.has_horse ? 14 : 0) +
        (agent.inventory.has_car ? 32 : 0);
      const economyScore = Math.min(100, wealthRaw / 3.2);

      const skills = Object.values(agent.skills || {});
      const topSkills = skills.sort((a, b) => b - a).slice(0, 4);
      const skillScore = topSkills.length > 0 ? Math.min(100, topSkills.reduce((acc, n) => acc + n, 0) / topSkills.length) : 0;

      const relations = Object.values(agent.relationships || {});
      const friendCount = relations.filter((r) => Number((r as any).friendship ?? (r as any).value ?? 0) >= 35).length;
      const relationScore = Math.min(100, friendCount * 12 + (agent.partner_id ? 16 : 0) + agent.allies.length * 8);

      const personality = agent.personality;
      const leadershipRaw =
        Math.max(0, personality.bravery) * 20 +
        Math.max(0, personality.intellect) * 22 +
        Math.max(0, personality.sociability) * 20 +
        Math.max(0, personality.ambition) * 20 +
        Math.max(0, personality.empathy) * 18;
      const leadershipScore = Math.min(100, leadershipRaw + (SOCIAL_CLASS_BONUS[agent.social_class] || 0));

      const finalScore =
        vitalScore * 0.27 +
        economyScore * 0.23 +
        skillScore * 0.2 +
        relationScore * 0.15 +
        leadershipScore * 0.15;

      return {
        id: agent.id,
        name: agent.name,
        socialClass: agent.social_class,
        job: agent.job,
        model: `${agent.model_slot} · ${agent.model_name}`,
        score: finalScore,
        breakdown: {
          vital: vitalScore,
          economy: economyScore,
          skill: skillScore,
          relation: relationScore,
          leadership: leadershipScore,
        },
      };
    });

    return rows.sort((a, b) => b.score - a.score);
  }, [agents]);

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="border-b border-white/20 pb-3">
        <div className="flex items-center gap-2 mb-2">
          <Crown className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-semibold tracking-wider text-slate-600 uppercase">Citizen Ranking</span>
        </div>
        <p className="text-[11px] text-slate-500">
          Composite score dari vital, ekonomi, skill, relasi, dan leadership.
        </p>
      </div>

      {ranked.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-xs italic px-3 text-center">
          No citizens available for ranking yet.
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-1 space-y-1.5 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-white/5">
          {ranked.map((row, index) => {
            const rank = index + 1;
            const badge = rankBadge(rank);
            const BadgeIcon = badge.icon;
            return (
              <button
                key={row.id}
                onClick={() => setSelectedAgent(row.id)}
                className={cn(
                  "w-full text-left p-2.5 rounded border shadow-sm transition-colors hover:bg-white/80",
                  badge.bg
                )}
                title="Click to focus citizen"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className={cn("h-6 w-6 rounded-full border flex items-center justify-center", badge.color)}>
                      <BadgeIcon className="w-3.5 h-3.5" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-slate-800 truncate">#{rank} {row.name}</div>
                      <div className="text-[10px] text-slate-500 truncate">{row.socialClass} · {row.job} · {row.model}</div>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Score</div>
                    <div className="text-sm font-black text-slate-800">{row.score.toFixed(1)}</div>
                  </div>
                </div>

                <div className="mt-2 grid grid-cols-5 gap-1 text-[9px] font-semibold">
                  <div className="rounded bg-cyan-100 text-cyan-800 px-1.5 py-1">Vital {row.breakdown.vital.toFixed(0)}</div>
                  <div className="rounded bg-amber-100 text-amber-800 px-1.5 py-1">Economy {row.breakdown.economy.toFixed(0)}</div>
                  <div className="rounded bg-indigo-100 text-indigo-800 px-1.5 py-1">Skill {row.breakdown.skill.toFixed(0)}</div>
                  <div className="rounded bg-emerald-100 text-emerald-800 px-1.5 py-1">Relation {row.breakdown.relation.toFixed(0)}</div>
                  <div className="rounded bg-rose-100 text-rose-800 px-1.5 py-1">Leadership {row.breakdown.leadership.toFixed(0)}</div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
