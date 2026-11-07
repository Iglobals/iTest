"""
Clear liveness_verification from all users in iTest MongoDB.
Run from iTest directory:
    python clear_liveness.py
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv('.env')

MONGO_URI = os.environ.get('MONGODB_URI')

if not MONGO_URI:
    print("❌ MONGODB_URI not found in .env file")
    exit(1)

print(f"Connecting to MongoDB...")
print(f"URI: {MONGO_URI[:30]}...")

try:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=30000,
        socketTimeoutMS=30000,
        connectTimeoutMS=30000
    )
    
    # Test connection
    client.admin.command('ping')
    print("✅ Connected successfully!")
    
    # Get database - explicitly specify itest_db
    # (the URI doesn't include /database_name so we need to specify it)
    db = client['itest_db']
    users_col = db['users']
    
    # Check current status
    total = users_col.count_documents({})
    with_liveness = users_col.count_documents({'liveness_verification': {'$exists': True}})
    completed = users_col.count_documents({'liveness_verification.status': 'completed'})
    
    print(f"\n📊 Current Status:")
    print(f"  Total users: {total}")
    print(f"  Users with liveness_verification field: {with_liveness}")
    print(f"  Users with completed verification: {completed}")
    
    if with_liveness > 0:
        print(f"\n👥 Sample users with verification:")
        samples = users_col.find(
            {'liveness_verification': {'$exists': True}},
            {'email': 1, 'full_name': 1, 'liveness_verification.status': 1}
        ).limit(5)
        
        for user in samples:
            lv = user.get('liveness_verification', {})
            print(f"  • {user.get('email', 'N/A')}: {lv.get('status', 'N/A')}")
        
        # Clear the field
        print(f"\n🧹 Clearing liveness_verification from {with_liveness} users...")
        result = users_col.update_many(
            {'liveness_verification': {'$exists': True}},
            {'$unset': {'liveness_verification': 1}}
        )
        
        print(f"✅ Cleared {result.modified_count} users")
        
        # Verify
        remaining = users_col.count_documents({'liveness_verification': {'$exists': True}})
        print(f"✅ Remaining users with liveness_verification: {remaining}")
    else:
        print(f"\n✨ No users have liveness_verification field. Nothing to clear!")
    
    client.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\n💡 Troubleshooting:")
    print("  1. Check your .env file has MONGODB_URI")
    print("  2. Check your network connection")
    print("  3. Try running from a different network if firewall is blocking")
