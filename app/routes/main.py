"""
Main Routes
Homepage and general application routes
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

# Create Blueprint
bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """
    Homepage - Landing page for TradeVerse
    
    If user is logged in, redirect to dashboard
    Otherwise, show the marketing homepage
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    return render_template('main/index.html')

@bp.route('/about')
def about():
    """About page - Information about TradeVerse"""
    return render_template('main/about.html')

@bp.route('/features')
def features():
    """Features page - Showcase all features"""
    return render_template('main/features.html')

@bp.route('/pricing')
def pricing():
    """Pricing page - Subscription plans"""
    return render_template('main/pricing.html')

@bp.route('/contact')
def contact():
    """Contact page - Contact form"""
    return render_template('main/contact.html')