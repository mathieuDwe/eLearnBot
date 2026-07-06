# 🔧 Documentation Technique — eLearnBot

> Version : 0.1.0 — Juillet 2026

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    UTILISATEUR                          │
│              (Professeur / Élève)                       │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   STREAMLIT (Frontend)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Accueil  │  │Professeu │  │ Élève    │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              PIPELINE RAG (Core)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ PDF      │─▶│Embeddings│─▶│ChromaDB  │              │
│  │Extractor │  │Generator │  │Vector DB│              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                          │                              │
│                          ▼                              │
│                     ┌──────────┐                        │
│                     │   LLM    │                        │
│                     │(Groq/    │                        │
│                     │ Gemini)  │                        │
│                     └──────────┘                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              STOCKAGE EXTERNE                           │
│  ┌──────────────────┐  ┌──────────────────┐             │
│  │   Google Drive   │  │   ChromaDB (local)│             │
│  │   (PDFs bruts)   │  │   (embeddings)    │             │
│  └──────────────────┘  └──────────────────┘             │
└─────────────────────────────────────────────────────────┘
```

## 2. Stack Technique

### Frontend
| Technologie | Version | Usage |
|------------|---------|-------|
| Streamlit | ≥ 1.28 | Interface utilisateur |
| Python | ≥ 3.10 | Langage hôte |

### Core — Pipeline RAG
| Module | Technologie | Rôle |
|--------|------------|------|
| `pdf_extractor.py` | PyPDF2 / pdfplumber | Extraction texte des PDF |
| `embeddings.py` | sentence-transformers | Génération d'embeddings (384 dims) |
| `vector_store.py` | ChromaDB | Stockage et recherche vectorielle |
| `rag_pipeline.py` | Orchestrateur | Pipeline complet RAG |

### LLM (au choix)
| Provider | Clé API | Modèle par défaut |
|----------|---------|-------------------|
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Gemini | `GEMINI_API_KEY` | `gemini-2.0-flash` |

### Stockage
| Service | Technologie | Usage |
|---------|------------|-------|
| Google Drive | API v3 | Stockage des PDF bruts |
| ChromaDB | Persistante locale | Stockage des embeddings |

## 3. Structure des Fichiers

```
src/
├── main.py                    # Point d'entrée Streamlit
├── __init__.py                # Version du package
├── pages/
│   ├── __init__.py
│   ├── accueil.py             # Page d'accueil
│   ├── professeur.py          # Interface upload & gestion
│   ├── eleve.py               # Interface questions & chat
│   └── aide.py                # Page d'aide & FAQ
├── core/
│   ├── __init__.py
│   ├── pdf_extractor.py       # Extraction & chunking PDF
│   ├── embeddings.py          # Génération embeddings
│   ├── vector_store.py        # Interface ChromaDB
│   └── rag_pipeline.py        # Pipeline RAG complet
└── integrations/
    ├── __init__.py
    └── google_drive.py        # Client Google Drive API
```

## 4. Pipeline RAG — Détail

### 4.1 Upload et Indexation

```
PDF Upload
    │
    ▼
Extraction texte (pdfplumber)
    │
    ▼
Découpage en chunks (500 mots, overlap 50)
    │
    ▼
Génération embeddings (sentence-transformers)
    │
    ▼
Stockage ChromaDB (collection: elearnbot_documents)
    │
    ▼
Upload Google Drive (copie de sauvegarde)
```

### 4.2 Réponse à une Question

```
Question utilisateur
    │
    ▼
Embedding de la question
    │
    ▼
Recherche cosinus dans ChromaDB (top-5)
    │
    ▼
Construction du prompt RAG (contexte + question)
    │
    ▼
Appel LLM (Groq / OpenAI / Gemini)
    │
    ▼
Réponse sourcée [Passage 1], [Passage 2], ...
```

## 5. Configuration des APIs

### 5.1 Google Drive

```python
# service_account.json requis :
{
  "type": "service_account",
  "project_id": "chatbot-educatif",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "...@chatbot-educatif.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
}
```

### 5.2 LLM

```bash
# Au choix :
GROQ_API_KEY="gsk_..."          # → llama-3.3-70b-versatile
OPENAI_API_KEY="sk-..."          # → gpt-4o-mini
GEMINI_API_KEY="AIza..."         # → gemini-2.0-flash
```

## 6. Déploiement

### 6.1 Local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Éditer .env avec vos clés
streamlit run src/main.py
```

### 6.2 Streamlit Cloud

1. Push sur GitHub
2. Connecter Streamlit Cloud
3. Définir les secrets :
   - `GOOGLE_DRIVE_FOLDER_ID`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`
   - `GROQ_API_KEY` (ou autre)
4. Déployer

## 7. Variables d'Environnement

| Variable | Requis | Défaut | Description |
|----------|--------|--------|-------------|
| `GOOGLE_DRIVE_FOLDER_ID` | Oui | — | ID du dossier Drive |
| `GOOGLE_APPLICATION_CREDENTIALS` | Non* | `service_account.json` | Chemin JSON compte de service |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Non* | — | Contenu JSON (Streamlit Cloud) |
| `GROQ_API_KEY` | Non | — | Clé API Groq |
| `OPENAI_API_KEY` | Non | — | Clé API OpenAI |
| `GEMINI_API_KEY` | Non | — | Clé API Gemini |
| `LLM_MODEL` | Non | (voir §2) | Modèle LLM |
| `EMBEDDING_MODEL` | Non | `all-MiniLM-L6-v2` | Modèle embeddings |
| `CHROMA_DB_PATH` | Non | `./chroma_db` | Chemin persistence ChromaDB |

*\* Soit `GOOGLE_APPLICATION_CREDENTIALS` (local), soit `GOOGLE_SERVICE_ACCOUNT_JSON` (cloud)*

## 8. Limitations Techniques

| Limitation | Cause | Solution future |
|------------|-------|-----------------|
| Pas d'OCR | Coût technique | Intégration Tesseract |
| PDF 10 Mo max | Limite Streamlit | Upload par chunk |
| Pas de transcription YouTube | Non implémenté | yt-dlp + Whisper |
| 30 req/min Groq | Rate limit gratuit | Cache + file d'attente |
| ChromaDB mono-instance | Architecture simple | Passage à Qdrant/Pinecone |

## 9. Sécurité

- **Google Drive** : utilisation d'un compte de service avec accès restreint au dossier
- **Clés API** : stockées en variables d'environnement, jamais commitées
- **Données utilisateur** : aucun stockage local permanent des PDF
- **Embeddings** : générés localement (sentence-transformers), pas d'envoi à un tiers

---

*Documentation générée pour eLearnBot v0.1.0*