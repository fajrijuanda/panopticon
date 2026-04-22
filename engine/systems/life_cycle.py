import uuid
import numpy as np
from typing import Optional
from models import (
    AgentSchema, LifePhaseEnum, EraEnum, Personality, GenderEnum, 
    Vitals, Inventory, ActionStateEnum, GravestoneNode, LogCategoryEnum
)

def calc_life_phase(age: int) -> LifePhaseEnum:
    if age <= 100: return LifePhaseEnum.BABY
    elif age <= 300: return LifePhaseEnum.CHILD
    elif age <= 600: return LifePhaseEnum.TEEN
    elif age <= 1200: return LifePhaseEnum.YOUNG_ADULT
    elif age <= 1800: return LifePhaseEnum.ADULT
    else: return LifePhaseEnum.ELDER

def calc_era(engine) -> EraEnum:
    max_level = 0
    if engine.houses:
        max_level = max(h.level for h in engine.houses)
    
    has_boat = any(a.inventory.has_boat for a in engine.agents.values())
    
    if max_level >= 4: return EraEnum.MODERN
    elif max_level >= 3: return EraEnum.MEDIEVAL
    elif max_level >= 2 or has_boat: return EraEnum.ANCIENT
    else: return EraEnum.PREHISTORIC

def kill_agent(engine, agent: AgentSchema, cause: str):
    agent.is_alive = False
    agent.actionState = ActionStateEnum.IDLE
    
    # Inheritance Logic
    heir = None
    if agent.partner_id and agent.partner_id in engine.agents and engine.agents[agent.partner_id].is_alive:
        heir = engine.agents[agent.partner_id]
    else:
        alive_children = [engine.agents[cid] for cid in agent.children if cid in engine.agents and engine.agents[cid].is_alive]
        if alive_children:
            heir = alive_children[0]
            
    if heir:
        heir.inventory.wood += agent.inventory.wood
        heir.inventory.food += agent.inventory.food
        heir.inventory.coin += agent.inventory.coin
        heir.inventory.stone += agent.inventory.stone
        heir.inventory.tools += agent.inventory.tools
        heir.inventory.meat += agent.inventory.meat
        heir.inventory.crop += agent.inventory.crop
        heir.inventory.fruit += agent.inventory.fruit
        heir.inventory.herb += agent.inventory.herb
        if agent.inventory.has_boat: heir.inventory.has_boat = True
        if agent.inventory.has_horse: heir.inventory.has_horse = True
        if agent.inventory.has_cart: heir.inventory.has_cart = True
        if agent.inventory.has_car: heir.inventory.has_car = True
        engine.add_log(LogCategoryEnum.ECONOMY, f"📜 {heir.name} inherited belongings from {agent.name}.")
        
        # Clear dead agent inventory
        agent.inventory = Inventory(wood=0, food=0, coin=0, stone=0, tools=0, meat=0, crop=0, fruit=0, herb=0)

    # Royal succession event chain (crown heir and coronation)
    if agent.social_class.value in {"royalty", "noble"}:
        candidates = []
        if agent.partner_id and agent.partner_id in engine.agents and engine.agents[agent.partner_id].is_alive:
            candidates.append(engine.agents[agent.partner_id])
        for cid in agent.children:
            if cid in engine.agents and engine.agents[cid].is_alive:
                candidates.append(engine.agents[cid])
        for ally_id in getattr(agent, "allies", []):
            if ally_id in engine.agents and engine.agents[ally_id].is_alive:
                candidates.append(engine.agents[ally_id])

        # unique keep-order
        unique = []
        seen = set()
        for cand in candidates:
            if cand.id in seen:
                continue
            seen.add(cand.id)
            unique.append(cand)

        successor = None
        if unique:
            if hasattr(engine, "_leadership_score"):
                successor = max(unique, key=lambda a: float(engine._leadership_score(a)))
            else:
                successor = unique[0]

        if successor:
            if successor.gender.value == "male":
                successor.royal_title = "king"
            else:
                successor.royal_title = "queen"
            if successor.social_class.value != "royalty":
                successor.social_class = successor.social_class.__class__("royalty")

            for a in engine.agents.values():
                if not a.is_alive or a.id == successor.id:
                    continue
                if a.royal_title in {"crown_prince", "crown_princess", "king", "queen"}:
                    a.royal_title = ""

            heirs = [engine.agents[cid] for cid in successor.children if cid in engine.agents and engine.agents[cid].is_alive]
            if heirs:
                crown_heir = max(heirs, key=lambda h: h.age)
                crown_heir.royal_title = "crown_prince" if crown_heir.gender.value == "male" else "crown_princess"
                engine.add_log(
                    LogCategoryEnum.SOCIAL,
                    f"👑 Crown heir declared: {crown_heir.name} became {crown_heir.royal_title.replace('_', ' ')}.",
                    interaction_type="crown_heir_declared",
                    participant_ids=[successor.id, crown_heir.id],
                    source_agent_id=successor.id,
                )

            engine.add_log(
                LogCategoryEnum.SOCIAL,
                f"🏰 Coronation: {successor.name} ascended as {successor.royal_title} after {agent.name}'s death.",
                interaction_type="coronation",
                participant_ids=[agent.id, successor.id],
                source_agent_id=successor.id,
            )
        
    engine.gravestones.append(GravestoneNode(
        id=str(uuid.uuid4())[:8], name=agent.name,
        x=agent.x, y=agent.y, death_tick=engine.tick, age_at_death=agent.age
    ))
    birth_tick = agent.birth_tick if hasattr(agent, 'birth_tick') and agent.birth_tick > 0 else 1
    age_years = (agent.age // 360) if agent.age >= 360 else 0
    engine.add_log(
        LogCategoryEnum.SYSTEM, 
        f"🪦 {agent.name} died from {cause} (age {engine.format_age(agent.age)}).",
        interaction_type="death",
        source_agent_id=agent.id
    )

def birth_child(engine, mother: AgentSchema):
    father = engine.agents.get(mother.partner_id) if mother.partner_id else None
    child_id = f"agent_{len(engine.agents)+1}_{str(uuid.uuid4())[:4]}"
    rng = getattr(engine, "world_rng", np.random)
    child_gender = GenderEnum(str(rng.choice(["male","female"])))
    if father and father.is_alive:
        cp = Personality(
            kindness=round(float(np.clip((mother.personality.kindness+father.personality.kindness)/2+np.random.uniform(-0.2,0.2),-1,1)),2),
            bravery=round(float(np.clip((mother.personality.bravery+father.personality.bravery)/2+np.random.uniform(-0.2,0.2),-1,1)),2),
            sociability=round(float(np.clip((mother.personality.sociability+father.personality.sociability)/2+np.random.uniform(-0.2,0.2),-1,1)),2),
            intellect=round(float(np.clip((mother.personality.intellect+father.personality.intellect)/2+np.random.uniform(-0.1,0.2),-1,1)),2),
            creativity=round(float(np.clip((mother.personality.creativity+father.personality.creativity)/2+np.random.uniform(-0.1,0.1),-1,1)),2),
            ambition=round(float(np.clip((mother.personality.ambition+father.personality.ambition)/2+np.random.uniform(-0.1,0.1),-1,1)),2),
            empathy=round(float(np.clip((mother.personality.empathy+father.personality.empathy)/2+np.random.uniform(-0.1,0.1),-1,1)),2),
            cunning=round(float(np.clip((mother.personality.cunning+father.personality.cunning)/2+np.random.uniform(-0.1,0.1),-1,1)),2),
        )
        fname = father.name
        father.children.append(child_id)
    else:
        cp = Personality(
            kindness=round(float(rng.uniform(-0.5,1.0)),2),
            bravery=round(float(rng.uniform(-0.5,1.0)),2),
            sociability=round(float(rng.uniform(-0.5,1.0)),2),
            intellect=round(float(rng.uniform(-0.5,1.0)),2),
        )
        fname = "Unknown"
        
    mother.children.append(child_id)
    parents_list = [mother.id]
    if father:
        parents_list.append(father.id)
        
    cx, cy = mother.x, mother.y
    for _ in range(20):
        nx = cx + int(rng.choice([-1,0,1]))
        ny = cy + int(rng.choice([-1,0,1]))
        if engine._is_land(nx, ny):
            cx, cy = nx, ny
            break
    child_name = f"{mother.name[:2]}{fname[:2]}_{str(uuid.uuid4())[:2]}"
    child = AgentSchema(
        id=child_id, name=child_name, gender=child_gender, x=cx, y=cy,
        age=0, max_age=int(np.random.randint(2000,2800)),
        life_phase=LifePhaseEnum.BABY, personality=cp,
        skills={
            "gathering": 5.0,
            "farming": 2.0,
            "hunting": 2.0,
            "fishing": 2.0,
            "trading": 1.0,
            "construction": 1.0,
            "medicine": 1.0,
            "diplomacy": 1.5,
            "leadership": 1.0,
        },
        vitals=Vitals(energy=100.0,hunger=100.0,social=100.0),
        inventory=Inventory(wood=0,food=0,coin=0,stone=0,tools=0,has_boat=False),
        currentThought=f"Born to {mother.name} and {fname}.",
        actionState=ActionStateEnum.IDLE, is_alive=True,
        house_id=mother.house_id,
        parents=parents_list,
        children=[],
        birth_tick=engine.tick,
    )
    engine.agents[child_id] = child
    # Add child to mother's house
    if mother.house_id:
        h = next((h for h in engine.houses if h.id == mother.house_id), None)
        if h:
            h.residents.append(child_id)
    gi = "♂" if child_gender == GenderEnum.MALE else "♀"
    engine.add_log(
        LogCategoryEnum.SOCIAL, 
        f"👶 {child_name} ({gi}) born to {mother.name}!",
        interaction_type="birth",
        participant_ids=[child_id, mother.id] + ([father.id] if father else []),
        source_agent_id=mother.id
    )

    # Royal birth line: assign crown prince/princess candidate title when born in royalty house.
    royal_parent = mother if mother.social_class.value == "royalty" else (father if father and father.social_class.value == "royalty" else None)
    if royal_parent:
        child.social_class = child.social_class.__class__("royalty")
        child.royal_title = "crown_prince" if child.gender.value == "male" else "crown_princess"
        engine.add_log(
            LogCategoryEnum.SOCIAL,
            f"👑 Royal birth: {child.name} was proclaimed {child.royal_title.replace('_', ' ')}.",
            interaction_type="royal_birth",
            participant_ids=[child.id, royal_parent.id],
            source_agent_id=royal_parent.id,
        )

def process_world_events(engine):
    engine.add_log(LogCategoryEnum.SYSTEM, "⚡ A world event is occurring...")
    rng = getattr(engine, "world_rng", np.random)
    for aid, agent in list(engine.agents.items()):
        if not agent.is_alive: continue
        if float(rng.random()) < 0.10:
            surv = agent.personality.bravery*0.3 + (agent.vitals.energy/100.0)*0.7
            if surv < 0.4:
                kill_agent(engine, agent, "disease")
            else:
                agent.vitals.energy = max(0.0, agent.vitals.energy - 30)
                engine.add_log(LogCategoryEnum.SYSTEM, f"🤒 {agent.name} survived disease.")
