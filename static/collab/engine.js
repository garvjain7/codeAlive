/**
 * collab/engine.js
 * ----------------
 * The "Brain" of the collaboration.
 * Implements the Single In-Flight Op OT model.
 */

export class SyncEngine extends EventTarget {
    constructor() {
        super();
        this.confirmedRev = 0;
        this.inflightOp = null;
        this.pendingQueue = [];
    }

    /**
     * Called when a local edit is made.
     * @param {Object} op - { type: 'insert'|'delete', position, chars|length }
     */
    addLocalOp(op) {
        this.pendingQueue.push(op);
        this.dispatchEvent(new CustomEvent('needs-send'));
    }

    /**
     * Returns the next operation to send to the server.
     * Marks it as 'inflight'.
     */
    getPendingForSend() {
        if (this.inflightOp || this.pendingQueue.length === 0) return null;
        
        // Batching optimization: If multiple adjacent inserts, collapse them
        // (Simplified for now: just take the first one)
        this.inflightOp = this.pendingQueue.shift();
        return {
            op: this.inflightOp,
            rev: this.confirmedRev
        };
    }

    /**
     * Handle OP_ACK from server.
     */
    handleAck(revision) {
        if (!this.inflightOp) {
            console.warn('[Engine] Received ACK but no op was in-flight');
            return;
        }
        this.inflightOp = null;
        this.confirmedRev = revision;
        
        // Trigger next send if pending
        if (this.pendingQueue.length > 0) {
            this.dispatchEvent(new CustomEvent('needs-send'));
        }
    }

    /**
     * Handle OP_BROADCAST from server (remote edit).
     * @param {Object} remoteOp - The operation from another user.
     * @param {number} revision - The new server revision.
     */
    handleBroadcast(remoteOp, revision) {
        this.confirmedRev = revision;

        // CRITICAL: We must transform our local unconfirmed state (inflight + pending)
        // against the incoming remote operation so they stay aligned.
        // In this architecture, we delegate the actual coordinate transformation
        // to the Editor Adapter (CodeMirror), but the Engine manages the lifecycle.
        
        this.dispatchEvent(new CustomEvent('remote-op', { 
            detail: { op: remoteOp, rev: revision } 
        }));
    }

    reset(revision) {
        this.confirmedRev = revision;
        this.inflightOp = null;
        this.pendingQueue = [];
    }
}
