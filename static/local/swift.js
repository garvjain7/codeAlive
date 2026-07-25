import { StreamLanguage } from "@codemirror/language";
import { swift } from "@codemirror/legacy-modes/mode/swift";
export const swiftLanguage = StreamLanguage.define(swift);
export function swiftSupport() { return swiftLanguage; }
