import os
import json
import time
import base64
import requests
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import rsa_outils

app = Flask(__name__)
app.config['SECRET_KEY'] = 'muriel-rsa-secret-key-2026'
socketio = SocketIO(app, cors_allowed_origins="*")

MAX_OCTETS = 190  # Limite RSA 2048 avec padding OAEP / SHA-256
HEADERS = {"ngrok-skip-browser-warning": "1"}

CONFIG_FICHIER = "config_muriel.json"

def charger_configuration():
    config = {
        "serveur_roxane_url": "https://abcd-1234.ngrok-free.dev",
        "chemin_cle_roxane": "roxane_publique.pem"
    }
    if os.path.exists(CONFIG_FICHIER):
        try:
            with open(CONFIG_FICHIER, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception:
            pass
    return config

def sauver_configuration(config):
    with open(CONFIG_FICHIER, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

if not (os.path.exists("muriel_privee.pem") and os.path.exists("muriel_publique.pem")):
    priv, pub = rsa_outils.generer_cles()
    rsa_outils.sauver_cles(priv, "muriel")

messages_historique = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.get_json() or {}
        config = charger_configuration()
        if "serveur_roxane_url" in data:
            config["serveur_roxane_url"] = data["serveur_roxane_url"].strip().rstrip("/")
        if "chemin_cle_roxane" in data:
            config["chemin_cle_roxane"] = data["chemin_cle_roxane"].strip()
        sauver_configuration(config)
        return jsonify({"status": "ok", "config": config})
    else:
        config = charger_configuration()
        cle_chargee = os.path.exists(config.get("chemin_cle_roxane", "roxane_publique.pem"))
        return jsonify({
            "config": config,
            "cle_roxane_presente": cle_chargee
        })

@app.route('/api/cle-muriel', methods=['GET'])
def api_cle_muriel():
    cle_pub = ""
    if os.path.exists("muriel_publique.pem"):
        with open("muriel_publique.pem", "r", encoding="utf-8") as f:
            cle_pub = f.read()
    return jsonify({"cle_publique": cle_pub})

@app.route('/api/messages', methods=['GET'])
def get_messages():
    return jsonify({"messages": messages_historique})

@app.route('/api/upload-cle-roxane', methods=['POST'])
def upload_cle_roxane():
    data = request.get_json(silent=True) or {}
    contenu = data.get("cle", "").strip()

    if not contenu:
        return jsonify({"erreur": "Aucun contenu de clé fourni"}), 400

    chemin = "roxane_publique.pem"
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)

    config = charger_configuration()
    config["chemin_cle_roxane"] = chemin
    sauver_configuration(config)

    return jsonify({"status": "ok", "message": "Clé publique de Roxane enregistrée avec succès."})

@app.route('/recevoir', methods=['POST'])
@app.route('/envoyer/muriel', methods=['POST'])
def recevoir_de_roxane():
    data = request.get_json(silent=True) or {}
    type_msg = data.get("type", "texte")

    if type_msg == "fichier":
        nom_fichier = data.get("nom_fichier", "fichier_recu")
        type_mime = data.get("type_mime", "application/octet-stream")
        cle_aes_chiffree = data.get("cle_aes_chiffree", "")
        nonce = data.get("nonce", "")
        donnees_chiffrees = data.get("donnees_chiffrees", "")

        if not (cle_aes_chiffree and nonce and donnees_chiffrees):
            return jsonify({"erreur": "Charge chiffrée de fichier incomplète"}), 400

        try:
            muriel_privee = rsa_outils.charger_privee("muriel_privee.pem")
            fichier_bytes = rsa_outils.dechiffrer_fichier(cle_aes_chiffree, nonce, donnees_chiffrees, muriel_privee)
            data_url = f"data:{type_mime};base64,{base64.b64encode(fichier_bytes).decode()}"
            succes = True
            erreur_desc = None
        except Exception as e:
            import traceback
            traceback.print_exc()
            succes = False
            data_url = ""
            erreur_desc = str(e)

        msg_obj = {
            "id": len(messages_historique) + 1,
            "auteur": "Roxane",
            "destinataire": "Muriel",
            "type": "fichier",
            "nom_fichier": nom_fichier,
            "type_mime": type_mime,
            "taille": len(base64.b64decode(donnees_chiffrees)) if donnees_chiffrees else 0,
            "data_url": data_url,
            "message_chiffre": f"[Clé AES chiffrée RSA-2048]: {cle_aes_chiffree[:40]}... (Payload AES-256-GCM)",
            "timestamp": time.strftime("%H:%M:%S"),
            "statut": "reçu" if succes else "erreur",
            "erreur": erreur_desc,
            "direction": "entrant"
        }
        messages_historique.append(msg_obj)
        socketio.emit('nouveau_message', msg_obj)
        return jsonify({"status": "ok", "recu": True, "dechiffre": succes})

    else:
        message_chiffre = data.get("message", "")
        if not message_chiffre:
            return jsonify({"erreur": "Paramètre 'message' manquant"}), 400

        try:
            muriel_privee = rsa_outils.charger_privee("muriel_privee.pem")
            clair = rsa_outils.dechiffrer(message_chiffre, muriel_privee)
            succes = True
        except Exception as e:
            clair = f"[Erreur de déchiffrement avec la clé privée de Muriel : {e}]"
            succes = False

        msg_obj = {
            "id": len(messages_historique) + 1,
            "auteur": "Roxane",
            "destinataire": "Muriel",
            "type": "texte",
            "message_clair": clair,
            "message_chiffre": message_chiffre,
            "timestamp": time.strftime("%H:%M:%S"),
            "statut": "reçu" if succes else "erreur",
            "direction": "entrant"
        }
        messages_historique.append(msg_obj)
        socketio.emit('nouveau_message', msg_obj)
        return jsonify({"status": "ok", "recu": True, "dechiffre": succes})

@socketio.on('envoyer_a_roxane')
def handle_envoyer_a_roxane(data):
    texte = (data.get("texte") or "").strip()
    if not texte:
        emit('erreur', {"message": "Le message ne peut pas être vide."})
        return

    octets_count = len(texte.encode('utf-8'))
    if octets_count > MAX_OCTETS:
        emit('erreur', {"message": f"Message trop long ({octets_count} octets). Limite texte direct: {MAX_OCTETS} octets."})
        return

    config = charger_configuration()
    chemin_cle_roxane = config.get("chemin_cle_roxane", "roxane_publique.pem")
    url_serveur = config.get("serveur_roxane_url", "").strip().rstrip("/")

    if not os.path.exists(chemin_cle_roxane):
        emit('erreur', {"message": "Clé publique de Roxane introuvable. Veuillez l'importer dans Configuration."})
        return

    if not url_serveur or "abcd-1234" in url_serveur or not url_serveur.startswith(("http://", "https://")):
        emit('erreur', {"message": "Adresse du serveur de Roxane non configurée ou invalide."})
        return

    try:
        roxane_pub = rsa_outils.charger_publique(chemin_cle_roxane)
        chiffre_b64 = rsa_outils.chiffrer(texte, roxane_pub)
    except Exception as e:
        emit('erreur', {"message": f"Erreur lors du chiffrement RSA : {str(e)}"})
        return

    cible_url = url_serveur + "/recevoir"
    statut_envoi = "envoyé"
    erreur_transmission = None

    try:
        rep = requests.post(
            cible_url,
            json={"type": "texte", "message": chiffre_b64},
            headers=HEADERS,
            timeout=10
        )
        rep.raise_for_status()
    except requests.exceptions.RequestException as e:
        statut_envoi = "echec_reseau"
        erreur_transmission = str(e)

    msg_obj = {
        "id": len(messages_historique) + 1,
        "auteur": "Muriel",
        "destinataire": "Roxane",
        "type": "texte",
        "message_clair": texte,
        "message_chiffre": chiffre_b64,
        "timestamp": time.strftime("%H:%M:%S"),
        "statut": statut_envoi,
        "erreur": erreur_transmission,
        "direction": "sortant"
    }
    messages_historique.append(msg_obj)
    emit('nouveau_message', msg_obj)

    if erreur_transmission:
        emit('avertissement', {"message": f"Message chiffré mais non transmis à Roxane : {erreur_transmission}"})

@socketio.on('envoyer_fichier_a_roxane')
def handle_envoyer_fichier_a_roxane(data):
    nom_fichier = data.get("nom_fichier", "fichier")
    type_mime = data.get("type_mime", "application/octet-stream")
    contenu_b64 = data.get("contenu_b64", "")

    if not contenu_b64:
        emit('erreur', {"message": "Fichier vide ou corrompu."})
        return

    try:
        fichier_bytes = base64.b64decode(contenu_b64)
    except Exception as e:
        emit('erreur', {"message": f"Erreur de lecture du fichier : {e}"})
        return

    config = charger_configuration()
    chemin_cle_roxane = config.get("chemin_cle_roxane", "roxane_publique.pem")
    url_serveur = config.get("serveur_roxane_url", "").strip().rstrip("/")

    if not os.path.exists(chemin_cle_roxane):
        emit('erreur', {"message": "Clé publique de Roxane introuvable. Veuillez l'importer dans Configuration."})
        return

    if not url_serveur or "abcd-1234" in url_serveur or not url_serveur.startswith(("http://", "https://")):
        emit('erreur', {"message": "Adresse du serveur de Roxane non configurée ou invalide."})
        return

    try:
        roxane_pub = rsa_outils.charger_publique(chemin_cle_roxane)
        paquet_chiffre = rsa_outils.chiffrer_fichier(fichier_bytes, roxane_pub)
    except Exception as e:
        emit('erreur', {"message": f"Erreur lors du chiffrement hybride du fichier : {e}"})
        return

    payload = {
        "type": "fichier",
        "nom_fichier": nom_fichier,
        "type_mime": type_mime,
        "cle_aes_chiffree": paquet_chiffre["cle_aes_chiffree"],
        "nonce": paquet_chiffre["nonce"],
        "donnees_chiffrees": paquet_chiffre["donnees_chiffrees"]
    }

    cible_url = url_serveur + "/recevoir"
    statut_envoi = "envoyé"
    erreur_transmission = None

    try:
        rep = requests.post(
            cible_url,
            json=payload,
            headers=HEADERS,
            timeout=25
        )
        rep.raise_for_status()
    except requests.exceptions.RequestException as e:
        statut_envoi = "echec_reseau"
        erreur_transmission = str(e)

    data_url = f"data:{type_mime};base64,{contenu_b64}"
    msg_obj = {
        "id": len(messages_historique) + 1,
        "auteur": "Muriel",
        "destinataire": "Roxane",
        "type": "fichier",
        "nom_fichier": nom_fichier,
        "type_mime": type_mime,
        "taille": len(fichier_bytes),
        "data_url": data_url,
        "message_chiffre": f"[Clé AES chiffrée RSA-2048]: {paquet_chiffre['cle_aes_chiffree'][:40]}... (Payload AES-256-GCM)",
        "timestamp": time.strftime("%H:%M:%S"),
        "statut": statut_envoi,
        "erreur": erreur_transmission,
        "direction": "sortant"
    }
    messages_historique.append(msg_obj)
    emit('nouveau_message', msg_obj)

    if erreur_transmission:
        emit('avertissement', {"message": f"Fichier chiffré mais non transmis à Roxane : {erreur_transmission}"})

@socketio.on('reinitialiser_chat')
def handle_reinitialiser():
    messages_historique.clear()
    emit('historique_vide')

if __name__ == '__main__':
    print("===============================================================")
    print("  Plateforme Web Anonyme RSA + Fichiers - Poste de MURIEL")
    print("  Application disponible sur : http://127.0.0.1:5000")
    print("===============================================================")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
