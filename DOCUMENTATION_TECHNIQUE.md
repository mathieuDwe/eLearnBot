# 🔧 Documentation Technique — eLearnBot

> **Version** : 1.0.0 — Juillet 2026  
> **Stack** : Streamlit · Supabase · ChromaDB · sentence-transformers  
> **Language** : Python 100%

---

## 1. Architecture Générale

```
┌──────────────────────────────────────────────────────────┐
│                   NAVIGATEUR                              │
│          (Cookie elearnbot_session — HMAC-SHA256)         │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                    STREAMLIT (main.py)                    │
│                                                          │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐  │
│  │Init session│  │Auto-login│  │Sync cloud│  │Routing│  │
│  │ (auth.py)  │  │(session) │  │(docstore)│  │(pages)│  │
│  └────────────┘  └──────────┘  └──────────┘  └───────┘  │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│              PIPELINE DE RÉPONSE (rag_pipeline.py)        │
│                                                          │
│  Question ──► Cache LLM (hit?) ──► OUI ──► Réponse      │
│                  │ NON                                     │
│                  ▼                                         │
│             LLM dispo? ──► OUI ──► Requête LLM            │
│                  │ NON                    │               │
│                  ▼                        ▼               │
│          ┌──────────────┐          Réponse + cache       │
│          │ Moteur non-LLM│                                │
│          │ (9 stratégies)│                                │
│          │    + BM25     │                                │
│          └──────┬───────┘                                │
│                 ▼                                          │
│           Confiance ≥ 0.5? ──► OUI ──► Réponse sourcée    │
│                 │ NON                                      │
│                 ▼                                          │
│           Fallback basique                                │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                      STOCKAGE                             │
│                                                          │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Supabase DB    │  │Supabase Stor.│  │  ChromaDB    │ │
│  │ (utilisateurs) │  │(bucket cours)│  │ (embeddings) │ │
│  │ table: users   │  │ (PDF bruts)  │  │ collection:  │ │
│  │ cols: username,│  │ (originaux)  │  │  elearnbot   │ │
│  │  password,type │  │ + métadonnées│  │              │ │
│  └────────────────┘  └──────────────┘  └──────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Stack Technique

### 2.1 Frontend
| Technologie | Version | Usage |
|------------|---------|-------|
| Streamlit | ≥ 1.28 | Interface utilisateur complète |
| Python | ≥ 3.10 | Langage hôte |
| st.query_params | natif | Passage cookie → serveur |

### 2.2 Backend — Pipeline RAG
| Module | Technologie | Rôle |
|--------|------------|------|
| `rag_pipeline.py` | Orchestrateur | Cache → LLM → non-LLM → fallback |
| `non_llm/document_analyzer.py` | NLP offline | Extraction phrases-clés, définitions, entités |
| `non_llm/question_analyzer.py` | NLP offline | Classification en 11 types de questions |
| `non_llm/retrieval.py` | BM25 (Okapi) | Recherche plein texte + phrase matching |
| `non_llm/strategies.py` | 9 stratégies | Réponses spécialisées par type |
| `non_llm/engine.py` | Orchestrateur | Scoring de confiance 0.0–1.0 |
| `document_store.py` | Supabase Storage | Stockage cloud des PDF |

### 2.3 Base de données
| Service | Technologie | Usage |
|---------|------------|-------|
| Supabase PostgreSQL | via `supabase-py` | Utilisateurs, rôles, métadonnées |
| Supabase Storage | bucket `cours` | Fichiers PDF originaux |
| ChromaDB | persistante locale | Stockage vectoriel (embeddings) |

### 2.4 Dépendances Principales
```
streamlit              # Interface web interactive
PyPDF2, pdfplumber    # Extraction PDF
groq, openai          # Clients LLM
google-genai          # API Google Gemini
supabase              # Client Supabase
python-dotenv         # Configuration env
requests              # Requêtes HTTP
imageio-ffmpeg        # Transcription vidéo
sentence-transformers # Embeddings locaux
chromadb              # Vectorstore persistant
```

### 2.5 LLM & Embeddings
| Provider | Clé API | Modèle |
|----------|---------|--------|
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Gemini | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4` (optionnel) |
| Embeddings | — | `sentence-transformers/all-MiniLM-L6-v2` (384 dims) |

---

## 3. Authentification et Sessions

### 3.1 Table utilisateurs (Supabase)
```sql
CREATE TABLE users (
  username TEXT PRIMARY KEY,
  password TEXT NOT NULL,    -- hash SHA-256
  type     TEXT NOT NULL DEFAULT 'eleve'  -- admin | professeur | eleve
);
```

