const MAX_TEXT_IMPORT_BYTES = 1024 * 1024;

const ALLOWED_EXTENSIONS = new Set([
  "txt",
  "md",
  "markdown",
  "json",
  "csv",
  "py",
  "js",
  "jsx",
  "ts",
  "tsx",
  "css",
  "html",
  "xml",
  "yaml",
  "yml",
  "toml",
  "sql",
  "c",
  "cc",
  "cpp",
  "cs",
  "go",
  "java",
  "php",
  "rb",
  "rs",
  "swift",
  "kt",
  "scala",
  "sh",
  "bash",
  "ps1",
  "dockerfile",
  "lua",
  "r",
  "dart",
  "perl",
  "pl",
  "vue",
  "svelte",
]);

const EXTENSION_TO_LANGUAGE = Object.freeze({
  txt: "text",
  md: "markdown",
  markdown: "markdown",
  json: "json",
  csv: "text",
  py: "python",
  js: "javascript",
  jsx: "jsx",
  ts: "typescript",
  tsx: "tsx",
  css: "css",
  html: "html",
  xml: "xml",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  sql: "sql",
  c: "c",
  cc: "cpp",
  cpp: "cpp",
  cs: "csharp",
  go: "go",
  java: "java",
  php: "php",
  rb: "ruby",
  rs: "rust",
  swift: "swift",
  kt: "kotlin",
  scala: "scala",
  sh: "shell",
  bash: "shell",
  ps1: "powershell",
  lua: "lua",
  r: "r",
  dart: "dart",
  perl: "perl",
  pl: "perl",
  vue: "vue",
  svelte: "svelte",
});

function normalizeExtension(fileName) {
  if (!fileName) return "";
  const parts = fileName.split(".");
  if (parts.length < 2) return "";
  return parts[parts.length - 1].toLowerCase();
}

export function getAllowedTextImportExtensions() {
  return Array.from(ALLOWED_EXTENSIONS).sort();
}

export function validateImportedTextFile(file, { maxBytes = MAX_TEXT_IMPORT_BYTES } = {}) {
  if (!file || typeof file !== "object") {
    return { ok: false, error: "Please choose a file first." };
  }

  if (!file.name) {
    return { ok: false, error: "The selected file does not have a valid name." };
  }

  const ext = normalizeExtension(file.name);
  if (!ext || !ALLOWED_EXTENSIONS.has(ext)) {
    return {
      ok: false,
      error: `Unsupported file type. Allowed extensions include: ${getAllowedTextImportExtensions().join(", ")}.`,
    };
  }

  if (typeof file.size === "number" && file.size > maxBytes) {
    return {
      ok: false,
      error: `File is too large. Maximum allowed size is ${Math.round(maxBytes / 1024 / 1024)}MB.`,
    };
  }

  return { ok: true, extension: ext };
}

export function inferLanguageFromFileName(fileName) {
  const ext = normalizeExtension(fileName);
  return EXTENSION_TO_LANGUAGE[ext] || "text";
}

export function readTextFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Unable to read the selected file."));
    reader.readAsText(file, "utf-8");
  });
}

export async function importTextFile(file) {
  const validation = validateImportedTextFile(file);
  if (!validation.ok) {
    throw new Error(validation.error);
  }

  const text = await readTextFile(file);
  if (typeof text !== "string") {
    throw new Error("The selected file could not be read as text.");
  }

  if (text.includes("\u0000")) {
    throw new Error("This file appears to contain binary data and cannot be imported as text.");
  }

  if (text.includes("\uFFFD")) {
    throw new Error("The selected file could not be read as valid UTF-8 text.");
  }

  return {
    text,
    extension: validation.extension,
    language: inferLanguageFromFileName(file.name),
  };
}

export function initEditorFileImport({ button, onImport, onError }) {
  if (!button || typeof onImport !== "function") return;

  const input = document.createElement("input");
  input.type = "file";
  input.accept = getAllowedTextImportExtensions()
    .map((ext) => `.${ext}`)
    .join(",");
  input.style.display = "none";

  document.body.appendChild(input);

  button.addEventListener("click", () => input.click());

  input.addEventListener("change", async () => {
    const [file] = input.files || [];
    if (!file) return;

    try {
      const result = await importTextFile(file);
      await onImport(result);
      input.value = "";
    } catch (error) {
      if (typeof onError === "function") {
        onError(error.message || "Unable to import the selected file.");
      }
      input.value = "";
    }
  });
}
