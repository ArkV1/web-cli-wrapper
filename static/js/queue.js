document.addEventListener('DOMContentLoaded', function() {
    const urlQueueForm = document.getElementById('url-queue-form');
    const fileQueueForm = document.getElementById('file-queue-form');
    const urlInputs = document.getElementById('url-inputs');
    const addUrlButton = document.getElementById('add-url');
    const refreshQueueButton = document.getElementById('refresh-queue');
    const queueTasks = document.getElementById('queue-tasks');
    const fileUpload = document.getElementById('file-upload');
    const filesInfo = document.getElementById('files-info');
    const fileList = document.getElementById('file-list');
    const clearQueueButton = document.getElementById('clear-queue');

    // Collapsible section elements
    const urlSectionHeader = document.getElementById('url-section-header');
    const fileSectionHeader = document.getElementById('file-section-header');
    const urlSectionContent = document.getElementById('url-section-content');
    const fileSectionContent = document.getElementById('file-section-content');
    const urlSectionToggle = document.getElementById('url-section-toggle');
    const fileSectionToggle = document.getElementById('file-section-toggle');

    // Initialize section states from localStorage or default to expanded
    let urlSectionCollapsed = localStorage.getItem('urlSectionCollapsed') === 'true';
    let fileSectionCollapsed = localStorage.getItem('fileSectionCollapsed') === 'true';

    // Function to toggle section visibility
    function toggleSection(content, toggle, collapsed) {
        if (collapsed) {
            content.classList.remove('expanded');
            content.classList.add('collapsed');
            toggle.style.transform = 'rotate(-90deg)';
        } else {
            content.classList.remove('collapsed');
            content.classList.add('expanded');
            toggle.style.transform = 'rotate(0)';
        }
    }

    // Initialize section states
    toggleSection(urlSectionContent, urlSectionToggle, urlSectionCollapsed);
    toggleSection(fileSectionContent, fileSectionToggle, fileSectionCollapsed);

    // Add click handlers for section toggles
    urlSectionHeader.addEventListener('click', () => {
        urlSectionCollapsed = !urlSectionCollapsed;
        localStorage.setItem('urlSectionCollapsed', urlSectionCollapsed);
        toggleSection(urlSectionContent, urlSectionToggle, urlSectionCollapsed);
    });

    fileSectionHeader.addEventListener('click', () => {
        fileSectionCollapsed = !fileSectionCollapsed;
        localStorage.setItem('fileSectionCollapsed', fileSectionCollapsed);
        toggleSection(fileSectionContent, fileSectionToggle, fileSectionCollapsed);
    });

    let socketService = null;

    // Initialize WebSocket connection
    async function initializeWebSocket() {
        if (!socketService) {
            socketService = new WebSocketService({
                debug: true,
                reconnectionAttempts: 10,
                reconnectionDelay: 3000,
                timeout: 120000
            });

            socketService.on('progress_update', handleProgressUpdate);
            socketService.on('queue_update', handleQueueUpdate);
        }

        try {
            await socketService.connect();
            socketService.emit('join_queue');
        } catch (error) {
            console.error('Failed to initialize WebSocket:', error);
        }
    }

    // Add URL input group
    function addUrlInput() {
        const group = document.createElement('div');
        group.className = 'url-input-group';
        group.innerHTML = `
            <div class="flex gap-4">
                <div class="flex-1">
                    <input type="text" placeholder="Enter YouTube URL" 
                           class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500">
                </div>
                <select class="px-3 py-2 border border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500">
                    <option value="Both">Both</option>
                    <option value="YouTube">YouTube Only</option>
                    <option value="Whisper">Whisper Only</option>
                </select>
                <button type="button" class="remove-url px-3 py-2 text-red-600 hover:text-red-800">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
        `;
        urlInputs.appendChild(group);

        // Add remove button handler
        group.querySelector('.remove-url').addEventListener('click', () => {
            group.remove();
        });
    }

    // Handle URL form submission
    async function handleUrlSubmit(event) {
        event.preventDefault();

        const urls = [];
        const model_name = document.getElementById('url-whisper-model').value;
        
        document.querySelectorAll('.url-input-group').forEach(group => {
            const url = group.querySelector('input').value.trim();
            const method = group.querySelector('select').value;
            if (url) {
                urls.push({ 
                    url, 
                    method,
                    model_name // Add model name to each URL
                });
            }
        });

        if (urls.length === 0) {
            alert('Please enter at least one URL');
            return;
        }

        try {
            const response = await fetch('/api/queue/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ urls })
            });

            const data = await response.json();
            if (data.success) {
                // Clear form
                urlInputs.innerHTML = '';
                addUrlInput();
                // Refresh queue
                fetchQueueStatus();
            } else {
                alert(data.error || 'Failed to add URLs to queue');
            }
        } catch (error) {
            console.error('Error adding to queue:', error);
            alert('Failed to add URLs to queue');
        }
    }

    // Add a FileList-like object to store all selected files
    let selectedFiles = {
        items: [],
        length: 0,
        item: function(index) {
            return this.items[index];
        },
        [Symbol.iterator]: function* () {
            yield* this.items;
        }
    };

    // Handle file selection
    function handleFileSelect(event) {
        let files;
        if (event.dataTransfer) {
            files = event.dataTransfer.files;
        } else if (event.target && event.target.files) {
            files = event.target.files;
        } else {
            console.error('No files found in event:', event);
            return;
        }

        const MAX_FILES = 100;
        const MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024; // 2GB
        const MAX_TOTAL_SIZE = 20 * 1024 * 1024 * 1024; // 20GB

        // Calculate current total size
        let currentTotalSize = selectedFiles.items.reduce((total, file) => total + file.size, 0);

        if (selectedFiles.length + files.length > MAX_FILES) {
            alert(`Too many files selected. Maximum allowed is ${MAX_FILES}`);
            return;
        }

        let validFiles = [];
        let skippedFiles = [];

        for (let file of files) {
            if (file.size > MAX_FILE_SIZE) {
                skippedFiles.push(`${file.name} (too large, max 2GB)`);
                continue;
            }
            if (currentTotalSize + file.size > MAX_TOTAL_SIZE) {
                skippedFiles.push(`${file.name} (would exceed total size limit of 20GB)`);
                continue;
            }
            currentTotalSize += file.size;
            validFiles.push(file);
        }

        if (validFiles.length === 0 && selectedFiles.length === 0) {
            alert('No valid files to process. Please check file size limits.');
            if (event.target) {
                event.target.value = '';
            }
            return;
        }

        // Add new valid files to the selectedFiles list
        selectedFiles.items.push(...validFiles);
        selectedFiles.length = selectedFiles.items.length;

        // Update the files display
        updateFilesDisplay(skippedFiles);
    }

    // Update files display
    function updateFilesDisplay(skippedFiles = []) {
        filesInfo.classList.remove('hidden');
        
        // Show valid files
        let html = '<div class="valid-files">';
        selectedFiles.items.forEach((file, index) => {
            html += `
                <div class="flex items-center justify-between py-1 text-green-700">
                    <div class="flex items-center flex-grow mr-2 min-w-0">
                        <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span class="truncate">${file.name}</span>
                        <span class="ml-2 flex-shrink-0">(${formatFileSize(file.size)})</span>
                    </div>
                    <button type="button" class="remove-file ml-2 text-red-600 hover:text-red-800" data-index="${index}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                    </button>
                </div>`;
        });
        html += '</div>';

        // Show skipped files if any
        if (skippedFiles.length > 0) {
            html += '<div class="mt-4 pt-4 border-t border-gray-200">';
            html += '<div class="font-medium text-red-600 mb-2">Skipped files:</div>';
            skippedFiles.forEach(fileName => {
                html += `
                    <div class="flex items-center py-1 text-red-600">
                        <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span class="truncate">${fileName}</span>
                    </div>`;
            });
            html += '</div>';
        }

        // Show total size
        const totalSize = selectedFiles.items.reduce((total, file) => total + file.size, 0);
        html += `
            <div class="mt-4 pt-4 border-t border-gray-200 text-gray-700 flex items-center">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Total size: ${formatFileSize(totalSize)}
            </div>`;
        
        fileList.innerHTML = html;

        // Add event listeners for remove buttons
        document.querySelectorAll('.remove-file').forEach(button => {
            button.addEventListener('click', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                selectedFiles.items.splice(index, 1);
                selectedFiles.length = selectedFiles.items.length;
                updateFilesDisplay();
                if (selectedFiles.length === 0) {
                    filesInfo.classList.add('hidden');
                    fileUpload.value = '';
                }
            });
        });
    }

    // Handle file upload form submission
    async function handleFileSubmit(event) {
        event.preventDefault();

        if (selectedFiles.length === 0) {
            alert('Please select at least one file');
            return;
        }

        const submitButton = event.target.querySelector('button[type="submit"]');
        const originalText = submitButton.textContent;
        submitButton.disabled = true;
        submitButton.textContent = 'Adding files to queue...';

        try {
            const formData = new FormData();
            let processedFiles = 0;
            const totalFiles = selectedFiles.length;

            // Add files to FormData
            for (let file of selectedFiles) {
                formData.append('files[]', file);
                processedFiles++;
                submitButton.textContent = `Processing... ${processedFiles}/${totalFiles}`;
            }
            
            formData.append('model_name', document.getElementById('whisper-model').value);

            const response = await fetch('/api/queue/add-files', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            if (data.success) {
                // Clear form
                selectedFiles.items = [];
                selectedFiles.length = 0;
                fileUpload.value = '';
                filesInfo.classList.add('hidden');
                fileList.innerHTML = '';
                
                // Show success message with details
                const message = `Successfully queued ${data.task_ids.length} files.\n` +
                              `Total size: ${formatFileSize(data.total_size)}\n` +
                              (data.skipped_files > 0 ? `Skipped ${data.skipped_files} files` : '');
                alert(message);
                
                // Refresh queue
                fetchQueueStatus();
            } else {
                alert(data.error || 'Failed to add files to queue');
            }
        } catch (error) {
            console.error('Error adding files to queue:', error);
            alert('Failed to add files to queue');
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = originalText;
        }
    }

    // Format file size
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Fetch and update queue status
    async function fetchQueueStatus() {
        try {
            const response = await fetch('/api/queue/status');
            const data = await response.json();
            if (data.success) {
                updateQueueTable(data.current_tasks, data.completed_results, data.queue_stats);
            }
        } catch (error) {
            console.error('Error fetching queue status:', error);
        }
    }

    // Update queue table
    function updateQueueTable(currentTasks, completedResults, queueStats) {
        // Update queue stats
        const queueStatsElement = document.getElementById('queue-stats');
        if (queueStats) {
            const statsHtml = [
                queueStats.pending > 0 ? `<span class="text-yellow-600">${queueStats.pending} pending</span>` : null,
                queueStats.processing > 0 ? `<span class="text-blue-600">${queueStats.processing} processing</span>` : null,
                queueStats.completed > 0 ? `<span class="text-green-600">${queueStats.completed} completed</span>` : null,
                queueStats.failed > 0 ? `<span class="text-red-600">${queueStats.failed} failed</span>` : null
            ].filter(Boolean).join(' • ');
            
            queueStatsElement.innerHTML = statsHtml || 'No tasks in queue';
        } else {
            queueStatsElement.innerHTML = '';
        }

        const tasks = [...Object.values(currentTasks), ...completedResults];
        queueTasks.innerHTML = tasks.map(task => `
            <tr>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    ${task.url || task.filename || 'Unknown'}
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                                ${getStatusClass(task.status)}">
                        ${task.status}
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <div class="w-full bg-gray-200 rounded-full h-2.5">
                        <div class="bg-indigo-600 h-2.5 rounded-full" style="width: ${task.progress || 0}%"></div>
                    </div>
                    <span class="text-xs text-gray-500">${task.message || ''}</span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    ${task.status === 'completed' ? `
                        <a href="/api/queue/result/${task.task_id}" 
                           class="text-indigo-600 hover:text-indigo-900"
                           target="_blank">
                            View Results
                        </a>
                    ` : ''}
                </td>
            </tr>
        `).join('');
    }

    // Get status CSS class
    function getStatusClass(status) {
        switch (status?.toLowerCase()) {
            case 'pending':
                return 'bg-yellow-100 text-yellow-800';
            case 'downloading':
            case 'transcribing':
                return 'bg-blue-100 text-blue-800';
            case 'completed':
                return 'bg-green-100 text-green-800';
            case 'failed':
                return 'bg-red-100 text-red-800';
            default:
                return 'bg-gray-100 text-gray-800';
        }
    }

    // Handle progress updates
    function handleProgressUpdate(data) {
        if (!data || !data.task_id) return;
        fetchQueueStatus();
    }

    // Handle queue updates
    function handleQueueUpdate(data) {
        fetchQueueStatus();
    }

    // Clear completed and failed tasks
    async function clearQueue() {
        if (!confirm('Are you sure you want to clear all completed and failed tasks from the queue?')) {
            return;
        }

        try {
            const response = await fetch('/api/queue/clear', {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                fetchQueueStatus();
                const message = `Cleared ${data.cleared_count} tasks from the queue`;
                alert(message);
            } else {
                alert(data.error || 'Failed to clear queue');
            }
        } catch (error) {
            console.error('Error clearing queue:', error);
            alert('Failed to clear queue');
        }
    }

    // Event listeners
    addUrlButton.addEventListener('click', addUrlInput);
    urlQueueForm.addEventListener('submit', handleUrlSubmit);
    fileQueueForm.addEventListener('submit', handleFileSubmit);
    fileUpload.addEventListener('change', handleFileSelect);
    refreshQueueButton.addEventListener('click', fetchQueueStatus);
    clearQueueButton.addEventListener('click', clearQueue);

    // Initialize
    initializeWebSocket();
    addUrlInput();
    fetchQueueStatus();

    // Poll for updates every 30 seconds as backup
    setInterval(fetchQueueStatus, 30000);

    // Add drag and drop support for files
    const dropZone = document.querySelector('.border-dashed');
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('border-indigo-500');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('border-indigo-500');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-indigo-500');
        handleFileSelect(e);
    });
}); 