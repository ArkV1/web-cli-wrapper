document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('source-form');
    const resultContainer = document.getElementById('result-container');
    const sourceViewer = document.getElementById('source-viewer');
    const downloadLink = document.getElementById('download-link');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const url = document.getElementById('url').value;
        
        try {
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
            console.error('Error:', error);
            alert('Failed to fetch source code. Please try again.');
        }
    });
}); 