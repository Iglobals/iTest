import os
import requests


def upload_image(file_storage, folder='itest/avatars'):
    """Signed server-side upload via the Cloudinary SDK. The old version
    POSTed to the REST endpoint with an unsigned upload_preset
    ('itest_public') that doesn't exist on the account, so Cloudinary
    rejected it and the avatar endpoint 500'd."""
    import cloudinary
    import cloudinary.uploader
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    if not all([cloud_name, api_key, api_secret]):
        raise RuntimeError('Cloudinary configuration is missing')

    result = cloudinary.uploader.upload(
        file_storage.stream,
        folder=folder,
        resource_type='image',
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
    )
    return {'url': result.get('secure_url') or result.get('url'), 'public_id': result.get('public_id')}


def delete_image(public_id: str):
    return {'message': 'delete not implemented in MVP'}
