import { create } from "zustand";
import { Agent, SimulationLog, ResourceNode, SettlementNode, GravestoneNode, HouseNode, GlobalQuest } from "../types/agent";

interface SyncPayload {
  agents: Record<string, Agent>;
  tick: number;
  calendar_date: string;
  logs: SimulationLog[];
  resources: ResourceNode[];
  settlements: SettlementNode[];
  gravestones: GravestoneNode[];
  houses: HouseNode[];
  global_quest: GlobalQuest | null;
  terrain: string[][];
  map_size: number;
  era: string;
  active_model: string;
  target_tick: number;
  map_preset: string;
  violence_level: "low" | "normal" | "high" | "extreme";
  weather: {
    condition: string;
    cloud_cover: number;
    rain_intensity: number;
    next_change_tick?: number;
  };
  hydrology: {
    avg_groundwater: number;
    low_groundwater_tiles: number;
  };
  metrics: SimulationMetrics;
}

interface SimulationMetrics {
  population: number;
  gini_coin: number;
  social_density: number;
  social_links: number;
  alliance_edges: number;
  territories: number;
}

interface SimulationState {
  agents: Record<string, Agent>;
  logs: SimulationLog[];
  resources: ResourceNode[];
  settlements: SettlementNode[];
  gravestones: GravestoneNode[];
  houses: HouseNode[];
  globalQuest: GlobalQuest | null;
  terrain: string[][];
  mapSize: number;
  tickCount: number;
  calendarDate: string;
  era: string;
  activeModel: string;
  targetTick: number;
  violenceLevel: "low" | "normal" | "high" | "extreme";
  metrics: SimulationMetrics;
  weather: {
    condition: string;
    cloud_cover: number;
    rain_intensity: number;
    next_change_tick?: number;
  };
  hydrology: {
    avg_groundwater: number;
    low_groundwater_tiles: number;
  };
  selectedAgentId: string | null;
  mapViewMode: "top-down" | "isometric";
  isRunning: boolean;
  setSelectedAgent: (id: string | null) => void;
  setMapViewMode: (mode: "top-down" | "isometric") => void;
  syncState: (payload: Partial<SyncPayload>) => void;
  setRunningStatus: (status: boolean) => void;
  toggleSimulation: () => void;
  setModel: (model: string) => void;
  setTargetTick: (tick: number) => void;
}

export const useSimulationStore = create<SimulationState>((set, get) => ({
  agents: {},
  logs: [],
  resources: [],
  settlements: [],
  gravestones: [],
  houses: [],
  globalQuest: null,
  terrain: [],
  mapSize: 80,
  tickCount: 0,
  calendarDate: "Y000 M01 D01",
  era: "prehistoric",
  activeModel: "qwen2.5:1.5b",
  targetTick: 0,
  violenceLevel: "normal",
  metrics: {
    population: 0,
    gini_coin: 0,
    social_density: 0,
    social_links: 0,
    alliance_edges: 0,
    territories: 0,
  },
  weather: {
    condition: "clear",
    cloud_cover: 0.25,
    rain_intensity: 0,
  },
  hydrology: {
    avg_groundwater: 0,
    low_groundwater_tiles: 0,
  },
  selectedAgentId: null,
  mapViewMode: "top-down",
  isRunning: false,
  setSelectedAgent: (id) => set({ selectedAgentId: id }),
  setMapViewMode: (mode) => set({ mapViewMode: mode }),
  toggleSimulation: () => {
    const isRunning = !get().isRunning;
    set({ isRunning });
    fetch(`http://localhost:8000/${isRunning ? "start" : "stop"}`, { method: "POST" });
  },
  setModel: (model) => {
    set({ activeModel: model });
    fetch(`http://localhost:8000/model/${model}`, { method: "POST" });
  },
  setTargetTick: (tick) => {
    set({ targetTick: tick });
    fetch(`http://localhost:8000/target/${tick}`, { method: "POST" });
  },
  syncState: (payload) => {
    set((state) => {
      const incomingLogs = payload.logs ?? [];
      const tickWentBack = payload.tick !== undefined && payload.tick < state.tickCount;
      const shouldReplaceLogs = (payload.tick !== undefined && payload.tick <= 1 && payload.logs !== undefined) || tickWentBack;
      const hasGlobalQuest = Object.prototype.hasOwnProperty.call(payload, "global_quest");
      let nextLogs = state.logs;

      if (shouldReplaceLogs) {
        nextLogs = incomingLogs.slice(-150);
      } else if (payload.logs !== undefined) {
        const seenIds = new Set(state.logs.map((log) => log.id));
        const mergedLogs = [...state.logs];
        for (const log of incomingLogs) {
          if (!seenIds.has(log.id)) {
            mergedLogs.push(log);
            seenIds.add(log.id);
          }
        }
        nextLogs = mergedLogs.slice(-150);
      }

      return {
        agents: payload.agents ?? state.agents,
        tickCount: payload.tick ?? state.tickCount,
        calendarDate: payload.calendar_date ?? state.calendarDate,
        logs: nextLogs,
        resources: payload.resources ?? state.resources,
        settlements: payload.settlements ?? state.settlements,
        gravestones: payload.gravestones ?? state.gravestones,
        houses: payload.houses ?? state.houses,
        globalQuest: hasGlobalQuest ? (payload.global_quest ?? null) : state.globalQuest,
        terrain: payload.terrain ?? state.terrain,
        mapSize: payload.map_size ?? state.mapSize,
        era: payload.era ?? state.era,
        activeModel: payload.active_model ?? state.activeModel,
        targetTick: payload.target_tick ?? state.targetTick,
        violenceLevel: payload.violence_level ?? state.violenceLevel,
        weather: payload.weather ?? state.weather,
        hydrology: payload.hydrology ?? state.hydrology,
        metrics: payload.metrics ?? state.metrics,
      };
    });
  },
  setRunningStatus: (status) => set({ isRunning: status }),
}));
