document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('pdf-form');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress');
    const resultContainer = document.getElementById('result-container');
    const pdfViewer = document.getElementById('pdf-viewer');
    const downloadLink = document.getElementById('download-link');

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
        progressBar.style.width = '50%';
        progressBar.classList.remove('bg-red-600');
        progressBar.classList.add('bg-indigo-600');
        progressText.textContent = 'Converting webpage to PDF...';
        resultContainer.classList.add('hidden');

        try {
            const response = await fetch('/api/convert-to-pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

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
            } else {
                throw new Error(data.error || 'Failed to convert webpage to PDF');
            }
        } catch (error) {
            progressText.textContent = `Error: ${error.message}`;
            progressBar.style.width = '100%';
            progressBar.classList.remove('bg-indigo-600');
            progressBar.classList.add('bg-red-600');
        }
    });
}); 