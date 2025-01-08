document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('transcription-form');
    const fileUpload = document.getElementById('file-upload');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const progressBarContainer = document.getElementById('progress-bar-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress');
    const resultsContainer = document.getElementById('results-container');
    const whisperResult = document.getElementById('whisper-result');
    const debugLogsBtn = document.getElementById('toggle-debug');
    const debugLogs = document.getElementById('debug-logs');
    const debugContent = document.getElementById('debug-content');
    const debugChevron = document.getElementById('debug-chevron');
    const submitDebugBtn = document.getElementById('submit-debug');
    const copyDebugBtn = document.getElementById('copy-debug');

    let socketService = null;
    let currentTaskId = null;
    let processedTaskIds = new Set();

    async function initializeWebSocket() {
        if (!socketService) {
            socketService = new WebSocketService({
                debug: true,
                onDebug: (message, data) => {
                    addDebugLog(message, data);
                },
                reconnectionAttempts: 10,
                reconnectionDelay: 3000,
                timeout: 120000
            });

            // Register progress handler only once when creating the service
            socketService.on('progress_update', (data) => {
                console.log('Received progress update:', data); // Debug log
                addDebugLog('Received transcription progress:', data);
                handleTranscriptionProgress(data);
            });
        }

        try {
            await socketService.connect();
            
            // If we have a current task, request its status
            if (currentTaskId) {
                socketService.emit('check_progress', { task_id: currentTaskId });
            }
            
        } catch (error) {
            addDebugLog('WebSocket connection failed:', error);
            console.error('Failed to initialize WebSocket:', error);
            const progressText = document.getElementById('progress-text');
            if (progressText) {
                progressText.textContent = 'Failed to connect to server';
            }
            throw error;
        }
    }

    // Handle file selection
    fileUpload.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            fileName.textContent = file.name;
            fileInfo.classList.remove('hidden');
        }
    });

    // Handle drag and drop
    const dropZone = fileUpload.closest('div');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        dropZone.classList.add('border-indigo-500');
    }

    function unhighlight(e) {
        dropZone.classList.remove('border-indigo-500');
    }

    dropZone.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        
        fileUpload.files = dt.files;
        fileName.textContent = file.name;
        fileInfo.classList.remove('hidden');
    }

    // Debug logs toggle functionality
    debugLogsBtn.addEventListener('click', () => {
        debugLogs.classList.toggle('hidden');
        debugChevron.classList.toggle('rotate-180');
        submitDebugBtn.classList.toggle('hidden');
        copyDebugBtn.classList.toggle('hidden');
    });

    // Submit logs functionality
    submitDebugBtn.addEventListener('click', async () => {
        try {
            // Format logs: split by double newlines and filter out empty lines
            const logs = debugContent.textContent
                .split('\n\n')
                .filter(log => log.trim())
                .join('\n');
                
            await clientLogger.info('Debug logs submitted', {
                taskId: currentTaskId,
                logs: logs,
                timestamp: new Date().toISOString()
            });
            
            // Show success message
            const successMessage = document.createElement('div');
            successMessage.className = 'text-green-600 text-sm mt-2';
            successMessage.textContent = 'Logs submitted successfully!';
            debugLogs.appendChild(successMessage);
            
            // Remove success message after 3 seconds
            setTimeout(() => {
                successMessage.remove();
            }, 3000);
        } catch (error) {
            console.error('Error submitting logs:', error);
            
            // Show error message
            const errorMessage = document.createElement('div');
            errorMessage.className = 'text-red-600 text-sm mt-2';
            errorMessage.textContent = 'Failed to submit logs. Please try again.';
            debugLogs.appendChild(errorMessage);
            
            // Remove error message after 3 seconds
            setTimeout(() => {
                errorMessage.remove();
            }, 3000);
        }
    });

    // Copy debug logs functionality
    copyDebugBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(debugContent.textContent)
            .then(() => {
                const originalText = copyDebugBtn.innerHTML;
                copyDebugBtn.innerHTML = '<span class="flex items-center"><svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>Copied!</span>';
                setTimeout(() => {
                    copyDebugBtn.innerHTML = originalText;
                }, 2000);
            })
            .catch(err => {
                console.error('Failed to copy text:', err);
            });
    });

    function addDebugLog(message, data = null) {
        const timestamp = new Date().toISOString();
        let logMessage = `[${timestamp}] ${message}`;
        
        if (data && !message.includes(JSON.stringify(data))) {
            logMessage += '\n' + JSON.stringify(data, null, 2);
        }
        
        if (!debugContent.textContent.trim()) {
            debugContent.textContent = logMessage;
        } else {
            debugContent.textContent = debugContent.textContent.trim() + '\n\n' + logMessage;
        }
    }

    function handleTranscriptionProgress(data) {
        if (!data || !data.task_id) {
            return;
        }

        // Get DOM elements
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress');
        const progressBarContainer = document.getElementById('progress-bar-container');
        const whisperResult = document.getElementById('whisper-result');
        const whisperBox = document.getElementById('whisper-result-box');

        // Debug log the elements
        addDebugLog('DOM Elements:', {
            hasProgressBar: !!progressBar,
            hasProgressText: !!progressText,
            hasProgressBarContainer: !!progressBarContainer,
            hasWhisperResult: !!whisperResult,
            hasWhisperBox: !!whisperBox
        });

        // Log debug messages if present
        if (data.debug) {
            addDebugLog(`[Transcription Debug] ${data.debug}`);
            
            // Handle language detection
            if (data.debug.includes('Detected language:')) {
                const languageMatch = data.debug.match(/Detected language:\s*(\w+)/);
                if (languageMatch && languageMatch[1]) {
                    const language = languageMatch[1];
                    const languageDetection = document.getElementById('language-detection');
                    const detectedLanguage = document.getElementById('detected-language');
                    if (languageDetection && detectedLanguage) {
                        languageDetection.classList.remove('hidden');
                        detectedLanguage.textContent = language;
                    }
                }
            }
        }

        // Show progress container if hidden
        if (progressBarContainer) {
            progressBarContainer.classList.remove('hidden');
        }

        // Update progress bar if progress is available
        if (typeof data.progress === 'number') {
            if (progressBar) {
                progressBar.style.width = `${data.progress}%`;
            }
            if (progressText) {
                progressText.textContent = data.message || `Progress: ${data.progress}%`;
            }
        }

        // Handle incoming segments from debug messages
        if (data.type === "debug" && data.message && data.message.includes('[') && data.message.includes('-->')) {
            addDebugLog('Found segment in debug message:', { message: data.message });
            
            // Show the results section and container
            document.getElementById('results-section').classList.remove('hidden');
            document.getElementById('results-container').classList.remove('hidden');
            
            // Show the whisper result box if it's hidden
            if (whisperBox) {
                whisperBox.classList.remove('hidden');
            }
            
            // Extract text from debug message
            const debugText = data.message;
            addDebugLog('Extracted debug text:', { debugText });
            
            // Remove timestamps and get just the text
            const textOnly = debugText.replace(/\[\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}\.\d{3}\]\s*/g, '').trim();
            addDebugLog('Extracted text only:', { textOnly });
            
            // Update whisper result if element exists and text is not already included
            if (whisperResult && textOnly) {
                addDebugLog('Current whisper result:', { 
                    currentText: whisperResult.textContent,
                    willAdd: !whisperResult.textContent.includes(textOnly)
                });
                
                if (!whisperResult.textContent.includes(textOnly)) {
                    if (!whisperResult.textContent) {
                        whisperResult.textContent = textOnly;
                    } else {
                        whisperResult.textContent += ' ' + textOnly;
                    }
                    whisperResult.scrollTop = whisperResult.scrollHeight;
                    addDebugLog('Updated whisper result with new text');
                }
            } else {
                addDebugLog('Could not update whisper result:', {
                    hasWhisperResult: !!whisperResult,
                    hasTextOnly: !!textOnly
                });
            }
        }
        // Handle final whisper result
        else if (data.whisper_result) {
            addDebugLog('Received final whisper result');
            
            // Show the results section and container
            document.getElementById('results-section').classList.remove('hidden');
            document.getElementById('results-container').classList.remove('hidden');
            
            // Show the whisper result box if it's hidden
            if (whisperBox) {
                whisperBox.classList.remove('hidden');
            }
            
            // Update the whisper result text
            if (whisperResult) {
                whisperResult.textContent = data.whisper_result;
                whisperResult.scrollTop = whisperResult.scrollHeight;
                addDebugLog('Updated whisper result with final text');
            }
        }

        if (data.complete) {
            addDebugLog('Transcription complete');
            if (progressText) {
                progressText.textContent = 'Transcription complete!';
            }
        }
    }

    function handleTranscriptionComplete(data) {
        // Hide progress indicators
        progressBarContainer.classList.add('hidden');
        
        // Show results section and container
        document.getElementById('results-section').classList.remove('hidden');
        document.getElementById('results-container').classList.remove('hidden');
        
        // Just ensure the whisper box is visible
        const whisperBox = document.getElementById('whisper-result-box');
        if (whisperBox) {
            whisperBox.classList.remove('hidden');
        }

        // Re-enable form
        form.classList.remove('processing');
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = false;
        }

        // Clear current task ID
        currentTaskId = null;
    }

    function handleTranscriptionError(error) {
        // Show error message
        const errorContainer = document.getElementById('error-container');
        const errorMessage = document.getElementById('error-message');
        if (errorContainer && errorMessage) {
            errorMessage.textContent = error;
            errorContainer.classList.remove('hidden');
        }

        // Hide progress indicators
        progressBarContainer.classList.add('hidden');

        // Hide results containers
        document.getElementById('results-section')?.classList.add('hidden');
        document.getElementById('results-container')?.classList.add('hidden');
        document.getElementById('whisper-result-box')?.classList.add('hidden');

        // Re-enable form
        form.classList.remove('processing');
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = false;
        }

        // Clear current task ID and disconnect socket since we're done
        currentTaskId = null;
        if (socketService) {
            socketService.disconnect();
            socketService = null;
        }
    }

    // Form submission handler
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const file = fileUpload.files[0];
        if (!file) {
            handleTranscriptionError('Please select a file to transcribe');
            return;
        }

        try {
            // Initialize WebSocket connection first
            await initializeWebSocket();
            
            // Reset UI state
            progressBar.style.width = '0%';
            progressText.textContent = 'Starting transcription...';
            
            // Show progress elements
            progressBarContainer.classList.remove('hidden');
            progressText.classList.remove('hidden');
            
            // Show results section and container
            document.getElementById('results-section').classList.remove('hidden');
            document.getElementById('results-container').classList.remove('hidden');
            document.getElementById('whisper-result-box').classList.remove('hidden');
            
            // Clear previous results
            if (whisperResult) {
                whisperResult.textContent = '';
            }
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('model_name', document.getElementById('whisper-model').value);
            
            // Add socket ID to form data
            if (!socketService || !socketService.socket) {
                throw new Error('Socket connection not established');
            }
            formData.append('sid', socketService.socket.id);
            console.log('Sending request with socket ID:', socketService.socket.id); // Debug log
            
            // Make API request
            const response = await fetch('/api/transcribe-file', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            console.log('Received response:', data); // Debug log
            
            if (!data.success) {
                throw new Error(data.error || 'Failed to start transcription');
            }
            
            // Store task ID for progress tracking
            currentTaskId = data.task_id;
            console.log('Started task:', currentTaskId); // Debug log
            
        } catch (error) {
            handleTranscriptionError(error.message);
        }
    });

    // Copy button functionality
    document.querySelectorAll('.copy-button').forEach(button => {
        button.addEventListener('click', function() {
            const resultBox = this.closest('.result-box');
            const textContent = resultBox.querySelector('pre').textContent;
            
            navigator.clipboard.writeText(textContent).then(() => {
                const originalText = this.textContent;
                this.textContent = 'Copied!';
                setTimeout(() => {
                    this.textContent = originalText;
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy text:', err);
            });
        });
    });
}); 