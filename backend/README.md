# Second Brain Backend

FastAPI application running on port 8000.

## Solver Properties: Quasi-Inviolability of Deductive Inferences
In the coherence solver:
- Node ranks (unary preferences) range from 1 (`speculatif`) to 5 (`certain`).
- Deductive inferences (`DEDUCTIF`) are assigned a logical weight of 5.0.
- Propriété structurelle : avec un rang maximum de 5 et un poids déductif de 5.0, le fait de réviser les prémisses plutôt que de violer une inférence déductive est un comportement émergent de la structure de coûts dans tous les cas d'inégalité stricte. Le cas dégénéré d'égalité exacte est tranché explicitement dans le même sens par un tie-break déterministe (DEDUCTIVE_TIE_BREAK = 1, garanti par la garde DEDUCTIVE_TIE_BREAK * n_deductif < SCALE * 1.0 dans solver.py), choix philosophique assumé : à mérite égal, préserver la déduction. Cette propriété est garantie par test_quinian_static_invariant et test_quinian_tie_break.
