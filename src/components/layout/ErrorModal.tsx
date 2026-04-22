import { AlertCircle, X } from "lucide-react";

interface ErrorModalProps {
  isOpen: boolean;
  title?: string;
  message: string;
  errorCode?: string;
  suggestion?: string;
  onClose: () => void;
}

export function ErrorModal({
  isOpen,
  title = "Error",
  message,
  errorCode,
  suggestion,
  onClose,
}: ErrorModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-9999 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-gradient-to-br from-slate-50 to-slate-100 rounded-2xl shadow-2xl p-8 max-w-md w-full mx-4 border border-slate-200">
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="bg-rose-100 rounded-full p-2">
            <AlertCircle className="w-5 h-5 text-rose-600" />
          </div>
          <h2 className="text-lg font-bold text-slate-800">{title}</h2>
          <button
            onClick={onClose}
            className="ml-auto p-1 hover:bg-slate-200 rounded-lg transition-colors"
            title="Close"
          >
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        {/* Message */}
        <p className="text-sm text-slate-700 mb-4 leading-relaxed">{message}</p>

        {/* Error Code */}
        {errorCode && (
          <div className="bg-slate-900/5 rounded-lg p-3 mb-4 border border-slate-200">
            <div className="text-[10px] text-slate-500 font-mono mb-1">ERROR CODE</div>
            <div className="text-[12px] text-slate-700 font-mono">{errorCode}</div>
          </div>
        )}

        {/* Suggestion */}
        {suggestion && (
          <div className="bg-blue-50 rounded-lg p-3 mb-6 border border-blue-200">
            <div className="text-[10px] text-blue-700 font-semibold mb-1">💡 SUGGESTION</div>
            <div className="text-[12px] text-blue-800">{suggestion}</div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 bg-slate-200 text-slate-800 rounded-lg font-semibold text-sm hover:bg-slate-300 transition-colors"
          >
            Close
          </button>
          <button
            onClick={() => {
              window.location.href = "/";
            }}
            className="flex-1 px-4 py-2.5 bg-rose-500 text-white rounded-lg font-semibold text-sm hover:bg-rose-600 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    </div>
  );
}
