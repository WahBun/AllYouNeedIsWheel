/**
 * Alert utility functions for displaying messages to users
 */

/**
 * Show an alert message that disappears after a set time
 * @param {string} message - The message to display
 * @param {string} type - Alert type (success, info, warning, danger)
 * @param {number} duration - Time in milliseconds before alert disappears
 */
function showAlert(message, type = 'info', duration = 5000) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.appendChild(document.createTextNode(String(message)));
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'btn-close';
    closeButton.dataset.bsDismiss = 'alert';
    closeButton.setAttribute('aria-label', 'Close');
    alertDiv.appendChild(closeButton);
    
    // Add the alert at the top of the content container
    const contentContainer = document.querySelector('.content-container') || document.querySelector('main');
    if (contentContainer) {
        contentContainer.prepend(alertDiv);
        
        // Auto-dismiss after duration
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }, duration);
    }
}

/**
 * Get a CSS class for a badge based on a status
 * @param {string} status - The status value
 * @returns {string} - The appropriate Bootstrap badge color class
 */
function getBadgeColor(status) {
    switch(status) {
        case 'pending':
            return 'warning';
        case 'completed':
            return 'success';
        case 'cancelled':
            return 'danger';
        case 'processing':
            return 'info';
        default:
            return 'secondary';
    }
}

// Export the functions
export { showAlert, getBadgeColor }; 
