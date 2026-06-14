import os
import requests


def upload_image(file_storage):
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    if not all([cloud_name, api_key, api_secret]):
        raise RuntimeError('Cloudinary configuration is missing')

    upload_url = f'https://api.cloudinary.com/v1_1/{cloud_name}/image/upload'
    files = {'file': (file_storage.filename, file_storage.stream, file_storage.mimetype)}
    payload = {'upload_preset': os.environ.get('CLOUDINARY_UPLOAD_PRESET', 'itest_public')}
    response = requests.post(upload_url, files=files, data=payload, auth=(api_key, api_secret))
    response.raise_for_status()
    return response.json()


def delete_image(public_id: str):
    return {'message': 'delete not implemented in MVP'}
