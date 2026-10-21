from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
import base64


def generer_cles():
    privee = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return privee, privee.public_key()


def sauver_cles(privee, nom):
    with open(f"{nom}_privee.pem", "wb") as f:
        f.write(privee.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    with open(f"{nom}_publique.pem", "wb") as f:
        f.write(privee.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo))


def charger_privee(chemin):
    with open(chemin, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def charger_publique(chemin):
    with open(chemin, "rb") as f:
        return serialization.load_pem_public_key(f.read())


PAD = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                   algorithm=hashes.SHA256(), label=None)


def chiffrer(message, publique):
    return base64.b64encode(publique.encrypt(message.encode(), PAD)).decode()


def dechiffrer(texte_b64, privee):
    return privee.decrypt(base64.b64decode(texte_b64), PAD).decode()
