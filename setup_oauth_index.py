"""
Run this once to create TTL index for OAuth states cleanup
This automatically deletes expired OAuth states after 10 minutes
"""
from app.utils.mongo import get_collection

def setup_oauth_index():
    oauth_col = get_collection('oauth_states')
    
    # Create TTL index - MongoDB will automatically delete documents
    # where expires_at is older than current time
    oauth_col.create_index('expires_at', expireAfterSeconds=0)
    
    print("✅ Created TTL index on oauth_states.expires_at")
    print("MongoDB will now automatically delete expired OAuth states")

if __name__ == '__main__':
    setup_oauth_index()
