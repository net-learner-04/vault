import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# Per-user Data Encryption Key size: first 32 bytes = AES-256 key,
# last 32 bytes = HMAC key (reserved for future integrity checks).
DEK_SIZE = 64
PBKDF2_ITERATIONS = 200_000
READ_CHUNK = 1024 * 1024


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def b64d(data: str) -> bytes:
    return base64.b64decode(data)


def generate_dek() -> bytes:
    """Return a fresh per-user data encryption key."""
    return os.urandom(DEK_SIZE)


def new_file_iv() -> bytes:
    """Return a random 16-byte IV for a single file."""
    return os.urandom(16)


def derive_kek(password: str, salt_b64: str) -> bytes:
    """Derive a 32-byte key encryption key from a user password."""
    salt = b64d(salt_b64)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def wrap_dek(dek: bytes, password: str) -> dict:
    """Encrypt a DEK with a key derived from the user password.

    The wrapped DEK stored in the database is useless without the password,
    which is why even an administrator reading the DB cannot decrypt a
    user's files.
    """
    salt = os.urandom(16)
    kek = derive_kek(password, b64e(salt))
    iv = os.urandom(16)
    encryptor = Cipher(algorithms.AES(kek), modes.GCM(iv)).encryptor()
    wrapped = encryptor.update(dek) + encryptor.finalize()
    return {
        "dek_wrapped": b64e(wrapped),
        "dek_nonce": b64e(iv),
        "dek_tag": b64e(encryptor.tag),
        "kek_salt": b64e(salt),
    }


def unwrap_dek(user, password: str) -> bytes:
    """Recover the DEK for a user using their plaintext password."""
    kek = derive_kek(password, user.kek_salt)
    decryptor = Cipher(
        algorithms.AES(kek),
        modes.GCM(b64d(user.dek_nonce), b64d(user.dek_tag)),
    ).decryptor()
    return decryptor.update(b64d(user.dek_wrapped)) + decryptor.finalize()


def wrap_with_key(dek: bytes, key: bytes) -> dict:
    """Encrypt a DEK with an already-derived 32-byte key."""
    iv = os.urandom(16)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(iv)).encryptor()
    wrapped = encryptor.update(dek) + encryptor.finalize()
    return {
        "dek_wrapped": b64e(wrapped),
        "dek_nonce": b64e(iv),
        "dek_tag": b64e(encryptor.tag),
    }


def unwrap_with_key(wrapped_b64: str, nonce_b64: str, tag_b64: str, key: bytes) -> bytes:
    """Recover a DEK wrapped with wrap_with_key()."""
    decryptor = Cipher(
        algorithms.AES(key),
        modes.GCM(b64d(nonce_b64), b64d(tag_b64)),
    ).decryptor()
    return decryptor.update(b64d(wrapped_b64)) + decryptor.finalize()


def key_from_token(token: str) -> bytes:
    """Derive a 32-byte key from a share token."""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).digest()


def recovery_key_from_secret(secret: str) -> bytes:
    """Derive a stable 32-byte admin recovery key from a server secret."""
    import hashlib
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_stream(in_file, out_file, dek: bytes, iv: bytes) -> int:
    """Stream-encrypt in_file into out_file using AES-256-CTR.

    Returns the number of plaintext bytes written. CTR has no padding, so the
    ciphertext on disk is exactly the same size as the plaintext.
    """
    cipher = Cipher(algorithms.AES(dek[:32]), modes.CTR(iv))
    encryptor = cipher.encryptor()
    size = 0
    while True:
        chunk = in_file.read(READ_CHUNK)
        if not chunk:
            break
        out_file.write(encryptor.update(chunk))
        size += len(chunk)
    out_file.write(encryptor.finalize())
    return size


def iter_decrypted(file_path: str, dek: bytes, iv_b64: str, offset: int = 0):
    """Yield decrypted chunks starting at a byte offset.

    AES-CTR supports random access, which lets us serve HTTP range requests
    (used by the video preview) without decrypting the whole file.
    """
    iv = b64d(iv_b64)
    block = offset // 16
    skip = offset % 16
    counter = int.from_bytes(iv, "big") + block
    start_iv = counter.to_bytes(16, "big")

    cipher = Cipher(algorithms.AES(dek[:32]), modes.CTR(start_iv))
    decryptor = cipher.decryptor()

    with open(file_path, "rb") as f:
        f.seek(block * 16)
        first = True
        while True:
            chunk = f.read(READ_CHUNK)
            if not chunk:
                break
            plain = decryptor.update(chunk)
            if first:
                if skip:
                    plain = plain[skip:]
                first = False
            if plain:
                yield plain
