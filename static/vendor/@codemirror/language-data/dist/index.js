import { LanguageDescription } from "@codemirror/language";
import { cpp } from "@codemirror/lang-cpp";
import { css } from "@codemirror/lang-css";
import { go } from "@codemirror/lang-go";
import { html } from "@codemirror/lang-html";
import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { php } from "@codemirror/lang-php";
import { python } from "@codemirror/lang-python";
import { rust } from "@codemirror/lang-rust";
import { sql } from "@codemirror/lang-sql";
import { vue } from "@codemirror/lang-vue";
import { xml } from "@codemirror/lang-xml";
import { yaml } from "@codemirror/lang-yaml";
import { csharp } from "@replit/codemirror-lang-csharp";
import { dartSupport } from "@local/lang-dart";
import { kotlinSupport } from "@local/lang-kotlin";
import { shellSupport } from "@local/lang-shell";
import { swiftSupport } from "@local/lang-swift";
import { rubySupport } from "@local/lang-ruby";
import { jsx } from "@local/lang-jsx";
import { typescript } from "@local/lang-typescript";
import { tsx } from "@local/lang-tsx";

function createLanguageDescription(spec) {
  return LanguageDescription.of({
    name: spec.name,
    alias: spec.alias || [],
    extensions: spec.extensions || [],
    filename: spec.filename,
    support: spec.support(),
    load: async () => spec.support(),
  });
}

export const languages = [
  createLanguageDescription({ name: "c", alias: ["c"], extensions: ["c"], support: () => cpp() }),
  createLanguageDescription({ name: "cpp", alias: ["cpp", "cc", "cxx"], extensions: ["cpp", "cc", "cxx"], support: () => cpp() }),
  createLanguageDescription({ name: "csharp", alias: ["csharp", "cs"], extensions: ["cs"], support: () => csharp() }),
  createLanguageDescription({ name: "css", alias: ["css"], extensions: ["css"], support: () => css() }),
  createLanguageDescription({ name: "dart", alias: ["dart"], extensions: ["dart"], support: () => dartSupport() }),
  createLanguageDescription({ name: "go", alias: ["go"], extensions: ["go"], support: () => go() }),
  createLanguageDescription({ name: "html", alias: ["html", "htm"], extensions: ["html", "htm"], support: () => html() }),
  createLanguageDescription({ name: "java", alias: ["java"], extensions: ["java"], support: () => java() }),
  createLanguageDescription({ name: "javascript", alias: ["javascript", "js", "mjs", "cjs"], extensions: ["js", "mjs", "cjs"], support: () => javascript() }),
  createLanguageDescription({ name: "json", alias: ["json"], extensions: ["json"], support: () => json() }),
  createLanguageDescription({ name: "jsx", alias: ["jsx"], extensions: ["jsx"], support: () => jsx() }),
  createLanguageDescription({ name: "kotlin", alias: ["kotlin", "kt"], extensions: ["kt"], support: () => kotlinSupport() }),
  createLanguageDescription({ name: "markdown", alias: ["markdown", "md"], extensions: ["md", "markdown"], support: () => markdown() }),
  createLanguageDescription({ name: "php", alias: ["php"], extensions: ["php"], support: () => php() }),
  createLanguageDescription({ name: "python", alias: ["python", "py"], extensions: ["py"], support: () => python() }),
  createLanguageDescription({ name: "ruby", alias: ["ruby", "rb"], extensions: ["rb"], support: () => rubySupport() }),
  createLanguageDescription({ name: "rust", alias: ["rust", "rs"], extensions: ["rs"], support: () => rust() }),
  createLanguageDescription({ name: "shell", alias: ["shell", "sh", "bash"], extensions: ["sh", "bash"], support: () => shellSupport() }),
  createLanguageDescription({ name: "sql", alias: ["sql"], extensions: ["sql"], support: () => sql() }),
  createLanguageDescription({ name: "swift", alias: ["swift"], extensions: ["swift"], support: () => swiftSupport() }),
  createLanguageDescription({ name: "typescript", alias: ["typescript", "ts"], extensions: ["ts"], support: () => typescript() }),
  createLanguageDescription({ name: "tsx", alias: ["tsx"], extensions: ["tsx"], support: () => tsx() }),
  createLanguageDescription({ name: "vue", alias: ["vue"], extensions: ["vue"], support: () => vue() }),
  createLanguageDescription({ name: "xml", alias: ["xml"], extensions: ["xml"], support: () => xml() }),
  createLanguageDescription({ name: "yaml", alias: ["yaml", "yml"], extensions: ["yaml", "yml"], support: () => yaml() }),
];
