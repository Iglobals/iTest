from app import create_app
from app.utils.mongo import get_collection
from bson import ObjectId
from datetime import datetime

app = create_app()
with app.app_context():
    users_col = get_collection('users')
    orgs_col = get_collection('organizations')
    
    admin = users_col.find_one({'email': 'eoluwaseyi205@gmail.com'})
    
    if admin:
        users_col.update_one({'_id': admin['_id']}, {'$set': {'role': 'platform_admin'}})
        admin['role'] = 'platform_admin'
        
        org = orgs_col.find_one({'name': 'iGlobals Educational Services'})
        if not org:
            orgs_col.insert_one({
                'name': 'iGlobals Educational Services',
                'slug': 'iglobals-educational-services',
                'admin_user_id': admin['_id'],
                'description': 'Official iGlobals Built-in Organization',
                'contact_email': admin['email'],
                'limits': {'max_classes': 1000, 'max_teachers': 1000, 'ai_proctoring': True, 'advanced_analytics': True},
                'pending_teacher_requests': [],
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            })
            print('Created iGlobals Org')
        else:
            print('iGlobals Org already exists')
