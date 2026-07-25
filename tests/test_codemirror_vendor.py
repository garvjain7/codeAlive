from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_editor_no_longer_uses_esm_sh_and_local_vendor_exists():
    editor_js = (ROOT / "static" / "editor.js").read_text(encoding="utf-8")
    highlights_js = (ROOT / "static" / "highlights.js").read_text(encoding="utf-8")
    image_handler_js = (ROOT / "static" / "image-handler.js").read_text(encoding="utf-8")
    adapter_js = (ROOT / "static" / "collab" / "adapter.js").read_text(encoding="utf-8")

    assert "esm.sh" not in editor_js
    assert "esm.sh" not in highlights_js
    assert "esm.sh" not in image_handler_js
    assert "esm.sh" not in adapter_js

    for rel_path in [
        "static/vendor/@codemirror/view/dist/index.js",
        "static/vendor/@codemirror/state/dist/index.js",
        "static/vendor/@codemirror/search/dist/index.js",
        "static/vendor/@codemirror/commands/dist/index.js",
        "static/vendor/@codemirror/language/dist/index.js",
        "static/vendor/@codemirror/language-data/dist/index.js",
        "static/vendor/@codemirror/theme-one-dark/dist/index.js",
    ]:
        assert (ROOT / rel_path).exists(), f"Missing vendored module: {rel_path}"

    assert (ROOT / "static" / "importmap.json").exists()
    assert "type=\"importmap\"" in (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def test_editor_uses_local_language_shims_for_special_cases():
    editor_js = (ROOT / "static" / "editor.js").read_text(encoding="utf-8")

    for specifier in [
        '@local/lang-dart',
        '@local/lang-kotlin',
        '@local/lang-shell',
        '@local/lang-swift',
        '@local/lang-ruby',
        '@local/lang-jsx',
        '@local/lang-typescript',
        '@local/lang-tsx',
    ]:
        assert specifier in editor_js, f"Missing local language shim import: {specifier}"
