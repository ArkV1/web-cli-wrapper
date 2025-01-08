class WebSocketService {
    constructor(options = {}) {
        this.socket = null;
        this.options = {
            debug: true,  // Force debug mode on
            reconnectionAttempts: options.reconnectionAttempts || 10,
            reconnectionDelay: options.reconnectionDelay || 1000,
            maxReconnectionDelay: 30000  // Maximum delay between reconnection attempts
        };
        this.onDebug = options.onDebug || console.log;
        this.currentTaskId = null;
        this.reconnectAttempts = 0;
        this.isConnecting = false;
        this.reconnectTimeout = null;
        this.lastEventTime = Date.now();
        this.eventListeners = new Map();
        this.lastProgressUpdate = null;
        this.cleanDisconnect = false;  // Flag to indicate a clean disconnect
        this.isCompleting = false;  // Flag to indicate we're in the completion process
    }

    setupEventHandlers() {
        if (!this.socket) return;

        this.socket.on('disconnect', () => {
            if (!this.cleanDisconnect) {
                this.log('Disconnected from WebSocket server');
                this.handleReconnect();
            }
        });

        this.socket.on('error', (error) => {
            this.logError('Socket error:', error);
            this.handleReconnect();
        });

        this.socket.on('join_request', (data) => {
            if (data && data.task_id && (!this.currentTaskId || this.currentTaskId !== data.task_id)) {
                this.log('Received join request for room:', data.task_id);
                this.socket.emit('join', { task_id: data.task_id });
            }
        });

        this.socket.on('joined', (data) => {
            this.log('Successfully joined room:', data);
        });

        this.socket.on('ping', () => {
            this.log('Received ping');
            this.lastEventTime = Date.now();
        });

        this.socket.on('pong', () => {
            this.log('Received pong');
            this.lastEventTime = Date.now();
        });

        this.socket.on('progress_update', (data) => {
            this.log('Received progress update:', data);
            this.lastEventTime = Date.now();
            this.lastProgressUpdate = data;

            if (data.task_id && !this.currentTaskId) {
                this.currentTaskId = data.task_id;
            }

            if (data.segments && data.segments.length > 0) {
                this.log(`Received ${data.segments.length} new transcript segments`);
            }

            if (data.complete) {
                this.isCompleting = true;
            }

            const listeners = this.eventListeners.get('progress_update') || new Set();
            this.log(`Notifying ${listeners.size} progress_update listeners`);
            for (const listener of listeners) {
                listener(data);
            }

            if (data.complete) {
                setTimeout(() => {
                    this.currentTaskId = null;
                    this.cleanDisconnect = true;
                    this.isCompleting = false;
                    this.disconnect();
                }, 2000);
            }
        });
    }

    connect() {
        if (this.connectPromise) {
            return this.connectPromise;
        }

        this.connectPromise = new Promise((resolve, reject) => {
            if (this.socket?.connected) {
                resolve(this.socket);
                return;
            }

            if (!this.socket) {
                this.socket = io();
                this.setupEventHandlers();
            }

            const timeout = setTimeout(() => {
                reject(new Error('Connection timeout'));
                this.connectPromise = null;
            }, 5000);

            this.socket.once('connect', () => {
                clearTimeout(timeout);
                this.log('Connected to server');
                resolve(this.socket);
                this.connectPromise = null;

                // Rejoin room if we had a task ID
                if (this.currentTaskId) {
                    this.socket.emit('join', { task_id: this.currentTaskId });
                    this.log(`Rejoining room for task: ${this.currentTaskId}`);
                }
            });

            this.socket.once('connect_error', (error) => {
                clearTimeout(timeout);
                this.log('Connection error:', error);
                reject(error);
                this.connectPromise = null;
            });
        });

        return this.connectPromise;
    }

    handleReconnect() {
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
        }

        if (this.reconnectAttempts >= this.options.reconnectionAttempts) {
            this.logError('Max reconnection attempts reached');
            return;
        }

        // Calculate delay with exponential backoff
        const delay = Math.min(
            this.options.reconnectionDelay * Math.pow(1.5, this.reconnectAttempts),
            this.options.maxReconnectionDelay
        );

        this.reconnectAttempts++;
        this.log(`Attempting to reconnect (attempt ${this.reconnectAttempts}) in ${delay}ms`);

        this.reconnectTimeout = setTimeout(() => {
            this.connect().catch(() => {
                // If connection fails, handleReconnect will be called again by connect_error
            });
        }, delay);
    }

    on(event, callback) {
        // Store the callback in our map
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, new Set());
        }
        
        // Check if this callback is already registered
        const listeners = this.eventListeners.get(event);
        if (listeners.has(callback)) {
            this.log(`Callback already registered for event: ${event}`);
            return;
        }
        
        listeners.add(callback);
        this.log(`Registered new listener for event: ${event}, total listeners: ${this.eventListeners.get(event).size}`);

        // Only add the socket listener if we have a socket
        if (this.socket) {
            this.socket.on(event, (...args) => {
                this.log(`Received ${event} event:`, ...args);
                this.lastEventTime = Date.now();
                callback(...args);
            });
        }
    }

    off(event, callback) {
        // Remove the callback from our map
        if (this.eventListeners.has(event)) {
            this.eventListeners.get(event).delete(callback);
        }
        this.socket?.off(event, callback);
    }

    emit(event, data, callback) {
        if (!this.socket?.connected) {
            return this.connect().then(() => this.emit(event, data, callback));
        }
        
        // Store task ID if this is a transcription request and it's different from current
        if (data && data.task_id && (!this.currentTaskId || this.currentTaskId !== data.task_id)) {
            this.currentTaskId = data.task_id;
            // Join the room for this task
            this.socket.emit('join', { task_id: data.task_id });
            this.log(`Joining room for task: ${data.task_id}`);
        }
        
        this.log(`Emitting event: ${event}`, data);
        this.lastEventTime = Date.now();
        this.socket.emit(event, data, (...args) => {
            this.log(`Response received for ${event}:`, ...args);
            if (callback) callback(...args);
        });
    }

    disconnect() {
        if (this.socket) {
            if (this.reconnectTimeout) {
                clearTimeout(this.reconnectTimeout);
                this.reconnectTimeout = null;
            }
            
            // Remove all event listeners
            this.eventListeners.forEach((listeners, event) => {
                listeners.forEach(callback => {
                    this.socket.off(event, callback);
                });
            });
            this.eventListeners.clear();
            
            this.currentTaskId = null;
            this.reconnectAttempts = 0;
            this.cleanDisconnect = true;  // Set the clean disconnect flag
            this.isCompleting = false;  // Reset completion flag
            this.socket.disconnect();
            this.log('Disconnected from server');  // This will be the only disconnect message
        }
    }

    log(...args) {
        if (this.options.debug) {
            this.onDebug(...args);
        }
    }

    logError(...args) {
        console.error(...args);
        this.log(...args);
    }
}

// Add this line at the end of the file
window.WebSocketService = WebSocketService;