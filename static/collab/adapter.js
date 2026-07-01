/**
 * collab/adapter.js
 * -----------------
 * The "Translator" between CodeMirror 6 and the Sync Engine.
 */

import { EditorView, Decoration, WidgetType } from "https://esm.sh/@codemirror/view";
import { StateField, StateEffect } from "https://esm.sh/@codemirror/state";

export class CodeMirrorAdapter {
    constructor(view, engine) {
        this.view = view;
        this.engine = engine;
        this._isRemoteUpdate = false;
    }

    /**
     * Listen for local changes and push to engine.
     */
    handleLocalUpdate(update) {
        if (this._isRemoteUpdate) return; // Ignore updates we just applied
        if (!update.docChanged) return;

        update.changes.iterChanges((fromA, toA, fromB, toB, text) => {
            const inserted = text.toString();
            
            if (fromA === toA && inserted.length > 0) {
                // INSERT
                this.engine.addLocalOp({
                    type: 'insert',
                    position: fromA,
                    chars: inserted
                });
            } else if (fromA < toA && inserted.length === 0) {
                // DELETE
                this.engine.addLocalOp({
                    type: 'delete',
                    position: fromA,
                    length: toA - fromA
                });
            } else if (fromA < toA && inserted.length > 0) {
                // REPLACE (Delete then Insert)
                this.engine.addLocalOp({
                    type: 'delete',
                    position: fromA,
                    length: toA - fromA
                });
                this.engine.addLocalOp({
                    type: 'insert',
                    position: fromA,
                    chars: inserted
                });
            }
        });
    }

    /**
     * Apply remote operation to CodeMirror.
     */
    applyRemoteOp(op) {
        this._isRemoteUpdate = true;
        try {
            let transaction;
            if (op.type === 'insert') {
                transaction = {
                    changes: { from: op.position, insert: op.chars },
                    annotations: [EditorView.remote.of(true)]
                };
            } else if (op.type === 'delete') {
                transaction = {
                    changes: { from: op.position, to: op.position + op.length },
                    annotations: [EditorView.remote.of(true)]
                };
            }
            
            if (transaction) {
                this.view.dispatch(transaction);
            }
        } finally {
            this._isRemoteUpdate = false;
        }
    }
}
