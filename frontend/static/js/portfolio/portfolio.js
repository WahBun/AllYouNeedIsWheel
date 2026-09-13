/**
 * Portfolio module
 * Handles portfolio view and position management
 */
import { loadPositionsTable } from '../dashboard/account.js?v=close-position-1';
import { loadPendingOrders } from '../dashboard/orders.js?v=close-position-1';
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
                await loadPositionsTable();
                showAlert('Portfolio refreshed successfully', 'success');
            });
        }
        
        await Promise.all([
            loadPositionsTable(),
            loadPendingOrders()
        ]);
        
        console.log('Portfolio initialization complete');
    } catch (error) {
        console.error('Error initializing portfolio:', error);
        showAlert(`Error initializing portfolio: ${error.message}`, 'danger');
    }
}

// Initialize the portfolio when the DOM is loaded
document.addEventListener('DOMContentLoaded', initializePortfolio); 
