"""Общий мастер-ключ администратора (один на всё приложение) — используется
и для личных данных сотрудников (personal_data.py), и для документов
авторов (document_vault.py). Вынесено в отдельный модуль, чтобы не
дублировать одну и ту же пару ключей в двух местах.

Схема (envelope encryption с асимметричным ключом): у администратора есть
пара RSA-ключей. Секретный ключ зашифрован его собственным паролем и
больше нигде не хранится в открытом виде. Публичный ключ хранится
открыто — им можно «запечатать» (зашифровать) секретный ключ доступа к
любой записи без пароля администратора, а «распечатать» может только тот,
кто знает пароль администратора.
"""
import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import storage

ADMIN_KEY_FILE = os.path.join(storage.DATA_DIR, "admin_master_key.json")
PBKDF2_ITERATIONS = 390_000


def _derive_key(password, salt_b64):
    salt = base64.b64decode(salt_b64)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    key = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def has_master_key():
    return os.path.exists(ADMIN_KEY_FILE)


def setup_master_key(admin_password):
    if has_master_key():
        raise ValueError("Мастер-ключ администратора уже настроен")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    salt_b64 = base64.b64encode(os.urandom(16)).decode("ascii")
    key = _derive_key(admin_password, salt_b64)
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    encrypted_priv = Fernet(key).encrypt(priv_bytes).decode("ascii")
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    os.makedirs(storage.DATA_DIR, exist_ok=True)
    with open(ADMIN_KEY_FILE, "w", encoding="utf-8") as f:
        json.dump({"salt": salt_b64, "encrypted_private_key": encrypted_priv, "public_key_pem": pub_bytes}, f)


def get_public_key():
    if not has_master_key():
        return None
    with open(ADMIN_KEY_FILE, "r", encoding="utf-8") as f:
        record = json.load(f)
    return serialization.load_pem_public_key(record["public_key_pem"].encode("ascii"))


def unlock_private_key(admin_password):
    """Возвращает секретный ключ администратора или None при неверном пароле."""
    if not has_master_key():
        return None
    with open(ADMIN_KEY_FILE, "r", encoding="utf-8") as f:
        record = json.load(f)
    key = _derive_key(admin_password, record["salt"])
    try:
        priv_bytes = Fernet(key).decrypt(record["encrypted_private_key"].encode("ascii"))
    except InvalidToken:
        return None
    return serialization.load_pem_private_key(priv_bytes, password=None)


def rsa_wrap(dek_bytes, public_key):
    ciphertext = public_key.encrypt(
        dek_bytes,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def rsa_unwrap(wrapped_b64, private_key):
    ciphertext = base64.b64decode(wrapped_b64)
    return private_key.decrypt(
        ciphertext,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
