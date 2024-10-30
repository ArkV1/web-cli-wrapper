import { getElements } from './elements.js';
import { initUIManager } from './uiManager.js';
import { initPDFManager } from './pdfManager.js';
import { initSourceManager } from './sourceManager.js';
import { initSocketManager } from './socketManager.js';

const WebCLIWrapper = (function() {
    function init() {
        document.addEventListener('DOMContentLoaded', function() {
            try {
                const elements = getElements();
                if (!elements) {
                    throw new Error("Failed to get elements");
                }

                const managers = [
                    { name: 'uiManager', init: initUIManager, args: [elements] },
                    { name: 'pdfManager', init: initPDFManager, args: [elements] },
                    { name: 'sourceManager', init: initSourceManager, args: [elements] },
                    { name: 'socketManager', init: initSocketManager, args: [elements] }
                ];

                const initializedManagers = {};

                for (const manager of managers) {
                    try {
                        initializedManagers[manager.name] = manager.init(...manager.args, initializedManagers);
                    } catch (error) {
                        console.error(`Failed to initialize ${manager.name}:`, error);
                    }
                }
            } catch (error) {
                console.error("Critical error during initialization:", error);
            }
        });
    }

    return { init };
})();

WebCLIWrapper.init();