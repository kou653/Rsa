// Client WebSocket
const socket = io();

const MAX_OCTETS = 190;
let afficherChiffre = false;
let configActuelle = {};

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    chargerConfiguration();
    chargerCleRoxane();
    chargerHistoriqueMessages();
});

// Navigation entre les onglets
function changerOnglet(onglet) {
    document.querySelectorAll('.page-section').forEach(sec => sec.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));

    const section = document.getElementById(`section-${onglet}`);
    const bouton = document.getElementById(`btn-tab-${onglet}`);

    if (section) section.classList.add('active');
    if (bouton) bouton.classList.add('active');

    if (onglet === 'chat') {
        const unread = document.getElementById('unread-count');
        unread.style.display = 'none';
        unread.innerText = '0';
        faireDefilerVersLeBas();
    }
}

// 1. Gestion de la Configuration Distante
async function chargerConfiguration() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        configActuelle = data.config || {};

        const inputUrl = document.getElementById('cfg-server-url');
        if (inputUrl) inputUrl.value = configActuelle.serveur_muriel_url || '';

        const badgeUrl = document.getElementById('sidebar-server-url');
        const subInfo = document.getElementById('chat-subinfo-target');
        const targetUrl = configActuelle.serveur_muriel_url || 'Non configuré';
        
        if (badgeUrl) badgeUrl.innerText = targetUrl;
        if (subInfo) subInfo.innerText = `Serveur Muriel : ${targetUrl}`;

        const badgeCle = document.getElementById('cfg-cle-status');
        const sideKey = document.getElementById('sidebar-key-status');

        if (data.cle_muriel_presente) {
            if (badgeCle) {
                badgeCle.innerHTML = '<i class="fa-solid fa-check"></i> Clé publique de Muriel prête (muriel_publique.pem)';
                badgeCle.style.color = '#34d399';
            }
            if (sideKey) {
                sideKey.innerText = 'muriel_publique.pem ✔';
                sideKey.style.color = '#34d399';
            }
        } else {
            if (badgeCle) {
                badgeCle.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Clé de Muriel absente';
                badgeCle.style.color = '#f87171';
            }
            if (sideKey) {
                sideKey.innerText = 'Non chargée ❌';
                sideKey.style.color = '#f87171';
            }
        }
    } catch (e) {
        console.error("Erreur config:", e);
    }
}

async function enregistrerConfig() {
    const url = document.getElementById('cfg-server-url').value.trim();
    const cleText = document.getElementById('cfg-cle-text').value.trim();
    const msgLabel = document.getElementById('config-save-msg');

    msgLabel.innerText = "Enregistrement en cours...";
    msgLabel.style.color = "#94a3b8";

    try {
        // Sauvegarder l'URL
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ serveur_muriel_url: url })
        });

        // Si une clé texte a été fournie, la sauvegarder
        if (cleText) {
            await fetch('/api/upload-cle-muriel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cle: cleText })
            });
            document.getElementById('cfg-cle-text').value = '';
        }

        msgLabel.innerText = "Paramètres mis à jour ✔";
        msgLabel.style.color = "#34d399";
        await chargerConfiguration();

        setTimeout(() => { msgLabel.innerText = ""; }, 3000);
    } catch (e) {
        msgLabel.innerText = "Erreur lors de la sauvegarde";
        msgLabel.style.color = "#f87171";
    }
}

// 2. Clé publique de Roxane
async function chargerCleRoxane() {
    try {
        const res = await fetch('/api/cle-roxane');
        const data = await res.json();
        document.getElementById('key-roxane-display').innerText = data.cle_publique || "Non générée";
    } catch (e) {
        console.error("Erreur chargement clé Roxane:", e);
    }
}

function copierCleRoxane() {
    const text = document.getElementById('key-roxane-display').innerText;
    navigator.clipboard.writeText(text).then(() => {
        alert("Votre clé publique a été copiée dans le presse-papier ! Vous pouvez l'envoyer à Muriel.");
    });
}

// 3. Messages & Chiffrement
function actualiserCompteurOctets(valeur) {
    const encoder = new TextEncoder();
    const octets = encoder.encode(valeur).length;
    const counter = document.getElementById('byte-counter');
    const alertBox = document.getElementById('composer-alert');

    counter.innerText = `${octets} / ${MAX_OCTETS} octets`;

    if (octets > MAX_OCTETS) {
        counter.style.color = '#f87171';
        alertBox.innerText = `Attention : message trop volumineux (${octets} octets > ${MAX_OCTETS} octets).`;
    } else {
        counter.style.color = 'var(--text-muted)';
        alertBox.innerText = '';
    }
}

