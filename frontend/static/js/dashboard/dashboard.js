/**
 * Main dashboard module
 * Coordinates all dashboard components and initializes the dashboard
 */
import { loadPortfolioData } from './account.js?v=close-position-1';
import { loadTickers } from './options-table.js?v=refactor-safety-3';
import { loadPendingOrders } from './orders.js?v=close-position-1';
import { showAlert } from '../utils/alerts.js?v=close-position-1';
import { fetchWeeklyOptionIncome } from './api.js?v=safety-1';
import { formatCurrency } from './account.js?v=close-position-1';

// Store weekly income data
let weeklyIncomeData = null;

/**
 * Update the weekly earnings summary card
 */
async function updateWeeklyEarningsSummary() {
    try {
        const data = await fetchWeeklyOptionIncome();
        weeklyIncomeData = data;
        
        // Update the weekly income summary card
        const weeklyIncomeSummary = document.getElementById('weekly-income-summary');
        if (weeklyIncomeSummary) {
            weeklyIncomeSummary.textContent = formatCurrency(data.total_income || 0);
        }
        
        // Update the count of positions expiring this Friday
        const weeklyPositionsCount = document.getElementById('weekly-positions-count');
        if (weeklyPositionsCount) {
            weeklyPositionsCount.textContent = data.positions_count || 0;
        }
        
        // Update the Friday date if available
        const fridayDate = document.getElementById('friday-date');
        if (fridayDate && data.this_friday) {
            fridayDate.textContent = data.this_friday;
        }
    } catch (error) {
        console.error('Error updating weekly earnings summary:', error);
    }
}

/**
 * Initialize the dashboard
 */
async function initializeDashboard() {
    try {
        console.log('Initializing dashboard...');
        
        // Create a container for alerts if it doesn't exist
        if (!document.querySelector('.content-container')) {
            const mainContainer = document.querySelector('main .container') || document.querySelector('main');
            if (mainContainer) {
                const contentContainer = document.createElement('div');
                contentContainer.className = 'content-container';
                mainContainer.prepend(contentContainer);
            }
        }
        
        // Load all dashboard components in parallel
        await Promise.all([
            loadPortfolioData(),
            loadTickers(),
            loadPendingOrders(),
            updateWeeklyEarningsSummary()
        ]);
        
        // Initialize Bootstrap tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
        
        console.log('Dashboard initialization complete');
    } catch (error) {
        console.error('Error initializing dashboard:', error);
        showAlert(`Error initializing dashboard: ${error.message}`, 'danger');
    }
}

// Initialize the dashboard when the DOM is loaded
document.addEventListener('DOMContentLoaded', initializeDashboard); 
