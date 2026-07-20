import { javascript } from "@codemirror/lang-javascript";
export function jsx(config = {}) { return javascript({ ...config, jsx: true }); }
export * from "@codemirror/lang-javascript";
