/* eslint-disable */
import { cn } from "@/lib/utils";
import { Agent } from "@/types/agent";
import { motion } from "framer-motion";
import type { AgentColorTheme } from "@/lib/utils";

interface AgentNodeProps {
  agent: Agent;
  colorTheme: AgentColorTheme;
  isSelected?: boolean;
  onClick?: () => void;
  scale?: number;
  mapSize?: number;
}

export function AgentNode({ agent, colorTheme, isSelected, onClick, scale = 1, mapSize = 50 }: AgentNodeProps) {
  const topPos = `${((agent.y + 0.5) / mapSize) * 100}%`;
  const leftPos = `${((agent.x + 0.5) / mapSize) * 100}%`;
  const topSkill = Object.entries(agent.skills || {}).sort((a, b) => Number(b[1]) - Number(a[1]))[0];

  // Life phase icon
  const phaseIcon: Record<string, string> = {
    baby: "👶",
    child: "🧒",
    teen: "🧑‍🎓",
    young_adult: "💪",
    adult: "🧑",
    elder: "🧓",
  };

  const genderIcon = agent.gender === "male" ? "♂" : "♀";
  const tooltip = [
    `${agent.name} (${genderIcon})`,
    `Class: ${agent.social_class}`,
    `Job: ${agent.job}`,
    `Action: ${agent.actionState}`,
    `Vitals: E ${Math.round(agent.vitals.energy)} | F ${Math.round(agent.vitals.hunger)} | H ${Math.round(agent.vitals.hydration)} | S ${Math.round(agent.vitals.social)}`,
    topSkill ? `Top skill: ${topSkill[0]} ${Number(topSkill[1]).toFixed(1)}` : "Top skill: -",
  ].join("\n");
  const lifeIcon = phaseIcon[agent.life_phase] || "🧑";

  // Size based on life phase
  const sizeClass = agent.life_phase === "baby" ? "w-2.5 h-2.5" 
    : agent.life_phase === "child" ? "w-3 h-3"
    : "w-4 h-4";

  return (
    <div
      className="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer z-20 transition-all duration-700 ease-in-out"
      style={{ top: topPos, left: leftPos }}
      onClick={onClick}
    >
      <motion.div
        whileHover={{ scale: 1.2 }}
        whileTap={{ scale: 0.9 }}
        className={cn(
          "rounded-full shadow-lg border-2 flex items-center justify-center text-[8px] font-bold relative",
          sizeClass
        )}
        style={{
          backgroundColor: colorTheme.base,
          borderColor: isSelected ? "#ffffff" : colorTheme.border,
          color: isSelected ? colorTheme.text : "transparent",
          boxShadow: `0 0 0 1px ${colorTheme.border}`,
        }}
      >
        {isSelected && agent.name.charAt(0)}
        
        {/* Thinking Indicator */}
        {agent.actionState === "thinking" && (
           <span className="absolute -top-3 -right-3 text-[14px]">💭</span>
        )}

        {/* Pregnancy Indicator */}
        {agent.is_pregnant && (
           <span className="absolute -top-3 -left-3 text-[12px]">🤰</span>
        )}

        {/* Boat Indicator */}
        {agent.inventory.has_boat && (
           <span className="absolute -bottom-3 -right-2 text-[10px]">⛵</span>
        )}
        
        {/* Render Ping Effect if active */}
        {(isSelected || agent.actionState !== "idle") && (
          <span 
            className="absolute -inset-1 rounded-full animate-ping pointer-events-none" 
            style={{ backgroundColor: agent.actionState === "thinking" ? "rgba(234,179,8,0.8)" : colorTheme.aura, opacity: 0.72 }}
          />
        )}
      </motion.div>
      
      {/* Label */}
      {isSelected && (
        <div className="absolute top-5 left-1/2 transform -translate-x-1/2 bg-white/90 backdrop-blur-sm text-slate-900 border border-slate-200 text-xs px-2 py-0.5 rounded shadow-sm whitespace-nowrap z-30 font-medium">
          <span className={agent.gender === "male" ? "text-blue-500" : "text-pink-500"}>{genderIcon}</span>{" "}
          {agent.name} {lifeIcon}
        </div>
      )}
    </div>
  );
}
