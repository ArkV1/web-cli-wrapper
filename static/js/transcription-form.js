document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('transcription-form');
    const progressBarContainer = document.getElementById('progress-bar-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress');
    const resultsContainer = document.getElementById('results-container');
    const youtubeResult = document.getElementById('youtube-result');
    const whisperResult = document.getElementById('whisper-result');
    const compareButton = document.getElementById('compare-transcripts');
    const comparisonBox = document.getElementById('comparison-result-box');
    let currentYoutubeTranscript = '';
    let currentWhisperTranscript = '';

    let socketService = null;
    let currentTaskId = null;

    const methodInputs = document.querySelectorAll('input[name="method"]');
    const whisperModelContainer = document.getElementById('whisper-model-container');
    
    const debugLogsBtn = document.getElementById('toggle-debug');
    const debugLogs = document.getElementById('debug-logs');
    const debugContent = document.getElementById('debug-content');
    const debugChevron = document.getElementById('debug-chevron');
    const submitDebugBtn = document.getElementById('submit-debug');
    const copyDebugBtn = document.getElementById('copy-debug');

    let processedTaskIds = new Set();

    const comparisonMode = document.getElementById('comparison-mode');
    const comparisonInline = document.getElementById('comparison-inline');
    const comparisonSideBySide = document.getElementById('comparison-side-by-side');
    const comparisonYoutube = document.getElementById('comparison-youtube');
    const comparisonWhisper = document.getElementById('comparison-whisper');
    const comparisonResult = document.getElementById('comparison-result');

    // Function to toggle Whisper model selection visibility
    function toggleWhisperModelVisibility() {
        const selectedMethod = document.querySelector('input[name="method"]:checked').value;
        if (selectedMethod === 'Whisper' || selectedMethod === 'Both') {
            whisperModelContainer.classList.remove('hidden');
        } else {
            whisperModelContainer.classList.add('hidden');
        }
    }
    
    // Function to adjust result box widths
    function adjustResultBoxWidths() {
        const method = document.querySelector('input[name="method"]:checked').value;
        const whisperBox = document.getElementById('whisper-result-box');
        const youtubeBox = document.getElementById('youtube-result-box');
        
        if (method === 'Whisper') {
            // If only Whisper is selected, make it full width
            whisperBox.classList.remove('lg:w-1/2');
            whisperBox.classList.add('w-full');
        } else {
            // If both are selected, make them half width
            whisperBox.classList.add('lg:w-1/2');
            whisperBox.classList.remove('w-full');
        }
    }
    
    // Add change event listeners to all method radio buttons
    methodInputs.forEach(input => {
        input.addEventListener('change', () => {
            toggleWhisperModelVisibility();
            adjustResultBoxWidths();
        });
    });
    
    // Initial checks
    toggleWhisperModelVisibility();
    adjustResultBoxWidths();

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
        
        // Only log the data once, and only if it's not already part of the message
        if (data && !message.includes(JSON.stringify(data))) {
            logMessage += '\n' + JSON.stringify(data, null, 2);
        }
        
        // If this is the first log, just set it
        if (!debugContent.textContent.trim()) {
            debugContent.textContent = logMessage;
        } else {
            // Otherwise, append with proper line breaks
            debugContent.textContent = debugContent.textContent.trim() + '\n\n' + logMessage;
        }
    }

    function handleTranscriptionProgress(data) {
        if (!data || !data.task_id) {
            return;
        }

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

        // Don't process updates for tasks we've already completed
        if (processedTaskIds.has(data.task_id) && data.complete) {
            return;
        }

        // Show progress container if hidden
        const progressBarContainer = document.getElementById('progress-bar-container');
        if (progressBarContainer) {
            progressBarContainer.classList.remove('hidden');
        }

        // Reset language detection on new transcription
        if (data.progress === 0) {
            const languageDetection = document.getElementById('language-detection');
            const detectedLanguage = document.getElementById('detected-language');
            if (languageDetection && detectedLanguage) {
                languageDetection.classList.remove('hidden');
                detectedLanguage.textContent = 'Detecting...';
            }
        }

        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress');
        const downloadSpeed = document.getElementById('download-speed');
        const eta = document.getElementById('eta');
        const errorContainer = document.getElementById('error-container');
        const whisperBox = document.getElementById('whisper-result-box');
        const whisperResult = document.getElementById('whisper-result');

        // Handle completion first
        if (data.complete) {
            if (data.success) {
                // Hide error container on success
                if (errorContainer) {
                    errorContainer.classList.add('hidden');
                }
                handleTranscriptionComplete(data);
                processedTaskIds.add(data.task_id);
                return;
            } else if (data.error) {
                handleTranscriptionError(data.error || 'Transcription failed');
                return;
            }
        }

        // For non-complete states, hide error container and show progress
        if (errorContainer) {
            errorContainer.classList.add('hidden');
        }

        // Update progress bar and text
        if (progressBar && progressText) {
            progressBar.style.width = `${data.progress}%`;
            progressBar.setAttribute('aria-valuenow', data.progress);
            progressText.textContent = data.message || `${Math.round(data.progress)}%`;
            progressText.classList.remove('hidden');
        }

        // Update download speed and ETA if available
        if (downloadSpeed && data.download_speed) {
            downloadSpeed.textContent = data.download_speed;
            downloadSpeed.classList.remove('hidden');
        }
        if (eta && data.eta) {
            eta.textContent = formatETA(data.eta);
            eta.classList.remove('hidden');
        }

        // Handle incoming segments
        if (data.debug && data.debug.includes('[') && data.debug.includes('-->') && whisperBox && whisperResult) {
            // Show the results section and container
            document.getElementById('results-section').classList.remove('hidden');
            document.getElementById('results-container').classList.remove('hidden');
            
            // Show the whisper result box if it's hidden
            whisperBox.classList.remove('hidden');
            
            // Extract timestamp and text from debug message
            const debugText = data.debug.replace('Stdout captured: ', '').replace('Print captured: ', '');
            
            // Remove timestamps and get just the text
            const textOnly = debugText.replace(/\[\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}\.\d{3}\]\s*/g, '');
            
            // Check if this segment is already in the result
            if (!whisperResult.textContent.includes(textOnly)) {
                // Append the text to the whisper result
                whisperResult.textContent += textOnly + '\n';
                
                // Auto-scroll to the bottom
                whisperResult.scrollTop = whisperResult.scrollHeight;
            }
        }
    }

    function formatETA(eta) {
        // If eta is already formatted (e.g. "37s"), return as is
        if (typeof eta === 'string' && eta.includes('s')) {
            return eta;
        }
        
        // Otherwise format the number of seconds
        const seconds = parseInt(eta);
        if (isNaN(seconds)) return '';
        
        if (seconds < 60) {
            return `${Math.round(seconds)}s`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = Math.round(seconds % 60);
            return `${minutes}m ${remainingSeconds}s`;
        }
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    }

    // Add smooth transitions for progress updates
    document.addEventListener('DOMContentLoaded', function() {
        const progressBar = document.getElementById('progress-bar');
        if (progressBar) {
            progressBar.style.transition = 'width 0.5s ease-in-out';
        }
    });

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
        }

        try {
            await socketService.connect();
            
            // Register progress handler
            socketService.on('progress_update', (data) => {
                addDebugLog('Received transcription progress:', data);
                handleTranscriptionProgress(data);
            });
            
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

    // Add comparison mode change handler
    comparisonMode.addEventListener('change', async () => {
        const mode = comparisonMode.value;
        if (mode === 'inline') {
            comparisonInline.classList.remove('hidden');
            comparisonSideBySide.classList.add('hidden');
        } else {
            comparisonInline.classList.add('hidden');
            comparisonSideBySide.classList.remove('hidden');
        }
        
        // Re-run comparison with new mode
        await compareTranscripts(mode);
    });

    // Extract comparison logic to reusable function
    async function compareTranscripts(mode = 'inline') {
        try {
            const response = await fetch('/api/compare-transcripts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    youtube_transcript: currentYoutubeTranscript,
                    whisper_transcript: currentWhisperTranscript,
                    mode: mode
                })
            });

            const data = await response.json();
            if (data.success) {
                // Hide individual transcript boxes
                document.getElementById('youtube-result-box').classList.add('hidden');
                document.getElementById('whisper-result-box').classList.add('hidden');
                
                // Show comparison result
                if (mode === 'inline') {
                    comparisonResult.innerHTML = data.comparison;
                    comparisonInline.classList.remove('hidden');
                    comparisonSideBySide.classList.add('hidden');
                } else {
                    const [youtubeComp, whisperComp] = data.comparison;
                    comparisonYoutube.innerHTML = youtubeComp;
                    comparisonWhisper.innerHTML = whisperComp;
                    comparisonInline.classList.add('hidden');
                    comparisonSideBySide.classList.remove('hidden');
                }
                
                comparisonBox.classList.remove('hidden');
                compareButton.classList.add('hidden');
            } else {
                console.error('Comparison failed:', data.error);
            }
        } catch (error) {
            console.error('Error comparing transcripts:', error);
        }
    }

    // Update the compare button click handler to use the new function
    compareButton.addEventListener('click', () => {
        compareTranscripts(comparisonMode.value);
    });

    // Add back button functionality
    document.getElementById('compare-back-button').addEventListener('click', () => {
        comparisonBox.classList.add('hidden');
        document.getElementById('youtube-result-box').classList.remove('hidden');
        document.getElementById('whisper-result-box').classList.remove('hidden');
        compareButton.classList.remove('hidden');
    });

    // Form submission handler
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        try {
            // Reset UI state
            const progressBar = document.getElementById('progress-bar');
            const progressText = document.getElementById('progress');
            const progressBarContainer = document.getElementById('progress-bar-container');
            const downloadSpeedText = document.getElementById('download-speed');
            const etaText = document.getElementById('eta');
            const whisperBox = document.getElementById('whisper-result-box');
            const whisperResult = document.getElementById('whisper-result');
            
            progressBar.style.width = '0%';
            progressText.textContent = 'Starting transcription...';
            downloadSpeedText.textContent = '';
            etaText.textContent = '';
            
            // Show progress elements
            progressBarContainer.classList.remove('hidden');
            progressText.classList.remove('hidden');
            downloadSpeedText.classList.add('hidden');
            etaText.classList.add('hidden');
            
            // Hide results section and container
            document.getElementById('results-section').classList.add('hidden');
            document.getElementById('results-container').classList.add('hidden');
            document.getElementById('youtube-result-box').classList.add('hidden');
            
            // Clear the whisper result text but keep the box visible if it's already showing
            if (whisperResult) {
                whisperResult.textContent = '';
            }
            
            if (compareButton) {
                compareButton.classList.add('hidden');
            }
            
            const url = document.getElementById('url').value;
            const method = document.querySelector('input[name="method"]:checked').value;
            const modelSelect = document.getElementById('whisper-model');
            const modelName = modelSelect ? modelSelect.value : 'large';
            
            // Initialize WebSocket connection first
            await initializeWebSocket();
            
            // Make API request
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    method: method,
                    use_whisper: method === 'Whisper' || method === 'Both',
                    model_name: modelName,
                    sid: socketService.socket.id
                })
            });

            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Failed to start transcription');
            }
            
            // Store task ID for progress tracking
            currentTaskId = data.task_id;
            
        } catch (error) {
            handleTranscriptionError(error.message);
        }
    });

    // Add this function after the DOMContentLoaded event listener starts
    function toggleContainerWidth(expand) {
        const mainContainer = document.getElementById('main-container');
        if (expand) {
            mainContainer.style.maxWidth = '90%';
            mainContainer.dataset.expanded = 'true';
        } else {
            mainContainer.style.maxWidth = '672px';
            mainContainer.dataset.expanded = 'false';
        }
    }

    function handleTranscriptionComplete(data) {
        // Show results section and container
        document.getElementById('results-section').classList.remove('hidden');
        document.getElementById('results-container').classList.remove('hidden');

        // Hide progress indicators
        const progressContainer = document.getElementById('progress-bar-container');
        if (progressContainer) {
            progressContainer.classList.add('hidden');
        }

        // Store current transcripts for comparison
        if (data.youtube_transcript) {
            currentYoutubeTranscript = data.youtube_transcript;
            const youtubeBox = document.getElementById('youtube-result-box');
            const youtubeResult = document.getElementById('youtube-result');
            if (youtubeBox && youtubeResult) {
                youtubeBox.classList.remove('hidden');
                youtubeResult.textContent = data.youtube_transcript;
            }
        }

        if (data.whisper_transcript) {
            currentWhisperTranscript = data.whisper_transcript;
            const whisperBox = document.getElementById('whisper-result-box');
            const whisperResult = document.getElementById('whisper-result');
            if (whisperBox && whisperResult) {
                whisperBox.classList.remove('hidden');
                whisperResult.textContent = data.whisper_transcript;
            }
        }

        // Adjust result box widths based on method
        adjustResultBoxWidths();

        // Enable compare button if both transcripts are available
        const compareButton = document.getElementById('compare-transcripts');
        if (compareButton && data.youtube_transcript && data.whisper_transcript) {
            compareButton.classList.remove('hidden');
        }

        // Re-enable form
        const form = document.getElementById('transcription-form');
        if (form) {
            form.classList.remove('processing');
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = false;
            }
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
        const progressBarContainer = document.getElementById('progress-bar-container');
        if (progressBarContainer) {
            progressBarContainer.classList.add('hidden');
        }

        // Hide results containers
        document.getElementById('results-section')?.classList.add('hidden');
        document.getElementById('results-container')?.classList.add('hidden');
        document.getElementById('youtube-result-box')?.classList.add('hidden');
        document.getElementById('whisper-result-box')?.classList.add('hidden');
        document.getElementById('compare-transcripts')?.classList.add('hidden');

        // Re-enable form
        const form = document.getElementById('transcription-form');
        if (form) {
            form.classList.remove('processing');
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = false;
            }
        }

        // Clear current task ID and disconnect socket since we're done
        currentTaskId = null;
        if (socketService) {
            socketService.disconnect();
            socketService = null;
        }
    }

    // Add copy functionality for result boxes
    document.querySelectorAll('.copy-button').forEach(button => {
        button.addEventListener('click', async () => {
            try {
                // Find the closest result box and get its pre element
                const resultBox = button.closest('.result-box');
                const preElement = resultBox.querySelector('pre');
                
                await navigator.clipboard.writeText(preElement.textContent);
                
                // Show copied state
                const originalText = button.innerHTML;
                button.innerHTML = '<span class="flex items-center"><svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>Copied!</span>';
                
                // Reset after 2 seconds
                setTimeout(() => {
                    button.innerHTML = originalText;
                }, 2000);
            } catch (err) {
                console.error('Failed to copy text:', err);
            }
        });
    });
});