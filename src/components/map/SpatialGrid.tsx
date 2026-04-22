/* eslint-disable */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSimulationStore } from "@/store/simulationStore";
import { AgentNode } from "./AgentNode";
import { buildUniqueAgentColorMap, cn, withAlpha } from "@/lib/utils";
import { Layers, LocateFixed, Maximize, ZoomIn, ZoomOut } from "lucide-react";

const TERRAIN_COLORS: Record<string, string> = {
  ocean: "#1e6091",
  beach: "#f0d9a0",
  grass: "#7ec850",
  forest: "#2d6a1e",
  mountain: "#8b7355",
  snow: "#e8e8e8",
  river: "#4a9bd9",
  road: "#a0896c",
  lake: "#3a7fb8",
};

const MAP_RENDER_SIZE = 900;

function formatAge(days: number) {
  const years = Math.floor(days / 360);
  const months = Math.floor((days % 360) / 30);
  const remDays = days % 30;
  return `${years}y ${months}m ${remDays}d`;
}

export function SpatialGrid() {
  const {
    agents,
    resources,
    settlements,
    gravestones,
    houses,
    terrain,
    mapSize,
    selectedAgentId,
    setSelectedAgent,
    mapViewMode,
    setMapViewMode,
    weather,
    hydrology,
    isRunning,
    tickCount,
  } = useSimulationStore();

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [displayedCloudCover, setDisplayedCloudCover] = useState(Math.max(0, Math.min(1, weather?.cloud_cover ?? 0.25)));
  const [pinCamera, setPinCamera] = useState(false);
  const [hoverTooltip, setHoverTooltip] = useState<null | { x: number; y: number; lines: string[] }>(null);
  const agentsRef = useRef(agents);
  const lastFocusedAgentRef = useRef<string | null>(null);

  const isIsometric = mapViewMode === "isometric";
  const gridSize = mapSize || 80;
  const toCellPercent = (value: number) => `${((value + 0.5) / gridSize) * 100}%`;
  const agentColorMap = useMemo(
    () => buildUniqueAgentColorMap(Object.keys(agents)),
    [agents],
  );

  const ownerNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const ag of Object.values(agents)) {
      map[ag.id] = ag.name;
    }
    return map;
  }, [agents]);

  const resourceTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const res of resources || []) {
      counts[res.type] = (counts[res.type] || 0) + 1;
    }
    return counts;
  }, [resources]);

  const productionZones = useMemo(() => {
    const zones: Array<{
      id: string;
      x: number;
      y: number;
      radius: number;
      label: string;
      details: string;
      ownerName: string;
      baseColor: string;
      current: number;
      capacity: number;
    }> = [];

    for (const agent of Object.values(agents)) {
      if (!agent.is_alive) continue;

      const ownerColor = agentColorMap[agent.id]?.base || "#94a3b8";
      const baseHouse = agent.house_id ? houses.find((house) => house.id === agent.house_id) : null;
      const ownedSettlement = settlements.find((settlement) => settlement.owner_id === agent.id) ?? null;
      const anchorX = baseHouse?.x ?? ownedSettlement?.x ?? undefined;
      const anchorY = baseHouse?.y ?? ownedSettlement?.y ?? undefined;

      const livestockTotal = Math.max(0, agent.inventory.chicken) + Math.max(0, agent.inventory.pig) + Math.max(0, agent.inventory.cow);
      if (livestockTotal > 0) {
        const livestockAnchorX = anchorX ?? agent.livestock_origin_x ?? agent.x;
        const livestockAnchorY = anchorY ?? agent.livestock_origin_y ?? agent.y;
        const label = agent.inventory.chicken > 0 && agent.inventory.pig + agent.inventory.cow > 0
          ? "Pasture"
          : agent.inventory.chicken >= agent.inventory.pig + agent.inventory.cow
            ? "Flock"
            : "Herd";
        const radius = Math.max(2, Math.min(10, Math.ceil(Math.sqrt(livestockTotal * 1.25)) + (baseHouse ? 1 : 0)));
        const capacity = radius * radius;

        zones.push({
          id: `livestock-${agent.id}`,
          x: livestockAnchorX,
          y: livestockAnchorY,
          radius,
          label,
          details: `${agent.inventory.chicken} 🐓, ${agent.inventory.pig} 🐖, ${agent.inventory.cow} 🐄`,
          ownerName: agent.name,
          baseColor: ownerColor,
          current: livestockTotal,
          capacity,
        });
      }

      const farmTotal = Math.max(0, agent.inventory.crop) + Math.max(0, agent.inventory.fruit);
      if (farmTotal > 0) {
        const farmAnchorX = anchorX ?? agent.farm_origin_x ?? agent.x;
        const farmAnchorY = anchorY ?? agent.farm_origin_y ?? agent.y;
        const radius = Math.max(2, Math.min(10, Math.ceil(Math.sqrt(farmTotal * 1.1)) + (baseHouse ? 1 : 0)));
        const capacity = radius * radius;

        zones.push({
          id: `farm-${agent.id}`,
          x: farmAnchorX,
          y: farmAnchorY,
          radius,
          label: "Farm",
          details: `${agent.inventory.crop} 🌾 crop, ${agent.inventory.fruit} 🍎 fruit`,
          ownerName: agent.name,
          baseColor: ownerColor,
          current: farmTotal,
          capacity,
        });
      }
    }

    return zones;
  }, [agents, agentColorMap, houses]);

  useEffect(() => {
    agentsRef.current = agents;
  }, [agents]);

  const toggleMode = () => {
    setMapViewMode(isIsometric ? "top-down" : "isometric");
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handlePointerUp = () => setIsDragging(false);

  const handleWheel = (e: React.WheelEvent) => {
    const zoomDelta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoom((prev) => Math.min(Math.max(0.3, prev + zoomDelta), 3));
  };

  const terrainCanvas = useMemo(() => {
    if (!terrain || terrain.length === 0) return null;
    const cellSize = MAP_RENDER_SIZE / gridSize;

    return (
      <div
        className="absolute inset-0"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${gridSize}, ${cellSize}px)`,
          gridTemplateRows: `repeat(${gridSize}, ${cellSize}px)`,
        }}
      >
        {terrain.flat().map((cell, idx) => (
          <div key={idx} style={{ backgroundColor: TERRAIN_COLORS[cell] || "#333" }} />
        ))}
      </div>
    );
  }, [terrain, gridSize]);

  useEffect(() => {
    if (!isRunning) return;

    const tick = window.setInterval(() => {
      const targetCover = weather?.condition === "rain"
        ? 0
        : Math.max(0, Math.min(1, weather?.cloud_cover ?? 0.25));

      setDisplayedCloudCover((prev) => {
        const delta = targetCover - prev;
        if (Math.abs(delta) < 0.01) return targetCover;
        const step = delta > 0 ? 0.05 : 0.12;
        return Math.max(0, Math.min(1, prev + Math.sign(delta) * step));
      });
    }, 350);

    return () => window.clearInterval(tick);
  }, [isRunning, weather?.condition, weather?.cloud_cover]);
  const centerCameraOnAgent = useCallback((agentId: string | null) => {
    if (!agentId) return;
    const selected = agentsRef.current[agentId];
    if (!selected) return;

    const targetX = ((selected.x + 0.5) / gridSize) * MAP_RENDER_SIZE;
    const targetY = ((selected.y + 0.5) / gridSize) * MAP_RENDER_SIZE;
    const mapCenter = MAP_RENDER_SIZE / 2;
    setPan({
      x: (mapCenter - targetX) * zoom,
      y: (mapCenter - targetY) * zoom,
    });
  }, [gridSize, zoom]);

  // Focus camera once when selection changes (from map click or log click).
  useEffect(() => {
    if (!selectedAgentId) {
      lastFocusedAgentRef.current = null;
      return;
    }

    if (lastFocusedAgentRef.current === selectedAgentId) {
      return;
    }

    centerCameraOnAgent(selectedAgentId);
    lastFocusedAgentRef.current = selectedAgentId;
  }, [selectedAgentId, centerCameraOnAgent]);

  // Lock behavior: only follow selected agent over time when pin camera is enabled.
  useEffect(() => {
    if (!pinCamera || !selectedAgentId) return;
    centerCameraOnAgent(selectedAgentId);
  }, [tickCount, pinCamera, selectedAgentId, centerCameraOnAgent]);

  useEffect(() => {
    if (!pinCamera || !selectedAgentId) return;
    centerCameraOnAgent(selectedAgentId);
  }, [pinCamera, selectedAgentId, centerCameraOnAgent]);

  const cloudCount = useMemo(() => {
    const cover = displayedCloudCover;
    if (cover <= 0.05) return 0;
    return Math.max(2, Math.round(4 + cover * 10));
  }, [displayedCloudCover]);

  const rainDrops = useMemo(() => {
    const intensity = Math.max(0, Math.min(1, weather?.rain_intensity ?? 0));
    const count = Math.max(0, Math.round(40 + intensity * 160));
    return Array.from({ length: count }, (_, i) => ({
      id: i,
      left: (i * 37) % 100,
      delay: (i * 0.07) % 2.4,
      duration: 0.7 + ((i * 13) % 10) / 10,
      opacity: 0.2 + (((i * 29) % 7) / 10),
    }));
  }, [weather?.rain_intensity]);

  return (
    <div
      className="relative w-full h-full flex flex-col items-center justify-center bg-slate-800 overflow-hidden cursor-grab active:cursor-grabbing"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
      onWheel={handleWheel}
    >
      <div className="absolute top-4 left-4 z-50 flex gap-2">
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleMode();
          }}
          className="flex items-center gap-2 px-3 py-2 bg-white/80 backdrop-blur-md border border-slate-200 rounded-lg shadow-sm text-sm font-medium text-slate-700 hover:bg-white transition-all focus:outline-none"
        >
          <Layers className="w-4 h-4" />
          {isIsometric ? "Top-Down" : "Isometric"}
        </button>

        <div className="flex bg-white/80 backdrop-blur-md border border-slate-200 rounded-lg shadow-sm overflow-hidden">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setZoom((z) => Math.max(0.3, z - 0.2));
            }}
            title="Zoom out"
            className="p-2 hover:bg-slate-100 border-r border-slate-200 text-slate-700"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setPan({ x: 0, y: 0 });
              setZoom(1);
            }}
            title="Reset zoom and pan"
            className="p-2 hover:bg-slate-100 border-r border-slate-200 text-slate-700"
          >
            <Maximize className="w-4 h-4" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setZoom((z) => Math.min(3, z + 0.2));
            }}
            title="Zoom in"
            className="p-2 hover:bg-slate-100 text-slate-700"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            setPinCamera((prev) => !prev);
          }}
          title="Pin camera to selected citizen"
          className={cn(
            "flex items-center gap-2 px-3 py-2 backdrop-blur-md border rounded-lg shadow-sm text-sm font-medium transition-all focus:outline-none relative",
            pinCamera ? "bg-cyan-600 text-white border-cyan-500" : "bg-white/80 text-slate-700 border-slate-200 hover:bg-white"
          )}
        >
          <LocateFixed className="w-4 h-4" />
          {pinCamera ? "Pin On" : "Pin Off"}
          {pinCamera && (
            <span className="absolute -top-2 -right-2 bg-emerald-500 text-white text-[9px] px-2 py-0.5 rounded-full font-bold whitespace-nowrap">
              🔒 Locked
            </span>
          )}
        </button>
      </div>

      <div className="absolute bottom-4 left-4 z-50 bg-black/60 backdrop-blur-md rounded-lg px-3 py-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-white font-medium">
        {Object.entries(TERRAIN_COLORS).map(([name, color]) => (
          <div key={name} className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <span className="capitalize">{name}</span>
          </div>
        ))}
      </div>

      <div className="absolute top-4 right-4 z-50 rounded-lg bg-black/60 px-3 py-2 text-[11px] font-medium text-white backdrop-blur-md">
        <div className="capitalize">Weather: {weather?.condition || "clear"}</div>
        <div>Groundwater avg: {hydrology?.avg_groundwater?.toFixed?.(1) ?? 0}</div>
        <div>Low-water tiles: {hydrology?.low_groundwater_tiles ?? 0}</div>
      </div>

      <div
        className="transition-transform ease-out duration-100 pointer-events-none"
        style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
      >
        <div
          className={cn("relative pointer-events-auto touch-none", isIsometric ? "shadow-2xl" : "")}
          style={{
            width: `${MAP_RENDER_SIZE}px`,
            height: `${MAP_RENDER_SIZE}px`,
            transform: isIsometric ? "rotateX(60deg) rotateZ(-45deg)" : "none",
            transition: "transform 1s ease-in-out",
            transformStyle: "preserve-3d",
          }}
        >
          {terrainCanvas}

          <div className={cn("pointer-events-none absolute inset-0 z-2 overflow-hidden", !isRunning && "weather-paused")}>
            {Array.from({ length: cloudCount }).map((_, i) => (
              <div
                key={`cloud-${i}`}
                className="weather-cloud"
                style={{
                  left: `${(i * 17) % 90}%`,
                  top: `${4 + ((i * 11) % 24)}%`,
                  animationDelay: `${(i * 0.8) % 4}s`,
                  opacity: Math.max(0.12, Math.min(0.75, displayedCloudCover)),
                }}
              />
            ))}

            {weather?.condition === "rain" && (
              <div className="absolute inset-0 weather-rain-layer">
                {rainDrops.map((drop) => (
                  <span
                    key={`drop-${drop.id}`}
                    className="weather-raindrop"
                    style={{
                      left: `${drop.left}%`,
                      animationDelay: `${drop.delay}s`,
                      animationDuration: `${drop.duration}s`,
                      opacity: drop.opacity,
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {Object.values(agents).map((agent) => (
            <AgentNode
              key={agent.id}
              agent={agent}
              colorTheme={agentColorMap[agent.id]}
              mapSize={gridSize}
              isSelected={selectedAgentId === agent.id}
              onClick={() => setSelectedAgent(selectedAgentId === agent.id ? null : agent.id)}
            />
          ))}

          {resources &&
            resources.map((res) => {
              const topPos = toCellPercent(res.y);
              const leftPos = toCellPercent(res.x);
              let icon = "🥩";
              if (res.type === "wood") icon = "🪵";
              else if (res.type === "coin") icon = "🪙";
              else if (res.type === "stone") icon = "🪨";
              else if (res.type === "fish") icon = "🐟";
              else if (res.type === "pig") icon = "🐖";
              else if (res.type === "cow") icon = "🐄";
              else if (res.type === "chicken") icon = "🐓";
              else if (res.type === "crop") icon = "🌾";
              else if (res.type === "fruit") icon = "🍎";
              else if (res.type === "herb") icon = "🌿";
              else if (res.type === "horse") icon = "🐎";

              return (
                <div
                  key={res.id}
                  className="absolute transform -translate-x-1/2 -translate-y-1/2 z-10 text-[10px] sm:text-xs select-none pointer-events-auto drop-shadow-lg"
                  style={{ top: topPos, left: leftPos }}
                  onMouseEnter={(e) => {
                    setHoverTooltip({
                      x: e.clientX,
                      y: e.clientY,
                      lines: [
                        `Resource: ${res.type.toUpperCase()}`,
                        `Coord: (${res.x}, ${res.y})`,
                        `Total ${res.type}: ${resourceTypeCounts[res.type] || 0}`,
                      ],
                    });
                  }}
                  onMouseMove={(e) => setHoverTooltip((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : prev))}
                  onMouseLeave={() => setHoverTooltip(null)}
                  title={`${res.type}`}
                >
                  {icon}
                </div>
              );
            })}

          {settlements &&
            settlements.map((settlement) => {
              const topPos = toCellPercent(settlement.y);
              const leftPos = toCellPercent(settlement.x);
              const ownerName = ownerNameMap[settlement.owner_id] || settlement.owner_id;
              const ownerColor = agentColorMap[settlement.owner_id];
              return (
                <div
                  key={settlement.id}
                  className="absolute transform -translate-x-1/2 -translate-y-1/2 z-5 text-base select-none pointer-events-auto drop-shadow-xl flex items-center justify-center"
                  style={{ top: topPos, left: leftPos }}
                  onMouseEnter={(e) => {
                    setHoverTooltip({
                      x: e.clientX,
                      y: e.clientY,
                      lines: [
                        `Settlement: ${settlement.id}`,
                        `Owner: ${ownerName}`,
                        `Coord: (${settlement.x}, ${settlement.y})`,
                        `Radius: ${settlement.territory_radius}`,
                        `Farming: ${settlement.is_farming ? "active" : "inactive"}`,
                        `Allies linked: ${settlement.allied_with?.length || 0}`,
                      ],
                    });
                  }}
                  onMouseMove={(e) => setHoverTooltip((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : prev))}
                  onMouseLeave={() => setHoverTooltip(null)}
                  title={`Settlement of ${ownerName}`}
                >
                  {settlement.territory_radius > 0 && (
                    <div
                      className="absolute border-2 border-dashed"
                      style={{
                        width: `${((settlement.territory_radius * 2 + 1) / gridSize) * MAP_RENDER_SIZE}px`,
                        height: `${((settlement.territory_radius * 2 + 1) / gridSize) * MAP_RENDER_SIZE}px`,
                        top: "50%",
                        left: "50%",
                        transform: "translate(-50%, -50%)",
                        borderColor: ownerColor?.territoryBorder || "rgba(52,211,153,0.45)",
                        backgroundColor: ownerColor?.territoryFill || "rgba(16,185,129,0.12)",
                      }}
                    />
                  )}
                  🏠
                  {settlement.is_farming && <span className="absolute -bottom-1 -right-2 text-[8px]">🌾</span>}
                </div>
              );
            })}

          {houses &&
            houses.map((house) => {
              const topPos = toCellPercent(house.y);
              const leftPos = toCellPercent(house.x);
              const ownerName = ownerNameMap[house.owner_id] || house.owner_id;
              const owner = agents[house.owner_id];
              const ownerColor = agentColorMap[house.owner_id];
              let icon = "🛖";
              if (house.is_under_construction) icon = "🚧";
              else if (house.type === "market") icon = "🏪";
              else if (house.type === "port") icon = "⚓";
              else if (house.type === "school") icon = "🎓";
              else {
                const houseIcons: Record<number, string> = { 1: "🛖", 2: "🏠", 3: "🏡", 4: "🏰" };
                icon = houseIcons[house.level] || "🛖";
              }
              const size = house.level >= 3 || house.type ? "text-lg" : "text-sm";

              return (
                <div
                  key={house.id}
                  className="absolute transform -translate-x-1/2 -translate-y-1/2 z-6 select-none pointer-events-auto"
                  style={{ top: topPos, left: leftPos }}
                  onMouseEnter={(e) => {
                    setHoverTooltip({
                      x: e.clientX,
                      y: e.clientY,
                      lines: [
                        `Building: ${house.type.toUpperCase()} (${house.id})`,
                        `Owner: ${ownerName}`,
                        `Coord: (${house.x}, ${house.y})`,
                        `Level: ${house.level}`,
                        `Residents: ${house.residents?.length || 0}`,
                        `Territory radius: ${house.territory_radius}`,
                        `Construction: ${house.is_under_construction ? `${house.labor_contributed}/${house.labor_required}` : "completed"}`,
                        owner ? `Owner resources: coin ${owner.inventory.coin}, wood ${owner.inventory.wood}, food ${owner.inventory.food}` : "Owner resources: -",
                      ],
                    });
                  }}
                  onMouseMove={(e) => setHoverTooltip((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : prev))}
                  onMouseLeave={() => setHoverTooltip(null)}
                >
                  {house.territory_radius > 0 && (
                    <div
                      className="absolute border-2 border-dashed"
                      style={{
                        width: `${((house.territory_radius * 2 + 1) / gridSize) * MAP_RENDER_SIZE}px`,
                        height: `${((house.territory_radius * 2 + 1) / gridSize) * MAP_RENDER_SIZE}px`,
                        top: "50%",
                        left: "50%",
                        transform: "translate(-50%, -50%)",
                        borderColor: ownerColor?.territoryBorder || "rgba(251,191,36,0.35)",
                        backgroundColor: withAlpha(ownerColor?.base || "#f59e0b", 0.07),
                      }}
                    />
                  )}
                  <span className={`${size} drop-shadow-xl`}>{icon}</span>
                </div>
              );
            })}

          {productionZones.map((zone) => {
            const topPos = toCellPercent(zone.y);
            const leftPos = toCellPercent(zone.x);
            const side = ((zone.radius * 2 + 1) / gridSize) * MAP_RENDER_SIZE;
            const borderColor = withAlpha(zone.baseColor, 0.55);
            const fillColor = withAlpha(zone.baseColor, 0.14);
            const isOverCapacity = zone.current >= zone.capacity;
            const upgradeCostWood = zone.radius + 1;
            const upgradeCostCoin = Math.max(0, zone.radius - 1);

            return (
              <div
                key={zone.id}
                className="absolute transform -translate-x-1/2 -translate-y-1/2 z-4 pointer-events-auto select-none"
                style={{ top: topPos, left: leftPos }}
                onMouseEnter={(e) => {
                  setHoverTooltip({
                    x: e.clientX,
                    y: e.clientY,
                    lines: [
                      `${zone.label} — ${zone.ownerName}`,
                      `Coord: (${zone.x}, ${zone.y})`,
                      `Area: ${zone.radius * 2 + 1}×${zone.radius * 2 + 1} tiles (radius ${zone.radius})`,
                      `Capacity: ${zone.current}/${zone.capacity}${isOverCapacity ? " ⚠️ FULL" : ""}`,
                      zone.details,
                      `Expand cost: ${upgradeCostWood} wood, ${upgradeCostCoin} coin`,
                    ],
                  });
                }}
                onMouseMove={(e) => setHoverTooltip((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : prev))}
                onMouseLeave={() => setHoverTooltip(null)}
              >
                <div
                  className="absolute border border-dashed"
                  style={{
                    width: `${side}px`,
                    height: `${side}px`,
                    top: "50%",
                    left: "50%",
                    transform: "translate(-50%, -50%)",
                    borderColor,
                    backgroundColor: fillColor,
                  }}
                />
                <span
                  className="absolute -top-2 -left-2 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider shadow-sm border whitespace-nowrap"
                  style={{
                    backgroundColor: withAlpha(zone.baseColor, 0.18),
                    color: zone.baseColor,
                    borderColor: withAlpha(zone.baseColor, 0.35),
                  }}
                >
                  {zone.label === "Farm" ? "🌾" : zone.label === "Flock" ? "🐓" : zone.label === "Herd" ? "🐖" : "🐄"} {zone.label} {zone.current}/{zone.capacity}
                </span>
              </div>
            );
          })}

          {gravestones &&
            gravestones.map((grave) => {
              const topPos = toCellPercent(grave.y);
              const leftPos = toCellPercent(grave.x);
              return (
                <div
                  key={grave.id}
                  className="absolute transform -translate-x-1/2 -translate-y-1/2 z-4 text-xs select-none pointer-events-auto opacity-60"
                  style={{ top: topPos, left: leftPos }}
                  onMouseEnter={(e) => {
                    setHoverTooltip({
                      x: e.clientX,
                      y: e.clientY,
                      lines: [
                        `Gravestone: ${grave.name}`,
                        `Coord: (${grave.x}, ${grave.y})`,
                        `Age at death: ${formatAge(grave.age_at_death)}`,
                        `Death tick: ${grave.death_tick}`,
                      ],
                    });
                  }}
                  onMouseMove={(e) => setHoverTooltip((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : prev))}
                  onMouseLeave={() => setHoverTooltip(null)}
                  title={`${grave.name} (†${formatAge(grave.age_at_death)})`}
                >
                  🪦
                </div>
              );
            })}
        </div>
      </div>

      {hoverTooltip && (
        <div
          className="fixed z-120 min-w-52.5 max-w-85 rounded-lg border border-slate-200/80 bg-white/95 px-3 py-2 text-[11px] text-slate-700 shadow-xl backdrop-blur-sm pointer-events-none"
          style={{ left: hoverTooltip.x + 14, top: hoverTooltip.y + 14 }}
        >
          {hoverTooltip.lines.map((line, idx) => (
            <div key={`${line}-${idx}`} className={idx === 0 ? "font-semibold text-slate-900" : "mt-0.5"}>
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
