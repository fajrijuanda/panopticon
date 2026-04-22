import uuid
import numpy as np
from typing import Dict, List, Tuple
from models import (
    AgentSchema, ResourceTypeEnum, ResourceNode,
    HouseNode, BuildingTypeEnum, LogCategoryEnum, LifePhaseEnum, EraEnum
)
from terrain import TerrainType

TERRAIN_RESOURCE_TABLE: Dict[str, List[Tuple[str, float]]] = {
    TerrainType.FOREST.value: [("wood", 0.50), ("fruit", 0.22), ("pig", 0.18), ("herb", 0.10)],
    TerrainType.GRASS.value: [("crop", 0.38), ("chicken", 0.20), ("cow", 0.18), ("stone", 0.12), ("coin", 0.06), ("herb", 0.06)],
    TerrainType.MOUNTAIN.value: [("stone", 0.75), ("coin", 0.25)],
    TerrainType.RIVER.value: [("fish", 1.0)],
    TerrainType.BEACH.value: [("fruit", 0.40), ("stone", 0.28), ("fish", 0.25), ("herb", 0.07)],
    TerrainType.OCEAN.value: [("fish", 1.0)],
    TerrainType.LAKE.value: [("fish", 1.0)],
}

def _has_nearby_terrain(engine, x: int, y: int, terrain_types: set[str], radius: int = 1) -> bool:
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx = x + dx
            ny = y + dy
            if 0 <= nx < engine.map_size and 0 <= ny < engine.map_size:
                if engine.terrain[ny][nx] in terrain_types:
                    return True
    return False

def _is_tile_occupied(engine, x: int, y: int) -> bool:
    if any(r.x == x and r.y == y for r in engine.resources):
        return True
    if any(s.x == x and s.y == y for s in engine.settlements):
        return True
    if any(h.x == x and h.y == y for h in engine.houses):
        return True
    return False

def _randint(engine, low: int, high: int | None = None) -> int:
    rng = getattr(engine, "world_rng", np.random)
    if hasattr(rng, "integers"): 
        return int(rng.integers(low, high))
    return int(rng.randint(low, high))

def _random(engine) -> float:
    rng = getattr(engine, "world_rng", np.random)
    return float(rng.random())

def _choice(engine, values, p=None):
    rng = getattr(engine, "world_rng", np.random)
    if p is not None:
        weights = np.asarray(p, dtype=float)
        total = float(weights.sum())
        if total <= 0 or not np.isfinite(total):
            weights = None
        else:
            weights = weights / total
        return rng.choice(values, p=weights)
    return rng.choice(values, p=p)

def _spawn_coastal_fish(engine, attempts: int = 120) -> bool:
    for _ in range(attempts):
        x = _randint(engine, 0, engine.map_size)
        y = _randint(engine, 0, engine.map_size)

        if engine.terrain[y][x] != TerrainType.OCEAN.value:
            continue
        if _is_tile_occupied(engine, x, y):
            continue
        # Keep fish mostly around coast so they stay reachable once boats/ports exist.
        if not _has_nearby_terrain(engine, x, y, {TerrainType.BEACH.value, TerrainType.RIVER.value}, radius=4):
            continue

        engine.resources.append(
            ResourceNode(id=str(uuid.uuid4())[:8], type=ResourceTypeEnum.FISH, x=x, y=y)
        )
        return True
    return False

def _coastal_fish_multiplier(engine) -> float:
    era = getattr(engine, "era", EraEnum.PREHISTORIC)
    era_multiplier = {
        EraEnum.PREHISTORIC: 1.0,
        EraEnum.ANCIENT: 1.15,
        EraEnum.MEDIEVAL: 1.35,
        EraEnum.MODERN: 1.6,
    }.get(era, 1.0)

    active_ports = 0
    for house in getattr(engine, "houses", []):
        house_type = getattr(house, "type", None)
        house_type_value = getattr(house_type, "value", house_type)
        if house_type_value == BuildingTypeEnum.PORT.value and not getattr(house, "is_under_construction", False):
            active_ports += 1

    # Ports improve fishing logistics and keep seafood flowing.
    port_multiplier = 1.0 + min(0.8, active_ports * 0.08)

    # Wetter worlds naturally sustain more coastal fish stock.
    water_level = float(getattr(engine, "env_params", {}).get("water", 50))
    water_multiplier = 1.0 + max(-0.15, min(0.25, (water_level - 50.0) / 200.0))

    return max(0.8, min(3.0, era_multiplier * port_multiplier * water_multiplier))

