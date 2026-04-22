import { useEffect, useState } from "react";
import { useSimulationStore } from "@/store/simulationStore";
import { Battery, Flame, BrainCircuit, Box, Users, Droplet, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

function VitalBar({
  label,
  value,
  textColor,
  icon: Icon,
}: {
  label: string;
  value: number;
  textColor: string;
  icon: LucideIcon;
}) {
  return (
    <div className="mb-3">
      <div className="flex justify-between items-center mb-1 text-xs font-semibold text-slate-600 uppercase tracking-wide">
        <div className="flex items-center gap-1.5">
          <Icon className={cn("w-3.5 h-3.5", textColor)} />
          {label}
        </div>
        <span>{Math.round(value)}%</span>
      </div>
      <div className="h-2 w-full bg-slate-200/50 rounded-full overflow-hidden">
        <svg className="h-full w-full block" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">
          <rect x="0" y="0" width={Math.max(0, Math.min(100, value))} height="8" className={cn("fill-current", textColor)} rx="4" ry="4" />
        </svg>
      </div>
    </div>
  );
}

function TraitBadge({ label, value }: { label: string, value: number }) {
  const color = value > 0.3 ? "bg-emerald-100 text-emerald-700" : value < -0.3 ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600";
  return <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-bold uppercase", color)}>{label}: {value > 0 ? "+" : ""}{value.toFixed(1)}</span>;
}

const CLASS_DISPLAY: Record<string, { icon: string; label: string; color: string }> = {
  nomad:    { icon: "🚶", label: "Nomad",    color: "text-slate-500" },
  peasant:  { icon: "🛖", label: "Peasant",  color: "text-amber-700" },
  citizen:  { icon: "🏠", label: "Citizen",  color: "text-blue-600" },
  noble:    { icon: "🏛️", label: "Noble",    color: "text-purple-600" },
  royalty:  { icon: "👑", label: "Royalty",  color: "text-yellow-500" },
};

const TELEMETRY_TABS = [
  { id: "needs", label: "Needs" },
  { id: "overview", label: "Overview" },
  { id: "inventory", label: "Inventory" },
  { id: "personality", label: "Personality" },
  { id: "family", label: "Family" },
  { id: "skills", label: "Skills" },
  { id: "relations", label: "Relations" },
] as const;

function formatAge(days: number) {
  const years = Math.floor(days / 360);
  const months = Math.floor((days % 360) / 30);
  const remDays = days % 30;
  return `${years}y ${months}m ${remDays}d`;
}

export function TelemetryPanel() {
  const { agents, selectedAgentId, settlements, houses } = useSimulationStore();
  const agent = selectedAgentId ? agents[selectedAgentId] : null;
  const [activeTab, setActiveTab] = useState<(typeof TELEMETRY_TABS)[number]["id"]>("needs");

  useEffect(() => {
    setActiveTab("needs");
  }, [selectedAgentId]);

  const relationshipSummary = agent ? (() => {
    const entries = Object.entries(agent.relationships || {})
      .map(([otherId, rel]) => {
        const other = agents[otherId];
        if (!other) return null;
        const value = Number((rel as any).value || 0);
        const friendship = Number((rel as any).friendship ?? value);
        const romance = Number((rel as any).romance ?? 0);
        const spouse = agent.partner_id === otherId;
        return {
          otherId,
          name: other.name,
          value,
          friendship,
          romance,
          spouse,
        };
      })
      .filter(Boolean) as Array<{ otherId: string; name: string; value: number; friendship: number; romance: number; spouse: boolean }>;

    entries.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
    const top = entries.slice(0, 4);
    const avgFriendship = entries.length ? entries.reduce((acc, row) => acc + row.friendship, 0) / entries.length : 0;
    const avgRomance = entries.length ? entries.reduce((acc, row) => acc + row.romance, 0) / entries.length : 0;
    return {
      total: entries.length,
      avgFriendship,
      avgRomance,
      top,
    };
  })() : null;

  if (!agent) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-slate-400 text-sm italic bg-white/30 rounded-xl border border-dashed border-slate-300">
        <Box className="w-8 h-8 mb-2 opacity-50" />
        Select citizens to view telemetry.
      </div>
    );
  }

  const genderIcon = agent.gender === "male" ? "♂" : "♀";
  const genderColor = agent.gender === "male" ? "text-blue-500" : "text-pink-500";
  const phaseLabels: Record<string, string> = {
    baby: "👶 Baby", child: "🧒 Child", teen: "🧑‍🎓 Teen",
    young_adult: "💪 Young Adult", adult: "🧑 Adult", elder: "🧓 Elder",
  };
  const classInfo = CLASS_DISPLAY[agent.social_class] || CLASS_DISPLAY.nomad;

  const ownedSettlement = settlements.find((settlement) => settlement.owner_id === agent.id) || null;
  const alliedSettlement = settlements.find((settlement) => settlement.allied_with?.includes(agent.id)) || null;
  const allianceName = ownedSettlement?.alliance_name || alliedSettlement?.alliance_name || "";
  const territoryName = ownedSettlement?.name || alliedSettlement?.name || "No territory claimed";
  const allianceMemberIds = ownedSettlement
    ? [ownedSettlement.owner_id, ...(ownedSettlement.allied_with || [])]
    : alliedSettlement
      ? [alliedSettlement.owner_id, ...(alliedSettlement.allied_with || [])]
      : [];
  const allianceMembers = allianceMemberIds
    .filter((id, index, list) => list.indexOf(id) === index)
    .map((id) => agents[id]?.name || id)
    .filter(Boolean);
  const directAllies = (agent.allies || [])
    .filter((id, index, list) => list.indexOf(id) === index)
    .map((id) => agents[id]?.name || id)
    .filter(Boolean);
  const allAllianceMembers = Array.from(new Set([agent.name, ...allianceMembers, ...directAllies]));
  const allianceDisplayName = allianceName || (allAllianceMembers.length > 1 ? `${agent.name}'s Alliance` : "No alliance yet");
  const hasAlliance = allAllianceMembers.length > 1;
  const partnerName = agent.partner_id ? (agents[agent.partner_id]?.name || agent.partner_id) : "";
  const roleLabel = ownedSettlement
    ? (ownedSettlement.allied_with?.length ? "Alliance Founder / Ruler" : "Territory Founder")
    : alliedSettlement
      ? "Alliance Member"
      : "Nomad";
  const house = houses.find((item) => item.id === agent.house_id) || houses.find((item) => item.owner_id === agent.id) || null;
  const livingWith = house
    ? house.residents
        .map((residentId) => agents[residentId]?.name || residentId)
        .filter(Boolean)
    : [];
  const hasVehicleNote = agent.inventory.has_horse
    ? "Horse available via wild horse resource or crop-based taming."
    : "Wild horse nodes can be tamed, or collect 10 crop to tame one.";

  const parentNames = (agent.parents || [])
    .map((parentId) => agents[parentId]?.name || "Unknown")
    .filter(Boolean);
  const childrenNames = (agent.children || [])
    .map((childId) => agents[childId]?.name || "Unknown")
    .filter(Boolean);
  const partner = agent.partner_id ? agents[agent.partner_id] : null;

  function FamilyNode({ title, name, accent }: { title: string; name: string; accent: string }) {
    return (
      <div className={cn("min-w-0 rounded-xl border px-3 py-2 text-center shadow-sm", accent)}>
        <div className="text-[9px] uppercase tracking-widest font-bold opacity-80">{title}</div>
        <div className="mt-0.5 text-sm font-semibold text-slate-800 truncate">{name}</div>
      </div>
    );
  }

  function TabButton({ id, label }: { id: (typeof TELEMETRY_TABS)[number]["id"]; label: string }) {
    return (
      <button
        onClick={() => setActiveTab(id)}
        className={cn(
          "px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-colors border",
          activeTab === id
            ? "bg-slate-900 text-white border-slate-900 shadow-sm"
            : "bg-white/60 text-slate-500 border-slate-200 hover:bg-white"
        )}
      >
        {label}
      </button>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar flex flex-col gap-3">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-lg font-bold bg-clip-text text-transparent bg-linear-to-r from-slate-900 to-slate-500">
            <span className={genderColor}>{genderIcon}</span> {agent.name}
          </h3>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mt-0.5">
            {phaseLabels[agent.life_phase]} · Age {formatAge(agent.age)}
          </p>
          <div className="flex items-center gap-2 mt-1">
            <span className={cn("text-xs font-bold", classInfo.color)}>{classInfo.icon} {classInfo.label}</span>
            <span className="text-[10px] bg-cyan-100 text-cyan-700 px-1.5 py-0.5 rounded font-mono font-bold tracking-tight">{agent.model_slot} · {agent.model_name}</span>
            <span className="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-mono font-bold tracking-tight">{agent.job}</span>
            {hasAlliance ? <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-semibold tracking-tight">🤝 Alliance</span> : null}
            {agent.royal_title ? <span className="text-[10px] bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded font-bold uppercase tracking-tight">{agent.royal_title.replace("_", " ")}</span> : null}
            {agent.partner_id && <span className="text-[10px] text-pink-500 font-semibold">💍 {partnerName}</span>}
            {agent.is_pregnant && <span className="text-[10px] text-amber-500">🤰 {agent.pregnancy_timer}d</span>}
            {agent.house_id && <span className="text-[10px] text-slate-400">🏠</span>}
            {agent.jailed_timer > 0 && <span className="text-[10px] text-red-500 font-bold">⛓️ Jailed ({agent.jailed_timer})</span>}
          </div>
        </div>
        <span className="px-2 py-1 text-[9px] uppercase tracking-wider font-bold rounded bg-slate-100 text-slate-600 border border-slate-200">
          {agent.actionState}
        </span>
      </div>

      {/* Thought */}
      <div className="min-h-20 bg-slate-900 rounded-xl p-3 shadow-inner relative overflow-hidden">
        <div className="absolute top-2 right-2 opacity-50"><BrainCircuit className="w-5 h-5 text-accent-cyan" /></div>
        <div className="text-[10px] font-mono text-white mb-1 uppercase tracking-widest">&gt; thought</div>
        <p className="text-xs font-mono text-slate-300 leading-relaxed">{agent.currentThought}</p>
        <p className="mt-2 text-[10px] font-mono text-slate-200">Generated at tick {agent.last_thought_tick}</p>
      </div>

      {/* Telemetry Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-white/20 pb-2">
        {TELEMETRY_TABS.map((tab) => (
          <TabButton key={tab.id} id={tab.id} label={tab.label} />
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="grid grid-cols-1 gap-2">
          <div className="rounded-xl border border-cyan-200 bg-cyan-500/10 p-3 text-xs text-slate-700">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold uppercase tracking-widest text-[10px] text-cyan-700">Territory</span>
              <span className="text-[10px] font-mono text-slate-500">{roleLabel}</span>
            </div>
            <div className="mt-1 font-semibold text-slate-800">{territoryName}</div>
            <div className="mt-1 text-[11px] text-slate-600">
              {ownedSettlement
                ? `Radius ${ownedSettlement.territory_radius} · Farming ${ownedSettlement.is_farming ? "active" : "inactive"}`
                : alliedSettlement
                  ? `Allied territory owned by ${agents[alliedSettlement.owner_id]?.name || alliedSettlement.owner_id}`
                  : "No claimed settlement yet."}
            </div>
          </div>

          <div className="rounded-xl border border-amber-200 bg-amber-500/10 p-3 text-xs text-slate-700">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold uppercase tracking-widest text-[10px] text-amber-700">Alliance / Kingdom</span>
              <span className="text-[10px] font-mono text-slate-500">{Math.max(0, allAllianceMembers.length - 1)} allies</span>
            </div>
            <div className="mt-1 font-semibold text-slate-800">{allianceDisplayName}</div>
            <div className="mt-1 text-[11px] text-slate-600">
              {hasAlliance
                ? `Members: ${allAllianceMembers.join(", ")}`
                : "Alliance forms when two citizens negotiate and link settlements."}
            </div>
          </div>

          <div className="rounded-xl border border-emerald-200 bg-emerald-500/10 p-3 text-xs text-slate-700">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold uppercase tracking-widest text-[10px] text-emerald-700">House Assets</span>
              <span className="text-[10px] font-mono text-slate-500">{house ? `Lv.${house.level}` : "No house"}</span>
            </div>
            <div className="mt-1 font-semibold text-slate-800">
              {house ? `${house.type.toUpperCase()} · (${house.x}, ${house.y})` : "No residential asset"}
            </div>
            <div className="mt-1 text-[11px] text-slate-600">
              {house
                ? `Residents: ${livingWith.length > 0 ? livingWith.join(", ") : "none"} · Radius ${house.territory_radius}`
                : "Build a residence to unlock family-based house assets and territorial expansion."}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-100 p-3 text-xs text-slate-700">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold uppercase tracking-widest text-[10px] text-slate-600">Transport</span>
              <span className="text-[10px] font-mono text-slate-500">Horse lane</span>
            </div>
            <div className="mt-1 font-semibold text-slate-800">
              {agent.inventory.has_horse ? "Horse unlocked" : "Horse not yet unlocked"}
            </div>
            <div className="mt-1 text-[11px] text-slate-600">{hasVehicleNote}</div>
          </div>
        </div>
      )}

      {activeTab === "needs" && (
        <div className="bg-white/40 rounded-xl p-3 ring-1 ring-black/5">
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500">Needs</span>
            <span className="text-[10px] text-slate-500 font-mono">vitals</span>
          </div>
          <VitalBar label="Energy" value={agent.vitals.energy} textColor="text-sky-500" icon={Battery} />
          <VitalBar label="Fullness" value={agent.vitals.hunger} textColor="text-rose-500" icon={Flame} />
          <VitalBar label="Hydration" value={agent.vitals.hydration} textColor="text-blue-500" icon={Droplet} />
          <VitalBar label="Social" value={agent.vitals.social} textColor="text-emerald-500" icon={Users} />
        </div>
      )}

      {activeTab === "inventory" && (
        <div className="flex flex-col gap-3">
          <div className="bg-white/40 rounded-xl p-3 ring-1 ring-black/5 grid grid-cols-4 gap-2">
            {[
              { icon: "🪵", label: "Wood", val: agent.inventory.wood },
              { icon: "🐖", label: "Pig", val: agent.inventory.pig },
              { icon: "🐄", label: "Cow", val: agent.inventory.cow },
              { icon: "🐔", label: "Chicken", val: agent.inventory.chicken },
              { icon: "🥩", label: "Meat", val: agent.inventory.meat },
              { icon: "🍎", label: "Fruit", val: agent.inventory.fruit },
              { icon: "🌾", label: "Crop", val: agent.inventory.crop },
              { icon: "🪙", label: "Coin", val: agent.inventory.coin },
              { icon: "🪨", label: "Stone", val: agent.inventory.stone },
              { icon: "🔨", label: "Tools", val: agent.inventory.tools },
              { icon: "🌿", label: "Herb", val: agent.inventory.herb },
              { icon: "🍄", label: "Food", val: agent.inventory.food },
            ].map(item => (
              <div key={item.label} className="text-center bg-white/30 rounded p-1">
                <div className="text-[8px] uppercase font-bold text-slate-500 mb-0.5">{item.icon} {item.label}</div>
                <div className="text-sm font-mono font-bold text-slate-700">{item.val}</div>
              </div>
            ))}
          </div>

          <div className="bg-white/40 rounded-xl p-2 ring-1 ring-black/5 flex justify-around text-xs">
            <div className={cn("text-center", agent.inventory.has_boat ? "opacity-100" : "opacity-30 grayscale")}>⛵ Boat</div>
            <div className={cn("text-center", agent.inventory.has_cart ? "opacity-100" : "opacity-30 grayscale")}>🛒 Cart</div>
            <div className={cn("text-center", agent.inventory.has_horse ? "opacity-100" : "opacity-30 grayscale")}>🐎 Horse</div>
            <div className={cn("text-center", agent.inventory.has_car ? "opacity-100" : "opacity-30 grayscale")}>🚗 Car</div>
          </div>
        </div>
      )}

      {activeTab === "personality" && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1">
            <TraitBadge label="Kind" value={agent.personality.kindness} />
            <TraitBadge label="Brave" value={agent.personality.bravery} />
            <TraitBadge label="Social" value={agent.personality.sociability} />
            <TraitBadge label="Intellect" value={agent.personality.intellect} />
            {agent.personality.creativity !== 0 && <TraitBadge label="Creative" value={agent.personality.creativity} />}
            {agent.personality.ambition !== 0 && <TraitBadge label="Ambition" value={agent.personality.ambition} />}
            {agent.personality.empathy !== 0 && <TraitBadge label="Empathy" value={agent.personality.empathy} />}
            {agent.personality.cunning !== 0 && <TraitBadge label="Cunning" value={agent.personality.cunning} />}
          </div>

          <div className="bg-white/40 rounded-xl p-3 ring-1 ring-black/5 flex flex-col gap-1.5 text-xs text-slate-700">
            <div>
              <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500">Desire</span>
              <p className="font-mono text-[9px] mt-0.5 leading-tight">{agent.desire || "No ambitions."}</p>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <div>
                <span className="font-semibold uppercase tracking-wider text-[10px] text-emerald-600">Likes</span>
                <p className="font-mono text-[9px] mt-0.5">{agent.likes?.join(', ') || "-"}</p>
              </div>
              <div>
                <span className="font-semibold uppercase tracking-wider text-[10px] text-rose-600">Dislikes</span>
                <p className="font-mono text-[9px] mt-0.5">{agent.dislikes?.join(', ') || "-"}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === "family" && (
        <div className="flex flex-col gap-3">
          <div className="rounded-xl border border-slate-200 bg-white/50 p-3 shadow-sm">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Family Tree</div>
                <div className="text-[11px] text-slate-600">Direct lineage and household connections</div>
              </div>
              <div className="text-[10px] font-mono text-slate-500">
                {agent.partner_id ? `Spouse: ${partner?.name || agent.partner_id}` : "No spouse"}
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex justify-center gap-2 flex-wrap">
                {parentNames.length > 0 ? parentNames.map((name, idx) => (
                  <FamilyNode key={`parent-${idx}`} title={idx === 0 ? "Parent" : "Parent"} name={name} accent="bg-amber-50 border-amber-200" />
                )) : <div className="text-xs italic text-slate-400">No parent data recorded</div>}
              </div>

              <div className="flex justify-center">
                <div className="rounded-2xl border-2 border-cyan-300 bg-cyan-50 px-4 py-3 text-center shadow-md min-w-44">
                  <div className="text-[9px] uppercase tracking-widest font-bold text-cyan-700">Selected Citizen</div>
                  <div className="mt-1 text-sm font-bold text-slate-800">{agent.name}</div>
                  <div className="mt-1 text-[10px] text-slate-600">{phaseLabels[agent.life_phase]} · {classInfo.label}</div>
                </div>
              </div>

              <div className="flex justify-center gap-2 flex-wrap">
                {agent.partner_id && partner && (
                  <FamilyNode title="Spouse" name={partner.name} accent="bg-rose-50 border-rose-200" />
                )}
              </div>

              <div className="flex justify-center gap-2 flex-wrap">
                {childrenNames.length > 0 ? childrenNames.map((name, idx) => (
                  <FamilyNode key={`child-${idx}`} title="Child" name={name} accent="bg-emerald-50 border-emerald-200" />
                )) : <div className="text-xs italic text-slate-400">No children yet</div>}
              </div>
            </div>
          </div>

          <div className="bg-white/40 rounded-xl p-3 ring-1 ring-black/5 flex flex-col gap-1.5 text-xs text-slate-700">
            <div className="flex justify-between">
              <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500">Parents</span>
              <span className="font-mono text-[10px]">{parentNames.length > 0 ? parentNames.join(" & ") : "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500">Children</span>
              <span className="font-mono text-[10px]">
                {agent.children?.length > 0 ? (
                  <span title={agent.children.map(c => agents[c]?.name || "Unknown").join(", ")}>
                    {agent.children.length} offspring
                  </span>
                ) : "0"}
              </span>
            </div>
          </div>
        </div>
      )}

      {activeTab === "skills" && (
        <div className="bg-white/40 rounded-xl p-3 ring-1 ring-black/5 flex flex-col gap-1.5 text-xs text-slate-700">
          <div className="flex items-center justify-between">
            <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500">Skills</span>
            <span className="text-[10px] text-slate-500 font-mono">multi-skill</span>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.entries(agent.skills || {})
              .sort((a, b) => Number(b[1]) - Number(a[1]))
              .slice(0, 8)
              .map(([name, value]) => (
                <div key={name} className="rounded bg-white/60 border border-slate-200 px-2 py-1 text-[10px] flex items-center justify-between">
                  <span className="uppercase font-semibold text-slate-600">{name}</span>
                  <span className="font-mono text-slate-700">{Number(value).toFixed(1)}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {activeTab === "relations" && (
        <div className="bg-white/40 rounded-xl p-3 ring-1 ring-black/5 flex flex-col gap-1.5 text-xs text-slate-700">
          <div className="flex items-center justify-between">
            <span className="font-semibold uppercase tracking-wider text-[10px] text-slate-500">Relationship Snapshot</span>
            <span className="text-[10px] font-mono text-slate-600">{relationshipSummary?.total ?? 0} links</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[11px] font-semibold">
            <div className="rounded bg-emerald-100 text-emerald-700 px-2 py-1">Friendship avg: {(relationshipSummary?.avgFriendship ?? 0).toFixed(1)}</div>
            <div className="rounded bg-rose-100 text-rose-700 px-2 py-1">Romance avg: {(relationshipSummary?.avgRomance ?? 0).toFixed(1)}</div>
          </div>

          <div className="space-y-1">
            {(relationshipSummary?.top || []).length === 0 ? (
              <div className="text-[11px] italic text-slate-500">No relationship data yet.</div>
            ) : (
              relationshipSummary!.top.map((row) => (
                <div key={row.otherId} className="rounded bg-white/60 border border-slate-200 p-2 text-[11px]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-700">{row.name} {row.spouse ? "💑" : ""}</span>
                    <span className="font-mono text-slate-600">Total {row.value.toFixed(1)}</span>
                  </div>
                  <div className="mt-0.5 flex items-center justify-between text-[10px] text-slate-600">
                    <span>Friendship {row.friendship.toFixed(1)}</span>
                    <span>Romance {row.romance.toFixed(1)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

    </div>
  );
}
