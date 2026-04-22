import os
from typing import Dict
import numpy as np
from models import SocialClassEnum, AgentSchema, LifePhaseEnum, LogCategoryEnum, EraEnum

SOCIAL_INTERACTION_RADIUS = 2
SOCIAL_LOG_COOLDOWN = 18
HOSTILE_CLASH_THRESHOLD = -65.0
HOSTILE_CLASH_BASE_PROB = 0.10
SOCIAL_MODE = os.getenv("PANOPTICON_SOCIAL_MODE", "full_llm").strip().lower()

POSITIVE_SOCIAL_EVENTS = [
    ("casual_chat", "had a casual chat"),
    ("small_talk", "exchanged small talk"),
    ("story_sharing", "shared personal stories"),
    ("joking", "laughed over jokes"),
    ("gossip", "exchanged local gossip"),
    ("cooperation_planning", "planned a cooperative move"),
    ("resource_tips", "shared resource gathering tips"),
    ("mutual_encouragement", "encouraged each other"),
]

TENSE_SOCIAL_EVENTS = [
    ("heated_debate", "got into a heated debate"),
    ("ideological_argument", "argued over their values"),
    ("territorial_dispute", "argued over nearby territory"),
    ("sarcastic_exchange", "traded sarcastic remarks"),
    ("passive_aggressive", "had a passive-aggressive exchange"),
    ("cold_shoulder", "gave each other the cold shoulder"),
]

ROMANTIC_SOCIAL_EVENTS = [
    ("flirt", "flirted"),
    ("romantic_banter", "exchanged playful romantic banter"),
    ("heart_to_heart", "had a heart-to-heart talk"),
    ("push_pull", "went through a romantic push-and-pull"),
    ("admiration", "showed open admiration"),
]

REPAIR_SOCIAL_EVENTS = [
    ("awkward_reconciliation", "attempted an awkward reconciliation"),
    ("apology", "offered an apology"),
    ("truce_talk", "held a careful truce talk"),
]


def _pick_event(rng, options):
    index = int(rng.integers(0, len(options)))
    return options[index]


def _count_close_friends(engine, agent_id: str, min_rel: float = 45.0) -> int:
    total = 0
    details = getattr(engine, "relationship_details", {})
    for key, detail in details.items():
        if agent_id not in key.split("::"):
            continue
        rel_val = float(detail.get("value", 0.0))
        if rel_val < min_rel:
            continue
        a_id, b_id = key.split("::")
        other_id = b_id if a_id == agent_id else a_id
        other = engine.agents.get(other_id)
        if other and other.is_alive:
            total += 1
    return total


def _violence_profile(engine, a: AgentSchema, b: AgentSchema):
    era = getattr(engine, "era", EraEnum.PREHISTORIC)
    era_factor = {
        EraEnum.PREHISTORIC: 0.85,
        EraEnum.ANCIENT: 1.0,
        EraEnum.MEDIEVAL: 1.2,
        EraEnum.MODERN: 1.1,
    }.get(era, 1.0)

    avg_bravery = (float(a.personality.bravery) + float(b.personality.bravery)) * 0.5
    avg_cunning = (float(a.personality.cunning) + float(b.personality.cunning)) * 0.5
    avg_kindness = (float(a.personality.kindness) + float(b.personality.kindness)) * 0.5
    aggression = max(0.0, (-avg_kindness * 0.7) + (max(0.0, avg_bravery) * 0.6) + (max(0.0, avg_cunning) * 0.5))

    clash_mult = max(0.35, min(2.2, era_factor * (0.8 + aggression)))
    lethal_mult = max(0.2, min(2.4, era_factor * (0.6 + aggression * 1.1)))
    allow_deadly = True
    return {"clash_mult": clash_mult, "lethal_mult": lethal_mult, "allow_deadly": allow_deadly}


def _rel_key(a: str, b: str) -> str:
    return "::".join(sorted([a, b]))


def _ensure_rel_detail(engine, key: str) -> Dict:
    if not hasattr(engine, "relationship_details"):
        engine.relationship_details = {}
    if key not in engine.relationship_details:
        base = float(engine.relationships.get(key, 0.0)) if hasattr(engine, "relationships") else 0.0
        engine.relationship_details[key] = {
            "friendship": base,
            "romance": 0.0,
            "value": base,
            "interactions": [],
            "last_tick": int(getattr(engine, "tick", 0)),
        }
    return engine.relationship_details[key]


