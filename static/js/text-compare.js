document.addEventListener('DOMContentLoaded', function() {
    const text1Input = document.getElementById('text1');
    const text2Input = document.getElementById('text2');
    const compareButton = document.getElementById('compare-btn');
    const comparisonMode = document.getElementById('comparison-mode');
    const resultsContainer = document.getElementById('results-container');
    const sideBySideView = document.getElementById('side-by-side-view');
    const inlineView = document.getElementById('inline-view');
    const legend = document.getElementById('legend');

    compareButton.addEventListener('click', async () => {
        const text1 = text1Input.value;
        const text2 = text2Input.value;
        const mode = comparisonMode.value;

        try {
            const response = await fetch('/api/compare-texts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text1: text1,
                    text2: text2,
                    mode: mode
                })
            });

            const data = await response.json();
            
            if (data.success) {
                resultsContainer.classList.remove('hidden');
                legend.classList.remove('hidden');
                
                if (mode === 'inline') {
                    sideBySideView.classList.add('hidden');
                    inlineView.classList.remove('hidden');
                    document.getElementById('inline-comparison').innerHTML = data.comparison;
                } else {
                    sideBySideView.classList.remove('hidden');
                    inlineView.classList.add('hidden');
                    document.getElementById('text1-comparison').innerHTML = data.comparison[0];
                    document.getElementById('text2-comparison').innerHTML = data.comparison[1];
                }
            } else {
                alert('Error comparing texts: ' + data.error);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to compare texts. Please try again.');
        }
    });

    // Update view when mode changes
    comparisonMode.addEventListener('change', () => {
        if (resultsContainer.classList.contains('hidden')) return;
        
        if (comparisonMode.value === 'inline') {
            sideBySideView.classList.add('hidden');
            inlineView.classList.remove('hidden');
        } else {
            sideBySideView.classList.remove('hidden');
            inlineView.classList.add('hidden');
        }
    });
});