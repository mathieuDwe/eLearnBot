# 🔧 Documentation Technique — eLearnBot

> Version : 1.0.0 — Juillet 2026  
> Stack : Streamlit · Supabase · ChromaDB · sentence-transformers

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
│  │ Init session│  │ Auto-login│  │Sync cloud│  │Routing│  │
│  │ (auth.py)   │  │(session) │  │(docstore)│  │(pages)│  │
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
│          ┌──────────────┐          Réponse + mise en cache│
│          │ Moteur non-LLM│                                │
│          │ (9 stratégies)│                                │
│          │    + BM25     │                                │
│          └──────┬───────┘                                │
│                 ▼                                          │
│           Confiance ≥ 0.5? ──► OUI ──► Réponse sourcée    │
│                 │ NON                                      │
│                 ▼                                          │
│           Fallback basique                                 │
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
│  │  password,type │  └──────────────┘  └──────────────┘ │
│  └────────────────┘                                     │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Stack Technique Détaillé

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
| `non_llm/document_analyzer.py` | NLP offline | Extraction phrases-clés, définitions, entités, listes, formules |
| `non_llm/question_analyzer.py` | NLP offline | Classification en 11 types de questions |
| `non_llm/retrieval.py` | BM25 (Okapi) | Recherche plein texte + phrase matching + proximité |
| `non_llm/strategies.py` | 9 stratégies | Réponses spécialisées par type de question |
| `non_llm/engine.py` | Orchestrateur | Scoring de confiance 0.0–1.0 |
| `document_store.py` | Supabase Storage | Stockage cloud des PDF + métadonnées |

### 2.3 Base de données

| Service | Technologie | Usage |
|---------|------------|-------|
| Supabase PostgreSQL | via `supabase-py` | Utilisateurs, rôles, métadonnées |
| Supabase Storage | bucket `cours` | Fichiers PDF originaux |
| ChromaDB | persistante locale | Stockage vectoriel (embeddings) |

### 2.4 LLM & Embeddings

| Provider | Clé API | Modèle |
|----------|---------|--------|
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Gemini | `GEMINI_API_KEY` | `gemini-2.0-flash` |
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
    "exp": "2026-07-18T12:00:00"
}
```

### 3.3 Auto-login sans flash

Le mécanisme évite l'affichage de la page login pour les utilisateurs avec cookie valide :

1. **1ʳᵉ visite** : `_cookie_attempted` absent → JS injecté + écran de chargement + `st.rerun()`
2. **Si cookie valide** : JS redirige vers `?session_token=...` → `try_auto_login()` → authentifié
3. **Si pas de cookie** : le rerun affiche le formulaire de login

### 3.4 Rôles et masquage

| Type | Pages accessibles | Connexions visibles |
|------|------------------|-------------------|
| `admin` | Toutes | ✅ Oui |
| `professeur` | Professeur, Élève, Légifrance, Aide | ❌ Non |
| `eleve` | Élève, Légifrance, Aide | ❌ Non |

---

## 4. Moteur Q&A Sans LLM (`src/core/non_llm/`)

### 4.1 Architecture du package

```
non_llm/
├── __init__.py             # API publique
├── document_analyzer.py    # Analyse hors ligne des documents
├── question_analyzer.py    # Classification des questions
├── retrieval.py            # Recherche BM25
├── strategies.py           # 9 stratégies de réponse
└── engine.py               # Orchestrateur + scoring
```

### 4.2 Analyseur de questions (`question_analyzer.py`)

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

### 4.3 Stratégies de réponse (`strategies.py`)

| Stratégie | Déclenchée pour | Méthode |
|-----------|----------------|---------|
| `answer_definition` | DEFINITION | Extraction phrase nominale + contexte |
| `answer_factoid` | FACTOID | Top-1 BM25 + vérification entité |
| `answer_list` | LIST | Agrégation items consécutifs |
| `answer_comparison` | COMPARISON | Tableau comparatif 2 colonnes |
| `answer_boolean` | BOOLEAN | Recherche présence/absence |
| `answer_summary` | SUMMARY | Phrases-clés + premieres phrases sections |
| `answer_formula` | FORMULA | Extraction motif mathématique |
| `answer_example` | EXAMPLE | Phrase contenant "exemple" |
| `answer_procedure` | HOW | Étapes numérotées + mots de liaison |

### 4.4 Scoring de confiance

Le moteur attribue un score de 0.0 à 1.0 basé sur :

- **Présence des termes** : ratio mots de la question trouvés
- **Proximité** : distance entre les termes dans le passage
- **Couverture** : proportion du passage pertinent
- **Spécificité** : rareté des termes dans le corpus
- **Structure** : présence de la réponse dans la structure attendue

Seuils : `≥ 0.5` → réponse affichée · `< 0.5` → fallback basique

### 4.5 Pipeline complet

```
Question
   │
   ▼
