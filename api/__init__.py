"""
Auto-Trader API
Flask application initialization and configuration.
"""

import os

from flask import Flask, jsonify, request
from core.logging_config import get_logger

# Configure logging
logger = get_logger('autotrader.api', 'api')

def create_app(config=None):
    """
    Create and configure the Flask application.
    
    Args:
        config (dict, optional): Configuration dictionary
        
    Returns:
        Flask: Configured Flask application
    """
    logger.info("Creating API application")
    frontend_dir = os.environ.get('FRONTEND_DIR')
    if frontend_dir:
        static_folder = os.path.join(frontend_dir, 'static')
        template_folder = os.path.join(frontend_dir, 'templates')
    else:
        static_folder = '../frontend/static'
        template_folder = '../frontend/templates'

    app = Flask(
        __name__,
        static_folder=static_folder,
        template_folder=template_folder,
    )
    
    # Default configuration
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE='sqlite:///:memory:',
    )
    
    # Override with passed config
    if config:
        app.config.update(config)
        logger.debug("Applied custom configuration")

    @app.before_request
    def protect_trading_writes():
        if (
            request.path.startswith('/api/')
            and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
            and request.headers.get('X-All-You-Need-Is-Wheel') != '1'
        ):
            return jsonify({
                'error': 'Trading write request rejected: missing same-origin safety header'
            }), 403
    
    # Register blueprints
    from api.routes import portfolio, options, recommendations
    app.register_blueprint(portfolio.bp)
    app.register_blueprint(options.bp)
    app.register_blueprint(recommendations.bp)
    logger.info("Registered API blueprints")
    
    @app.route('/health')
    def health_check():
        logger.debug("Health check endpoint called")
        return {'status': 'healthy'}
        
    logger.info("API application created successfully")
    return app 
