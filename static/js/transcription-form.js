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
    
    // Add change event listeners to all method radio buttons
    methodInputs.forEach(input => {
        input.addEventListener('change', toggleWhisperModelVisibility);
    });
    
    // Initial visibility check
    toggleWhisperModelVisibility();

    debugLogsBtn.addEventListener('click', () => {
        debugLogs.classList.toggle('hidden');
        debugChevron.classList.toggle('rotate-180');
        document.getElementById('copy-debug').classList.toggle('hidden');
    });

    // Add copy functionality for debug logs
    const copyDebugBtn = document.getElementById('copy-debug');
    copyDebugBtn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(debugContent.textContent);
            const originalText = copyDebugBtn.innerHTML;
            copyDebugBtn.innerHTML = '<span class="flex items-center"><svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>Copied!</span>';
            setTimeout(() => {
                copyDebugBtn.innerHTML = originalText;
            }, 2000);
        } catch (err) {
            console.error('Failed to copy text:', err);
        }
    });

    function addDebugLog(message, data = null) {
        const timestamp = new Date().toISOString();
        let logMessage = `[${timestamp}] ${message}`;
        if (data) {
            logMessage += '\n' + JSON.stringify(data, null, 2);
        }
        debugContent.textContent = logMessage + '\n\n' + debugContent.textContent;
    }

    function handleTranscriptionProgress(data) {
        if (!data || !data.task_id) {
            return;
        }

        // Don't process updates for tasks we've already completed
        if (processedTaskIds.has(data.task_id) && data.complete) {
            return;
        }

        // Hide any previous error messages
        const errorContainer = document.getElementById('error-container');
        if (errorContainer) {
            errorContainer.classList.add('hidden');
        }

        // Show progress container if hidden
        const progressBarContainer = document.getElementById('progress-bar-container');
        if (progressBarContainer) {
            progressBarContainer.classList.remove('hidden');
        }

        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress');
        const downloadSpeed = document.getElementById('download-speed');
        const eta = document.getElementById('eta');

        if (data.error) {
            handleTranscriptionError(data.error);
            return;
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

        // Handle completion
        if (data.complete) {
            if (data.success) {
                handleTranscriptionComplete(data);
                processedTaskIds.add(data.task_id);
            } else {
                handleTranscriptionError(data.error || 'Transcription failed');
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
                onDebug: addDebugLog,
                reconnectionAttempts: 10,
                reconnectionDelay: 3000
            });
        }

        try {
            await socketService.connect();
            addDebugLog('WebSocket connected successfully');
            
            // Register progress handler
            socketService.on('transcription_progress', handleTranscriptionProgress);
            
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
            
            progressBar.style.width = '0%';
            progressText.textContent = 'Starting transcription...';
            downloadSpeedText.textContent = '';
            etaText.textContent = '';
            
            // Show progress elements
            progressBarContainer.classList.remove('hidden');
            progressText.classList.remove('hidden');
            downloadSpeedText.classList.add('hidden');
            etaText.classList.add('hidden');
            
            // Hide results
            document.getElementById('results-section').classList.add('hidden');
            document.getElementById('results-container').classList.add('hidden');
            document.getElementById('youtube-result-box').classList.add('hidden');
            document.getElementById('whisper-result-box').classList.add('hidden');
            
            if (compareButton) {
                compareButton.classList.add('hidden');
            }
            
            const url = document.getElementById('url').value;
            const method = document.querySelector('input[name="method"]:checked').value;
            const modelSelect = document.getElementById('whisper-model');
            const modelName = modelSelect ? modelSelect.value : 'large';
            
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    method: method,
                    use_whisper: method === 'Whisper' || method === 'Both',
                    model_name: modelName
                })
            });

            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Failed to start transcription');
            }

            // Initialize WebSocket connection
            currentTaskId = data.task_id;
            await initializeWebSocket();
            
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
        const progressContainer = document.getElementById('progress-container');
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

        // Clear current task ID since we're done
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

        // Clear current task ID since we're done
        currentTaskId = null;
    }

    // Initialize WebSocket connection
    const socket = new WebSocketService({
        debug: true,
        onDebug: (message, ...args) => {
            const debugContent = document.getElementById('debug-content');
            if (debugContent) {
                const timestamp = new Date().toISOString();
                const formattedMessage = typeof message === 'object' ? JSON.stringify(message, null, 2) : message;
                const formattedArgs = args.map(arg => typeof arg === 'object' ? JSON.stringify(arg, null, 2) : arg).join(' ');
                debugContent.textContent += `[${timestamp}] ${formattedMessage} ${formattedArgs}\n`;
                debugContent.scrollTop = debugContent.scrollHeight;
            }
        }
    });

    // Set up event listeners
    socket.on('transcription_progress', handleTranscriptionProgress);

    // Handle form submission
    document.getElementById('transcription-form')?.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Clear previous results and errors
        document.getElementById('youtube-result-box')?.classList.add('hidden');
        document.getElementById('whisper-result-box')?.classList.add('hidden');
        document.getElementById('error-container')?.classList.add('hidden');
        document.getElementById('compare-button')?.classList.add('hidden');

        // Show progress container
        const progressContainer = document.getElementById('progress-container');
        if (progressContainer) {
            progressContainer.classList.remove('hidden');
        }

        // Disable form while processing
        this.classList.add('processing');
        const submitButton = this.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            // Get form data
            const url = document.getElementById('video-url').value;
            const method = Array.from(document.getElementsByName('transcription-method'))
                .find(radio => radio.checked)?.value || 'YouTube';
            const modelName = document.getElementById('whisper-model')?.value || 'base';

            // Ensure socket is connected
            await socket.connect();

            // Make API request
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url,
                    method,
                    model_name: modelName,
                    sid: socket.socket.id
                })
            });

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Failed to start transcription');
            }

        } catch (error) {
            handleTranscriptionError(error.message);
        }
    });
});