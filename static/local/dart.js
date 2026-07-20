import { StreamLanguage } from "@codemirror/language";
import { dart } from "@codemirror/legacy-modes/mode/clike";
export const dartLanguage = StreamLanguage.define(dart);
export function dartSupport() { return dartLanguage; }
