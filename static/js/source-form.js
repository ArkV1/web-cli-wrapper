document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('source-form');
    const resultContainer = document.getElementById('result-container');
    const sourceViewer = document.getElementById('source-viewer');
    const downloadLink = document.getElementById('download-link');

    const debugLogsBtn = document.getElementById('toggle-debug');
    const debugLogs = document.getElementById('debug-logs');
    const debugContent = document.getElementById('debug-content');
    const debugChevron = document.getElementById('debug-chevron');

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
        
        addDebugLog('Starting source code fetch...');
        const url = document.getElementById('url').value;
        
        try {
            addDebugLog('Fetching source code', { url: url });
            const response = await fetch('/api/fetch-source', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: url })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            // Display the source code
            sourceViewer.textContent = data.source;
            
            // Create blob and update download link
            const blob = new Blob([data.source], { type: 'text/html' });
            const downloadUrl = window.URL.createObjectURL(blob);
            
            // Extract domain name for filename
            const domain = new URL(url).hostname;
            const filename = `${domain}-source.html`;
            
            downloadLink.href = downloadUrl;
            downloadLink.download = filename;
            
            // Show the result container
            resultContainer.classList.remove('hidden');
            
            // Scroll to results
            resultContainer.scrollIntoView({ behavior: 'smooth' });

        } catch (error) {
            addDebugLog('Error occurred', { error: error.message });
            console.error('Error:', error);
            alert('Failed to fetch source code. Please try again.');
        }
    });
}); 