function handleKeyPress(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        envoyerMessage();
    }
}

function envoyerMessage() {
    const input = document.getElementById('message-input');
    const texte = input.value.trim();
    const alertBox = document.getElementById('composer-alert');

    if (!texte) return;

    const encoder = new TextEncoder();
    if (encoder.encode(texte).length > MAX_OCTETS) {
        alertBox.innerText = `Le message dépasse la taille maximale autorisée (${MAX_OCTETS} octets).`;
        return;
    }

    socket.emit('envoyer_a_muriel', { texte: texte });

    input.value = '';
    actualiserCompteurOctets('');
    alertBox.innerText = '';
}

// Réception du socket
socket.on('nouveau_message', (msg) => {
    ajouterMessageAuDOM(msg);
    faireDefilerVersLeBas();

    const chatTab = document.getElementById('section-chat');
    if (!chatTab.classList.contains('active')) {
        const unread = document.getElementById('unread-count');
        const count = parseInt(unread.innerText || '0') + 1;
        unread.innerText = count;
        unread.style.display = 'inline-block';
    }
});

socket.on('erreur', (err) => {
    const alertBox = document.getElementById('composer-alert');
    alertBox.innerText = err.message || 'Erreur lors de l’envoi.';
});

socket.on('avertissement', (data) => {
    const alertBox = document.getElementById('composer-alert');
    alertBox.innerText = data.message || '';
});

socket.on('historique_vide', () => {
    const container = document.getElementById('chat-messages');
    container.innerHTML = `
        <div class="empty-state" id="empty-state">
            <div class="empty-icon"><i class="fa-solid fa-lock"></i></div>
            <h4>Aucun message dans cette session</h4>
            <p>Écrivez ci-dessous pour transmettre un message chiffré à la machine de Muriel.</p>
        </div>
    `;
});

function ajouterMessageAuDOM(msg) {
    const emptyState = document.getElementById('empty-state');
    if (emptyState) emptyState.remove();

    const container = document.getElementById('chat-messages');
    const isSent = (msg.auteur === 'Roxane');

    let badgeStatus = '';
    if (isSent) {
        if (msg.statut === 'envoyé') {
            badgeStatus = '<span class="message-status-badge status-ok"><i class="fa-solid fa-check"></i> Transmis</span>';
        } else {
            badgeStatus = '<span class="message-status-badge status-err" title="' + (msg.erreur || '') + '"><i class="fa-solid fa-circle-exclamation"></i> Échec réseau</span>';
        }
    }

    const messageRow = document.createElement('div');
    messageRow.className = `message-row ${isSent ? 'sent' : 'received'}`;

    messageRow.innerHTML = `
        <div class="message-meta">
            <strong>${msg.auteur}</strong> • <span>${msg.timestamp}</span> ${badgeStatus}
        </div>
        <div class="message-bubble">
            <div class="bubble-text">${echapperHtml(msg.message_clair)}</div>
            <div class="cipher-badge ${afficherChiffre ? 'visible' : ''}">
                <div class="cipher-tag"><i class="fa-solid fa-key"></i> RSA Base64 Chiffré :</div>
                <div>${msg.message_chiffre}</div>
            </div>
        </div>
    `;

    container.appendChild(messageRow);
}

async function chargerHistoriqueMessages() {
    try {
        const res = await fetch('/api/messages');
        const data = await res.json();
        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(msg => ajouterMessageAuDOM(msg));
            faireDefilerVersLeBas();
        }
    } catch (e) {
        console.error("Erreur historique:", e);
    }
}

function basculerModeChiffre() {
    afficherChiffre = !afficherChiffre;
    const btn = document.getElementById('btn-toggle-raw');
    const label = document.getElementById('label-inspect');

    if (afficherChiffre) {
        btn.classList.add('active');
        label.innerText = 'Masquer Chiffré';
    } else {
        btn.classList.remove('active');
        label.innerText = 'Voir Chiffré';
    }

    document.querySelectorAll('.cipher-badge').forEach(el => {
        if (afficherChiffre) {
            el.classList.add('visible');
        } else {
            el.classList.remove('visible');
        }
    });
}

function reinitialiserChat() {
    if (confirm("Effacer l'affichage des messages de cette session ?")) {
        socket.emit('reinitialiser_chat');
    }
}

function faireDefilerVersLeBas() {
    const container = document.getElementById('chat-messages');
    container.scrollTop = container.scrollHeight;
}

function echapperHtml(texte) {
    const div = document.createElement('div');
    div.innerText = texte;
    return div.innerHTML;
}
