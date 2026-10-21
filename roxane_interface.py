import os
import tkinter as tk
from tkinter import filedialog, scrolledtext

import requests
from rsa_outils import charger_publique, chiffrer

HEADERS = {"ngrok-skip-browser-warning": "1"}
MAX_OCTETS = 190  # limite RSA 2048 avec OAEP/SHA-256

racine = tk.Tk()
racine.title("Roxane - Messagerie chiffrée")
racine.geometry("520x430")

# --- Zone 1 : clé publique de Muriel ---
cadre_cle = tk.LabelFrame(racine, text="1. Clé publique de Muriel", padx=8, pady=8)
cadre_cle.pack(fill="x", padx=10, pady=8)
chemin_cle = tk.StringVar(value="muriel_publique.pem" if os.path.exists("muriel_publique.pem") else "")
tk.Entry(cadre_cle, textvariable=chemin_cle).pack(side="left", fill="x", expand=True)


def parcourir():
    f = filedialog.askopenfilename(filetypes=[("Clé PEM", "*.pem")])
    if f:
        chemin_cle.set(f)


tk.Button(cadre_cle, text="Parcourir...", command=parcourir).pack(side="left", padx=5)

# --- Zone 2 : serveur ---
cadre_serv = tk.LabelFrame(racine, text="2. Adresse du serveur (donnée par Muriel)", padx=8, pady=8)
cadre_serv.pack(fill="x", padx=10, pady=4)
champ_url = tk.Entry(cadre_serv)
champ_url.insert(0, "https://abcd-1234.ngrok-free.dev")
champ_url.pack(fill="x")

# --- Zone 3 : message ---
cadre_msg = tk.LabelFrame(racine, text="3. Mon message", padx=8, pady=8)
cadre_msg.pack(fill="both", expand=True, padx=10, pady=8)
zone = scrolledtext.ScrolledText(cadre_msg, height=6)
zone.pack(fill="both", expand=True)
statut = tk.Label(racine, text="", anchor="w")
statut.pack(fill="x", padx=10)


def envoyer():
    texte = zone.get("1.0", "end").strip()
    if not texte:
        statut.config(text="Écris un message d'abord.", fg="red")
        return
    if len(texte.encode()) > MAX_OCTETS:
        statut.config(text=f"Message trop long (max {MAX_OCTETS} octets).", fg="red")
        return
    if not os.path.exists(chemin_cle.get()):
        statut.config(text="Clé publique de Muriel introuvable.", fg="red")
        return

    adresse = champ_url.get().strip().rstrip("/")
    if "abcd-1234" in adresse:
        statut.config(text="Remplace l'adresse d'exemple par celle donnée par Muriel.", fg="red")
        return
    if not adresse.startswith(("http://", "https://")):
        statut.config(text="L'adresse doit commencer par https:// (ou http://).", fg="red")
        return

    try:
        msg = chiffrer(texte, charger_publique(chemin_cle.get()))
        url = adresse + "/envoyer/muriel"
        rep = requests.post(url, json={"message": msg}, headers=HEADERS, timeout=10)
        rep.raise_for_status()
        statut.config(text="Message chiffré et envoyé ✔", fg="green")
        zone.delete("1.0", "end")
    except Exception as e:
        statut.config(text=f"Erreur : {e}", fg="red")


tk.Button(racine, text="Chiffrer et envoyer", command=envoyer).pack(pady=8)
racine.mainloop()