import katex from "katex";
import "katex/dist/katex.min.css";

// KaTeX rendering only; the formula string comes from the backend. No physics.
export function EquationView({ tex }: { tex: string }) {
  const html = katex.renderToString(tex, { throwOnError: false });
  return <div className="overflow-x-auto py-2" dangerouslySetInnerHTML={{ __html: html }} />;
}
