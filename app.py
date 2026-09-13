"""
Auto-Trader Web Application
Main entry point for the web application
"""

import os
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify
from api import create_app
from core.logging_config import get_logger
from db.database import OptionsDatabase
from core.connection import IBConnection, suppress_ib_logs

# Configure logging
logger = get_logger('autotrader.app', 'api')

# Create Flask application with necessary configs
def create_application():
    # Create the app through the factory function
    app = create_app()
    
    # Load connection configuration
    connection_config_path = os.environ.get('CONNECTION_CONFIG', 'connection.json')
    logger.info(f"Loading connection configuration from: {connection_config_path}")

    connection_config = {}
    
    if os.path.exists(connection_config_path):
        try:
            with open(connection_config_path, 'r') as f:
                connection_config = json.load(f)
                logger.info(f"Loaded connection configuration from {connection_config_path}")
                # Initialize the database
                db_path = connection_config['db_path']
                logger.info(f"Initializing database at {db_path}")
                options_db = OptionsDatabase(db_path)
                app.config['database'] = options_db
        except Exception as e:
            logger.error(f"Error loading connection configuration: {str(e)}")
            # Use default values
            connection_config = {
                "host": "127.0.0.1",
                "port": 7497,  # Use 7496 for TWS, 7497 for IB Gateway
                "client_id": 1,
                "readonly": True  # Default to readonly for safety
            }
    else:
        logger.warning(f"Connection configuration file {connection_config_path} not found, using defaults")
        # Use default values
        connection_config = {
            "host": "127.0.0.1",
            "port": 7497,
            "client_id": 1,
            "readonly": True
        }
    # Store connection config in the app
    app.config['connection_config'] = connection_config
    logger.info(f"Using connection config: {connection_config}")
    
    return app

# Create the application
app = create_application()

# Web routes
@app.route('/')
def index():
    """
    Render the dashboard page
    """
    logger.info("Rendering dashboard page")
    return render_template('dashboard.html')

@app.route('/portfolio')
def portfolio():
    """
    Render the portfolio page
    """
    logger.info("Rendering portfolio page")
    return render_template('portfolio.html')

@app.route('/options')
def options():
    """
    Temporarily redirect options page to home
    """
    logger.info("Options page accessed but currently unavailable - redirecting to home")
    return redirect(url_for('index'))

@app.route('/rollover')
def rollover():
    """
    Render the rollover page for options approaching strike price
    """
    logger.info("Rendering rollover page")
    return render_template('rollover.html')

@app.route('/recommendations')
def recommendations():
    """
    Temporarily redirect recommendations page to home
    """
    logger.info("Recommendations page accessed but currently unavailable - redirecting to home")
    return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    """
    Handle 404 errors
    """
    logger.warning(f"404 error: {request.path}")
    return render_template('error.html', error_code=404, message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    """
    Handle 500 errors
    """
    logger.error(f"500 error: {str(e)}")
    return render_template('error.html', error_code=500, message="Server error"), 500

if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 8000))
    
    # Run the application
    logger.info(f"Starting Flask development server on port {port}")
    app.run(host='127.0.0.1', port=port, debug=True)
