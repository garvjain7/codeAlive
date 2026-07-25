#!/usr/bin/env bash
# scripts/update-codemirror.sh
#
# Re-fetches all vendored CodeMirror packages directly from the public npm
# registry tarball URLs. Requires only `curl` and `tar` - no npm, no node,
# no build tools. Run this from the repo root.
#
# Usage:
#   ./scripts/update-codemirror.sh
#
# To bump a version: edit the version number for that package below, then
# re-run. Always re-run the app's test suite / manually check the editor
# after bumping - these are real semver releases and can have breaking
# changes like any other dependency.

set -euo pipefail

VENDOR_DIR="static/vendor"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# name -> version -> entry file (relative to the extracted package dir)
# Keep this in sync with vendor-graph.json if you regenerate that from Node.
declare -A PKG_VERSION=(
  ["@codemirror/view"]="6.43.5"
  ["@codemirror/state"]="6.7.1"
  ["@codemirror/search"]="6.7.1"
  ["@codemirror/commands"]="6.10.4"
  ["@codemirror/language"]="6.12.4"
  ["@codemirror/theme-one-dark"]="6.1.3"
  ["@codemirror/autocomplete"]="6.20.3"
  ["@codemirror/lint"]="6.9.7"
  ["@codemirror/lang-cpp"]="6.0.3"
  ["@codemirror/lang-css"]="6.3.1"
  ["@codemirror/lang-go"]="6.0.1"
  ["@codemirror/lang-html"]="6.4.11"
  ["@codemirror/lang-java"]="6.0.2"
  ["@codemirror/lang-javascript"]="6.2.5"
  ["@codemirror/lang-json"]="6.0.2"
  ["@codemirror/lang-markdown"]="6.5.0"
  ["@codemirror/lang-php"]="6.0.2"
  ["@codemirror/lang-python"]="6.2.1"
  ["@codemirror/lang-rust"]="6.0.2"
  ["@codemirror/lang-sql"]="6.10.0"
  ["@codemirror/lang-vue"]="0.1.3"
  ["@codemirror/lang-xml"]="6.1.0"
  ["@codemirror/lang-yaml"]="6.1.3"
  ["@codemirror/legacy-modes"]="6.5.3"  # provides mode/clike.js (dart,kotlin), mode/shell.js, mode/swift.js, mode/ruby.js
  ["@lezer/common"]="1.5.2"
  ["@lezer/highlight"]="1.2.3"
  ["@lezer/lr"]="1.4.10"
  ["@lezer/cpp"]="1.1.6"
  ["@lezer/css"]="1.3.4"
  ["@lezer/go"]="1.0.1"
  ["@lezer/html"]="1.3.13"
  ["@lezer/java"]="1.1.3"
  ["@lezer/javascript"]="1.5.4"
  ["@lezer/json"]="1.0.3"
  ["@lezer/markdown"]="1.6.4"
  ["@lezer/php"]="1.0.5"
  ["@lezer/python"]="1.1.19"
  ["@lezer/rust"]="1.0.2"
  ["@lezer/xml"]="1.0.6"
  ["@lezer/yaml"]="1.0.4"
  ["@marijn/find-cluster-break"]="1.0.3"
  ["@replit/codemirror-lang-csharp"]="6.2.0"
  ["crelt"]="1.0.7"
  ["style-mod"]="4.1.3"
  ["w3c-keyname"]="2.2.8"
)

fetch_package() {
  local name="$1" version="$2"
  # npm scoped tarball URL pattern: registry.npmjs.org/@scope/name/-/name-version.tgz
  local basename tarball_url
  if [[ "$name" == @*/* ]]; then
    basename="${name#*/}"
  else
    basename="$name"
  fi
  tarball_url="https://registry.npmjs.org/${name}/-/${basename}-${version}.tgz"

  echo "Fetching $name@$version ..."
  local dest="$TMP_DIR/${name//\//_}"
  mkdir -p "$dest"
  curl -sL "$tarball_url" -o "$dest.tgz"
  tar -xzf "$dest.tgz" -C "$dest" --strip-components=1  # npm tarballs wrap contents in a "package/" dir

  local out="$VENDOR_DIR/$name"
  mkdir -p "$out"
  cp "$dest/package.json" "$out/package.json"

  if [[ "$name" == "@codemirror/legacy-modes" ]]; then
    mkdir -p "$out/mode"
    cp "$dest/mode/clike.js" "$out/mode/clike.js"
    cp "$dest/mode/shell.js" "$out/mode/shell.js"
    cp "$dest/mode/swift.js" "$out/mode/swift.js"
    cp "$dest/mode/ruby.js" "$out/mode/ruby.js"
    return
  fi

  # Read the ESM entry point from package.json (module field, or
  # exports.import, or fall back to main) without needing node - grep+sed.
  local entry
  entry=$(grep -o '"module"[[:space:]]*:[[:space:]]*"[^"]*"' "$dest/package.json" | sed -E 's/.*"module"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/' || true)
  if [[ -z "$entry" ]]; then
    entry=$(grep -o '"import"[[:space:]]*:[[:space:]]*"[^"]*"' "$dest/package.json" | head -1 | sed -E 's/.*"import"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/' || true)
  fi
  if [[ -z "$entry" ]]; then
    entry=$(grep -o '"main"[[:space:]]*:[[:space:]]*"[^"]*"' "$dest/package.json" | sed -E 's/.*"main"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')
  fi
  entry="${entry#./}"

  mkdir -p "$out/$(dirname "$entry")"
  cp "$dest/$entry" "$out/$entry"
  echo "  -> $out/$entry"
}

echo "== Vendoring ${#PKG_VERSION[@]} packages into $VENDOR_DIR =="
for name in "${!PKG_VERSION[@]}"; do
  fetch_package "$name" "${PKG_VERSION[$name]}"
done

echo
echo "== Validating: checking for any leftover esm.sh/jsdelivr/unpkg references =="
if grep -rlE "esm\.sh|jsdelivr\.net|unpkg\.com" "$VENDOR_DIR" 2>/dev/null; then
  echo "WARNING: found references above - inspect them."
else
  echo "Clean - no external CDN references found in vendored files."
fi

echo
echo "Done. Remember to also regenerate static/importmap.json if any package's"
echo "entry file path changed (rare, but check the package.json diff)."
