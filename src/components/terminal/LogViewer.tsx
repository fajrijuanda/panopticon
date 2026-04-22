import { useSimulationStore } from "@/store/simulationStore";
import { useEffect, useRef, useState } from "react";
import { ListFilter } from "lucide-react";
import { cn } from "@/lib/utils";

const TYPE_COLORS: Record<string, string> = {
  ECONOMY: "text-accent-orange",
  SOCIAL: "text-accent-blue",
  SPATIAL: "text-accent-cyan",
  SYSTEM: "text-slate-400"
};

const TYPE_ROW_STYLES: Record<string, string> = {
  ECONOMY: "border-amber-300/40 bg-amber-500/12",
  SOCIAL: "border-sky-300/40 bg-sky-500/12",
  SPATIAL: "border-cyan-300/40 bg-cyan-500/12",
  SYSTEM: "border-slate-300/40 bg-slate-500/10",
};

export function LogViewer() {
  const { logs, agents, setSelectedAgent } = useSimulationStore();
  const viewportRef = useRef<HTMLDivElement>(null);
  const seenLogIdsRef = useRef<Set<string>>(new Set());
  const freshTimersRef = useRef<number[]>([]);
  const [filter, setFilter] = useState<string>("ALL");
  const [freshLogIds, setFreshLogIds] = useState<Record<string, boolean>>({});

  useEffect(() => {
    // Keep the newest entries visible at the top of the stream.
    if (viewportRef.current) {
      viewportRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [logs.length]);

  useEffect(() => {
    if (logs.length === 0) return;

    const unseenIds: string[] = [];
    for (const log of logs) {
      if (!seenLogIdsRef.current.has(log.id)) {
        unseenIds.push(log.id);
      }
    }

    if (unseenIds.length > 0) {
      setFreshLogIds((prev) => {
        const next = { ...prev };
        for (const id of unseenIds) next[id] = true;
        return next;
      });

      const timeoutId = window.setTimeout(() => {
        setFreshLogIds((prev) => {
          const next = { ...prev };
          for (const id of unseenIds) delete next[id];
          return next;
        });
      }, 5500);
      freshTimersRef.current.push(timeoutId);
    }

    for (const log of logs) {
      seenLogIdsRef.current.add(log.id);
    }
  }, [logs]);

  useEffect(() => {
    return () => {
      for (const timeoutId of freshTimersRef.current) {
        window.clearTimeout(timeoutId);
      }
      freshTimersRef.current = [];
    };
  }, []);

  const filteredLogs = logs
    .filter(log => filter === "ALL" || log.category === filter)
    .slice()
    .reverse();

  const nameToId = useState(() => {
    return new Map<string, string>();
  })[0];

  useEffect(() => {
    nameToId.clear();
    for (const ag of Object.values(agents)) {
      nameToId.set(ag.name.toLowerCase(), ag.id);
    }
  }, [agents, nameToId]);

  const findPrimaryAgentId = (message: string, participantIds?: string[], sourceAgentId?: string) => {
    if (sourceAgentId && agents[sourceAgentId]) return sourceAgentId;
    if (participantIds && participantIds.length > 0) {
      const live = participantIds.find((id) => Boolean(agents[id]));
      if (live) return live;
    }

    const matches = message.match(/Citizen\s+\d+/g) || [];
    for (const m of matches) {
      const id = nameToId.get(m.toLowerCase());
      if (id) return id;
    }
    return null;
  };

  const renderMessage = (message: string) => {
    const chunks = message.split(/(Citizen\s+\d+)/g);
    return chunks.map((chunk, idx) => {
      if (/^Citizen\s+\d+$/.test(chunk)) {
        const targetId = nameToId.get(chunk.toLowerCase());
        if (targetId) {
          return (
            <button
              key={`${chunk}-${idx}`}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedAgent(targetId);
              }}
              className="rounded px-0.5 font-semibold text-cyan-700 underline decoration-dotted underline-offset-2 hover:bg-cyan-100"
            >
              {chunk}
            </button>
          );
        }
      }
      return <span key={`${chunk}-${idx}`}>{chunk}</span>;
    });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header / Filter Tabs */}
      <div className="flex items-center justify-between mb-3 border-b border-white/20 pb-2 gap-2">
        <div className="flex items-center gap-2">
          <ListFilter className="w-4 h-4 text-slate-500" />
          <span className="text-xs font-semibold tracking-wider text-slate-600 uppercase">Memory Stream</span>
        </div>
        <div className="flex gap-1 flex-wrap justify-end">
          {["ALL", "ECONOMY", "SOCIAL", "SPATIAL", "SYSTEM"].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-2 py-1 text-[9px] font-bold uppercase rounded transition-colors",
                filter === f ? "bg-slate-800 text-white" : "bg-white/50 text-slate-500 hover:bg-slate-300"
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Terminal View */}
      <div ref={viewportRef} className="flex-1 overflow-y-auto overflow-x-hidden terminal-scroll pr-2 bg-linear-to-b from-white/10 to-transparent rounded p-1">
        {filteredLogs.length === 0 ? (
          <div className="text-xs text-slate-400 font-mono italic">Waiting for events...</div>
        ) : (
          <div className="flex flex-col gap-1.5 min-h-max">
            {filteredLogs.map(log => {
              const targetId = findPrimaryAgentId(log.message, log.participant_ids, log.source_agent_id);
              const isFresh = Boolean(freshLogIds[log.id]);
              return (
              <div
                key={log.id}
                className={cn(
                  "w-full overflow-hidden text-xs font-mono flex items-start leading-[1.4] gap-2 rounded border px-2 py-1 transition-all",
                  TYPE_ROW_STYLES[log.category] || "border-slate-300/30 bg-slate-500/10",
                  isFresh ? "log-enter-right ring-1 ring-white/70 shadow-md" : "opacity-80",
                  targetId ? "cursor-pointer hover:bg-cyan-100/60" : ""
                )}
                onClick={() => {
                  if (targetId) setSelectedAgent(targetId);
                }}
                title={targetId ? "Click to focus citizen" : undefined}
              >
                <span className="text-slate-400 shrink-0 whitespace-nowrap">
                  [{log.calendar_date || String(log.tick).padStart(4, "0")}]
                </span>
                <span className={cn("font-semibold shrink-0", TYPE_COLORS[log.category] || "text-slate-500")}>
                  {log.category}
                </span>
                {isFresh ? (
                  <span className="shrink-0 rounded bg-white/60 px-1 py-0.5 text-[9px] font-bold tracking-wide text-slate-700">
                    NEW
                  </span>
                ) : null}
                <span className="text-slate-700 whitespace-pre-wrap wrap-break-word flex-1 min-w-0">{renderMessage(log.message)}</span>
              </div>
            )})}
          </div>
        )}
      </div>
    </div>
  );
}
