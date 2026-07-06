# 🎓 Chatbot Éducatif — RAG avec Streamlit et Google Drive

> **Transformez vos cours en assistant interactif !**  
> Le professeur upload ses PDF, les élèves posent des questions en langage naturel.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io/)
[![Licence](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)
[![Statut](https://img.shields.io/badge/Statut-EN%20DÉVELOPPEMENT-orange.svg)]()

---

## ✨ Fonctionnalités Principales

- 📤 **Upload simplifié** — Le professeur uploade ses PDF directement via l'interface
- 💬 **Questions en langage naturel** — Les élèves posent des questions comme à un professeur
- 🔍 **Réponses sourcées** — Chaque réponse cite le passage du cours utilisé
- 🎥 **Support vidéo** — Intégration possible de liens YouTube
- 👨‍🏫 **Mode Professeur** — Upload et gestion des cours
- 👨‍🎓 **Mode Élève** — Consultation et questions
- ☁️ **Hébergement gratuit** — Pas de frais, pas de carte bancaire
- 🔒 **Respect de la vie privée** — Toutes les données appartiennent à l'utilisateur

---

## 🏗️ Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  UTILISATEUR│────▶│ STREAMLIT   │────▶│  GOOGLE     │
│  (Professeur│     │   CLOUD     │     │  DRIVE      │
│   ou Élève) │     │  (Gratuit)  │     │  (15 Go)    │
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  API LLM    │
                   │ (Gratuite)  │
                   └─────────────┘
```

> 📖 Pour les détails techniques complets, consultez [DOCUMENTATION_TECHNIQUE.md](DOCUMENTATION_TECHNIQUE.md).

---

## 📋 Prérequis

Avant de commencer, vous aurez besoin de :

| Prérequis | Détails |
|-----------|---------|
| **Compte Google** | Pour Google Drive et Google Cloud |
| **Compte Streamlit Cloud** | Gratuit sur [share.streamlit.io](https://share.streamlit.io) |
| **Compte GitHub** | Pour héberger le code source |
| **Python 3.10+** | Uniquement pour le développement local |
| **Clé API LLM** | Optionnel : Groq, Gemini, ou autre (gratuit) |

---

## 🚀 Installation Locale

### 1️⃣ Cloner le dépôt

```bash
git clone https://github.com/votre-username/chatbot-educatif.git
cd chatbot-educatif
```

### 2️⃣ Créer un environnement virtuel

```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3️⃣ Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4️⃣ Configurer les variables d'environnement

Créer un fichier `.env` à la racine du projet :

```bash
# .env
GOOGLE_DRIVE_FOLDER_ID=votre_id_dossier_drive
GOOGLE_APPLICATION_CREDENTIALS=chemin/vers/service_account.json

# Optionnel : Clé API LLM (si vous en utilisez une)
OPENAI_API_KEY=votre_cle_api  # OU
GROQ_API_KEY=votre_cle_api     # OU
GEMINI_API_KEY=votre_cle_api
```

### 5️⃣ Lancer l'application

```bash
streamlit run src/main.py
```

L'application sera accessible sur [http://localhost:8501](http://localhost:8501)

---

## ⚙️ Configuration Google Drive

### Étape 1 : Créer un projet Google Cloud

1. Allez sur [console.cloud.google.com](https://console.cloud.google.com)
2. Cliquez sur **"Sélectionner un projet"** → **"Nouveau projet"**
3. Nommez-le `chatbot-educatif`
4. Attendez la création

### Étape 2 : Activer l'API Google Drive

1. Menu → **API et services** → **Bibliothèque**
2. Recherchez **"Google Drive API"**
3. Cliquez → **"Activer"**

### Étape 3 : Créer un compte de service

1. Menu → **API et services** → **Identifiants**
2. Cliquez **"+ Créer des identifiants"** → **"Compte de service"**
3. Nommez-le (ex: `chatbot-drive`)
4. Cliquez **"Créer et continuer"**
5. (Optionnel) Sélectionnez le rôle **"Propriétaire"**
6. Cliquez **"Terminé"**

### Étape 4 : Télécharger la clé JSON

1. Dans **Identifiants**, cliquez sur votre compte de service
2. Onglet **"Clés"** → **"Ajouter une clé"** → **"JSON"**
3. Le fichier est téléchargé automatiquement
4. **⚠️** Renommez-le en `service_account.json`

### Étape 5 : Créer le dossier Drive

1. Créez un nouveau dossier Google Drive (ex: `Chatbot Cours`)
2. Copiez l'**ID du dossier** (dans l'URL : `drive.google.com/drive/folders/XXXXXXXXX`)

### Étape 6 : Partager le dossier

1. Clic droit sur le dossier → **"Partager"**
2. Ajoutez l'email du compte de service (format : `...@chatbot-educatif.iam.gserviceaccount.com`)
3. Donnez le rôle **"Éditeur"**
4. Cliquez **"Envoyer"**

---

## 🔐 Configuration des Secrets Streamlit

Pour déployer sur Streamlit Cloud, ajoutez ces secrets dans l'interface :

```toml
# Streamlit Cloud > Settings > Secrets

# ID de votre dossier Google Drive
GOOGLE_DRIVE_FOLDER_ID = "XXXXXXXXXXXXXXXXXXXXXXXXXX"

# Contenu complet du fichier JSON du compte de service
# (copier-coller le contenu du fichier service_account.json)
GOOGLE_SERVICE_ACCOUNT_JSON = '''
{
  "type": "service_account",
  "project_id": "chatbot-educatif",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "...@chatbot-educatif.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
'''

# Optionnel : Clé API LLM (choisir une)
# GROQ_API_KEY = "votre_cle_groq"
# GEMINI_API_KEY = "votre_cle_gemini"
```

---

## 🌐 Déploiement sur Streamlit Cloud

### 1️⃣ Push sur GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/votre-username/chatbot-educatif.git
git push -u origin main
```

### 2️⃣ Connecter Streamlit Cloud

1. Allez sur [share.streamlit.io](https://share.streamlit.io)
2. Cliquez **"New app"**
3. Sélectionnez votre dépôt GitHub
4. Choisissez la branche `main`
5. Spécifiez le fichier : `src/main.py`

### 3️⃣ Ajouter les Secrets

1. Dans les paramètres de l'app, allez dans **"Settings"** → **"Secrets"**
2. Collez les variables comme indiqué dans la section précédente

### 4️⃣ Déployer

Cliquez sur **"Deploy!"** et attendez ~2-3 minutes.

Votre application sera accessible sur : `https://votre-app.streamlit.app`

---

## 📁 Structure du Projet

```bash
chatbot-educatif/
│
├── src/
│   ├── main.py                 # 🚀 Point d'entrée
│   ├── pages/
│   │   ├── 01_professeur.py    # 👨‍🏫 Interface professeur
│   │   ├── 02_eleve.py         # 👨‍🎓 Interface élève
│   │   └── 03_aide.py          # ❓ Page d'aide
│   ├── core/
│   │   ├── rag_pipeline.py     # 🔄 Pipeline RAG
│   │   ├── pdf_extractor.py    # 📄 Extraction PDF
│   │   ├── embeddings.py       # 🧠 Embeddings
│   │   └── vector_store.py     # 💾 Base vectorielle
│   └── integrations/
│       └── google_drive.py     # ☁️ Client Drive
│
├── .streamlit/
│   └── config.toml             # ⚙️ Config Streamlit
│
├── requirements.txt             # 📦 Dépendances
├── README.md                   # 📖 Ce fichier
├── DOCUMENTATION_TECHNIQUE.md  # 🔧 Documentation technique
└── LICENSE                    # 📜 Licence MIT
```

---

## 📖 Utilisation

### 👨‍🏫 Pour le Professeur

1. **Ouvrir l'application** → Sélectionner **"Mode Professeur"**
2. **Uploader un cours** → Glisser-déposer un fichier PDF ou cliquer sur "Parcourir"
3. **Attendre l'indexation** → Un message confirme l'ajout successful
4. **Consulter la liste** → Voir tous les cours uploadés

### 👨‍🎓 Pour l'Élève

1. **Ouvrir l'application** → Sélectionner **"Mode Élève"**
2. **Choisir un cours** → Cliquer sur la carte du cours souhaité
3. **Poser une question** → Taper la question dans la zone de chat
4. **Recevoir la réponse** → Le chatbot répond en citant le passage source

### 💡 Exemples de Questions

- *"Résume ce chapitre en 3 points"*
- *"Explique le théorème de Pythagore"*
- *"Donne un exemple concret de ce concept"*
- *"Quelle est la formule de l'énergie cinétique ?"*

---

## ⚠️ Limitations Connues

| Limitation | Détail |
|------------|-------|
| **Taille PDF** | Maximum 10 Mo par fichier |
| **Taille totale** | 15 Go disponibles sur Google Drive gratuit |
| **API LLM** | Rate limit sur les APIs gratuites (30 req/min avec Groq) |
| **Pas d'OCR** | Les PDF scannés ne sont pas supportés en v1 |
| **Vidéos** | Seuls les liens YouTube sont stockés, pas de transcription |

---

## 📜 Licence

Ce projet est distribué sous la licence **MIT**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

```
MIT License

Copyright (c) 2026 Chatbot Éducatif

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🤝 Contact et Contribution

| Canal | Détails |
|-------|---------|
| **Issues** | Utilisez les GitHub Issues pour signaler un bug ou demander une fonctionnalité |
| **Pull Requests** | Les contributions sont les bienvenues ! |

---

*⭐ N'oubliez pas de mettre une étoile si ce projet vous est utile !*
