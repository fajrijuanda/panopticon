import json
import os
import requests
from models import AgentSchema, LifePhaseEnum

LLM_BASE_URL = os.getenv("PANOPTICON_LLM_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_EXPLICIT_ENDPOINT = os.getenv("PANOPTICON_LLM_ENDPOINT", "").strip()


def _read_timeout() -> float | None:
    raw = os.getenv("PANOPTICON_LLM_TIMEOUT_SECONDS", "600").strip().lower()
    if raw in {"", "none", "off", "false", "0"}:
        return None
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 600.0


OLLAMA_TIMEOUT_SECONDS = _read_timeout()
OLLAMA_RETRIES = max(0, int(os.getenv("PANOPTICON_LLM_RETRIES", "1")))
FALLBACK_MODEL = os.getenv("PANOPTICON_LLM_FALLBACK_MODEL", "qwen2.5:1.5b")
UNAVAILABLE_MODELS: set[str] = set()
UNAVAILABLE_MODEL_WARNED: set[str] = set()


def _get_candidate_endpoints() -> list[str]:
    if LLM_EXPLICIT_ENDPOINT:
        return [LLM_EXPLICIT_ENDPOINT]

    endpoints = [
        f"{LLM_BASE_URL}/api/generate",
        f"{LLM_BASE_URL}/api/chat",
        f"{LLM_BASE_URL}/v1/chat/completions",
    ]

    # Keep order while deduplicating.
    seen = set()
    deduped = []
    for endpoint in endpoints:
        if endpoint in seen:
            continue
        seen.add(endpoint)
        deduped.append(endpoint)
    return deduped


def _build_request_payload(endpoint: str, model: str, prompt: str) -> dict:
    if endpoint.endswith("/api/chat"):
        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False,
        }

    if endpoint.endswith("/v1/chat/completions"):
        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }

    # Default Ollama generate payload.
    return {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
    }


def _fallback_action(reason: str) -> dict:
    return {
        "thought": reason,
        "move_x": 0,
        "move_y": 0,
        "action": "idle",
    }


def _is_small_model(model: str) -> bool:
    lowered = (model or "").lower()
    return any(tag in lowered for tag in ("1.5b", "1.3b", "1b", "0.5b"))


def _heuristic_fallback_action(agent: AgentSchema, engine, reason: str) -> dict:
    """Best-effort action for when the model response is invalid/timeouts.

    This keeps agents responsive (especially for small models) instead of freezing in idle.
    """
    vision_radius = engine.get_vision_radius(agent) if hasattr(engine, "get_vision_radius") else 8
    target_resource = None
    best_dist = 10**9

    # Prioritize immediate survival when possible.
    urgent_food = float(getattr(agent.vitals, "hunger", 0.0)) < 35.0
    urgent_hydration = float(getattr(agent.vitals, "hydration", 100.0)) < 45.0

    for resource in getattr(engine, "resources", []):
        dist = abs(resource.x - agent.x) + abs(resource.y - agent.y)
        if dist > vision_radius:
            continue

        rtype = getattr(getattr(resource, "type", None), "value", "")
        if urgent_food and rtype not in {"food", "fish", "crop", "fruit", "pig", "cow", "chicken"}:
            continue
        if urgent_hydration and rtype not in {"food", "fish", "fruit", "herb", "crop"}:
            continue

        if dist < best_dist:
            best_dist = dist
            target_resource = resource

    if target_resource is not None:
        tx, ty = int(target_resource.x), int(target_resource.y)
        dx = 0 if tx == agent.x else (1 if tx > agent.x else -1)
        dy = 0 if ty == agent.y else (1 if ty > agent.y else -1)
        return {
            "thought": f"{reason} I will move toward nearby resources.",
            "move_x": dx,
            "move_y": dy,
            "action": "moving",
        }

    # Exploration fallback when no visible target.
    direction_cycle = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, -1)]
    idx = (int(getattr(engine, "tick", 0)) + sum(ord(ch) for ch in str(getattr(agent, "id", "a")))) % len(direction_cycle)
    dx, dy = direction_cycle[idx]
    return {
        "thought": f"{reason} I will explore nearby tiles.",
        "move_x": dx,
        "move_y": dy,
        "action": "moving",
    }


