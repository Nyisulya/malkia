import os
import time
from functools import lru_cache
import boto3
from botocore.config import Config
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from storages.backends.s3boto3 import S3Boto3Storage


_CFG_CACHE = {'ts': 0.0, 'cfg': None}
_CFG_TTL_SECONDS = 10


def get_r2_config(use_cache=True):
    """
    Retrieves Cloudflare R2 configuration from SystemConfig (database UI)
    with fallback to environment variables / settings.py.
    """
    if use_cache and _CFG_CACHE['cfg'] is not None and (time.time() - _CFG_CACHE['ts']) < _CFG_TTL_SECONDS:
        return _CFG_CACHE['cfg']

    account_id = getattr(settings, 'R2_ACCOUNT_ID', '') or os.getenv('R2_ACCOUNT_ID', '')
    access_key = getattr(settings, 'R2_ACCESS_KEY_ID', '') or os.getenv('R2_ACCESS_KEY_ID', '')
    secret_key = getattr(settings, 'R2_SECRET_ACCESS_KEY', '') or os.getenv('R2_SECRET_ACCESS_KEY', '')
    bucket_name = getattr(settings, 'R2_BUCKET_NAME', '') or os.getenv('R2_BUCKET_NAME', '')
    public_domain = getattr(settings, 'R2_PUBLIC_DOMAIN', '') or os.getenv('R2_PUBLIC_DOMAIN', '')

    try:
        from core.models import SystemConfig
        db_account = SystemConfig.get_value('R2_ACCOUNT_ID', '').strip()
        db_access = SystemConfig.get_value('R2_ACCESS_KEY_ID', '').strip()
        db_secret = SystemConfig.get_value('R2_SECRET_ACCESS_KEY', '').strip()
        db_bucket = SystemConfig.get_value('R2_BUCKET_NAME', '').strip()
        db_domain = SystemConfig.get_value('R2_PUBLIC_DOMAIN', '').strip()

        if db_account:
            account_id = db_account
        if db_access:
            access_key = db_access
        if db_secret:
            secret_key = db_secret
        if db_bucket:
            bucket_name = db_bucket
        if db_domain:
            public_domain = db_domain
    except Exception:
        pass

    endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com" if account_id else ""
    is_configured = bool(account_id and access_key and secret_key and bucket_name)

    cfg = {
        'is_configured': is_configured,
        'account_id': account_id,
        'access_key': access_key,
        'secret_key': secret_key,
        'bucket_name': bucket_name,
        'endpoint_url': endpoint_url,
        'public_domain': public_domain,
    }
    _CFG_CACHE['cfg'] = cfg
    _CFG_CACHE['ts'] = time.time()
    return cfg


def test_r2_connection():
    """
    Tests live connectivity to the configured Cloudflare R2 bucket.
    Returns (success: bool, message: str).
    """
    cfg = get_r2_config(use_cache=False)
    if not cfg['is_configured']:
        return False, "Cloudflare R2 credentials are incomplete. Please provide Account ID, Bucket Name, Access Key ID, and Secret Access Key."

    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=cfg['endpoint_url'],
            aws_access_key_id=cfg['access_key'],
            aws_secret_access_key=cfg['secret_key'],
            region_name='auto',
            config=Config(signature_version='s3v4')
        )
        res = s3_client.list_objects_v2(Bucket=cfg['bucket_name'], Prefix='malkia_files/', MaxKeys=5)
        count = res.get('KeyCount', 0)
        return True, f"Connected to Cloudflare R2 Bucket '{cfg['bucket_name']}' (Isolated folder: malkia_files/, {count} object(s) verified)!"
    except Exception as exc:
        return False, f"Cloudflare R2 Connection Error: {str(exc)}"


@lru_cache(maxsize=4)
def _build_r2_storage(access_key, secret_key, bucket_name, endpoint_url, custom_domain):
    return S3Boto3Storage(
        access_key=access_key,
        secret_key=secret_key,
        bucket_name=bucket_name,
        endpoint_url=endpoint_url,
        region_name='auto',
        signature_version='s3v4',
        addressing_style='path',
        custom_domain=custom_domain,
        querystring_auth=(custom_domain is None),
        querystring_expire=86400,  # 24-hour signed links for staff
        file_overwrite=False,
    )


class MalkiaDynamicR2Storage(FileSystemStorage):
    """
    Smart storage backend for Malkia C&F:
    - When Cloudflare R2 credentials are configured (in System Settings or .env),
      stores and serves all scanned client files directly from Cloudflare R2.
    - When R2 credentials are not yet entered, seamlessly falls back to organized
      local media storage so file opening never fails.
    """

    def _get_r2_storage(self):
        cfg = get_r2_config()
        if not cfg['is_configured']:
            return None

        custom_domain = cfg['public_domain'].replace('https://', '').replace('http://', '').strip('/') if cfg['public_domain'] else None
        return _build_r2_storage(
            cfg['access_key'],
            cfg['secret_key'],
            cfg['bucket_name'],
            cfg['endpoint_url'],
            custom_domain,
        )

    def _open(self, name, mode='rb'):
        local_path = os.path.join(settings.MEDIA_ROOT, name)
        if os.path.exists(local_path):
            return super()._open(name, mode)
        r2 = self._get_r2_storage()
        if r2 is not None:
            try:
                return r2._open(name, mode)
            except Exception as e:
                print(f"[Cloudflare R2 Read Fallback] {e}")
        return super()._open(name, mode)

    def _save(self, name, content):
        r2 = self._get_r2_storage()
        if r2 is not None:
            try:
                return r2._save(name, content)
            except Exception as e:
                print(f"[Cloudflare R2 Upload Fallback to Local] {e}")
        return super()._save(name, content)

    def url(self, name):
        r2 = self._get_r2_storage()
        if r2 is not None:
            # Never probe R2 over the network while rendering a page.
            # Local files (legacy or upload fallback) are served directly;
            # everything else gets a locally-signed R2 URL.
            local_path = os.path.join(settings.MEDIA_ROOT, name)
            if os.path.exists(local_path):
                return super().url(name)
            try:
                return r2.url(name)
            except Exception:
                return super().url(name)
        return super().url(name)

    def exists(self, name):
        r2 = self._get_r2_storage()
        if r2 is not None:
            try:
                return r2.exists(name)
            except Exception:
                pass
        return super().exists(name)

