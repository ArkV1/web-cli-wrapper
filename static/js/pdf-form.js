document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('pdf-form');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress');
    const resultContainer = document.getElementById('result-container');
    const pdfViewer = document.getElementById('pdf-viewer');
    const downloadLink = document.getElementById('download-link');

    // Add new progress stages
    const progressStages = {
        'Fetching webpage...': { start: 0, end: 33 },
        'Converting webpage to PDF...': { start: 33, end: 66 },
        'Finalizing PDF...': { start: 66, end: 90 },
        'Complete': { start: 90, end: 100 }
    };

    // Add log functionality
    const logContent = document.createElement('div');
    logContent.id = 'log-content';
    logContent.className = 'space-y-1';

    function addLog(message, type = 'info') {
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        const timestamp = new Date().toLocaleTimeString();
        logEntry.textContent = `[${timestamp}] ${message}`;
        logContent.appendChild(logEntry);
        logContent.scrollTop = logContent.scrollHeight;
    }

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
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
        
        addLog('Starting PDF conversion...', 'info');
        progressBar.style.width = '33%';
        progressText.textContent = 'Fetching webpage...';
        resultContainer.classList.add('hidden');

        try {
            addLog(`Processing URL: ${formData.url}`, 'info');
            
            const response = await fetch('/api/convert-to-pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            progressBar.style.width = '66%';
            progressText.textContent = 'Converting webpage to PDF...';
            addLog('Webpage fetched, converting to PDF...', 'info');

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
                addLog('PDF conversion completed successfully!', 'success');
            } else {
                throw new Error(data.error || 'Failed to convert webpage to PDF');
            }
        } catch (error) {
            progressText.textContent = `Error: ${error.message}`;
            progressBar.style.width = '100%';
            progressBar.classList.remove('bg-indigo-600');
            progressBar.classList.add('bg-red-600');
            addLog(`Error: ${error.message}`, 'error');
        }
    });
}); 