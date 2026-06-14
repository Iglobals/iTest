from bson.objectid import ObjectId
from app.extensions import mongo_client
from flask import current_app

def get_collection(name):
    return current_app.mongo[name]

def build_object_id(id_str):
    if not id_str:
        return None
    try:
        return ObjectId(id_str)
    except Exception:
        return None

def paginate_cursor(cursor, page=1, per_page=10):
    skip = (page - 1) * per_page
    return list(cursor.skip(skip).limit(per_page))
