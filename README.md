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

---

## Dérivation de l'Engagement

Le système calcule de manière autonome et déterministe un **palier d'engagement dérivé** pour chaque conclusion logique, par propagation en chaîne depuis les prémisses sources.

### 1. Règle de Dérivation (Theophrastus / Weakest Link)
Pour toute conclusion $N$ issue d'une ou plusieurs inférences $I$:

$$derive(N) = \max_{I} \left( \text{clamp}( \min_{P \in \text{premises}(I)} (\text{rang\_effectif}(P)) - \text{malus}(I.\text{strength}), 1, 5 ) \right)$$

Où :
* **rang_effectif(P)** = $derive(P)$ si $P$ est lui-même issu d'une inférence, sinon son palier manuel.
* **Malus par force d'inférence** :
  * Déductif (`deductif`) = `0`
  * Défaisable Fort (`defaisable_fort`) = `1`
  * Défaisable Faible (`defaisable_faible`) = `2`

*Le résultat est borné (clampé) strictement entre 1 (spéculatif) et 5 (certain).*

### 2. Choix de Conception : Non-accumulation
Conformément aux problèmes ouverts en théorie de l'argumentation, nous assumons de ne pas accumuler la force d'arguments convergents vers une même conclusion. Une conclusion reçoit la force du meilleur argument (max de ses inférences directes), sans addition ou sur-pondération quantitative.

### 3. Sur-engagement et Sous-engagement
Le palier manuel saisi par l'utilisateur n'est jamais écrasé automatiquement. C'est l'écart (gap) qui fournit l'information critique :
* **Sur-engagement** : Si le palier manuel saisi est strictement supérieur au palier dérivé ($\text{manuel} > \text{dérivé}$). Le nœud est marqué avec un badge orange et l'écart est affiché pour inviter à la prudence.
* **Sous-engagement** : Si le palier manuel saisi est strictement inférieur au palier dérivé ($\text{manuel} < \text{dérivé}$). Cela traduit une attitude prudente de la part de l'utilisateur, ce qui n'est pas problématique et ne l'alerte donc pas.
