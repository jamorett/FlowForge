import { useQuery } from "@tanstack/react-query";
import katex from "katex";
import "katex/dist/katex.min.css";
import { fetchLatex } from "../api/client";

/** A DSL expression rendered as real math (SymPy LaTeX from the API); raw text if it does not parse. */
export function Formula({ expr, block = false, className = "" }: { expr: string; block?: boolean; className?: string }) {
  const q = useQuery({ queryKey: ["latex", expr], queryFn: () => fetchLatex(expr), staleTime: Infinity, enabled: !!expr });
  const tex = q.data?.latex;
  if (!tex) {
    return <code className={`font-mono text-[11px] text-neutral-300 break-all ${className}`} title={q.data?.error}>{expr}</code>;
  }
  const html = katex.renderToString(`a^{\\Delta}_{ij} = ${tex}`, { throwOnError: false, displayMode: block });
  return <span className={`text-neutral-100 ${className}`} title={expr} dangerouslySetInnerHTML={{ __html: html }} />;
}