def _resource_capacity_multiplier(engine) -> float:
    """Era-aware cap multiplier so early eras do not feel resource-starved."""
    era = getattr(engine, "era", EraEnum.PREHISTORIC)
    return {
        EraEnum.PREHISTORIC: 4.0,
        EraEnum.ANCIENT: 3.1,
        EraEnum.MEDIEVAL: 2.4,
        EraEnum.MODERN: 2.0,
    }.get(era, 2.2)

def _spawn_attempts_per_tick(engine) -> int:
    era = getattr(engine, "era", EraEnum.PREHISTORIC)
    return {
        EraEnum.PREHISTORIC: 3,
        EraEnum.ANCIENT: 2,
        EraEnum.MEDIEVAL: 2,
        EraEnum.MODERN: 1,
    }.get(era, 1)

def _map_density_scale(engine) -> float:
    # Keep node density stable when map size grows beyond the old 160 baseline.
    map_size = max(1, int(getattr(engine, "map_size", 160)))
    return max(0.8, (map_size * map_size) / float(160 * 160))

def _resource_spawn_threshold(engine) -> float:
    """Lower threshold means more frequent spawn attempts."""
    era = getattr(engine, "era", EraEnum.PREHISTORIC)
    return {
        EraEnum.PREHISTORIC: 0.36,
        EraEnum.ANCIENT: 0.48,
        EraEnum.MEDIEVAL: 0.62,
        EraEnum.MODERN: 0.68,
    }.get(era, 0.7)

def _get_era_based_resources(engine) -> Dict[str, List[Tuple[str, float]]]:
    """Generate resource table with era-specific metals."""
    era = getattr(engine, "era", EraEnum.PREHISTORIC)
    
    table = {
        TerrainType.FOREST.value: [("wood", 0.50), ("fruit", 0.22), ("pig", 0.18), ("herb", 0.10)],
        TerrainType.GRASS.value: [("crop", 0.31), ("chicken", 0.18), ("cow", 0.17), ("stone", 0.13), ("coin", 0.08), ("herb", 0.10), ("horse", 0.03)],
        TerrainType.MOUNTAIN.value: [("stone", 0.60), ("coin", 0.20)],  # Base mountain
        TerrainType.RIVER.value: [("fish", 1.0)],
        TerrainType.BEACH.value: [("fruit", 0.40), ("stone", 0.28), ("fish", 0.25), ("herb", 0.07)],
        TerrainType.OCEAN.value: [("fish", 1.0)],
        TerrainType.LAKE.value: [("fish", 1.0)],
    }
    
    # Add metal resources based on era
    if era == EraEnum.PREHISTORIC:
        table[TerrainType.FOREST.value] = [("wood", 0.72), ("fruit", 0.12), ("pig", 0.12), ("herb", 0.04)]
        table[TerrainType.GRASS.value] = [("crop", 0.26), ("chicken", 0.22), ("cow", 0.19), ("stone", 0.19), ("coin", 0.02), ("herb", 0.09), ("horse", 0.03)]
        table[TerrainType.MOUNTAIN.value] = [("stone", 0.92), ("coin", 0.08)]
        table[TerrainType.BEACH.value] = [("fruit", 0.44), ("stone", 0.34), ("fish", 0.18), ("herb", 0.04)]

    elif era == EraEnum.ANCIENT:
        table[TerrainType.FOREST.value] = [("wood", 0.52), ("fruit", 0.20), ("pig", 0.18), ("herb", 0.10)]
        table[TerrainType.GRASS.value] = [("crop", 0.33), ("chicken", 0.18), ("cow", 0.16), ("stone", 0.14), ("coin", 0.08), ("herb", 0.09), ("horse", 0.02)]
        table[TerrainType.MOUNTAIN.value] = [("stone", 0.54), ("coin", 0.20), ("copper", 0.26)]
        table[TerrainType.BEACH.value] = [("fruit", 0.42), ("stone", 0.28), ("fish", 0.24), ("herb", 0.06)]
        
    elif era == EraEnum.MEDIEVAL:
        table[TerrainType.FOREST.value] = [("wood", 0.44), ("fruit", 0.18), ("pig", 0.18), ("herb", 0.20)]
        table[TerrainType.GRASS.value] = [("crop", 0.28), ("chicken", 0.16), ("cow", 0.15), ("stone", 0.12), ("coin", 0.16), ("herb", 0.12), ("horse", 0.01)]
        table[TerrainType.MOUNTAIN.value] = [("stone", 0.36), ("copper", 0.20), ("silver", 0.18), ("iron", 0.16), ("coin", 0.10)]
        table[TerrainType.BEACH.value] = [("fruit", 0.34), ("stone", 0.24), ("fish", 0.34), ("herb", 0.08)]
        
    elif era == EraEnum.MODERN:
        table[TerrainType.FOREST.value] = [("wood", 0.34), ("fruit", 0.16), ("pig", 0.18), ("herb", 0.32)]
        table[TerrainType.GRASS.value] = [("crop", 0.20), ("chicken", 0.14), ("cow", 0.14), ("stone", 0.08), ("coin", 0.36), ("herb", 0.08)]
        table[TerrainType.MOUNTAIN.value] = [("copper", 0.24), ("silver", 0.20), ("iron", 0.26), ("coin", 0.18), ("stone", 0.12)]
        table[TerrainType.BEACH.value] = [("fruit", 0.26), ("stone", 0.18), ("fish", 0.46), ("herb", 0.10)]
    
    return table

