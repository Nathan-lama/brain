# Second Brain - Cohérence Argumentative

Ce projet est un "second brain" de cohérence argumentative, conçu pour fonctionner à 100% en local.

## Structure du Projet

Le projet est organisé sous forme de monorepo :

- `/infra` : Fichiers de configuration de l'infrastructure (Docker Compose avec Postgres + pgvector et Ollama).
- `/backend` : API FastAPI en Python 3.12+ gérée par `uv`.
- `/frontend` : Application Next.js (App Router, Tailwind, TypeScript, TanStack Query et shadcn/ui).
- `.env` : Configuration des variables d'environnement.

---

## Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Python 3.12+](https://www.python.org/)
- [uv](https://github.com/astral-sh/uv) (installé via `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`)
- [Node.js 18+](https://nodejs.org/)

---

## Lancement Rapide

### 1. Démarrer l'infrastructure
Dans le dossier `/infra`, lancez les conteneurs de base de données et d'Ollama :
```bash
docker compose -f infra/docker-compose.yml up -d
```

### 2. Télécharger les modèles locaux sur Ollama
Exécutez les commandes suivantes pour installer le modèle de chat Qwen2.5 et le modèle d'embeddings :
```bash
# Modèle de chat (Qwen 2.5 7B Instruct)
docker exec -it ollama ollama pull qwen2.5:7b-instruct

# Modèle d'embeddings
docker exec -it ollama ollama pull nomic-embed-text
```

### 3. Lancer le Backend
Allez dans le dossier `/backend`, installez les dépendances et lancez l'application :
```bash
cd backend
uv sync
uv run uvicorn src.main:app --reload --port 8000
```
Le backend tourne alors sur : [http://localhost:8000](http://localhost:8000)

### 4. Lancer le Frontend
Allez dans le dossier `/frontend`, installez les paquets et démarrez le serveur Next.js en mode de développement :
```bash
cd frontend
npm install
npm run dev
```
Le site est disponible sur : [http://localhost:3000](http://localhost:3000)

---

## Vérification et Qualité

### Backend
- **Tests unitaires** : `uv run pytest`
- **Linting** : `uv run ruff check`

### URLs de Test
- Santé du Backend : `curl http://localhost:8000/health` -> `{"status":"ok"}`
- Page d'accueil : [http://localhost:3000](http://localhost:3000) (affiche "backend: ok")
