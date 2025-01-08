/**
 * Client-side logging utility
 */
class ClientLogger {
    constructor(options = {}) {
        this.endpoint = options.endpoint || '/api/logs';
        this.defaultMetadata = options.metadata || {};
    }

    /**
     * Send a log entry to the server
     * @param {string} level - Log level (info, warning, error)
     * @param {string} message - Log message
     * @param {Object} metadata - Additional metadata to include
     * @returns {Promise} - Promise that resolves when the log is sent
     */
    async log(level, message, metadata = {}) {
        try {
            const response = await fetch(this.endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    level,
                    message,
                    metadata: {
                        ...this.defaultMetadata,
                        ...metadata,
                        url: window.location.href,
                        timestamp: new Date().toISOString()
                    }
                })
            });

            if (!response.ok) {
                console.error('Failed to send log to server:', await response.text());
            }
        } catch (error) {
            console.error('Error sending log to server:', error);
        }
    }

    /**
     * Log an info message
     * @param {string} message - Log message
     * @param {Object} metadata - Additional metadata
     */
    info(message, metadata = {}) {
        return this.log('info', message, metadata);
    }

    /**
     * Log a warning message
     * @param {string} message - Log message
     * @param {Object} metadata - Additional metadata
     */
    warning(message, metadata = {}) {
        return this.log('warning', message, metadata);
    }

    /**
     * Log an error message
     * @param {string} message - Log message
     * @param {Object} metadata - Additional metadata
     */
    error(message, metadata = {}) {
        return this.log('error', message, metadata);
    }
}

// Create a global logger instance
window.clientLogger = new ClientLogger(); 