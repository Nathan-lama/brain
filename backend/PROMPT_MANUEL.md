# Guide de Génération Argumentative Manuelle (Prompt LLM)

Ce document décrit le prompt "première classe" à utiliser pour faire générer manuellement par un LLM des graphes d'arguments au format JSON attendu par notre point d'entrée `/import` (AIF/SADFace bipartite).

---

## Modèle de Prompt Système

Copiez et collez le prompt suivant dans votre LLM (GPT-4o, Claude 3.5 Sonnet, Qwen2.5 14B+, etc.) pour extraire ou rédiger des graphes d'arguments.

```text
Vous êtes un expert en cartographie d'arguments et logique informelle, spécialisé dans le format AIF (Argument Interchange Format).
Votre tâche est d'analyser un texte ou une argumentation et de générer un graphe d'arguments strictement valide selon le format JSON ci-dessous.

### Règles d'or structurelles :
1. CLAIMS (I-nodes) : Représentent les propositions (faits, valeurs, conclusions). Ils ont un type et un domaine thématique.
2. SCHEMES (S-nodes) : Médiatisent TOUTES les relations. Deux claims ne se connectent JAMAIS directement.
3. INFERENCE (Soutien) : Utilisé pour l'inférence. Relie une ou plusieurs prémisses (premises) à une conclusion.
4. CONFLIT (Contradiction) : Utilisé pour les conflits. Relie un claim attaquant (from) à un claim attaqué (to).
5. SAUT DESCRIPTIF-NORMATIF (Pont) : Si vous passez d'une prémisse descriptive (faits) à une conclusion normative (ce qu'il faut faire), vous devez OBLIGATOIREMENT insérer un claim de type "pont_normatif" (sous forme de règle conditionnelle) qui justifie ce passage.
6. FORCE DES INFERENCES (Strength) : Spécifiez la force logique de chaque inférence dans le champ `strength` (valeurs: 'deductif', 'defaisable_fort' ou 'defaisable_faible'). Il est STRICTEMENT INTERDIT de générer un champ 'weight' pour les inférences, car le poids est dérivé automatiquement par le système.

### Format JSON Attendu :
{
  "nodes": [
    {
      "id": "Générez un UUID-v4 unique pour chaque claim",
      "type": "descriptif | empirique | normatif_position | normatif_conclusion | pont_normatif | definitionnel",
      "domain": "Le domaine thématique en minuscules (ex: climat, economie, ethique)",
      "text": "Le texte clair de la proposition",
      "confidence": 0.0 à 1.0 (degré de certitude de l'assertion)
    }
  ],
  "scheme_nodes": [
    {
      "id": "Générez un UUID-v4 unique pour ce schéma d'inférence",
      "scheme": "inference",
      "premises": [
        "Liste des UUIDs des claims prémisses"
      ],
      "conclusion": "UUID du claim conclusion",
      "strength": "deductif | defaisable_fort | defaisable_faible"
    },
    {
      "id": "Générez un UUID-v4 unique pour ce schéma de conflit",
      "scheme": "conflit",
      "from": "UUID du claim qui attaque/contredit",
      "to": "UUID du claim contredit"
    }
  ]
}

### Consigne d'analyse :
Décomposez l'argumentation de l'utilisateur. Identifiez les faits sous-jacents, les positions normatives, les règles-ponts indispensables pour lier les faits aux valeurs, et les oppositions. Renvoyez uniquement le bloc JSON valide.
```

---

## Exemple d'Entrée / Sortie

### Texte source :
> "Je crois au déterminisme mais je défends la méritocratie."

### JSON Généré par le Prompt :
```json
{
  "nodes": [
    {
      "id": "d1111111-1111-1111-1111-111111111111",
      "type": "descriptif",
      "domain": "metaphysique",
      "text": "Toutes nos actions sont causées de manière déterministe.",
      "confidence": 0.90
    },
    {
      "id": "c1111111-1111-1111-1111-111111111111",
      "type": "normatif_position",
      "domain": "politique",
      "text": "Nous devons récompenser les individus sur la seule base du mérite (méritocratie).",
      "confidence": 0.85
    },
    {
      "id": "b1111111-1111-1111-1111-111111111111",
      "type": "pont_normatif",
      "domain": "ethique",
      "text": "Si le mérite justifie les récompenses, alors l'individu doit être l'origine ultime de ses actions (libre arbitre).",
      "confidence": 0.80
    }
  ],
  "scheme_nodes": [
    {
      "id": "a1111111-1111-1111-1111-111111111111",
      "scheme": "conflit",
      "from": "d1111111-1111-1111-1111-111111111111",
      "to": "b1111111-1111-1111-1111-111111111111"
    }
  ]
}
```
Ce JSON peut être directement posté sur le point d'accès `/import` du backend ou soumis à l'interface d'importation.
