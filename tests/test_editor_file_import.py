import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run_node_assertion(script: str) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def test_validate_imported_text_file_rejects_unsupported_extension():
    output = run_node_assertion(
        """
        import { validateImportedTextFile } from './static/editor-file-import.js';
        const result = validateImportedTextFile({ name: 'photo.png', size: 100 });
        if (result.ok !== false || !result.error.includes('Unsupported file type')) {
          throw new Error(JSON.stringify(result));
        }
        console.log('ok');
        """
    )
    assert output == "ok"


def test_validate_imported_text_file_accepts_supported_extension():
    output = run_node_assertion(
        """
        import { validateImportedTextFile } from './static/editor-file-import.js';
        const result = validateImportedTextFile({ name: 'script.py', size: 200 });
        if (result.ok !== true || result.extension !== 'py') {
          throw new Error(JSON.stringify(result));
        }
        console.log('ok');
        """
    )
    assert output == "ok"


def test_infer_language_from_filename():
    output = run_node_assertion(
        """
        import { inferLanguageFromFileName } from './static/editor-file-import.js';
        const python = inferLanguageFromFileName('app.py');
        const markdown = inferLanguageFromFileName('notes.md');
        if (python !== 'python' || markdown !== 'markdown') {
          throw new Error(JSON.stringify({ python, markdown }));
        }
        console.log('ok');
        """
    )
    assert output == "ok"
