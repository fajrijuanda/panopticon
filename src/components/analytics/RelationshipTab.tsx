"use client";

import { useSimulationStore } from "@/store/simulationStore";
import { useMemo } from "react";
import { Users, Heart, Handshake } from "lucide-react";
import { cn } from "@/lib/utils";

const RELATIONSHIP_COLORS: Record<string, string> = {
  very_close: "border-rose-300 bg-rose-50 text-rose-900",
  close: "border-red-300 bg-red-50 text-red-900",
  friends: "border-amber-300 bg-amber-50 text-amber-900",
  acquaintances: "border-blue-300 bg-blue-50 text-blue-900",
  neutral: "border-slate-300 bg-slate-100 text-slate-900",
  distant: "border-purple-300 bg-purple-50 text-purple-900",
  hostile: "border-orange-300 bg-orange-50 text-orange-900",
};

function getRelationshipStatus(value: number): string {
  if (value >= 75) return "very_close";
  if (value >= 50) return "close";
  if (value >= 25) return "friends";
  if (value >= 15) return "acquaintances";
  if (value > -25) return "neutral";
  if (value > -50) return "distant";
  return "hostile";
}

function RelationshipIcon({ value, spouse_id }: { value: number; spouse_id?: string }) {
  if (spouse_id) return <Heart className="w-4 h-4 text-rose-200 drop-shadow-sm" />;
  if (value >= 50) return <Handshake className="w-4 h-4" />;
  return <Users className="w-4 h-4" />;
}

export function RelationshipTab() {
  const { agents } = useSimulationStore();

  const overview = useMemo(() => {
    const aliveAgents = Object.values(agents).filter(a => a.is_alive);
    const pairs = new Map<string, {
      a_id: string;
      b_id: string;
      a_name: string;
      b_name: string;
      value: number;
      friendship: number;
      romance: number;
      spouse: boolean;
      status: string;
    }>();

    for (const a of aliveAgents) {
      const relDict = a.relationships || {};
      for (const [otherId, rel] of Object.entries(relDict)) {
        const b = agents[otherId];
        if (!b || !b.is_alive) continue;
        const key = [a.id, otherId].sort().join("::");
        if (pairs.has(key)) continue;

        const value = Number((rel as any).value || 0);
        const friendship = Number((rel as any).friendship ?? value);
        const romance = Number((rel as any).romance ?? 0);
        const spouse = a.partner_id === otherId || b.partner_id === a.id;

        pairs.set(key, {
          a_id: a.id,
          b_id: otherId,
          a_name: a.name,
          b_name: b.name,
          value,
          friendship,
          romance,
          spouse,
          status: getRelationshipStatus(value),
        });
      }
    }

    const list = Array.from(pairs.values()).sort((x, y) => Math.abs(y.value) - Math.abs(x.value));
    const spousePairs = list.filter(x => x.spouse).length;
    const friendPairs = list.filter(x => x.friendship >= 35).length;
    const romancePairs = list.filter(x => x.romance >= 30).length;

    return {
      list,
      spousePairs,
      friendPairs,
      romancePairs,
      population: aliveAgents.length,
    };
  }, [agents]);

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Header */}
      <div className="border-b border-white/20 pb-3">
        <div className="flex items-center gap-2 mb-2">
          <Users className="w-4 h-4 text-slate-500" />
          <span className="text-xs font-semibold tracking-wider text-slate-600 uppercase">Global Relationships</span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs font-semibold">
          <div className="rounded border border-slate-300 bg-white px-2 py-1.5 text-slate-700">Population: {overview.population}</div>
          <div className="rounded border border-slate-300 bg-white px-2 py-1.5 text-slate-700">Pairs: {overview.list.length}</div>
          <div className="rounded border border-emerald-300 bg-emerald-50 px-2 py-1.5 text-emerald-900">Friend pairs: {overview.friendPairs}</div>
          <div className="rounded border border-rose-300 bg-rose-50 px-2 py-1.5 text-rose-900">Romance pairs: {overview.romancePairs}</div>
          <div className="rounded border border-indigo-300 bg-indigo-50 px-2 py-1.5 text-indigo-900 col-span-2">Married pairs: {overview.spousePairs}</div>
        </div>
      </div>

      {/* Pair List */}
      {overview.list.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-xs italic px-3 text-center">
          No social bonds yet — citizens will interact over time
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-1 space-y-1.5 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-white/5">
          {overview.list.slice(0, 50).map(rel => (
            <div
              key={`${rel.a_id}-${rel.b_id}`}
              className={cn(
                "p-2.5 rounded border text-xs font-mono space-y-1.5 shadow-sm",
                RELATIONSHIP_COLORS[rel.status] || "border-slate-300 bg-white text-slate-900"
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <RelationshipIcon value={rel.value} spouse_id={rel.spouse ? rel.b_id : undefined} />
                  <span className="font-bold text-slate-900">{rel.a_name}</span>
                  <span className="opacity-80 text-slate-600">↔</span>
                  <span className="font-bold text-slate-900">{rel.b_name}</span>
                  {rel.spouse && <span className="text-amber-700">💑</span>}
                </div>
                <div className="font-bold text-slate-900">{rel.value.toFixed(1)}</div>
              </div>
              <div className="text-[10px] text-slate-700 font-semibold">
                Status: <span className="capitalize">{rel.status}</span>
              </div>
              <div className="text-[10px] text-slate-700 flex items-center justify-between gap-2">
                <span>Friendship: {rel.friendship.toFixed(1)}</span>
                <span>Romance: {rel.romance.toFixed(1)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