### 3.2 Cookie signé HMAC-SHA256
- **Nom** : `elearnbot_session`
- **Durée** : 24 h (configurable via `SESSION_DAYS`)
- **Clé** : `SESSION_SECRET` (ou `SUPABASE_KEY` en fallback)
- **Contenu** : `base64(payload).signature`

```python
payload = {
    "username": "...",
    "role": "...",
    "type": "...",
    "exp": "2026-07-21T12:00:00"
}
```

### 3.3 Auto-login sans flash
1. **1ʳᵉ visite** : `_cookie_attempted` absent → JS injecté + écran chargement
2. **Si cookie valide** : Redirection auto vers `?session_token=...`
3. **Si pas de cookie** : Affichage du formulaire login

### 3.4 Rôles et Permissions
| Type | Pages accessibles | Connexions visibles |
|------|------------------|-------------------|
| `admin` | Toutes | ✅ Oui |
| `professeur` | Professeur, Élève, Aide | ❌ Non |
| `eleve` | Élève, Légifrance, Aide | ❌ Non |

---

## 4. Moteur Q&A Sans LLM (`src/core/non_llm/`)

### 4.1 Architecture du package
```
non_llm/
├── __init__.py               # API publique
├── document_analyzer.py      # Analyse hors ligne
├── question_analyzer.py      # Classification
├── retrieval.py              # Recherche BM25
├── strategies.py             # 9 stratégies
└── engine.py                 # Orchestrateur
```

### 4.2 Classification des questions (11 types)
| Type | Exemple |
|------|---------|
| `DEFINITION` | *"Qu'est-ce que la photosynthèse ?"* |
| `FACTOID` | *"Quelle est la capitale de la France ?"* |
| `HOW` | *"Comment calculer l'aire d'un cercle ?"* |
| `WHY` | *"Pourquoi le ciel est bleu ?"* |
| `LIST` | *"Liste les planètes du système solaire"* |
| `COMPARISON` | *"Différence entre mitose et méiose"* |
| `BOOLEAN` | *"Est-ce que l'eau bout à 100°C ?"* |
| `SUMMARY` | *"Résume ce chapitre"* |
| `FORMULA` | *"Quelle est la formule d'Einstein ?"* |
| `EXAMPLE` | *"Donne un exemple de réaction chimique"* |
| `UNKNOWN` | *"Question non classifiable"* |

### 4.3 Les 9 Stratégies de réponse
| Stratégie | Déclenchée pour | Méthode |
|-----------|----------------|---------|
| `answer_definition` | DEFINITION | Extraction phrase nominale + contexte |
| `answer_factoid` | FACTOID | Top-1 BM25 + vérification entité |
| `answer_list` | LIST | Agrégation items |
| `answer_comparison` | COMPARISON | Tableau comparatif |
| `answer_boolean` | BOOLEAN | Recherche oui/non |
| `answer_summary` | SUMMARY | Phrases-clés + premières phrases |
| `answer_formula` | FORMULA | Extraction motif mathématique |
| `answer_example` | EXAMPLE | Phrase contenant "exemple" |
| `answer_procedure` | HOW | Étapes numérotées |

### 4.4 Scoring de confiance
Score de 0.0 à 1.0 basé sur :
- **Présence des termes** : ratio mots trouvés
- **Proximité** : distance entre termes
- **Couverture** : proportion pertinente
- **Spécificité** : rareté dans corpus
- **Structure** : présence dans structure attendue

**Seuil** : `≥ 0.5` → réponse affichée · `< 0.5` → fallback

---

## 5. Stockage Cloud (`document_store.py`)

### 5.1 Architecture
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Upload UI    │→ │ Supabase     │→ │ Cache        │
│(professeur)  │  │ Storage      │  │ mémoire      │
└──────────────┘  └──────────────┘  └──────────────┘
                        │
                        ▼
                  ┌──────────────┐
                  │ Métadonnées  │
                  │ (JSON)       │
                  └──────────────┘
