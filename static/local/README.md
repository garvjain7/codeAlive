# local/ — hand-written glue, NOT vendored npm packages

CodeMirror 6 has no official `@codemirror/lang-dart`, `lang-kotlin`, `lang-swift`,
or `lang-shell` package (they use the CM5-style `legacy-modes` tokenizer), and
no separate packages for jsx/typescript/tsx (they're just configs of
`@codemirror/lang-javascript`). These 7 files are the same few lines every
CM6 app needs to write for these cases — nothing here comes from npm.
