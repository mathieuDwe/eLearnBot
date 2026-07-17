# 🎓 eLearnBot — Chatbot Éducatif RAG

> **Transformez vos cours en assistant interactif !**  
> Le professeur upload ses PDF, les élèves posent des questions en langage naturel.  
> Réponses sourcées, pas de LLM nécessaire en fallback, stockage cloud Supabase.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io/)
[![Supabase](https://img.shields.io/badge/Supabase-Storage-green.svg)](https://supabase.com/)
[![Licence](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)
[![Statut](https://img.shields.io/badge/Statut-EN%20DÉVELOPPEMENT-orange.svg)]()

---

## ✨ Fonctionnalités

- 📤 **Upload simplifié** — Déposez vos PDF, l'indexation est automatique
- 💬 **Moteur Q&A sans LLM** — Réponses via BM25, patrons linguistiques et 9 stratégies spécialisées (fonctionne même sans API LLM)
- 🔍 **Réponses sourcées** — Chaque réponse cite le passage exact du cours avec score de confiance
- ⚡ **Triple mode** — Cache → LLM → Moteur non-LLM → fallback basique (résilient)
- 👨‍🏫 **3 rôles** — Admin, Professeur, Élève — chaque rôle voit les pages qui le concernent
- 🔐 **Auto-login** — Reconnexion automatique via cookie signé HMAC-SHA256 (24 h)
- ☁️ **Stockage cloud** — Tous les documents persistés dans Supabase Storage (bucket `cours`)
- 🗄️ **Base de données** — Utilisateurs, rôles et index stockés dans Supabase PostgreSQL
- 🧠 **Recherche vectorielle** — ChromaDB + embeddings pour la similarité sémantique
- 🎥 **Support vidéo** — Transcription Whisper pour les fichiers MP4

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   UTILISATEUR                           │
│           (Admin / Professeur / Élève)                  │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│              STREAMLIT (Interface)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Accueil  │  │Professeur│  │ Élève    │  │ Aide   │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘ │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│                PIPELINE DE RÉPONSE                      │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ Cache    │──▶ Pipeline RAG      │──▶ Réponse      │  │
│  │ (LLM)    │  │ (BM25 + vecteurs) │  │ sourcée      │  │
│  └──────────┘  │ + Moteur non-LLM  │  └──────────────┘  │
│                │ (9 stratégies)    │                     │
│                └──────────────────┘                     │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│                    STOCKAGE                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Supabase DB  │  │Supabase Stor.│  │  ChromaDB    │  │
│  │(utilisateurs)│  │ (PDF bruts)  │  │ (embeddings) │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 Prérequis

| Prérequis | Détails |
|-----------|---------|
| **Compte Supabase** | Gratuit sur [supabase.com](https://supabase.com) |
| **Compte Streamlit Cloud** | Gratuit sur [share.streamlit.io](https://share.streamlit.io) |
| **Compte GitHub** | Pour héberger le code source |
| **Python 3.10+** | Développement local uniquement |
| **Clé API LLM** | Optionnel : Groq, Gemini (gratuit) |

---

## 🚀 Installation Locale

### 1️⃣ Cloner le dépôt

```bash
git clone https://github.com/mathieuDwe/eLearnBot.git
cd eLearnBot
```

### 2️⃣ Créer un environnement virtuel

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4️⃣ Créer le fichier `.env`

```bash
# .env — copiez et renseignez vos valeurs
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_KEY=cle_publique_anon_ou_service_role
SESSION_SECRET=une_chaine_aleatoire_secrete

# Optionnel (au moins un pour le mode LLM) :
# GROQ_API_KEY=gsk_...
# GEMINI_API_KEY=AIza...
```

### 5️⃣ Créer la table utilisateurs dans Supabase

Exécutez cette requête dans l'éditeur SQL de Supabase :

```sql
CREATE TABLE users (
  username TEXT PRIMARY KEY,
  password TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'eleve'
);
```

> **Types disponibles :** `admin`, `professeur`, `eleve`

### 6️⃣ Lancer l'application

```bash
streamlit run src/main.py
```

L'application est accessible sur [http://localhost:8501](http://localhost:8501)

---

## ⚙️ Configuration Supabase

### Créer le Storage bucket

Dans le dashboard Supabase → **Storage** → **Create bucket** :
- Nom : `cours`
- Public : `✅` (nécessaire pour la lecture depuis Streamlit)

> Si le bucket n'existe pas, un administrateur peut le créer depuis l'interface **Professeur** → section stockage.

### Créer un utilisateur admin

```sql
-- Mot de passe hashé en SHA-256 :
INSERT INTO users (username, password, type)
VALUES ('admin', 'hash_sha256_du_mot_de_passe', 'admin');
```

> En Python : `hashlib.sha256("motdepasse".encode()).hexdigest()`

---

## 🔐 Configuration des Secrets Streamlit Cloud

```toml
SUPABASE_URL = "https://votre-projet.supabase.co"
SUPABASE_KEY = "cle_publique_anon_ou_service_role"
SESSION_SECRET = "une_chaine_aleatoire_secrete"

# Optionnel (au moins un pour le mode LLM) :
# GROQ_API_KEY = "gsk_..."
# GEMINI_API_KEY = "AIza..."
```

---

## 📁 Structure du Projet

```
eLearnBot/
│
├── src/
│   ├── main.py                    # 🚀 Point d'entrée Streamlit
│   ├── core/
│   │   ├── auth.py                # 🔐 Authentification (Supabase, JWT-like)
│   │   ├── session.py             # 🍪 Cookie signé HMAC-SHA256
│   │   ├── document_store.py      # ☁️ Stockage cloud Supabase
│   │   ├── rag_pipeline.py        # 🔄 Pipeline triple mode
│   │   ├── reindexer.py           # 🔁 Ré-indexation automatique
│   │   └── non_llm/               # 🧠 Moteur Q&A sans LLM
│   │       ├── document_analyzer.py
│   │       ├── question_analyzer.py
│   │       ├── retrieval.py
│   │       ├── strategies.py
│   │       └── engine.py
│   ├── pages/
│   │   ├── accueil.py             # 🏠 Page d'accueil
│   │   ├── professeur.py          # 👨‍🏫 Interface professeur
│   │   ├── eleve.py               # 👨‍🎓 Interface élève
│   │   ├── legifrance.py          # ⚖️ Recherche juridique
│   │   └── aide.py                # ❓ Aide filtrée par rôle
│   └── integrations/
│       └── supabase_storage.py    # ☁️ Client Supabase Storage
│
├── tests/                          # 🧪 307 tests
│   ├── unit/                      # Tests unitaires non-LLM
│   ├── integration/               # Tests complexes & juridiques
│   ├── regression/                # Tests régression & sécurité
│   └── functional/                # Tests fonctionnels
│
├── DOCUMENTATION_TECHNIQUE.md      # 🔧 Documentation technique
├── README.md                       # 📖 Ce fichier
└── requirements.txt                # 📦 Dépendances
```

---

## 📖 Utilisation par Rôle

### 👑 Admin
- Gère les utilisateurs (création, suppression, changement de rôle)
- Voit l'ensemble des pages et les indicateurs de connexion
- Accède à la configuration technique

### 👨‍🏫 Professeur
- Upload des cours (PDF)
- Gère les vidéos (MP4)
- Consulte les documents indexés
- Page Aide : voit upload, formats, vidéo, limitations

### 👨‍🎓 Élève
- Parcours les cours disponibles
- Pose des questions en langage naturel
- Reçoit des réponses sourcées
- Page Aide : voit comment poser une question

---

## 🧠 Moteur Q&A Sans LLM

Quand aucune API LLM n'est configurée ou en cas de panne, eLearnBot utilise son moteur interne basé sur :

- **BM25** (Okapi) pour la recherche plein texte
- **9 stratégies de réponse** : définition, fait, liste, comparaison, booléen, résumé, formule, exemple, procédure
- **Analyse de confiance** : score de 0.0 à 1.0
- **Analyse de questions** : classification en 11 types (DEFINITION, FACTOID, HOW, WHY, LIST, COMPARISON, BOOLEAN, SUMMARY, FORMULA, EXAMPLE, UNKNOWN)

Le pipeline bascule automatiquement : **Cache LLM → LLM → Moteur non-LLM → Fallback basique**

---

## 🧪 Tests

```bash
# Tout exécuter
pytest tests/

# Tests unitaires non-LLM
pytest tests/unit/test_non_llm_qa.py -v

# Tests d'intégration
pytest tests/integration/ -v

# Tests de sécurité
pytest tests/regression/test_security.py -v
```

**Couverture :** 307 tests (unitaires, intégration juridique, questions complexes, régression, sécurité)

---

## ⚠️ Limitations Connues

| Limitation | Détail |
|------------|--------|
| **Taille PDF** | Maximum 10 Mo par fichier |
| **Pas d'OCR** | Les PDF scannés ne sont pas supportés |
| **Rate limit LLM** | 30 req/min avec Groq (gratuit) |
| **Transcription** | Les vidéos longues prennent plusieurs minutes |

---

## 📜 Licence

Projet distribué sous licence **MIT**. Voir [LICENSE](LICENSE).

---

*⭐ N'oubliez pas de mettre une étoile si ce projet vous est utile !*