question_analyzer.classify() ──► type + mots-clés
   │
   ▼
retrieval.search(query, documents)
   │  BM25 + phrase matching + section-aware
   ▼
Top-5 passages avec scores
   │
   ▼
stratégie correspondant au type
   │
   ▼
Réponse + score de confiance
```

---

## 5. Stockage Cloud (`document_store.py`)

### 5.1 Architecture

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Upload UI       │───▶│  Supabase Storage│───▶│  Cache mémoire   │
│  (professeur.py) │    │  (bucket 'cours')│    │  (dict Python)   │
└──────────────────┘    └──────────────────┘    └──────────────────┘
                              │
                              ▼
                        ┌──────────────────┐
                        │  Métadonnées     │
                        │  (JSON dans le   │
                        │   bucket aussi)  │
                        └──────────────────┘
```

### 5.2 Modes de fonctionnement

| Mode | Condition | Comportement |
|------|-----------|-------------|
| **Cloud** | `SUPABASE_URL` + `SUPABASE_KEY` configurés | Persistance réelle dans Supabase |
| **Mémoire** | Supabase non configuré | Cache dictionnaire uniquement (perdu au redémarrage) |

### 5.3 Fonctions clés

| Fonction | Rôle |
|----------|------|
| `upload_pdf(file, filename)` | Upload + indexation |
| `sync_from_cloud()` | Restaure le cache mémoire au démarrage |
| `get_available_documents()` | Liste des documents indexés |
| `count_documents()` | Nombre total de documents |
| `is_cloud_configured()` | Vérifie si Supabase est actif |

---

## 6. Ré-indexation Automatique (`reindexer.py`)

Au démarrage, `auto_reindex_on_startup()` :

1. Vérifie la date de dernière vérification
2. Si > 24 h → liste les fichiers dans Supabase Storage
3. Compare avec l'index ChromaDB
4. Ré-indexe les nouveaux fichiers ou modifiés
5. Met à jour le cache mémoire
6. Retourne un rapport (nouveaux, mis à jour, erreurs)

---

## 7. Tests

### 7.1 Structure

```
tests/
├── unit/
│   └── test_non_llm_qa.py       # 67 tests — moteur non-LLM
├── integration/
│   ├── test_complex_questions.py # 62 tests — corpus multi-matières
│   └── test_legal_questions.py   # 60 tests — corpus juridique
├── regression/
│   ├── test_edge_cases.py       # Tests réindexeur, cas limites
│   └── test_security.py         # Tests token, cookie, rôles
└── functional/
    └── test_workflows.py        # Tests parcours complets
```

**Total : 307 tests**

### 7.2 Lancer les tests

```bash
pytest tests/                          # Tout
pytest tests/ -q --tb=short            # Mode silencieux
pytest tests/unit/test_non_llm_qa.py -v -k "test_strategy"  # Filtre
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
| `ADMIN_SECRET_CODE` | Non | `admin123` | Code pour créer un admin |

*\* Requis pour la persistance cloud — sans, le mode mémoire est utilisé*

---

## 9. Sécurité

- **Cookie** : signé HMAC-SHA256, clé séparée (`SESSION_SECRET`)
- **Mots de passe** : hashés SHA-256 (avec fallback bcrypt)
- **Rôles** : vérification côté serveur à chaque accès
- **Supabase** : clé stockée en variable d'environnement, jamais commitée
- **Bucket Storage** : en mode public pour la lecture Streamlit
- **Session** : nettoyée au logout (`clear_session_cookie` + suppression des clés)

---

## 10. Déploiement

### 10.1 Local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Éditer avec vos clés
streamlit run src/main.py
```

### 10.2 Streamlit Cloud

1. Push sur GitHub
2. Connecter sur [share.streamlit.io](https://share.streamlit.io)
3. Définir les secrets (`SUPABASE_URL`, `SUPABASE_KEY`, `SESSION_SECRET`, clés LLM)
4. Déployer

> Le bucket Supabase Storage (`cours`) doit être créé manuellement avant le premier upload.

---

## 11. Limitations Techniques

| Limitation | Cause | Solution future |
|------------|-------|-----------------|
| Pas d'OCR | Coût technique | Intégration Tesseract |
| PDF 10 Mo max | Limite Streamlit | Upload par chunk |
| 30 req/min Groq | Rate limit gratuit | Cache + file d'attente |
| ChromaDB mono-instance | Architecture simple | Passage à Qdrant/Pinecone |
| Transcription lente | Whisper local | API Whisper distante |

---

*Documentation générée pour eLearnBot v1.0.0*