```

### 5.2 Modes de fonctionnement
| Mode | Condition | Comportement |
|------|-----------|-------------|
| **Cloud** | `SUPABASE_URL` + `SUPABASE_KEY` | Persistance réelle |
| **Mémoire** | Supabase non configuré | Cache dict (perdu au restart) |

### 5.3 Fonctions clés
| Fonction | Rôle |
|----------|------|
| `upload_pdf(file, filename)` | Upload + indexation |
| `sync_from_cloud()` | Restaure cache au démarrage |
| `get_available_documents()` | Liste indexée |
| `count_documents()` | Total documents |
| `is_cloud_configured()` | Vérifie Supabase |

---

## 6. Ré-indexation Automatique (`reindexer.py`)

Au démarrage, `auto_reindex_on_startup()` :

1. Vérifie la date de dernière vérification
2. Si > 24 h → liste fichiers dans Supabase Storage
3. Compare avec l'index ChromaDB
4. Ré-indexe nouveaux ou modifiés
5. Met à jour cache mémoire
6. Retourne un rapport

---

## 7. Structure du Projet

```
eLearnBot/
├── src/
│   ├── main.py                  # 🚀 Point d'entrée
│   ├── core/
│   │   ├── auth.py              # 🔐 Authentification
│   │   ├── session.py           # 🍪 Cookies HMAC
│   │   ├── document_store.py    # ☁️ Supabase
│   │   ├── rag_pipeline.py      # 🔄 Pipeline
│   │   ├── reindexer.py         # 🔁 Ré-indexation
│   │   └── non_llm/             # 🧠 Moteur Q&A
│   │       ├── document_analyzer.py
│   │       ├── question_analyzer.py
│   │       ├── retrieval.py
│   │       ├── strategies.py
│   │       └── engine.py
│   ├── pages/
│   │   ├── accueil.py           # 🏠 Accueil
│   │   ├── professeur.py        # 👨‍🏫 Professeur
│   │   ├── eleve.py             # 👨‍🎓 Élève
│   │   ├── legifrance.py        # ⚖️ Juridique
│   │   └── aide.py              # ❓ Aide
│   └── integrations/
│       └── supabase_storage.py  # ☁️ Client Supabase
│
├── tests/                        # 🧪 307 tests
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── functional/
│
├── DOCUMENTATION_TECHNIQUE.md   # 🔧 Docs
├── README.md                    # 📖 Guide
├── requirements.txt             # 📦 Dépendances
└── .env.example                 # ⚙️ Config
```

---

## 8. Variables d'Environnement

| Variable | Requis | Défaut | Description |
|----------|--------|--------|-------------|
| `SUPABASE_URL` | Oui* | — | URL du projet Supabase |
| `SUPABASE_KEY` | Oui* | — | Clé anon ou service_role |
| `SESSION_SECRET` | Non | `SUPABASE_KEY` | Clé HMAC pour cookie |
| `GROQ_API_KEY` | Non | — | Clé API Groq |
| `GEMINI_API_KEY` | Non | — | Clé API Gemini |
| `OPENAI_API_KEY` | Non | — | Clé API OpenAI |
| `ADMIN_SECRET_CODE` | Non | `admin123` | Code création admin |

*Requis pour persistance cloud — sans, mode mémoire utilisé*

---

## 9. Sécurité

- **Cookie** : signé HMAC-SHA256, clé séparée
- **Mots de passe** : hashés SHA-256
- **Rôles** : vérification serveur à chaque accès
- **Supabase** : clé env, jamais commitée
- **Storage** : public pour lecture Streamlit
- **Session** : nettoyage au logout

---

## 10. Déploiement

### 10.1 Local
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run src/main.py
```

### 10.2 Streamlit Cloud
1. Push sur GitHub
2. Connecter sur [share.streamlit.io](https://share.streamlit.io)
3. Définir secrets (`SUPABASE_URL`, `SUPABASE_KEY`, etc.)
4. Déployer

---

## 11. Tests

### 11.1 Exécution
```bash
pytest tests/                   # Tout
pytest tests/ -q --tb=short     # Silencieux
pytest tests/unit/ -v           # Unitaires
pytest tests/integration/ -v    # Intégration
```

### 11.2 Couverture
- **307 tests** : unitaires, intégration, régression, sécurité, fonctionnels

---

## 12. Limitations Connues

| Limitation | Cause | Solution future |
|------------|-------|-----------------|
| Pas d'OCR | Coût technique | Intégration Tesseract |
| PDF 10 Mo max | Limite Streamlit | Upload par chunk |
| 30 req/min Groq | Rate limit gratuit | Cache + file d'attente |
| ChromaDB mono-instance | Architecture simple | Qdrant/Pinecone |
| Transcription lente | Whisper local | Whisper distante |

---

## 13. Roadmap Future

- [ ] Support OCR pour PDFs scannés
- [ ] Chunking intelligent pour gros fichiers
- [ ] Queue système pour requêtes LLM
- [ ] Passage à Qdrant/Pinecone
- [ ] API REST publique
- [ ] Support multilingue

---

*Documentation mise à jour : 21 Juillet 2026*
*eLearnBot v1.0.0*
