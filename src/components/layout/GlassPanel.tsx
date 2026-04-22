import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GlassPanelProps {
  children: ReactNode;
  className?: string;
  title?: string;
  noBorder?: boolean;
}

export function GlassPanel({ children, className, title, noBorder }: GlassPanelProps) {
  return (
    <div
      className={cn(
        "glass-panel rounded-2xl flex flex-col overflow-hidden relative",
        noBorder ? "border-transparent" : "",
        className
      )}
    >
      {/* Decorative inner glow */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent pointer-events-none" />
      
      {title && (
        <div className="px-5 py-3 border-b border-black/5 bg-white/30 backdrop-blur-md z-10 flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wider uppercase text-slate-800">{title}</h2>
          {/* Decorative dots */}
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
            <div className="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
            <div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div>
          </div>
        </div>
      )}
      <div className="flex-1 p-5 relative z-10 overflow-hidden flex flex-col">
        {children}
      </div>
    </div>
  );
}
