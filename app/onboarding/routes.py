from flask import Blueprint, render_template, request, redirect, url_for, g, flash
from app.auth.decorators import require_auth
from app.utils.mongo import get_collection
from bson.objectid import ObjectId
from datetime import datetime
import re

onboarding_bp = Blueprint('onboarding', __name__, url_prefix='/onboarding')

@onboarding_bp.route('/', methods=['GET', 'POST'])
@require_auth()
def index():
    if g.current_user.get('onboarded'):
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        role = request.form.get('role')
        if role not in ['student', 'teacher', 'org_admin']:
            flash("Invalid role selected.", "error")
            return redirect(url_for('onboarding.index'))
            
        users_col = get_collection('users')
        user_id = g.current_user['_id']
        
        update_data = {
            "role": role,
            "onboarded": True,
            "updated_at": datetime.utcnow()
        }
        
        if role == 'student':
            update_data["institution"] = request.form.get('institution', '').strip()
            update_data["programme"] = request.form.get('programme', '').strip()
            
        elif role == 'teacher':
            update_data["institution"] = request.form.get('institution', '').strip()
            update_data["phone"] = request.form.get('phone', '').strip()
            
        elif role == 'org_admin':
            org_name = request.form.get('org_name', '').strip()
            if not org_name:
                flash("Organization name is required.", "error")
                return redirect(url_for('onboarding.index'))
                
            org_slug = re.sub(r'[^a-z0-9]+', '-', org_name.lower()).strip('-')
            
            orgs_col = get_collection('organizations')
            # Check for slug collision
            base_slug = org_slug
            counter = 1
            while orgs_col.find_one({"slug": org_slug}):
                org_slug = f"{base_slug}-{counter}"
                counter += 1
                
            org_data = {
                "name": org_name,
                "slug": org_slug,
                "admin_user_id": user_id,
                "description": request.form.get('org_description', '').strip(),
                "contact_email": request.form.get('org_email', '').strip() or g.current_user.get('email'),
                "limits": {
                    "max_classes": 5,
                    "max_teachers": 10,
                    "ai_proctoring": False,
                    "advanced_analytics": False
                },
                "pending_teacher_requests": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = orgs_col.insert_one(org_data)
            update_data["organization_id"] = result.inserted_id
            
        # Perform the user update
        users_col.update_one({"_id": user_id}, {"$set": update_data})
        
        return redirect(url_for('dashboard.index'))
        
    return render_template('onboarding/index.html')
