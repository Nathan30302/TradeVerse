"""
Secure credential manager using Fernet encryption.
Provides encrypt/decrypt utilities for storing API keys and sensitive broker credentials.
"""
from cryptography.fernet import Fernet
import os
import json
from typing import Dict, Any, Optional
import requests

try:
    import boto3
    _HAS_BOTO3 = True
except Exception:
    _HAS_BOTO3 = False


def _get_cipher():
    """Get or create the encryption cipher key from environment."""
    # Priority: explicit env var -> HashiCorp Vault -> AWS Secrets Manager -> generate dev key
    key = os.environ.get('CREDENTIAL_ENCRYPTION_KEY')
    if key:
        return Fernet(key if isinstance(key, bytes) else key.encode())

    # Try Vault if configured
    vault_addr = os.environ.get('VAULT_ADDR')
    vault_token = os.environ.get('VAULT_TOKEN')
    vault_path = os.environ.get('VAULT_SECRET_PATH')  # e.g., secret/data/tradeverse/fernet
    if vault_addr and vault_token and vault_path:
        try:
            url = vault_addr.rstrip('/') + f"/v1/{vault_path}"
            headers = {'X-Vault-Token': vault_token}
            r = requests.get(url, headers=headers, timeout=5)
            r.raise_for_status()
            data = r.json()
            # Support KV v2 shape
            if 'data' in data and 'data' in data['data']:
                secret = data['data']['data'].get('CREDENTIAL_ENCRYPTION_KEY')
            else:
                secret = data.get('data', {}).get('CREDENTIAL_ENCRYPTION_KEY') or data.get('data')
            if secret:
                return Fernet(secret if isinstance(secret, bytes) else secret.encode())
        except Exception:
            pass

    # Try AWS Secrets Manager if configured
    aws_secret_name = os.environ.get('AWS_SECRETS_MANAGER_SECRET')
    aws_region = os.environ.get('AWS_REGION')
    if _HAS_BOTO3 and aws_secret_name:
        try:
            session = boto3.session.Session()
            client = session.client(service_name='secretsmanager', region_name=aws_region)
            resp = client.get_secret_value(SecretId=aws_secret_name)
            secret_str = resp.get('SecretString')
            if secret_str:
                # SecretString may be JSON
                try:
                    s = json.loads(secret_str)
                    secret = s.get('CREDENTIAL_ENCRYPTION_KEY') or s.get('fernet_key') or s.get('key')
                except Exception:
                    secret = secret_str
                if secret:
                    return Fernet(secret if isinstance(secret, bytes) else secret.encode())
        except Exception:
            pass

    # Fallback: generate a development key (do not use in production)
    key = Fernet.generate_key().decode()
    os.environ['CREDENTIAL_ENCRYPTION_KEY'] = key
    return Fernet(key if isinstance(key, bytes) else key.encode())


def bootstrap_secrets():
    """Attempt to fetch credentials (Fernet key) from Vault or AWS Secrets Manager at startup.
    If found, set the environment variable and return True. Otherwise return False.
    """
    # Try Vault first
    vault_addr = os.environ.get('VAULT_ADDR')
    vault_token = os.environ.get('VAULT_TOKEN')
    vault_path = os.environ.get('VAULT_SECRET_PATH')
    if vault_addr and vault_token and vault_path:
        try:
            url = vault_addr.rstrip('/') + f"/v1/{vault_path}"
            headers = {'X-Vault-Token': vault_token}
            r = requests.get(url, headers=headers, timeout=5)
            r.raise_for_status()
            data = r.json()
            if 'data' in data and 'data' in data['data']:
                secret = data['data']['data'].get('CREDENTIAL_ENCRYPTION_KEY')
            else:
                secret = data.get('data', {}).get('CREDENTIAL_ENCRYPTION_KEY') or data.get('data')
            if secret:
                os.environ['CREDENTIAL_ENCRYPTION_KEY'] = secret
                return True
        except Exception:
            pass

    # Try AWS Secrets Manager
    aws_secret_name = os.environ.get('AWS_SECRETS_MANAGER_SECRET')
    aws_region = os.environ.get('AWS_REGION')
    if _HAS_BOTO3 and aws_secret_name:
        try:
            import boto3
            session = boto3.session.Session()
            client = session.client(service_name='secretsmanager', region_name=aws_region)
            resp = client.get_secret_value(SecretId=aws_secret_name)
            secret_str = resp.get('SecretString')
            if secret_str:
                try:
                    s = json.loads(secret_str)
                    secret = s.get('CREDENTIAL_ENCRYPTION_KEY') or s.get('fernet_key') or s.get('key')
                except Exception:
                    secret = secret_str
                if secret:
                    os.environ['CREDENTIAL_ENCRYPTION_KEY'] = secret
                    return True
        except Exception:
            pass

    return False


def encrypt_credentials(credentials: Dict[str, Any]) -> str:
    """Encrypt credential dict to hex string."""
    cipher = _get_cipher()
    plaintext = json.dumps(credentials).encode('utf-8')
    ciphertext = cipher.encrypt(plaintext)
    return ciphertext.hex()


def decrypt_credentials(encrypted_hex: str) -> Dict[str, Any]:
    """Decrypt hex-encoded credentials back to dict."""
    try:
        cipher = _get_cipher()
        ciphertext = bytes.fromhex(encrypted_hex)
        plaintext = cipher.decrypt(ciphertext)
        return json.loads(plaintext.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Failed to decrypt credentials: {e}")


def mask_sensitive_data(data: Dict[str, Any], sensitive_keys=None) -> Dict[str, Any]:
    """Mask sensitive fields (keys, tokens) in a dict for logging."""
    if sensitive_keys is None:
        sensitive_keys = {'api_key', 'api_token', 'secret', 'password', 'auth_token', 'bearer_token'}
    
    masked = data.copy()
    for key in sensitive_keys:
        if key in masked and masked[key]:
            value = str(masked[key])
            if len(value) > 4:
                masked[key] = f"{value[:2]}...{value[-2:]}"
            else:
                masked[key] = "****"
    return masked
