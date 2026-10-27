/// <reference types="vite/client" />
declare module "plotly.js-dist-min" {
  const Plotly: {
    newPlot: (el: HTMLElement, data: unknown[], layout?: Record<string, unknown>) => Promise<void>;
    react: (el: HTMLElement, data: unknown[], layout?: Record<string, unknown>) => Promise<void>;
    purge: (el: HTMLElement) => void;
  };
  export default Plotly;
}
declare module "katex" {
  const katex: { renderToString: (tex: string, opts?: Record<string, unknown>) => string };
  export default katex;
}
