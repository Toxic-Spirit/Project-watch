# app_config.py
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-secret-key-change-in-production')

    # Database Configuration (Uses the variable set in .env)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dealon_watches.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # User Roles
    ROLES = {
        'CUSTOMER': 'Customer',
        'SELLER': 'Seller',
        'ADMIN': 'Admin'
    }
