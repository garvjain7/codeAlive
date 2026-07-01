/**
 * collab/transport.js
 * -------------------
 * Stateless transport layer for CodeAlive Workshops.
 * Manages WebSocket lifecycle, Heartbeats, and State Machine transitions.
 */

export const ConnectionState = {
    DISCONNECTED: 'DISCONNECTED',
    CONNECTING:   'CONNECTING',
    SYNCING:      'SYNCING',
    READY:        'READY',
    RECONNECTING: 'RECONNECTING'
};

export class CollabTransport extends EventTarget {
    constructor(roomId, sessionId) {
        super();
        this.roomId = roomId;
        this.sessionId = sessionId;
        this.state = ConnectionState.DISCONNECTED;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectDelay = 30000; // 30s
        this.pingInterval = null;
    }

    /**
     * Entry point: Start the connection process.
     */
    connect() {
        if (this.ws) return;
        this._setState(ConnectionState.CONNECTING);
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/collab/ws/${this.roomId}?session_id=${this.sessionId}`;
        
        this.ws = new WebSocket(url);
        this.ws.onopen = () => this._onOpen();
        this.ws.onmessage = (e) => this._onMessage(e);
        this.ws.onerror = (e) => this._onError(e);
        this.ws.onclose = (e) => this._onClose(e);
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    _setState(newState) {
        if (this.state === newState) return;
        console.log(`[Transport] ${this.state} -> ${newState}`);
        this.state = newState;
        this.dispatchEvent(new CustomEvent('statechange', { detail: newState }));
    }

    _onOpen() {
        this.reconnectAttempts = 0;
        this._startHeartbeat();
        // Transition to SYNCING — waiting for JOIN_APPROVED snapshot
        this._setState(ConnectionState.SYNCING);
    }

    _onMessage(event) {
        try {
            const msg = JSON.parse(event.data);
            
            // Handle logical READY state
            if (msg.type === 'JOIN_APPROVED') {
                this._setState(ConnectionState.READY);
            }

            // Dispatch any incoming message to listeners
            this.dispatchEvent(new CustomEvent('message', { detail: msg }));
        } catch (err) {
            console.error('[Transport] Parse error:', err);
        }
    }

    _onError(error) {
        console.error('[Transport] Socket error:', error);
    }

    _onClose(event) {
        this._stopHeartbeat();
        this.ws = null;

        // Code 4001 = Auth Failed (Backend logic)
        if (event.code === 4001) {
            this._setState(ConnectionState.DISCONNECTED);
            this.dispatchEvent(new CustomEvent('fatal', { detail: 'Unauthorized' }));
            return;
        }

        // Attempt reconnection for unexpected closures
        if (this.state !== ConnectionState.DISCONNECTED) {
            this._setState(ConnectionState.RECONNECTING);
            this._scheduleReconnect();
        }
    }

    _scheduleReconnect() {
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
        this.reconnectAttempts++;
        console.log(`[Transport] Reconnecting in ${delay}ms... (Attempt ${this.reconnectAttempts})`);
        setTimeout(() => this.connect(), delay);
    }

    _startHeartbeat() {
        this.pingInterval = setInterval(() => {
            this.send({ type: 'PING' });
        }, 30000); // 30s heartbeat
    }

    _stopHeartbeat() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    disconnect() {
        this._setState(ConnectionState.DISCONNECTED);
        if (this.ws) {
            this.ws.close();
        }
    }
}
