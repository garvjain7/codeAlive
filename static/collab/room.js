/**
 * collab/room.js
 * --------------
 * The "Orchestrator" for a Workshop session.
 */

import { CollabTransport, ConnectionState } from './transport.js';
import { SyncEngine } from './engine.js';
import { CodeMirrorAdapter } from './adapter.js';

export class WorkshopRoom {
    constructor(roomId, sessionId, editorView) {
        this.roomId = roomId;
        this.sessionId = sessionId;
        this.editorView = editorView;
        
        this.transport = new CollabTransport(roomId, sessionId);
        this.engine = new SyncEngine();
        this.adapter = new CodeMirrorAdapter(editorView, this.engine);
        
        this.setupListeners();
    }

    init() {
        this.transport.connect();
    }

    setupListeners() {
        // 1. Transport -> Engine/UI
        this.transport.addEventListener('statechange', (e) => this._onStateChange(e.detail));
        this.transport.addEventListener('message', (e) => this._onMessage(e.detail));
        this.transport.addEventListener('fatal', (e) => this._onFatal(e.detail));

        // 2. Engine -> Transport (Outgoing)
        this.engine.addEventListener('needs-send', () => {
            const data = this.engine.getPendingForSend();
            if (data) {
                this.transport.send({
                    type: 'OP',
                    op: data.op,
                    rev: data.rev
                });
            }
        });

        // 3. Engine -> Adapter (Incoming)
        this.engine.addEventListener('remote-op', (e) => {
            this.adapter.applyRemoteOp(e.detail.op);
        });
    }

    _onStateChange(state) {
        // Update UI overlays
        const overlay = document.getElementById('collab-overlay');
        const statusText = document.getElementById('collab-status-text');
        
        if (state === ConnectionState.READY) {
            if (overlay) overlay.classList.add('hidden');
            this.editorView.dispatch({ effects: [/* Unlock editor */] });
        } else {
            if (overlay) overlay.classList.remove('hidden');
            if (statusText) statusText.textContent = this._getStatusMessage(state);
            // Lock editor during non-ready states
        }
    }

    _getStatusMessage(state) {
        switch (state) {
            case ConnectionState.CONNECTING: return 'Connecting to workshop...';
            case ConnectionState.SYNCING:    return 'Syncing document state...';
            case ConnectionState.RECONNECTING: return 'Connection lost. Retrying...';
            default: return 'Waiting...';
        }
    }

    _onMessage(msg) {
        switch (msg.type) {
            case 'JOIN_APPROVED':
                this.engine.reset(msg.revision);
                // Initial content load is handled by the main app initialization
                // or we can set it here if it's a fresh join
                break;
            
            case 'OP_ACK':
                this.engine.handleAck(msg.revision);
                break;

            case 'OP_BROADCAST':
                this.engine.handleBroadcast(msg.op, msg.revision);
                break;
                
            case 'ERROR':
                if (msg.code === 'outdated_revision') {
                    // Force a full resync
                    window.location.reload(); 
                }
                break;
        }
    }

    _onFatal(reason) {
        alert(`Session Error: ${reason}. Redirecting to login.`);
        window.location.href = '/auth/login?next=' + encodeURIComponent(window.location.pathname);
    }
}
