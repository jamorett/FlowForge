import { useState } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

export function EquationView({ tex, label }: { tex: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const html = katex.renderToString(tex, { throwOnError: false, displayMode: true });

  const handleCopy = () => {
    navigator.clipboard.writeText(tex);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative glass-panel rounded-xl p-4 my-2 border border-cyan-500/20 bg-slate-900/60 transition-all hover:border-cyan-500/40">
      {label && (
        <div className="text-xs font-semibold text-cyan-400 tracking-wider uppercase mb-2">
          {label}
        </div>
      )}
      <div
        className="overflow-x-auto text-neutral-100 py-1"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <div className="flex justify-between items-center mt-3 pt-2 border-t border-white/5 text-xs text-neutral-400">
        <code className="text-[11px] text-neutral-400 font-mono truncate max-w-[80%]">
          {tex}
        </code>
        <button
          onClick={handleCopy}
          className="px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 text-neutral-300 border border-white/10 transition-colors"
        >
          {copied ? "Copied!" : "Copy LaTeX"}
        </button>
      </div>
    </div>
  );
}
