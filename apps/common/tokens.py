import hashlib
import secrets


def make_token():
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_token(raw):
    return hashlib.sha256(raw.encode()).hexdigest()
