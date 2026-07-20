import { StreamLanguage } from "@codemirror/language";
import { shell } from "@codemirror/legacy-modes/mode/shell";
export const shellLanguage = StreamLanguage.define(shell);
export function shellSupport() { return shellLanguage; }
