from flask_sqlalchemy import SQLAlchemy
from pymongo import MongoClient
import os

db = SQLAlchemy()
mongo_client = None

def init_mongo(app):
    global mongo_client
    uri = app.config.get('MONGO_URI')
    if uri:
        mongo_client = MongoClient(uri)
        try:
            app.mongo = mongo_client.get_database() # Defaults to db from URI
        except Exception:
            app.mongo = mongo_client.get_database('itest')
    else:
        app.mongo = None

# We can also add Mail or Limiter here later if needed
