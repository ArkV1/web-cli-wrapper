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

    async function initializeWebSocket() {
        if (!socketService) {
            socketService = new WebSocketService({
                debug: true,
                maxReconnectAttempts: 5,
                reconnectDelay: 2000,
                onDebug: addDebugLog
            });
        }

        try {
            await socketService.connect();
            addDebugLog('WebSocket connected successfully');
            
            socketService.on('transcription_progress', (data) => {
                addDebugLog('Received transcription progress:', data);
                
                if (data.task_id !== currentTaskId) return;
                
                // Update progress bar
                progressBar.style.width = `${data.progress}%`;
                progressText.textContent = data.message || `Progress: ${data.progress}%`;
                
                if (data.complete) {
                    if (data.success) {
                        progressText.textContent = 'Transcription complete!';
                        
                        // Show results section and container
                        document.getElementById('results-section').classList.remove('hidden');
                        resultsContainer.classList.remove('hidden');
                        
                        // Handle YouTube transcript
                        if (data.youtube_transcript) {
                            const youtubeBox = document.getElementById('youtube-result-box');
                            youtubeResult.textContent = data.youtube_transcript;
                            youtubeBox.classList.remove('hidden');
                            currentYoutubeTranscript = data.youtube_transcript;
                        }
                        
                        // Handle Whisper transcript
                        if (data.whisper_transcript) {
                            const whisperBox = document.getElementById('whisper-result-box');
                            whisperResult.textContent = data.whisper_transcript;
                            whisperBox.classList.remove('hidden');
                            currentWhisperTranscript = data.whisper_transcript;
                        }

                        // Show compare button if both transcripts are available
                        if (data.youtube_transcript && data.whisper_transcript) {
                            compareButton.classList.remove('hidden');
                        }

                        // Disconnect socket after successful completion
                        socketService.disconnect();
                    } else {
                        progressText.textContent = `Error: ${data.error || 'Unknown error occurred'}`;
                    }
                }
            });
        } catch (error) {
            addDebugLog('WebSocket connection failed:', error);
            console.error('Failed to initialize WebSocket:', error);
            progressText.textContent = 'Failed to connect to server';
            throw error;
        }
    }

    // Add comparison button click handler
    compareButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/api/compare-transcripts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    youtube_transcript: currentYoutubeTranscript,
                    whisper_transcript: currentWhisperTranscript
                })
            });

            const data = await response.json();
            if (data.success) {
                // Hide individual transcript boxes
                document.getElementById('youtube-result-box').classList.add('hidden');
                document.getElementById('whisper-result-box').classList.add('hidden');
                
                // Show comparison result
                const comparisonResult = document.getElementById('comparison-result');
                comparisonResult.innerHTML = data.comparison;
                comparisonBox.classList.remove('hidden');
                
                // Hide compare button
                compareButton.classList.add('hidden');
            } else {
                console.error('Comparison failed:', data.error);
            }
        } catch (error) {
            console.error('Error comparing transcripts:', error);
        }
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
            progressBar.style.width = '0%';
            progressText.textContent = 'Starting transcription...';
            
            // Hide all result containers
            document.getElementById('results-section').classList.add('hidden');
            document.getElementById('results-container').classList.add('hidden');
            document.getElementById('youtube-result-box').classList.add('hidden');
            document.getElementById('whisper-result-box').classList.add('hidden');
            
            if (compareButton) {
                compareButton.classList.add('hidden');
            }
            
            // Show progress elements
            progressBarContainer.classList.remove('hidden');
            progressText.classList.remove('hidden');
            
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
            
            // Start heartbeat to check progress
            socketService.startHeartbeat(currentTaskId);
            
        } catch (error) {
            console.error('Error starting transcription:', error);
            progressText.textContent = `Error: ${error.message}`;
            progressText.classList.remove('hidden');
        }
    });
});