def get_relationship(engine, a: str, b: str) -> float:
    key = _rel_key(a, b)
    if hasattr(engine, "relationship_details") and key in engine.relationship_details:
        detail = engine.relationship_details[key]
        return float(detail.get("value", engine.relationships.get(key, 0.0)))
    return float(engine.relationships.get(key, 0.0))


def add_relationship(engine, a: str, b: str, amount: float, relationship_type: str = "friendship", interaction_tag: str = ""):
    key = _rel_key(a, b)
    detail = _ensure_rel_detail(engine, key)

    field = "romance" if relationship_type == "romance" else "friendship"
    detail[field] = float(max(-100.0, min(100.0, float(detail.get(field, 0.0)) + amount)))

    combined = float(np.clip((detail.get("friendship", 0.0) * 0.65) + (detail.get("romance", 0.0) * 1.0), -100.0, 100.0))
    detail["value"] = combined
    detail["last_tick"] = int(getattr(engine, "tick", 0))

    if interaction_tag:
        interactions = list(detail.get("interactions", []))
        interactions.append(interaction_tag)
        detail["interactions"] = interactions[-8:]

    engine.relationships[key] = combined


def calc_social_class(engine, agent: AgentSchema) -> SocialClassEnum:
    """Determine social class based on houses, social leadership, alliances, and land control."""
    owned_houses = [h for h in engine.houses if h.owner_id == agent.id and not h.is_under_construction]
    if agent.partner_id:
        partner_houses = [h for h in engine.houses if h.owner_id == agent.partner_id and not h.is_under_construction]
        owned_houses.extend(partner_houses)

    owned_settlements = [s for s in engine.settlements if s.owner_id == agent.id]
    territory_total = sum(int(getattr(s, "territory_radius", 0)) for s in owned_settlements)
    alliance_count = len([aid for aid in agent.allies if aid in engine.agents and engine.agents[aid].is_alive])
    close_friends = _count_close_friends(engine, agent.id)

    if territory_total >= 12 and (close_friends >= 8 or alliance_count >= 5):
        return SocialClassEnum.ROYALTY
    if territory_total >= 7 and (close_friends >= 5 or alliance_count >= 3):
        return SocialClassEnum.NOBLE
    if territory_total >= 3 or close_friends >= 4:
        return SocialClassEnum.CITIZEN

    if owned_houses:
        max_level = max(h.level for h in owned_houses)
        if max_level >= 4:
            return SocialClassEnum.ROYALTY
        if max_level >= 3:
            return SocialClassEnum.NOBLE
        if max_level >= 2:
            return SocialClassEnum.CITIZEN
        return SocialClassEnum.PEASANT

    owns_settlement = bool(owned_settlements)
    if owns_settlement:
        return SocialClassEnum.CITIZEN
    return SocialClassEnum.NOMAD


def _crossed_threshold(old_rel: float, new_rel: float):
    if old_rel < 25 <= new_rel:
        return "acquaintances"
    if old_rel < 50 <= new_rel:
        return "friends"
    if old_rel < 75 <= new_rel:
        return "very_close"
    if old_rel > -25 >= new_rel:
        return "distant"
    if old_rel > -50 >= new_rel:
        return "hostile"
    return None


def _ensure_runtime_maps(engine):
    if not hasattr(engine, "social_pair_last_log"):
        engine.social_pair_last_log = {}
    if not hasattr(engine, "social_links"):
        engine.social_links = set()
    if not hasattr(engine, "relationship_details"):
        engine.relationship_details = {}


