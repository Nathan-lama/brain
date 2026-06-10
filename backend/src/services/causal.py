import uuid

import networkx as nx
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination
from pgmpy.models import DiscreteBayesianNetwork
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CausalEdge, Node, NodeType


class CausalService:
    @staticmethod
    async def get_causal_graph(db: AsyncSession) -> tuple[list[Node], list[CausalEdge]]:
        """Fetches all empirical nodes and causal edges."""
        # 1. Fetch empirical nodes
        nodes_res = await db.execute(
            select(Node).filter(Node.type == NodeType.EMPIRIQUE)
        )
        nodes = nodes_res.scalars().all()

        # 2. Fetch causal edges
        edges_res = await db.execute(select(CausalEdge))
        edges = edges_res.scalars().all()

        return nodes, edges

    @staticmethod
    async def add_causal_edge(
        db: AsyncSession, cause_id: uuid.UUID, effect_id: uuid.UUID, strength: float
    ) -> CausalEdge:
        """Adds a causal edge, checking for cycle (DAG) and type constraints."""
        # 1. Verify both nodes are empirical
        res_cause = await db.execute(select(Node).filter(Node.id == cause_id))
        cause = res_cause.scalar_one_or_none()
        res_effect = await db.execute(select(Node).filter(Node.id == effect_id))
        effect = res_effect.scalar_one_or_none()

        if not cause or cause.type != NodeType.EMPIRIQUE:
            raise ValueError("The cause node must exist and be of type 'empirique'.")
        if not effect or effect.type != NodeType.EMPIRIQUE:
            raise ValueError("The effect node must exist and be of type 'empirique'.")

        # 2. Fetch existing edges to construct a networkx DAG and test for cycles
        edges_res = await db.execute(select(CausalEdge))
        existing_edges = edges_res.scalars().all()

        G = nx.DiGraph()
        for edge in existing_edges:
            G.add_edge(edge.cause_id, edge.effect_id)

        # Add the proposed edge
        G.add_edge(cause_id, effect_id)

        if not nx.is_directed_acyclic_graph(G):
            raise ValueError(
                "Adding this causal link would create a cycle (violating DAG constraint)."
            )

        # 3. Save edge
        new_edge = CausalEdge(cause_id=cause_id, effect_id=effect_id, strength=strength)
        db.add(new_edge)
        await db.flush()
        return new_edge

    @staticmethod
    async def delete_causal_edge(db: AsyncSession, edge_id: uuid.UUID) -> bool:
        """Deletes a causal edge."""
        await db.execute(delete(CausalEdge).filter(CausalEdge.id == edge_id))
        return True

    @staticmethod
    def _build_bayesian_network(
        nodes: list[Node], edges: list[CausalEdge], interventions: dict[uuid.UUID, int]
    ) -> tuple[DiscreteBayesianNetwork, dict[uuid.UUID, float]]:
        """
        Builds a pgmpy DiscreteBayesianNetwork.
        If a node is in interventions, its incoming edges are severed and its CPD is set to do(X=x).
        """
        interventions = interventions or {}

        # 1. Define edges in the graph (excluding incoming to intervened nodes)
        dag_edges = []
        for edge in edges:
            if edge.effect_id not in interventions:
                dag_edges.append((edge.cause_id, edge.effect_id))

        model = DiscreteBayesianNetwork(dag_edges)

        # Add any isolated empirical nodes
        model.add_nodes_from([n.id for n in nodes])

        # Map to find node weights easily
        node_confidences = {n.id: n.weight for n in nodes}

        # Strengths map by effect node
        # effect_id -> list of (cause_id, strength)
        incoming_strengths = {}
        for edge in edges:
            incoming_strengths.setdefault(edge.effect_id, []).append(
                (edge.cause_id, edge.strength)
            )

        # 2. Add CPDs for each node
        for node in nodes:
            node_id = node.id
            confidence = max(0.0, min(1.0, node_confidences.get(node_id, 0.5)))

            if node_id in interventions:
                # Intervened node: no parents, forced to 0 or 1
                val = float(interventions[node_id])
                cpd = TabularCPD(
                    variable=node_id, variable_card=2, values=[[1.0 - val], [val]]
                )
                model.add_cpds(cpd)
            else:
                parents = list(model.get_parents(node_id))
                if not parents:
                    # Root node (no parents): CPD values are [1 - conf, conf]
                    cpd = TabularCPD(
                        variable=node_id,
                        variable_card=2,
                        values=[[1.0 - confidence], [confidence]],
                    )
                    model.add_cpds(cpd)
                else:
                    # Parents exist: Noisy-OR with leak based on target's own confidence
                    k = len(parents)
                    # Get strengths for this node's parents
                    parent_strengths = dict(incoming_strengths.get(node_id, []))

                    values = []
                    # pgmpy order: last evidence variable changes fastest
                    for j in range(2**k):
                        parent_states = []
                        for i in range(k):
                            # Extract bit matching pgmpy's evidence order
                            bit = (j >> (k - 1 - i)) & 1
                            parent_states.append(bit)

                        # Noisy-OR leak model formula:
                        # P(Y=1 | parents) = 1 - (1 - target_conf) * prod_i( (1 - w_i)**x_i )
                        prod = 1.0
                        for i, parent_id in enumerate(parents):
                            w = parent_strengths.get(parent_id, 0.0)
                            x = parent_states[i]
                            prod *= (1.0 - w) ** x

                        p_y_1 = 1.0 - (1.0 - confidence) * prod
                        values.append(p_y_1)

                    cpd_values = [[1.0 - val for val in values], values]

                    cpd = TabularCPD(
                        variable=node_id,
                        variable_card=2,
                        values=cpd_values,
                        evidence=parents,
                        evidence_card=[2] * k,
                    )
                    model.add_cpds(cpd)

        # Validate structure and CPD alignments
        model.check_model()
        return model, node_confidences

    @staticmethod
    async def compute_credences(
        db: AsyncSession, interventions: dict[uuid.UUID, int] = None
    ) -> dict[uuid.UUID, float]:
        """
        Computes marginal probabilities (credences) for all empirical nodes
        using pgmpy variable elimination.
        """
        nodes, edges = await CausalService.get_causal_graph(db)
        if not nodes:
            return {}

        model, _ = CausalService._build_bayesian_network(nodes, edges, interventions)
        inference = VariableElimination(model)

        credences = {}
        for node in nodes:
            nid = node.id
            if interventions and nid in interventions:
                credences[nid] = float(interventions[nid])
            else:
                try:
                    res = inference.query(variables=[nid], show_progress=False)
                    credences[nid] = round(float(res.values[1]), 4)
                except Exception:
                    # Fallback to database weight on inference failure
                    credences[nid] = node.weight

        return credences

    @staticmethod
    async def run_whatif(
        db: AsyncSession, interventions: dict[uuid.UUID, int]
    ) -> tuple[dict[uuid.UUID, float], list[str]]:
        """
        Runs a whatif scenario comparing baseline credences with intervened credences.
        Returns (intervened_credences, readable_effects_list).
        """
        nodes, edges = await CausalService.get_causal_graph(db)
        if not nodes:
            return {}, []

        # 1. Compute baseline credences (no interventions)
        baseline_model, node_conf = CausalService._build_bayesian_network(
            nodes, edges, {}
        )
        baseline_inference = VariableElimination(baseline_model)
        baseline_credences = {}
        for node in nodes:
            try:
                res = baseline_inference.query(variables=[node.id], show_progress=False)
                baseline_credences[node.id] = round(float(res.values[1]), 4)
            except Exception:
                baseline_credences[node.id] = node.weight

        # 2. Compute intervened credences
        intervened_credences = await CausalService.compute_credences(db, interventions)

        # 3. Build readable text descriptions
        node_map = {n.id: n for n in nodes}
        readable_effects = []

        # List interventions in text
        intervention_texts = []
        for nid, val in interventions.items():
            node_text = node_map[nid].text if nid in node_map else str(nid)
            state_text = "haute/vraie" if val == 1 else "basse/fausse"
            intervention_texts.append(f"do({node_text}={state_text})")

        header = "Si " + " et ".join(intervention_texts) + " :"
        readable_effects.append(header)

        # Show changes in downstream nodes (only show significant differences, e.g. > 0.001)
        changes_found = False
        for node in nodes:
            nid = node.id
            if nid in interventions:
                continue  # skip intervened nodes themselves

            p_base = baseline_credences.get(nid, node.weight)
            p_inter = intervened_credences.get(nid, node.weight)

            if abs(p_base - p_inter) > 0.001:
                node_text = node.text
                readable_effects.append(
                    f"  - {node_text} : credence estimée {p_base:.2f} ➜ {p_inter:.2f}"
                )
                changes_found = True

        if not changes_found:
            readable_effects.append("  - aucun effet significatif détecté en aval.")

        return intervened_credences, readable_effects
