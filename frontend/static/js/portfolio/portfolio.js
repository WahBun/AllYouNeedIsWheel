/**
 * Portfolio module
 * Handles portfolio view and position management
 */
import {
    loadPositionsTable,
    refreshLivePositions,
    startLivePositionUpdates
} from '../dashboard/account.js?v=account-live-3';
import { loadPendingOrders } from '../dashboard/orders.js?v=poll-stable-1';
import { showAlert } from '../utils/alerts.js?v=close-position-1';
import { initializeClosePosition } from './close-position.js?v=refactor-safety-2';

/**
 * Initialize the portfolio page
 */
async function initializePortfolio() {
    try {
        console.log('Initializing portfolio page...');
        
        // Create a container for alerts if it doesn't exist
        if (!document.querySelector('.content-container')) {
            const mainContainer = document.querySelector('main .container') || document.querySelector('main');
            if (mainContainer) {
                const contentContainer = document.createElement('div');
                contentContainer.className = 'content-container';
                mainContainer.prepend(contentContainer);
            }
        }
        
        initializeClosePosition();

        // Add event listener for the global refresh button
        const refreshPortfolioButton = document.getElementById('refresh-portfolio');
        if (refreshPortfolioButton) {
            refreshPortfolioButton.addEventListener('click', async () => {
                const originalContent = refreshPortfolioButton.innerHTML;
                refreshPortfolioButton.disabled = true;
                refreshPortfolioButton.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
                try {
                    const liveResult = await refreshLivePositions();
                    const result = liveResult || await loadPositionsTable();
                    if (!result) throw new Error('Portfolio data is unavailable');
                    showAlert('Portfolio refreshed successfully', 'success');
                } catch (error) {
                    showAlert(`Portfolio refresh failed: ${error.message}`, 'danger');
                } finally {
                    refreshPortfolioButton.disabled = false;
                    refreshPortfolioButton.innerHTML = originalContent;
                }
            });
        }
        
        await Promise.all([
            loadPositionsTable(),
            loadPendingOrders()
        ]);
        startLivePositionUpdates();
        
        console.log('Portfolio initialization complete');
    } catch (error) {
        console.error('Error initializing portfolio:', error);
        showAlert(`Error initializing portfolio: ${error.message}`, 'danger');
    }
}

// Initialize the portfolio when the DOM is loaded
document.addEventListener('DOMContentLoaded', initializePortfolio); 