def spawn_resource(engine, force=False):
    base_abundance = float(engine.env_params.get("abundance", 50))
    max_res = int(base_abundance * 1.5 * _resource_capacity_multiplier(engine) * _map_density_scale(engine))

    # Maintain a small, steady stock of ocean & lake fish so sea resources regenerate
    # similarly to land resources over time.
    if len(engine.resources) < max_res:
        base_min = max(4, int(engine.env_params.get("abundance", 50) // 8))
        min_coastal_fish = max(4, int(round(base_min * _coastal_fish_multiplier(engine))))
        coastal_fish_count = sum(
            1
            for res in engine.resources
            if res.type == ResourceTypeEnum.FISH
            and 0 <= res.x < engine.map_size
            and 0 <= res.y < engine.map_size
            and engine.terrain[res.y][res.x] in [TerrainType.OCEAN.value, TerrainType.RIVER.value, TerrainType.LAKE.value]
        )
        if coastal_fish_count < min_coastal_fish:
            deficit = max(0, min_coastal_fish - coastal_fish_count)
            replenish_threshold = max(0.15, 0.55 - (deficit * 0.05))
            replenish_chance = force or _random(engine) > replenish_threshold
            if replenish_chance and _spawn_coastal_fish(engine):
                return

    spawn_threshold = _resource_spawn_threshold(engine)
    attempts_per_tick = _spawn_attempts_per_tick(engine)
    for _ in range(attempts_per_tick):
        if len(engine.resources) >= max_res:
            break
        if not force and _random(engine) <= spawn_threshold:
            continue
        for _ in range(70):
            x = _randint(engine, 0, engine.map_size)
            y = _randint(engine, 0, engine.map_size)

            if _is_tile_occupied(engine, x, y):
                continue

            t = engine.terrain[y][x]
            
            # Use era-based resource table
            era_resource_table = _get_era_based_resources(engine)
            options = era_resource_table.get(t)
            
            if not options:
                continue

            # Fish in ocean/lake should appear close to coast/edges, not deep in the middle
            if t == TerrainType.OCEAN.value:
                if not _has_nearby_terrain(engine, x, y, {TerrainType.BEACH.value, TerrainType.RIVER.value, TerrainType.LAKE.value}, radius=4):
                    continue
            
            # Lake fish should stay somewhat near rivers/other water
            if t == TerrainType.LAKE.value:
                if not _has_nearby_terrain(engine, x, y, {TerrainType.RIVER.value, TerrainType.BEACH.value}, radius=3):
                    continue

            kinds = [kind for kind, _ in options]
            probs = [prob for _, prob in options]
            r_type = str(_choice(engine, kinds, p=probs))

            engine.resources.append(
                ResourceNode(id=str(uuid.uuid4())[:8], type=ResourceTypeEnum(r_type), x=x, y=y)
            )
            break

def execute_trade(engine, responder_id: str, offer_data: dict):
    initiator_id = offer_data.get("from")
    give = offer_data.get("give", {})  # initiator gives to responder
    take = offer_data.get("take", {})  # initiator takes from responder
    
    init_agent = engine.agents.get(initiator_id)
    resp_agent = engine.agents.get(responder_id)
    
    if not init_agent or not init_agent.is_alive or not resp_agent or not resp_agent.is_alive:
        return
    if abs(init_agent.x - resp_agent.x) + abs(init_agent.y - resp_agent.y) > 3:
        return
        
    # Verify Inventory
    def has_items(agent, items_dict):
        for k, v in items_dict.items():
            if not hasattr(agent.inventory, k) or getattr(agent.inventory, k, 0) < v: return False
        return True
        
    if has_items(init_agent, give) and has_items(resp_agent, take):
        for k, v in give.items():
            setattr(init_agent.inventory, k, getattr(init_agent.inventory, k) - v)
            setattr(resp_agent.inventory, k, getattr(resp_agent.inventory, k) + v)
        for k, v in take.items():
            setattr(resp_agent.inventory, k, getattr(resp_agent.inventory, k) - v)
            setattr(init_agent.inventory, k, getattr(init_agent.inventory, k) + v)
        
        give_str = ", ".join(f"{v} {k}" for k, v in give.items())
        take_str = ", ".join(f"{v} {k}" for k, v in take.items())
        engine.add_log(LogCategoryEnum.ECONOMY, f"🤝 {init_agent.name} & {resp_agent.name} traded: {init_agent.name} gave {give_str} for {take_str}.")
        if hasattr(engine, "gain_skill"):
            engine.gain_skill(init_agent, "trading", 1.4)
            engine.gain_skill(resp_agent, "trading", 1.2)
            engine.gain_skill(init_agent, "diplomacy", 0.4)
            engine.gain_skill(resp_agent, "diplomacy", 0.3)
        init_agent.personality.sociability = min(1.0, init_agent.personality.sociability + 0.05)
        resp_agent.personality.sociability = min(1.0, resp_agent.personality.sociability + 0.05)
        if hasattr(engine, "_sync_production_origins"):
            engine._sync_production_origins(init_agent)
            engine._sync_production_origins(resp_agent)

def try_build_buildings(engine, agent: AgentSchema):
    """Try to build or upgrade houses, markets, ports, and schools."""
    if agent.life_phase not in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT, LifePhaseEnum.ELDER]:
        return
        
    t = engine.terrain[agent.y][agent.x]
    is_land = t in [TerrainType.GRASS.value, TerrainType.FOREST.value, TerrainType.BEACH.value, TerrainType.ROAD.value]
    
    owned_residences = [h for h in engine.houses if h.owner_id == agent.id and h.type == BuildingTypeEnum.RESIDENCE]
    
    # 1. Residence
    if is_land:
        if not owned_residences:
            if agent.inventory.wood >= 5:
                agent.inventory.wood -= 5
                house = HouseNode(
                    id=str(uuid.uuid4())[:8], owner_id=agent.id, type=BuildingTypeEnum.RESIDENCE,
                    x=agent.x, y=agent.y, level=1, residents=[agent.id], territory_radius=1
                )
                if agent.partner_id:
                    house.residents.append(agent.partner_id)
                    if engine.agents.get(agent.partner_id):
                        engine.agents[agent.partner_id].house_id = house.id
                engine.houses.append(house)
                agent.house_id = house.id
                engine.add_log(LogCategoryEnum.SOCIAL, f"🛖 {agent.name} built a Hut!")
        else:
            house = owned_residences[0]
            if house.level == 1 and house.territory_radius < 1:
                house.territory_radius = 1
            if house.level == 1 and agent.inventory.wood >= 10 and agent.inventory.stone >= 5 and agent.inventory.tools >= 1 and not house.is_under_construction:
                agent.inventory.wood -= 10; agent.inventory.stone -= 5; agent.inventory.tools -= 1;
                house.level = 2; house.territory_radius = 2; house.is_under_construction = False; house.labor_required = 0; house.labor_contributed = 0
                engine.add_log(LogCategoryEnum.SOCIAL, f"🏠 {agent.name} upgraded Hut → House.")
            elif house.level == 2 and agent.inventory.wood >= 20 and agent.inventory.stone >= 15 and agent.inventory.tools >= 3 and agent.inventory.coin >= 30 and not house.is_under_construction:
                agent.inventory.wood -= 20; agent.inventory.stone -= 15; agent.inventory.tools -= 3; agent.inventory.coin -= 30;
                house.level = 3; house.territory_radius = 5; house.is_under_construction = False; house.labor_required = 0; house.labor_contributed = 0
                engine.add_log(LogCategoryEnum.SOCIAL, f"🏘️ {agent.name} upgraded House → Mansion.")
            elif house.level == 3 and agent.inventory.wood >= 40 and agent.inventory.stone >= 30 and agent.inventory.tools >= 5 and agent.inventory.coin >= 100 and not house.is_under_construction:
                agent.inventory.wood -= 40; agent.inventory.stone -= 30; agent.inventory.tools -= 5; agent.inventory.coin -= 100;
                house.level = 4; house.territory_radius = 10; house.is_under_construction = True; house.labor_required = 24; house.labor_contributed = 0
                engine.add_log(LogCategoryEnum.SOCIAL, f"🚧 {agent.name} started a Castle project!")

    # 2. Commerce & Education (Only 1 per agent to prevent spam)
    owned_special = [h for h in engine.houses if h.owner_id == agent.id and h.type != BuildingTypeEnum.RESIDENCE]
    if not owned_special:
        # MARKET
        if is_land and agent.inventory.coin >= 50 and agent.inventory.stone >= 20 and agent.inventory.wood >= 20:
            agent.inventory.coin -= 50; agent.inventory.stone -= 20; agent.inventory.wood -= 20
            engine.houses.append(HouseNode(id=str(uuid.uuid4())[:8], owner_id=agent.id, type=BuildingTypeEnum.MARKET, x=agent.x, y=agent.y, level=1, is_under_construction=True, labor_required=18))
            engine.add_log(LogCategoryEnum.ECONOMY, f"🚧 {agent.name} started a Market project!")
        
        # PORT
        elif t == TerrainType.BEACH.value and any(
            0 <= agent.x + dx < engine.map_size
            and 0 <= agent.y + dy < engine.map_size
            and engine.terrain[agent.y + dy][agent.x + dx] == TerrainType.OCEAN.value
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
        ):
            if agent.inventory.wood >= 40 and agent.inventory.stone >= 20 and agent.inventory.coin >= 30:
                agent.inventory.wood -= 40; agent.inventory.stone -= 20; agent.inventory.coin -= 30
                engine.houses.append(HouseNode(id=str(uuid.uuid4())[:8], owner_id=agent.id, type=BuildingTypeEnum.PORT, x=agent.x, y=agent.y, level=1, is_under_construction=True, labor_required=22))
                engine.add_log(LogCategoryEnum.ECONOMY, f"🚧 {agent.name} started a Port project!")
                
        # SCHOOL
        elif is_land and agent.inventory.coin >= 150 and agent.inventory.stone >= 50 and agent.inventory.wood >= 50:
            agent.inventory.coin -= 150; agent.inventory.stone -= 50; agent.inventory.wood -= 50
            engine.houses.append(HouseNode(id=str(uuid.uuid4())[:8], owner_id=agent.id, type=BuildingTypeEnum.SCHOOL, x=agent.x, y=agent.y, level=1, is_under_construction=True, labor_required=28))
            engine.add_log(LogCategoryEnum.SOCIAL, f"🚧 {agent.name} started a School project!")

def process_labor_action(engine, agent: AgentSchema):
    """Called when an agent decides to 'work'."""
    for house in engine.houses:
        if house.is_under_construction and abs(house.x - agent.x) + abs(house.y - agent.y) <= 2:
            owner = engine.agents.get(house.owner_id)
            if owner:
                construction_skill = float(engine.get_skill(agent, "construction")) if hasattr(engine, "get_skill") else 0.0
                wage = 2 + int(construction_skill // 25)
                # Pay wage (owner can always self-build without payment)
                if owner.id != agent.id:
                    paid = min(owner.inventory.coin, wage)
                    owner.inventory.coin -= paid
                    agent.inventory.coin += paid
                
                # Contribute labor
                agent.vitals.energy = max(0, agent.vitals.energy - 6)
                labor_units = 1 + (1 if construction_skill >= 35 else 0) + (1 if owner.id == agent.id else 0)
                house.labor_contributed += labor_units
                if hasattr(engine, "gain_skill"):
                    engine.gain_skill(agent, "construction", 1.0 + (0.4 if labor_units > 1 else 0.0))
                
                if house.labor_contributed >= house.labor_required:
                    house.is_under_construction = False
                    icon = "🏰" if house.level == 4 else "🏘️"
                    engine.add_log(LogCategoryEnum.ECONOMY, f"{icon} Construction completed by {agent.name} for owner {owner.name}!")
            return

def execute_taxation(engine):
    """Tax citizens standing inside a Lord's territory."""
    for house in engine.houses:
        if house.territory_radius > 0 and house.owner_id in engine.agents and not house.is_under_construction:
            owner = engine.agents[house.owner_id]
            for aid, agent in engine.agents.items():
                if aid != owner.id and agent.is_alive and abs(agent.x - house.x) + abs(agent.y - house.y) <= house.territory_radius:
                    if agent.inventory.coin >= 1:
                        agent.inventory.coin -= 1
                        owner.inventory.coin += 1
                        # Log sparsely to avoid spam
                        if np.random.rand() < 0.1:
                            engine.add_log(LogCategoryEnum.ECONOMY, f"👑 {owner.name} taxed 1 Coin from {agent.name} in their territory.")