def _extract_llm_text(data: dict) -> str | dict | None:
    if not isinstance(data, dict):
        return None

    # Ollama-style success payload.
    if "response" in data:
        return data["response"]

    # OpenAI-compatible payloads or custom wrappers.
    if isinstance(data.get("choices"), list) and data["choices"]:
        choice0 = data["choices"][0]
        if isinstance(choice0, dict):
            if "text" in choice0:
                return choice0["text"]
            message = choice0.get("message")
            if isinstance(message, dict):
                return message.get("content")

    for key in ("content", "output", "output_text", "text", "result"):
        if key in data:
            return data[key]

    return None


def _parse_action_payload(raw: str | dict) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise ValueError("Unsupported LLM payload type")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Some providers prepend text around JSON; keep best-effort extraction.
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def query_llm_for_action(agent: AgentSchema, context_memories: list, engine) -> dict:
    model = engine.get_agent_model(agent.id) if hasattr(engine, "get_agent_model") else engine.active_model
    compact_mode = _is_small_model(model)

    if agent.life_phase == LifePhaseEnum.BABY:
        return {"thought": "I am too young to think.", "move_x": 0, "move_y": 0, "action": "idle"}

    vision_radius = engine.get_vision_radius(agent) if hasattr(engine, "get_vision_radius") else 8

    nearby_res = []
    for resource in engine.resources:
        if abs(resource.x - agent.x) + abs(resource.y - agent.y) <= vision_radius:
            nearby_res.append(f"{resource.type.value} at ({resource.x},{resource.y})")
    resource_context = ", ".join(nearby_res) if nearby_res else "None nearby"

    current_terrain = "unknown"
    if 0 <= agent.x < engine.map_size and 0 <= agent.y < engine.map_size:
        current_terrain = engine.terrain[agent.y][agent.x]

    nearby_agents = []
    for other_id, other_agent in engine.agents.items():
        if other_id == agent.id or not other_agent.is_alive:
            continue
        distance = abs(other_agent.x - agent.x) + abs(other_agent.y - agent.y)
        if distance <= vision_radius:
            relation = int(engine.get_relationship(agent.id, other_id))
            nearby_agents.append(
                f"{other_agent.name} (ID:{other_id}, {other_agent.gender.value}, age {other_agent.age}, dist {distance}, rel {relation})"
            )
    people_context = ", ".join(nearby_agents) if nearby_agents else "No one nearby"

    memory_summary = engine.get_agent_memory_summary(agent.id) if hasattr(engine, "get_agent_memory_summary") else {}
    remembered_spots = memory_summary.get("resource_spots", [])
    remembered_tiles = memory_summary.get("tile_notes", [])
    remembered_events = memory_summary.get("recent_events", [])

    remembered_resource_context = "; ".join(
        f"{spot['type']} at {spot['coord']} (seen {spot['seen_count']}x, {spot['age']} ticks ago)"
        for spot in remembered_spots
    ) if remembered_spots else "No remembered resource hotspots"

    remembered_tile_context = "; ".join(
        f"tile {note['coord']} terrain={note['terrain']} visits={note['visits']} fertility_hint={note['fertility_hint']} livestock_hint={note['livestock_hint']}"
        for note in remembered_tiles
    ) if remembered_tiles else "No learned terrain suitability yet"

    remembered_event_context = "; ".join(remembered_events) if remembered_events else "No recent notable events"

    owned_settlement = None
    for settlement in engine.settlements:
        if settlement.owner_id == agent.id:
            owned_settlement = settlement
            break

    if owned_settlement:
        settlement_context = (
            f"You own settlement at ({owned_settlement.x},{owned_settlement.y}), radius {owned_settlement.territory_radius}. "
            "You may defend or expand it."
        )
    else:
        settlement_context = "You are nomadic and may claim a new territory if strategic."

    nearby_claims = []
    for settlement in engine.settlements:
        distance = abs(settlement.x - agent.x) + abs(settlement.y - agent.y)
        if distance <= 12:
            owner = engine.agents.get(settlement.owner_id)
            owner_name = owner.name if owner and owner.is_alive else settlement.owner_id
            nearby_claims.append(
                f"{owner_name}(ID:{settlement.owner_id}) at ({settlement.x},{settlement.y}) radius {settlement.territory_radius}, dist {distance}"
            )
    territory_context = ", ".join(nearby_claims) if nearby_claims else "No nearby territory claims."

    personality = agent.personality
    traits = []
    if personality.kindness > 0.3:
        traits.append("kind")
    elif personality.kindness < -0.3:
        traits.append("hostile")
    if personality.bravery > 0.3:
        traits.append("brave")
    elif personality.bravery < -0.3:
        traits.append("timid")
    if personality.sociability > 0.3:
        traits.append("extroverted")
    elif personality.sociability < -0.3:
        traits.append("introverted")
    if personality.creativity > 0.3:
        traits.append("creative")
    if personality.ambition > 0.3:
        traits.append("ambitious")
    if personality.empathy > 0.3:
        traits.append("empathetic")
    if personality.cunning > 0.3:
        traits.append("cunning")
    trait_str = ", ".join(traits) if traits else "neutral"

    intellect_score = personality.intellect
    if intellect_score > 0.6:
        knowledge_desc = f"You are highly strategic for {engine.era.value} era."
    elif intellect_score > 0.0:
        knowledge_desc = f"You are reasonably strategic for {engine.era.value} era."
    else:
        knowledge_desc = f"You rely on simple instincts in {engine.era.value} era."

    if agent.life_phase == LifePhaseEnum.CHILD:
        rules = f"""
Rules:
1. {knowledge_desc}
2. You can explore, gather food, and seek safety near others.
3. Prioritize fullness/hydration and avoid danger."""
    elif agent.life_phase == LifePhaseEnum.TEEN:
        rules = f"""
Rules:
1. {knowledge_desc}
2. You can gather, trade, socialize, and learn territorial politics.
3. Prioritize fullness/hydration and social bonding."""
    elif agent.life_phase == LifePhaseEnum.ELDER:
        rules = f"""
Rules:
1. {knowledge_desc}
2. Conserve energy.
3. {settlement_context}
4. Mentor younger citizens and keep social cohesion."""
    else:
        rules = f"""
Rules:
1. {knowledge_desc}
2. You are self-aware: if needs are ignored, you can die and your lineage can end.
3. If fullness < 20 or hydration < 50, find resources urgently.
4. If social < 40, seek interaction.
5. {settlement_context}
6. You can gather, trade, work, marry, claim_territory, form_alliance, and contest_territory.
7. If desperate and unkind, stealing is possible but risky."""

    partner_status = ""
    if agent.partner_id:
        partner = engine.agents.get(agent.partner_id)
        if partner and partner.is_alive:
            partner_status = f"You are married to {partner.name}."

    pregnancy_status = ""
    if agent.is_pregnant:
        pregnancy_status = f"You are pregnant with {agent.pregnancy_timer} days remaining."

    alliance_context = f"Current allies: {agent.allies}" if agent.allies else "Current allies: none."

    territory_law = ""
    for house in engine.houses:
        if house.territory_radius <= 0 or house.is_under_construction:
            continue
        if abs(agent.x - house.x) + abs(agent.y - house.y) <= house.territory_radius:
            lord = engine.agents.get(house.owner_id)
            if lord and lord.is_alive:
                territory_law = (
                    f"LAW: You are in Lord {lord.name}'s territory. "
                    "Stealing is punishable and taxes may apply."
                )
                break

    if not territory_law:
        for settlement in engine.settlements:
            if settlement.owner_id == agent.id:
                continue
            if abs(agent.x - settlement.x) + abs(agent.y - settlement.y) <= settlement.territory_radius:
                owner = engine.agents.get(settlement.owner_id)
                if owner and owner.is_alive:
                    territory_law = f"Territory notice: you are inside {owner.name}'s claimed zone."
                    break

    jail_status = ""
    if agent.jailed_timer > 0:
        jail_status = f"You are jailed for {agent.jailed_timer} more ticks and cannot move."

    judgment_prompt = ""
    if agent.pending_judgments:
        crime = agent.pending_judgments[0]
        thief_name = crime.get("thief_name", "Unknown")
        thief_id = crime.get("thief_id", "")
        victim_name = crime.get("victim_name", "Unknown")
        judgment_prompt = (
            f"CRIME REPORT: {thief_name}(ID:{thief_id}) stole from {victim_name}. "
            f"Reply with action='judge', trade_target='{thief_id}', and judgment fine|jail|execute|forgive."
        )

    trade_offer_ctx = ""
    if getattr(agent, "incoming_trade_offer", None):
        offer = agent.incoming_trade_offer
        trade_offer_ctx = (
            f"INCOMING TRADE: {offer['from_name']} offers {offer['give']} and requests {offer['take']}. "
            "Reply with accept_trade or reject_trade."
        )

    prompt = f"""
You are {agent.name}, {agent.gender.value}, {agent.life_phase.value.replace('_', ' ')}, age {agent.age}.
Model slot: {getattr(agent, 'model_slot', 'A')} / model: {model}
Job: {getattr(agent, 'job', 'Nomad')}
Personality: {trait_str}
Desire: {agent.desire if agent.desire else 'None yet'}
Likes: {agent.likes}
Dislikes: {agent.dislikes}
Vitals: energy {agent.vitals.energy:.0f}, fullness {agent.vitals.hunger:.0f} (100=full, 0=starving), hydration {agent.vitals.hydration:.0f}, social {agent.vitals.social:.0f}, happiness {agent.vitals.happiness:.0f}
Inventory: wood {agent.inventory.wood}, food {agent.inventory.food}, meat {agent.inventory.meat}, pig {agent.inventory.pig}, cow {agent.inventory.cow}, chicken {agent.inventory.chicken}, crop {agent.inventory.crop}, fruit {agent.inventory.fruit}, herb {agent.inventory.herb}, coin {agent.inventory.coin}, stone {agent.inventory.stone}, tools {agent.inventory.tools}
Skills: {getattr(agent, 'skills', {})}
Vehicles: boat {agent.inventory.has_boat}, cart {agent.inventory.has_cart}, horse {agent.inventory.has_horse}, car {agent.inventory.has_car}
Location: ({agent.x},{agent.y}) terrain={current_terrain}
{partner_status}
{pregnancy_status}
{alliance_context}
{rules}

Nearby resources: {resource_context}
Nearby citizens: {people_context}
Nearby territory claims: {territory_context}
Remembered resource spots: {remembered_resource_context}
Learned terrain suitability notes: {remembered_tile_context}
Recent personal memory events: {remembered_event_context}

Important:
- Coordinate orientation: x increases to the east/right, x decreases to the west/left; y increases downward (south), y decreases upward (north).
- Fullness scale is strict: 100 means full, 0 means starving.
- Do not say you are hungry/starving unless fullness < 35.
- If fullness >= 70, do not prioritize food unless planning ahead for inventory.
- You have limited vision radius {vision_radius}. You cannot reliably know events/resources outside this radius unless from memory.
- You cannot walk on ocean or snow.
- Mountains drain energy; roads are efficient.
- Your food likes/dislikes are fixed from birth and cannot be changed.
- If your energy is getting low and you have a house, returning home to rest is a good strategy.
- Decide whether to gather now or skip based on your personality (can be greedy or satisfied with enough).
- Use remembered hotspots and tile suitability to plan revisits for food/farming/livestock.
- Think about survival, reproduction, alliances, and influence over time.

Past context: {' '.join(context_memories[-3:]) if context_memories else 'None'}
{territory_law}
{jail_status}
{judgment_prompt}
{trade_offer_ctx}

Reply STRICTLY as JSON:
{{
  "thought": "reasoning",
  "likes": ["str"],
  "dislikes": ["str"],
  "desire": "new ambition",
  "move_x": -1|0|1,
  "move_y": -1|0|1,
  "action": "idle|moving|trading|gathering|marrying|working|steal|judge|accept_trade|reject_trade|claim_territory|form_alliance|contest_territory",
  "trade_target": "agent_id_or_territory_owner_id",
  "trade_offer": {{"give": {{"item": 0}}, "take": {{"item": 0}}}},
  "judgment": "fine|jail|execute|forgive"
}}
"""

    if compact_mode:
        prompt = f"""
You are {agent.name} in a civilization simulation.
Age phase: {agent.life_phase.value}. Era: {engine.era.value}. Job: {getattr(agent, 'job', 'Nomad')}.
Vitals: energy {agent.vitals.energy:.0f}, fullness {agent.vitals.hunger:.0f}, hydration {agent.vitals.hydration:.0f}, social {agent.vitals.social:.0f}.
Inventory: food {agent.inventory.food}, crop {agent.inventory.crop}, fruit {agent.inventory.fruit}, wood {agent.inventory.wood}, stone {agent.inventory.stone}, coin {agent.inventory.coin}.
Location: ({agent.x},{agent.y}) terrain={current_terrain}. Vision radius: {vision_radius}.
Nearby resources: {resource_context}
Nearby citizens: {people_context}
Memory hints: {remembered_resource_context}

Rules:
- move_x and move_y must be integers in -1,0,1.
- If fullness < 35 or hydration < 45, prioritize food/water-related resource movement.
- If nothing urgent, explore or gather.
- Return ONLY valid JSON, no markdown, no extra text.

Output JSON exactly:
{{
    "thought": "short reason",
    "move_x": -1,
    "move_y": 0,
    "action": "moving"
}}
"""

    last_error: Exception | None = None

    model_candidates = [model]
    if FALLBACK_MODEL and FALLBACK_MODEL not in model_candidates:
        model_candidates.append(FALLBACK_MODEL)

    for active_model in model_candidates:
        if active_model in UNAVAILABLE_MODELS and active_model != FALLBACK_MODEL:
            continue

        switch_model = False
        for endpoint in _get_candidate_endpoints():
            payload = _build_request_payload(endpoint, active_model, prompt)
            for attempt in range(OLLAMA_RETRIES + 1):
                try:
                    response = requests.post(endpoint, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
                    response.raise_for_status()
                    data = response.json()

                    if isinstance(data, dict) and data.get("error"):
                        raise RuntimeError(str(data.get("error")))

                    raw = _extract_llm_text(data)
                    if raw is None:
                        if isinstance(data, dict):
                            raise KeyError(f"response (keys: {list(data.keys())})")
                        raise KeyError("response")

                    return _parse_action_payload(raw)
                except requests.exceptions.Timeout as exc:
                    last_error = exc
                    if attempt < OLLAMA_RETRIES:
                        continue
                    # Try another endpoint variant if available.
                    break
                except requests.exceptions.HTTPError as exc:
                    last_error = exc
                    status_code = getattr(exc.response, "status_code", None)
                    body = ""
                    try:
                        body = (exc.response.text or "").lower() if exc.response is not None else ""
                    except Exception:
                        body = ""

                    model_not_found = status_code == 404 and "model" in body and "not found" in body
                    if model_not_found:
                        UNAVAILABLE_MODELS.add(active_model)
                        if active_model not in UNAVAILABLE_MODEL_WARNED:
                            UNAVAILABLE_MODEL_WARNED.add(active_model)
                            print(f"LLM Warning: model '{active_model}' not found. Falling back to '{FALLBACK_MODEL}'.")
                        switch_model = True
                        break

                    # 404/405 likely endpoint mismatch; try next endpoint variant.
                    if status_code in (404, 405):
                        break
                    if attempt < OLLAMA_RETRIES:
                        continue
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < OLLAMA_RETRIES:
                        continue
                    break

            if switch_model:
                break

        if switch_model:
            continue

    if isinstance(last_error, requests.exceptions.Timeout):
        timeout_text = "unlimited timeout" if OLLAMA_TIMEOUT_SECONDS is None else f"{OLLAMA_TIMEOUT_SECONDS}s"
        print(f"LLM Error: request timed out after {timeout_text} for model {model}")
        return _heuristic_fallback_action(agent, engine, "I could not think in time.")

    print(f"LLM Error: {last_error}")
    return _heuristic_fallback_action(agent, engine, "I failed to parse a stable plan.")


def query_llm_for_global_quest(engine) -> dict | None:
    """Generate a world quest blueprint for all citizens."""
    alive_agents = [a for a in engine.agents.values() if a.is_alive]
    pop = len(alive_agents)
    if pop <= 0:
        return None

    stock = {
        "wood": sum(a.inventory.wood for a in alive_agents),
        "stone": sum(a.inventory.stone for a in alive_agents),
        "food": sum(a.inventory.food for a in alive_agents),
        "crop": sum(a.inventory.crop for a in alive_agents),
        "fish": sum(1 for r in getattr(engine, "resources", []) if getattr(getattr(r, "type", None), "value", "") == "fish"),
        "fruit": sum(a.inventory.fruit for a in alive_agents),
        "herb": sum(a.inventory.herb for a in alive_agents),
    }

    transition_context = {}
    if hasattr(engine, "get_civilization_transition_context"):
        try:
            transition_context = engine.get_civilization_transition_context() or {}
        except Exception:
            transition_context = {}

    allowed_resources = sorted(
        list(
            getattr(
                engine,
                "_quest_resource_options",
                lambda: {"wood", "stone", "food", "crop", "fruit", "herb", "fish"},
            )()
        )
    )

    prompt = f"""
You are generating one GLOBAL cooperative quest for a civilization simulation.
The quest is for ALL citizens and reward is split proportionally by each citizen's contribution.

Current world context:
- Era: {engine.era.value}
- Tick: {engine.tick}
- Population: {pop}
- Resource stock: {stock}
- Allowed resources for quest: {allowed_resources}

Civilization transition context (derived from trusted development indicators):
{json.dumps(transition_context, ensure_ascii=True)}

Use the transition context above to choose a quest that helps the civilization progress to its next era.
Prioritize the top_gaps indicators whenever target_era is not null.

Output STRICT JSON with this shape:
{{
  "title": "short quest title",
    "resource": "one of allowed resources",
  "target_amount": 20-220,
  "reward_coin": 20-400,
  "deadline_ticks": 80-600,
    "description": "1 sentence objective with cooperative contribution and proportional reward"
}}

Rules:
- Pick exactly one resource type.
- Keep quest feasible for current population and current stock dynamics.
- When target_era exists, make the quest materially help transition readiness (close at least one top gap).
- If already in modern era (no target_era), focus on resilience and inequality reduction.
- reward_coin should feel meaningful but not game-breaking.
- Description must explicitly mention cooperative contribution and proportional reward split.
"""

    last_error: Exception | None = None
    model = getattr(engine, "active_model", FALLBACK_MODEL) or FALLBACK_MODEL
    model_candidates = [model]
    if FALLBACK_MODEL and FALLBACK_MODEL not in model_candidates:
        model_candidates.append(FALLBACK_MODEL)

    for active_model in model_candidates:
        for endpoint in _get_candidate_endpoints():
            payload = _build_request_payload(endpoint, active_model, prompt)
            try:
                response = requests.post(endpoint, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
                response.raise_for_status()
                data = response.json()
                raw = _extract_llm_text(data)
                if raw is None:
                    continue
                parsed = _parse_action_payload(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as exc:
                last_error = exc
                continue

    if last_error is not None:
        print(f"LLM Quest Error: {last_error}")
    return None
