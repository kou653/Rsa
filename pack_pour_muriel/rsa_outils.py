from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
import os


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


# --- Chiffrement Hybride RSA + AES-256-GCM pour Fichiers & Photos de toute taille ---

def chiffrer_fichier(donnees_octets, publique_destinataire):
    """
    1. Génère une clé symétrique AES-256 éphémère (32 octets) et un nonce (12 octets).
    2. Chiffre le fichier avec AESGCM (ultra-rapide, sans limite de taille, intégrité garantie).
    3. Chiffre la clé AES avec la clé publique RSA du destinataire (RSA-2048 OAEP).
    Retourne un dict avec la clé chiffrée, le nonce et le payload chiffré en Base64.
    """
    cle_aes = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(cle_aes)
    nonce = os.urandom(12)

    fichier_chiffre = aesgcm.encrypt(nonce, donnees_octets, None)

    # Chiffrement de la clé AES avec RSA
    cle_aes_chiffree = publique_destinataire.encrypt(cle_aes, PAD)

    return {
        "cle_aes_chiffree": base64.b64encode(cle_aes_chiffree).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "donnees_chiffrees": base64.b64encode(fichier_chiffre).decode()
    }


def dechiffrer_fichier(cle_aes_chiffree_b64, nonce_b64, donnees_chiffrees_b64, privee_destinataire):
    """
    1. Déchiffre la clé AES avec la clé privée RSA (RSA-2048 OAEP).
    2. Déchiffre le fichier avec AESGCM.
    Retourne les octets d'origine déchiffrés.
    """
    cle_aes_chiffree = base64.b64decode(cle_aes_chiffree_b64)
    nonce = base64.b64decode(nonce_b64)
    donnees_chiffrees = base64.b64decode(donnees_chiffrees_b64)

    # Récupération de la clé AES avec RSA
    cle_aes = privee_destinataire.decrypt(cle_aes_chiffree, PAD)

    # Déchiffrement AES
    aesgcm = AESGCM(cle_aes)
    return aesgcm.decrypt(nonce, donnees_chiffrees, None)
