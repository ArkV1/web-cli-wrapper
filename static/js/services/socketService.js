class WebSocketService {
    constructor(options = {}) {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.options = {
            maxReconnectAttempts: options.maxReconnectAttempts || 3,
            reconnectDelay: options.reconnectDelay || 1000,
            timeout: options.timeout || 60000,
            debug: options.debug || false
        };
        this.eventHandlers = new Map();
        this.connectionPromise = null;
        this.heartbeatInterval = null;
        this.isConnecting = false;
        this.onDebug = options.onDebug || console.log;
    }

    async connect(url = window.location.origin) {
        if (this.socket?.connected) {
            return Promise.resolve(this.socket);
        }

        if (this.isConnecting) {
            return this.connectionPromise;
        }

        this.isConnecting = true;
        this.connectionPromise = new Promise((resolve, reject) => {
            try {
                this.socket = io(url, {
                    transports: ['websocket'],
                    reconnection: true,
                    reconnectionAttempts: this.options.maxReconnectAttempts,
                    reconnectionDelay: this.options.reconnectDelay,
                    timeout: this.options.timeout
                });

                this.socket.on('connect', () => {
                    this.log('Connected to WebSocket server');
                    this.isConnecting = false;
                    resolve(this.socket);
                });

                this.socket.on('connect_error', (error) => {
                    this.logError('Connection error:', error);
                    if (!this.socket.connected) {
                        this.isConnecting = false;
                        reject(error);
                    }
                });
            } catch (error) {
                this.isConnecting = false;
                reject(error);
            }
        });

        return this.connectionPromise;
    }

    setupEventListeners() {
        this.socket.on('disconnect', () => {
            this.log('Disconnected from WebSocket server');
            this.connectionPromise = null;
        });

        this.socket.on('reconnect_attempt', (attemptNumber) => {
            this.log(`Reconnection attempt ${attemptNumber}`);
            this.reconnectAttempts = attemptNumber;
        });

        this.socket.on('error', (error) => {
            this.log('Socket error:', error);
        });
    }

    on(event, callback) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, new Set());
        }
        this.eventHandlers.get(event).add(callback);
        
        const wrappedCallback = (...args) => {
            this.log(`Received event: ${event}`, ...args);
            callback(...args);
        };
        
        this.socket?.on(event, wrappedCallback);
        return () => this.off(event, wrappedCallback);
    }

    off(event, callback) {
        this.socket?.off(event, callback);
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.delete(callback);
        }
    }

    emit(event, data, callback) {
        this.log(`Emitting event: ${event}`, data);
        if (!this.socket?.connected) {
            return this.connect().then(() => {
                this.socket.emit(event, data, (...args) => {
                    this.log(`Response for ${event}:`, ...args);
                    if (callback) callback(...args);
                });
            }).catch(error => {
                this.logError(`Failed to emit ${event}:`, error);
                throw error;
            });
        }
        
        this.socket.emit(event, data, (...args) => {
            this.log(`Response for ${event}:`, ...args);
            if (callback) callback(...args);
        });
    }

    disconnect() {
        if (this.socket) {
            // Clear any existing heartbeat interval
            if (this.heartbeatInterval) {
                clearInterval(this.heartbeatInterval);
                this.heartbeatInterval = null;
            }
            
            // Disconnect the socket
            this.socket.disconnect();
            console.log('[WebSocket] Disconnected from server');
        }
    }

    log(...args) {
        if (this.options.debug) {
            this.onDebug(...args);
        }
    }

    logError(...args) {
        this.onDebug('ERROR:', ...args);
    }

    startHeartbeat(taskId) {
        // Clear any existing heartbeat first
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
        
        this.heartbeatInterval = setInterval(() => {
            if (this.socket && this.socket.connected) {
                this.emit('check_progress', { task_id: taskId });
            } else {
                clearInterval(this.heartbeatInterval);
            }
        }, 5000);
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
}

// Add this line at the end of the file
window.WebSocketService = WebSocketService;