import { javascript } from "@codemirror/lang-javascript";
export function tsx(config = {}) { return javascript({ ...config, jsx: true, typescript: true }); }
export * from "@codemirror/lang-javascript";
