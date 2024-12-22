class WebSocketService {
    constructor(options = {}) {
        this.socket = null;
        this.options = {
            debug: options.debug || false,
            timeout: options.timeout || 60000,
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
    }

    async connect(url = window.location.origin) {
        // Prevent multiple simultaneous connection attempts
        if (this.isConnecting) {
            this.log('Connection attempt already in progress');
            return;
        }

        if (this.socket?.connected) {
            return Promise.resolve(this.socket);
        }

        this.isConnecting = true;
        this.cleanDisconnect = false;  // Reset the clean disconnect flag

        return new Promise((resolve, reject) => {
            try {
                // Clear any existing socket
                if (this.socket) {
                    this.socket.removeAllListeners();
                    this.socket.disconnect();
                }

                this.socket = io(url, {
                    transports: ['websocket'],
                    timeout: this.options.timeout,
                    reconnection: false,  // We'll handle reconnection ourselves
                    forceNew: true  // Force a new connection
                });

                this.socket.on('connect', () => {
                    this.log('Connected to WebSocket server');
                    this.reconnectAttempts = 0;
                    this.isConnecting = false;
                    this.lastEventTime = Date.now();
                    
                    // Request latest status for current task if any
                    if (this.currentTaskId) {
                        this.emit('check_progress', { task_id: this.currentTaskId });
                    }
                    
                    resolve(this.socket);
                });

                this.socket.on('connect_error', (error) => {
                    this.logError('Connection error:', error);
                    this.isConnecting = false;
                    if (!this.socket.connected) {
                        this.handleReconnect();
                        reject(error);
                    }
                });

                this.setupEventListeners();
            } catch (error) {
                this.isConnecting = false;
                reject(error);
            }
        });
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

    setupEventListeners() {
        this.socket.on('disconnect', () => {
            // Only log if it's not a clean disconnect
            if (!this.cleanDisconnect) {
                this.log('Disconnected from WebSocket server');
                this.handleReconnect();
            }
        });

        this.socket.on('error', (error) => {
            this.logError('Socket error:', error);
            this.handleReconnect();
        });

        // Monitor for activity
        this.socket.on('ping', () => {
            this.lastEventTime = Date.now();
        });

        this.socket.on('pong', () => {
            this.lastEventTime = Date.now();
        });

        // Set up a heartbeat to detect stale connections
        setInterval(() => {
            const now = Date.now();
            if (now - this.lastEventTime > this.options.timeout) {
                this.log('Connection appears stale, attempting reconnect');
                this.socket.disconnect();
                this.handleReconnect();
            }
        }, 5000);  // Check every 5 seconds

        // Handle transcription progress updates
        this.socket.on('transcription_progress', (data) => {
            this.lastEventTime = Date.now();
            this.lastProgressUpdate = data;

            // Update current task ID if not set
            if (data.task_id && !this.currentTaskId) {
                this.currentTaskId = data.task_id;
            }

            // Clear task ID and set clean disconnect if transcription is complete
            if (data.complete) {
                this.currentTaskId = null;
                this.cleanDisconnect = true;
            }
        });
    }

    on(event, callback) {
        // Store the callback in our map
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, new Set());
        }
        this.eventListeners.get(event).add(callback);

        this.socket?.on(event, (...args) => {
            this.lastEventTime = Date.now();
            callback(...args);
        });
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
        
        // Store task ID if this is a transcription request
        if (data && data.task_id) {
            this.currentTaskId = data.task_id;
        }
        
        this.log(`Emitting event: ${event}`, data);
        this.lastEventTime = Date.now();
        this.socket.emit(event, data, (...args) => {
            this.log(`Response for ${event}:`, ...args);
            if (callback) callback(...args);
        });
    }

    disconnect() {
        if (this.socket) {
            if (this.reconnectTimeout) {
                clearTimeout(this.reconnectTimeout);
                this.reconnectTimeout = null;
            }
            this.currentTaskId = null;
            this.reconnectAttempts = 0;
            this.cleanDisconnect = true;  // Set the clean disconnect flag
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