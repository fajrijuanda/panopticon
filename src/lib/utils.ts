import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

function hashString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function hslToHex(h: number, s: number, l: number): string {
  const sat = Math.max(0, Math.min(1, s));
  const lig = Math.max(0, Math.min(1, l));
  const c = (1 - Math.abs(2 * lig - 1)) * sat;
  const hh = ((h % 360) + 360) % 360 / 60;
  const x = c * (1 - Math.abs((hh % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;

  if (hh >= 0 && hh < 1) {
    r = c;
    g = x;
  } else if (hh >= 1 && hh < 2) {
    r = x;
    g = c;
  } else if (hh >= 2 && hh < 3) {
    g = c;
    b = x;
  } else if (hh >= 3 && hh < 4) {
    g = x;
    b = c;
  } else if (hh >= 4 && hh < 5) {
    r = x;
    b = c;
  } else {
    r = c;
    b = x;
  }

  const m = lig - c / 2;
  const toHex = (v: number) => {
    const value = Math.round((v + m) * 255);
    return value.toString(16).padStart(2, "0");
  };

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

export function withAlpha(hex: string, alpha: number): string {
  const raw = hex.replace("#", "");
  if (raw.length !== 6) {
    return `rgba(255,255,255,${Math.max(0, Math.min(1, alpha))})`;
  }
  const r = parseInt(raw.slice(0, 2), 16);
  const g = parseInt(raw.slice(2, 4), 16);
  const b = parseInt(raw.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, alpha))})`;
}

export function getReadableTextColor(hex: string): string {
  const raw = hex.replace("#", "");
  if (raw.length !== 6) return "#ffffff";
  const r = parseInt(raw.slice(0, 2), 16);
  const g = parseInt(raw.slice(2, 4), 16);
  const b = parseInt(raw.slice(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.62 ? "#0f172a" : "#ffffff";
}

export interface AgentColorTheme {
  base: string;
  border: string;
  aura: string;
  text: string;
  territoryFill: string;
  territoryBorder: string;
}

function baseColorFromId(id: string): string {
  const hash = hashString(id);
  const numericSuffix = Number.parseInt(id.replace(/\D+/g, ""), 10);
  const hasNumericSuffix = Number.isFinite(numericSuffix) && numericSuffix > 0;

  const hueSeed = hasNumericSuffix
    ? (numericSuffix * 137.508) % 360
    : (hash % 360);
  const sat = 0.62 + ((hash >> 8) % 18) / 100;
  const lig = 0.48 + ((hash >> 16) % 14) / 100;
  return hslToHex(hueSeed, sat, lig);
}

export function buildUniqueAgentColorMap(agentIds: string[]): Record<string, AgentColorTheme> {
  const used = new Set<string>();
  const result: Record<string, AgentColorTheme> = {};

  for (const id of [...agentIds].sort()) {
    let base = baseColorFromId(id);
    let nudge = 0;
    while (used.has(base) && nudge < 36) {
      const h = (hashString(`${id}-${nudge}`) + nudge * 37) % 360;
      base = hslToHex(h, 0.68, 0.52);
      nudge += 1;
    }
    used.add(base);

    const border = withAlpha(base, 0.95);
    const aura = withAlpha(base, 0.48);
    const text = getReadableTextColor(base);
    result[id] = {
      base,
      border,
      aura,
      text,
      territoryFill: withAlpha(base, 0.12),
      territoryBorder: withAlpha(base, 0.48),
    };
  }

  return result;
}
