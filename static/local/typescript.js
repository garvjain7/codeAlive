import { javascript } from "@codemirror/lang-javascript";
export function typescript(config = {}) { return javascript({ ...config, typescript: true }); }
export * from "@codemirror/lang-javascript";
