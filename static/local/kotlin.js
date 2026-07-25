import { StreamLanguage } from "@codemirror/language";
import { kotlin } from "@codemirror/legacy-modes/mode/clike";
export const kotlinLanguage = StreamLanguage.define(kotlin);
export function kotlinSupport() { return kotlinLanguage; }
