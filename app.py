import os
import json
import time
import requests
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import rsa_outils

app = Flask(__name__)
app.config['SECRET_KEY'] = 'roxane-rsa-secret-key-2026'
socketio = SocketIO(app, cors_allowed_origins="*")

MAX_OCTETS = 190  # Limite RSA 2048 avec padding OAEP / SHA-256
HEADERS = {"ngrok-skip-browser-warning": "1"}

# Configuration par défaut
CONFIG_FICHIER = "config_roxane.json"

def charger_configuration():
    config = {
        "serveur_muriel_url": "https://abcd-1234.ngrok-free.dev",
        "chemin_cle_muriel": "muriel_publique.pem"
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

# Vérifier et générer les clés de Roxane si besoin
if not (os.path.exists("roxane_privee.pem") and os.path.exists("roxane_publique.pem")):
    priv, pub = rsa_outils.generer_cles()
    rsa_outils.sauver_cles(priv, "roxane")

# Historique des messages locaux de Roxane (session)
# Chaque item: { id, auteur, destinataire, message_clair, message_chiffre, timestamp, statut, type }
# auteur: 'Roxane' (envoyé) ou 'Muriel' (reçu)
messages_historique = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.get_json() or {}
        config = charger_configuration()
        if "serveur_muriel_url" in data:
            config["serveur_muriel_url"] = data["serveur_muriel_url"].strip().rstrip("/")
        if "chemin_cle_muriel" in data:
            config["chemin_cle_muriel"] = data["chemin_cle_muriel"].strip()
        sauver_configuration(config)
        return jsonify({"status": "ok", "config": config})
    else:
        config = charger_configuration()
        cle_chargee = os.path.exists(config.get("chemin_cle_muriel", "muriel_publique.pem"))
        return jsonify({
            "config": config,
            "cle_muriel_presente": cle_chargee
        })

@app.route('/api/cle-roxane', methods=['GET'])
def api_cle_roxane():
    """Fournit la clé publique de Roxane au format texte pour la transmettre à Muriel."""
    cle_pub = ""
    if os.path.exists("roxane_publique.pem"):
        with open("roxane_publique.pem", "r", encoding="utf-8") as f:
            cle_pub = f.read()
    return jsonify({"cle_publique": cle_pub})

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Retourne l'historique des échanges."""
    return jsonify({"messages": messages_historique})

@app.route('/api/upload-cle-muriel', methods=['POST'])
def upload_cle_muriel():
    """Permet de charger ou mettre à jour la clé publique de Muriel depuis l'interface."""
    contenu = ""
    if 'fichier' in request.files:
        f = request.files['fichier']
        contenu = f.read().decode('utf-8')
    else:
        data = request.get_json(silent=True) or {}
        contenu = data.get("cle", "")

    if not contenu:
        return jsonify({"erreur": "Aucun contenu de clé fourni"}), 400

    chemin = "muriel_publique.pem"
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)

    config = charger_configuration()
    config["chemin_cle_muriel"] = chemin
    sauver_configuration(config)

    return jsonify({"status": "ok", "message": "Clé publique de Muriel enregistrée avec succès."})

# Endpoint pour recevoir un message chiffré provenant de la machine de Muriel
@app.route('/recevoir', methods=['POST'])
@app.route('/envoyer/roxane', methods=['POST'])
def recevoir_de_muriel():
    """
    Endpoint HTTP que la machine distante de Muriel appelle pour déposer un message chiffré à destination de Roxane.
    """
    data = request.get_json(silent=True) or {}
    message_chiffre = data.get("message", "")
    if not message_chiffre:
        return jsonify({"erreur": "Paramètre 'message' manquant"}), 400

    try:
        # Roxane déchiffre avec sa propre clé privée
        roxane_privee = rsa_outils.charger_privee("roxane_privee.pem")
        clair = rsa_outils.dechiffrer(message_chiffre, roxane_privee)
        succes = True
    except Exception as e:
        clair = f"[Erreur de déchiffrement avec la clé privée de Roxane : {e}]"
        succes = False

    msg_obj = {
        "id": len(messages_historique) + 1,
        "auteur": "Muriel",
        "destinataire": "Roxane",
        "message_clair": clair,
        "message_chiffre": message_chiffre,
        "timestamp": time.strftime("%H:%M:%S"),
        "statut": "reçu" if succes else "erreur",
        "direction": "entrant"
    }
    messages_historique.append(msg_obj)
    socketio.emit('nouveau_message', msg_obj)

    return jsonify({"status": "ok", "recu": True, "dechiffre": succes})

@socketio.on('envoyer_a_muriel')
def handle_envoyer_a_muriel(data):
    """
    Roxane saisit un message -> chiffré avec la clé publique de Muriel
    -> envoyé en HTTP POST vers la machine distante de Muriel.
    """
    texte = (data.get("texte") or "").strip()
    if not texte:
        emit('erreur', {"message": "Le message ne peut pas être vide."})
        return

    octets_count = len(texte.encode('utf-8'))
    if octets_count > MAX_OCTETS:
        emit('erreur', {"message": f"Message trop long ({octets_count} octets). Limite RSA 2048: {MAX_OCTETS} octets."})
        return

    config = charger_configuration()
    chemin_cle_muriel = config.get("chemin_cle_muriel", "muriel_publique.pem")
    url_serveur = config.get("serveur_muriel_url", "").strip().rstrip("/")

    # Vérification présence de la clé publique de Muriel
    if not os.path.exists(chemin_cle_muriel):
        emit('erreur', {"message": f"Fichier de clé publique de Muriel introuvable ({chemin_cle_muriel}). Veuillez l'importer dans la configuration."})
        return

    # Vérification URL
    if not url_serveur or "abcd-1234" in url_serveur:
        emit('erreur', {"message": "L'adresse du serveur de Muriel n'est pas configurée (remplacez l'adresse d'exemple dans Configuration)."})
        return

    if not url_serveur.startswith(("http://", "https://")):
        emit('erreur', {"message": "L'adresse du serveur distant de Muriel doit débuter par http:// ou https://"})
        return

    # 1. Chiffrement avec la clé publique de Muriel
    try:
        muriel_pub = rsa_outils.charger_publique(chemin_cle_muriel)
        chiffre_b64 = rsa_outils.chiffrer(texte, muriel_pub)
    except Exception as e:
        emit('erreur', {"message": f"Erreur lors du chiffrement RSA : {str(e)}"})
        return

    # 2. Transmission réseau vers la machine distante de Muriel
    cible_url = url_serveur + "/envoyer/muriel"
    statut_envoi = "envoyé"
    erreur_transmission = None

    try:
        rep = requests.post(
            cible_url,
            json={"message": chiffre_b64},
            headers=HEADERS,
            timeout=10
        )
        rep.raise_for_status()
    except requests.exceptions.RequestException as e:
        statut_envoi = "echec_reseau"
        erreur_transmission = str(e)

    # 3. Sauvegarde dans l'historique local de Roxane
    msg_obj = {
        "id": len(messages_historique) + 1,
        "auteur": "Roxane",
        "destinataire": "Muriel",
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
        emit('avertissement', {"message": f"Message chiffré mais non transmis à Muriel : {erreur_transmission}"})

@socketio.on('reinitialiser_chat')
def handle_reinitialiser():
    messages_historique.clear()
    emit('historique_vide')

if __name__ == '__main__':
    print("===============================================================")
    print("  Plateforme Web Anonyme RSA - Poste de ROXANE")
    print("  Application disponible sur : http://127.0.0.1:5000")
    print("===============================================================")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
