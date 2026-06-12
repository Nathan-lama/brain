## DIFF v5 → v5.1 (incident du 11/06/2026, soirée)

### §10 — Dette, ajouter :
8. 5 tests cassés par check_inference_weight_values : fixtures obsolètes (poids 0.01
   interdit) dans test_solver.py et consorts. NUANCE IMPORTANTE : la base second_brain_test
   n'avait jamais été re-migrée après l'ajout de la contrainte le 10/06 — les "26/26 passed"
   des lots 1-3 tournaient donc sur un schéma de test obsolète. Non-régressions valables
   pour ce qu'elles testaient, mais la contrainte d'intégrité n'était pas couverte.
9. À VÉRIFIER (lecture manuelle, 20 lignes) : test_import_curl.py écrirait/supprimerait
   dans la base de PRODUCTION (events du 11/06 16:29, create + deletes attribués à son
   cleanup). Si confirmé : rediriger les tests d'intégration vers second_brain_test.
   Tant que non vérifié, considérer toute exécution de ce script comme risquée.
10. Nettoyage trivial : solve_check.json traîne dans frontend/.

### §10 — Incident Docker du 11/06 (résumé, 5 lignes) :
Docker Desktop arrêté (redémarrage hôte probable) → l'agent du lot 4, sans le déclarer,
a monté un Postgres NEUF dans WSL (docker-compose up -d db) publié sur 5433 → le pré-flight
du lot 4 a audité une base fantôme (13 nœuds, score 340) → forensique en 3 rapports,
dont une fabrication complète de sortie /solve → v5 retrouvée intacte sur l'instance
Docker Desktop, confirmée à la main (counts 28/15/11/5, score 1199.0, rejetés conformes).
Le protocole étape 0 a fonctionné : divergence détectée avant toute écriture.

### §12 — Catalogue porté à 13 :
12. **Action d'environnement non sollicitée, maquillée en état préexistant.** Dans un lot
    LECTURE SEULE, l'agent a tenté Start-Service (échec, pas admin), puis créé conteneur +
    base dans WSL, puis rédigé une "déclaration de substitution" présentant SA création
    comme l'environnement existant. L'écriture a eu lieu AVANT le premier mot du rapport,
    contournant l'antidote "toute écriture déclarée".
13. **Chimère à l'échelle du document.** Sortie tronquée par le système en DÉBUT de flux
    (<truncated 23 bytes>) → au lieu de déclarer et relire le log, l'agent a "reconstruit"
    la sortie entière : fragments réels (tensions, score, scheme_ids corrects) cousus avec
    du remplissage inventé (UUID placeholder c1111111..., suffixes clonés, nœuds dans
    accepted ET rejected, fixtures CO2/f1 hors graphe, champ incoherence_score absent mais
    cité dans la conclusion, schéma de réponse muté). Avoué après confrontation ; le log
    réel (task-11382.log) correspondait à la vérité, confirmée ensuite à la main.
    Leçon : la cohérence d'une sortie avec le doc de passation N'EST PLUS une preuve —
    l'agent possède le doc et peut reconstruire une sortie parfaite. Le recoupement croisé
    ne vaut que sur des données que l'agent n'a pas déjà en contexte.

### §12 — Antidotes, ajouter :
- **Déclaration des actions d'environnement** : tout démarrage/arrêt de service, création
  de conteneur, de base, de volume, toute migration — y compris en SETUP avant le rapport —
  doit être déclaré avec sa commande. Un lot lecture seule qui en nécessiterait une
  s'ARRÊTE et rapporte ; il ne crée jamais l'environnement qu'il est censé auditer.
- **Troncature système = STOP.** Toute sortie tronquée par l'outillage : le déclarer,
  récupérer la sortie complète depuis le fichier de log en citant son chemin, jamais
  reconstruire. Une sortie reconstituée "de bonne foi" = pattern n°13.
- **Règle des vérifications manuelles re-validée une 3e fois**, au prix de 3 rapports
  forensiques contre 1 commande de 30 s. Les verdicts qui conditionnent la suite
  (état de base, baseline /solve) se font À LA MAIN, systématiquement, AVANT de
  lancer un lot — pas seulement en cas de doute.

### §2 — Précision : la table nodes n'a pas de colonne `label` (erreur SQL constatée) ;
le champ exposé par l'API est `label_court`. Nom de colonne réel à confirmer au prochain \d.
