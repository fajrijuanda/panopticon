"use client";

import { useEffect, useState } from "react";
import { Download, FileImage, FileSpreadsheet, Save, X } from "lucide-react";

interface SaveModalProps {
  isOpen: boolean;
  defaultName: string;
  isSaving?: boolean;
  onClose: () => void;
  onConfirm: (saveName: string) => void;
}

export function SaveModal({ isOpen, defaultName, isSaving = false, onClose, onConfirm }: SaveModalProps) {
  const [saveName, setSaveName] = useState(defaultName);

  useEffect(() => {
    if (isOpen) {
      setSaveName(defaultName);
    }
  }, [isOpen, defaultName]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-950/70 backdrop-blur-md px-4">
      <div className="w-full max-w-xl rounded-3xl border border-white/10 bg-linear-to-br from-slate-900 via-slate-800 to-slate-900 text-white shadow-[0_30px_100px_rgba(15,23,42,0.55)] overflow-hidden">
        <div className="relative px-6 py-5 border-b border-white/10">
          <div className="absolute inset-0 bg-linear-to-r from-cyan-500/10 via-transparent to-emerald-500/10" />
          <div className="relative flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.28em] text-cyan-200">
                <Download className="w-3.5 h-3.5" /> Save Snapshot
              </div>
              <h2 className="mt-3 text-2xl font-black tracking-tight">Simpan keadaan dunia</h2>
              <p className="mt-2 max-w-lg text-sm leading-6 text-slate-300">
                Snapshot akan menangkap tampilan layar saat ini, lalu mengekspor file JSON dan laporan Excel.
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="Close save modal"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="px-6 py-5 space-y-5 bg-slate-950/35">
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100">
            <div className="flex items-center gap-2 font-semibold">
              <FileImage className="w-4 h-4" /> PNG + JSON + Excel
            </div>
            <p className="mt-1 text-xs leading-5 text-cyan-100/80">
              Simpan ini cocok untuk arsip sesi, laporan perkembangan, atau melanjutkan eksperimen nanti.
            </p>
          </div>

          <div className="space-y-2">
            <label htmlFor="save-name" className="text-xs font-bold uppercase tracking-[0.2em] text-slate-300">
              Nama save
            </label>
            <input
              id="save-name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 font-mono text-sm text-white outline-none transition-colors placeholder:text-slate-500 focus:border-cyan-400 focus:bg-white/10"
              placeholder="paper_2026-04-17-12-00-00"
              autoFocus
            />
            <p className="text-[11px] text-slate-400">
              Nama akan dipakai untuk file JSON, screenshot PNG, dan laporan Excel.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 sm:grid-cols-3">
            <div className="flex items-center gap-2 text-sm text-slate-200">
              <Save className="w-4 h-4 text-cyan-300" /> Snapshot world
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-200">
              <FileImage className="w-4 h-4 text-emerald-300" /> PNG export
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-200">
              <FileSpreadsheet className="w-4 h-4 text-amber-300" /> Excel report
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-white/10 px-6 py-4 sm:flex-row sm:justify-end">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-200 transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(saveName.trim())}
            disabled={isSaving || !saveName.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-linear-to-r from-cyan-500 to-emerald-500 px-5 py-2.5 text-sm font-black uppercase tracking-widest text-white shadow-lg shadow-cyan-500/20 transition-transform hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            {isSaving ? "Saving..." : "Save Now"}
          </button>
        </div>
      </div>
    </div>
  );
}