def process_social_interactions(engine):
    """
    Process social interactions for citizens within nearby radius.
    This does not require standing on the exact same tile.
    """
    mode = str(getattr(engine, "social_mode", SOCIAL_MODE)).lower()

    _ensure_runtime_maps(engine)
    rng = getattr(engine, "world_rng", np.random)
    alive_agents = [
        a for a in engine.agents.values()
        if a.is_alive and a.life_phase != LifePhaseEnum.BABY
    ]

    for i in range(len(alive_agents)):
        for j in range(i + 1, len(alive_agents)):
            a = alive_agents[i]
            b = alive_agents[j]
            dist = abs(a.x - b.x) + abs(a.y - b.y)
            if dist > SOCIAL_INTERACTION_RADIUS:
                continue

            pair_key = _rel_key(a.id, b.id)
            closeness = max(0.2, (SOCIAL_INTERACTION_RADIUS + 1 - dist) / (SOCIAL_INTERACTION_RADIUS + 1))
            avg_kindness = (a.personality.kindness + b.personality.kindness) / 2.0
            avg_sociability = (a.personality.sociability + b.personality.sociability) / 2.0
            avg_empathy = (a.personality.empathy + b.personality.empathy) / 2.0

            # Social vitals always recover from proximity, regardless of mode
            social_boost = 6.0 + (closeness * 9.0) + (max(0.0, avg_sociability) * 2.0)
            a.vitals.social = min(100.0, a.vitals.social + social_boost)
            b.vitals.social = min(100.0, b.vitals.social + social_boost)

            # In full_llm mode, skip detailed relationship/event processing
            if mode == "full_llm":
                continue


            old_rel = get_relationship(engine, a.id, b.id)
            rel_change = 1.0 + (closeness * 1.8) + (avg_kindness * 1.2) + (avg_empathy * 0.8) + (max(0.0, avg_sociability) * 0.6)

            can_build_romance = (
                a.life_phase in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT]
                and b.life_phase in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT]
                and a.gender != b.gender
            )

            age_gap = abs(int(a.age) - int(b.age))
            interaction_type = "casual_chat"
            interaction_label = "had a casual chat"

            # Determine detailed interaction flavor before applying relationship updates.
            if old_rel <= -20 and float(rng.random()) < 0.25:
                interaction_type, interaction_label = _pick_event(rng, REPAIR_SOCIAL_EVENTS)
                rel_change = abs(rel_change) * 0.45
            elif avg_kindness < -0.45 and float(rng.random()) < 0.24:
                interaction_type, interaction_label = _pick_event(rng, TENSE_SOCIAL_EVENTS)
                rel_change = -abs(rel_change) * 0.75
            elif can_build_romance and old_rel >= 30 and float(rng.random()) < 0.22:
                interaction_type, interaction_label = _pick_event(rng, ROMANTIC_SOCIAL_EVENTS)
                rel_change = abs(rel_change) * 1.1
            elif age_gap >= 420 and float(rng.random()) < 0.20:
                interaction_type = "mentoring"
                interaction_label = "had a mentoring exchange"
                rel_change = abs(rel_change) * 0.9
            elif float(rng.random()) < 0.14:
                interaction_type = "strategic_negotiation"
                interaction_label = "held a strategic negotiation"
                rel_change = abs(rel_change) * 0.65
            elif float(rng.random()) < 0.10:
                interaction_type = "awkward_silence"
                interaction_label = "shared an awkward silence"
                rel_change = abs(rel_change) * 0.2
            else:
                interaction_type, interaction_label = _pick_event(rng, POSITIVE_SOCIAL_EVENTS)

            add_relationship(engine, a.id, b.id, float(rel_change), relationship_type="friendship", interaction_tag=interaction_type)
            new_rel = get_relationship(engine, a.id, b.id)

            # Very hostile pairs can escalate into physical conflict at close range.
            if (
                a.is_alive
                and b.is_alive
                and dist <= 1
                and new_rel <= HOSTILE_CLASH_THRESHOLD
            ):
                violence = _violence_profile(engine, a, b)
                hostility_factor = min(1.0, abs(new_rel) / 100.0)
                clash_prob = (HOSTILE_CLASH_BASE_PROB + (0.20 * hostility_factor)) * float(violence.get("clash_mult", 1.0))
                clash_prob += 0.05 if avg_kindness < -0.55 else 0.0
                if float(rng.random()) < clash_prob:
                    a_power = 1.0 + max(0.0, float(a.personality.bravery)) * 0.9 + (float(a.vitals.energy) / 120.0) + (float(a.inventory.tools) * 0.08)
                    b_power = 1.0 + max(0.0, float(b.personality.bravery)) * 0.9 + (float(b.vitals.energy) / 120.0) + (float(b.inventory.tools) * 0.08)
                    win_roll = float(rng.random())
                    a_win_prob = a_power / max(0.2, (a_power + b_power))

                    winner = a if win_roll < a_win_prob else b
                    loser = b if winner is a else a

                    add_relationship(engine, a.id, b.id, -8.0, relationship_type="friendship", interaction_tag="violent_clash")
                    engine.add_log(
                        LogCategoryEnum.SOCIAL,
                        f"⚔️ Violent clash: {a.name} and {b.name} fought after prolonged hostility.",
                        interaction_type="violent_clash",
                        participant_ids=[a.id, b.id],
                        relationship_change=-8.0,
                        source_agent_id=winner.id,
                    )

                    # Not every clash is lethal, but severe hostility can end in death.
                    lethal_prob = (0.35 + (0.30 * hostility_factor)) * float(violence.get("lethal_mult", 1.0))
                    lethal_prob = float(min(0.98, max(0.0, lethal_prob)))
                    if bool(violence.get("allow_deadly", True)) and float(rng.random()) < lethal_prob and loser.is_alive:
                        engine._kill_agent(loser, f"killed in hostile clash with {winner.name}")
                        engine.add_log(
                            LogCategoryEnum.SOCIAL,
                            f"☠️ Deadly outcome: {winner.name} killed {loser.name} in a hostile clash.",
                            interaction_type="deadly_clash",
                            participant_ids=[winner.id, loser.id],
                            relationship_change=-20.0,
                            source_agent_id=winner.id,
                        )
                        engine.social_pair_last_log[pair_key] = engine.tick
                        continue

            if can_build_romance:
                romance_delta = max(0.0, new_rel - 35.0) * 0.015
                romance_delta += max(0.0, avg_empathy) * 0.15
                romance_delta += max(0.0, avg_sociability) * 0.08
                if avg_kindness < -0.45:
                    romance_delta *= 0.4
                if interaction_type in {"flirt", "romantic_banter", "heart_to_heart", "push_pull", "admiration"}:
                    romance_delta += 0.35
                if float(rng.random()) < 0.35:
                    romance_tag = "romantic_bonding"
                    if interaction_type in {"push_pull"}:
                        romance_tag = "romantic_push_pull"
                    elif interaction_type in {"heart_to_heart", "admiration"}:
                        romance_tag = "romantic_deepening"
                    add_relationship(engine, a.id, b.id, float(romance_delta), relationship_type="romance", interaction_tag=romance_tag)

            if new_rel >= 15:
                engine.social_links.add(pair_key)

            last_log_tick = engine.social_pair_last_log.get(pair_key, -9999)
            if engine.tick - last_log_tick < SOCIAL_LOG_COOLDOWN:
                continue

            threshold_event = _crossed_threshold(old_rel, new_rel)
            message = None

            if threshold_event == "acquaintances":
                message = f"🤝 After they {interaction_label}, {a.name} & {b.name} became acquaintances."
                interaction_type = "became_acquaintances"
            elif threshold_event == "friends":
                message = f"😊 After they {interaction_label}, {a.name} & {b.name} became friends."
                interaction_type = "became_friends"
            elif threshold_event == "very_close":
                message = f"💕 After they {interaction_label}, {a.name} & {b.name} became very close allies."
                interaction_type = "became_close"
            elif threshold_event == "distant":
                message = f"😶 After they {interaction_label}, {a.name} & {b.name} started drifting apart."
                interaction_type = "drifted_apart"
            elif threshold_event == "hostile":
                message = f"⚠️ After they {interaction_label}, tension rose between {a.name} and {b.name}."
                interaction_type = "tension_rising"
            elif rel_change < 0:
                message = f"💢 {a.name} and {b.name} {interaction_label}."
                interaction_type = f"negative_{interaction_type}"
            elif a.vitals.social < 45 or b.vitals.social < 45:
                message = f"🗣️ {a.name} and {b.name} {interaction_label} to ease loneliness."
                interaction_type = f"lonely_{interaction_type}"
            elif dist == 0:
                message = f"🫂 {a.name} and {b.name} {interaction_label} face-to-face."
                interaction_type = f"close_{interaction_type}"
            else:
                # Always emit periodic nearby interaction logs so social activity
                # remains visible even when citizens are not on the same tile.
                message = f"💬 {a.name} and {b.name} {interaction_label} nearby."
                interaction_type = f"nearby_{interaction_type}"

            if message:
                engine.add_log(
                    LogCategoryEnum.SOCIAL, 
                    message,
                    interaction_type=interaction_type,
                    participant_ids=[a.id, b.id],
                    relationship_change=float(rel_change),
                    source_agent_id=a.id
                )
                engine.social_pair_last_log[pair_key] = engine.tick
