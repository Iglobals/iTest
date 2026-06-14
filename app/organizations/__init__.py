from flask import Blueprint

# Ensure routes are imported so they are registered with the blueprint
from app.organizations.routes import org_bp
