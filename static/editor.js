// ── EDITOR BEHAVIOR (CodeMirror 6) ───────────────────────────────────────────
import {
  EditorView,
  keymap,
  highlightActiveLine,
  lineNumbers,
  drawSelection,
  highlightSpecialChars,
  dropCursor,
  rectangularSelection,
  crosshairCursor,
} from "https://esm.sh/@codemirror/view";
import { highlightSelectionMatches, search, openSearchPanel } from "https://esm.sh/@codemirror/search";
import {
  EditorState,
  Compartment,
} from "https://esm.sh/@codemirror/state";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from "https://esm.sh/@codemirror/commands";
import {
  indentOnInput,
  syntaxHighlighting,
  defaultHighlightStyle,
  bracketMatching,
  foldGutter,
  foldKeymap,
  LanguageDescription,
} from "https://esm.sh/@codemirror/language";
import { languages } from "https://esm.sh/@codemirror/language-data";
import { oneDark } from "https://esm.sh/@codemirror/theme-one-dark";

import { editorContainer, setView, lineInfo, charInfo, editorHintEmpty, editorHintHighlight } from "./dom.js";
import { handleEditorUpdate, handleImmediateDetection } from "./detection.js";
import { highlightsField } from "./highlights.js";
import { imagePlugin } from "./image-handler.js";

// ── Language Management ──────────────────────────────────────────────────────
const languageConf = new Compartment();

async function getLanguageExtension(langName) {
  if (!langName || langName === "text") return [];
  const desc = LanguageDescription.matchLanguageName(languages, langName);
  if (desc) {
    const lang = await desc.load();
    return lang;
  }
  return [];
}

// ── Editor Initialization ────────────────────────────────────────────────────
let _getLanguage = () => "text";

export function initEditor(getLanguage) {
  _getLanguage = getLanguage;
}

export async function createEditor(initialCode = "", initialLang = "text", isReadOnly = false) {
  console.log("Creating editor for lang:", initialLang);
  const langExtension = await getLanguageExtension(initialLang);
  console.log("Language extension loaded");

  const state = EditorState.create({
    doc: initialCode,
    extensions: [
      lineNumbers(),
      highlightActiveLine(),
      highlightSpecialChars(),
      history(),
      foldGutter(),
      drawSelection(),
      dropCursor(),
      EditorState.allowMultipleSelections.of(true),
      indentOnInput(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      bracketMatching(),
      rectangularSelection(),
      crosshairCursor(),
      search({top: true}),
      highlightSelectionMatches(),
      languageConf.of(langExtension),
      readOnlyConf.of(EditorState.readOnly.of(isReadOnly)),
      highlightsField,
      imagePlugin,
      oneDark,
      keymap.of([
        ...defaultKeymap,
        ...historyKeymap,
        ...foldKeymap,
        indentWithTab,
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          const code = update.state.doc.toString();
          updateStats(update.state.doc);
          
          // Trigger detection
          if (update.transactions.some(tr => tr.isUserEvent("input.paste"))) {
            handleImmediateDetection(code);
          } else {
            handleEditorUpdate(code);
          }

          // Toggle hints
          if (code.length > 0) {
            editorHintEmpty.classList.add("hidden");
            editorHintHighlight.classList.remove("hidden");
          } else {
            editorHintEmpty.classList.remove("hidden");
            editorHintHighlight.classList.add("hidden");
          }

          // Show edit warning if editing a shared snippet (ONLY IF NOT READ-ONLY)
          const isReadOnly = update.state.readOnly;
          if (!isReadOnly && window.location.pathname !== "/editor") {
            const isUserChange = update.transactions.some(tr => 
              tr.isUserEvent("input") || 
              tr.isUserEvent("delete") || 
              tr.isUserEvent("undo") || 
              tr.isUserEvent("redo") || 
              tr.isUserEvent("paste") || 
              tr.isUserEvent("drop")
            );
            if (isUserChange) {
              import("./ui.js").then(({ showEditWarning, setHasEditingStarted }) => {
                if (setHasEditingStarted(true)) {
                  showEditWarning();
                }
              });
            }
          }
        }
      }),
    ],
  });

  const view = new EditorView({
    state,
    parent: editorContainer,
  });

  setView(view);
  updateStats(state.doc);
  return view;
}

function updateStats(doc) {
  const count = doc.lines;
  const chars = doc.length;
  lineInfo.textContent = `${count} line${count !== 1 ? "s" : ""}`;
  charInfo.textContent = `${chars} chars`;
}

const readOnlyConf = new Compartment();

export async function setLanguage(langName) {
  const { view } = await import("./dom.js");
  if (!view) return;

  const extension = await getLanguageExtension(langName);
  view.dispatch({
    effects: languageConf.reconfigure(extension),
  });
}

export async function setReadOnly(isReadOnly) {
  const { view } = await import("./dom.js");
  if (!view) return;
  
  view.dispatch({
    effects: readOnlyConf.reconfigure(EditorState.readOnly.of(isReadOnly))
  });
}

// ── Legacy Compatibility ──────────────────
export function mirrorToHighlight(code, language) {
  setLanguage(language);
}
export function updateLineNumbers() {}
export function syncHighlightScroll() {}

export async function triggerSearch() {
  const { view } = await import("./dom.js");
  if (!view) return;
  openSearchPanel(view);
  view.focus();
}
