import { StreamLanguage } from "@codemirror/language";
import { ruby } from "@codemirror/legacy-modes/mode/ruby";
export const rubyLanguage = StreamLanguage.define(ruby);
export function rubySupport() { return rubyLanguage; }
