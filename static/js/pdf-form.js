document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('pdf-form');
    const progressContainer = document.getElementById('progress-container');
    const progressBarContainer = document.getElementById('progress-bar-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress');
    const resultContainer = document.getElementById('result-container');
    const pdfViewer = document.getElementById('pdf-viewer');
    const downloadLink = document.getElementById('download-link');

    const debugLogsBtn = document.getElementById('toggle-debug');
    const debugLogs = document.getElementById('debug-logs');
    const debugContent = document.getElementById('debug-content');
    const debugChevron = document.getElementById('debug-chevron');

    // Add new progress stages
    const progressStages = {
        'Fetching webpage...': { start: 0, end: 33 },
        'Converting webpage to PDF...': { start: 33, end: 66 },
        'Finalizing PDF...': { start: 66, end: 90 },
        'Complete': { start: 90, end: 100 }
    };

    // Add debug log toggle functionality
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

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        addDebugLog('Starting PDF conversion...');
        
        const formData = {
            url: document.getElementById('url').value,
            orientation: document.getElementById('orientation').value,
            zoom: document.getElementById('zoom').value,
            exclude: document.getElementById('exclude').value
        };

        // Reset UI state
        progressContainer.classList.remove('hidden');
        progressBar.style.width = '0%';
        progressBar.classList.remove('bg-red-600');
        progressBar.classList.add('bg-indigo-600');
        progressText.textContent = 'Fetching webpage...';
        resultContainer.classList.add('hidden');

        try {
            addDebugLog('Processing URL', { url: formData.url });
            
            const response = await fetch('/api/convert-to-pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            progressBar.style.width = '66%';
            progressText.textContent = 'Converting webpage to PDF...';
            addDebugLog('Webpage fetched, converting to PDF...');

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Server error occurred');
            }

            if (data.success) {
                const pdfPath = `/output/${data.filename}`;
                pdfViewer.src = pdfPath;
                downloadLink.href = pdfPath;
                resultContainer.classList.remove('hidden');
                progressBar.style.width = '100%';
                progressText.textContent = 'Conversion complete!';
                addDebugLog('PDF conversion completed successfully!');
            } else {
                throw new Error(data.error || 'Failed to convert webpage to PDF');
            }
        } catch (error) {
            progressText.textContent = `Error: ${error.message}`;
            progressBar.style.width = '100%';
            progressBar.classList.remove('bg-indigo-600');
            progressBar.classList.add('bg-red-600');
            addDebugLog('Error occurred', { error: error.message });
        }
    });
}); 