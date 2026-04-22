import numpy as np

import uuid

import os

import hashlib

import re

from typing import Any, Dict, List, Tuple, Optional

from models import (

    ActionStateEnum,

    LifePhaseEnum, ResourceTypeEnum, EraEnum, LogCategoryEnum, GenderEnum,

    AgentSchema, ResourceNode, SettlementNode, HouseNode, GravestoneNode, 

    SimulationLog, Personality, Vitals, Inventory, BuildingTypeEnum, SocialClassEnum

)

from terrain import TerrainType, generate_terrain, apply_disaster



import systems.social as social

import systems.life_cycle as life_cycle

import systems.economy as economy

import systems.save_load as save_load
from llm_client import query_llm_for_global_quest



MAP_SIZE = 220

SAVE_DIR = os.path.join(os.path.dirname(__file__), "saves")

LOG_DUPLICATE_COOLDOWN = 8

TICKS_PER_DAY = 24

NEEDS_DRAIN_SCALE = 0.62
HYDRATION_AUTODRINK_TRIGGER = 60
DEHYDRATION_DEATH_THRESHOLD = 7
DEHYDRATION_DEATH_CHANCE = 0.06
QUEST_COOLDOWN_TICKS = 120
SOCIAL_MODE = os.getenv("PANOPTICON_SOCIAL_MODE", "full_llm").strip().lower()

DEFAULT_MODEL = "qwen3:4b"

DEFAULT_SKILL_PROFILE = {

    "gathering": 12.0,

    "farming": 8.0,

    "hunting": 8.0,

    "fishing": 8.0,

    "trading": 6.0,

    "construction": 6.0,

    "medicine": 4.0,

    "diplomacy": 6.0,

    "leadership": 5.0,

}

MODEL_ALIASES = {

    "llama3.1": "llama3.1:latest",

    "qwen2.5": "qwen3:4b",

    "qwen3": "qwen3:4b",

    "gemma": "gemma3:4b",

    "mistral": "mistral:latest",

}





def normalize_model_name(model_name: str) -> str:

    return MODEL_ALIASES.get(model_name, model_name)



class SpatialEngine:

    def __init__(self):

        self.tick = 0

        self.map_size = MAP_SIZE

        self.map_preset: str = "archipelago"

        self.env_params: dict = {"fertility": 50, "abundance": 50, "water": 50}

        self.agents: Dict[str, AgentSchema] = {}

        self.logs: List[SimulationLog] = []

        self.resources: List[ResourceNode] = []

        self.settlements: List[SettlementNode] = []

        self.houses: List[HouseNode] = []

        self.gravestones: List[GravestoneNode] = []

        self.relationships: Dict[str, float] = {}

        self.social_pair_last_log: Dict[str, int] = {}

        self.social_links = set()

        self.log_signature_last_tick: Dict[str, int] = {}

        self.pending_cognitive_tasks = []

        self.think_turn_cursor: int = 0

        self.global_quest: Optional[Dict[str, Any]] = None

        self.quest_history: List[Dict[str, Any]] = []

        self.next_quest_tick: int = 20

        self.terrain: List[List[str]] = []

        self.original_terrain: List[List[str]] = []  # Backup for restart

        self.elevation: np.ndarray = np.zeros((MAP_SIZE, MAP_SIZE))

        self.original_elevation: np.ndarray = np.zeros((MAP_SIZE, MAP_SIZE))

        self.island_infos: List[Dict] = []

        self.era: EraEnum = EraEnum.PREHISTORIC

        self.active_model: str = DEFAULT_MODEL

        self.social_mode: str = SOCIAL_MODE if SOCIAL_MODE in {"full_llm", "hybrid"} else "full_llm"

        self.target_tick: int = 0

        self.violence_level: str = "normal"

        self.world_seed: int = 0

        self.world_rng = np.random.default_rng(0)

        self.model_assignments: Dict[str, str] = {}

        self.agent_world_memory: Dict[str, Dict[str, Any]] = {}

        self.agent_idle_ticks: Dict[str, int] = {}

        self.agent_movement_sessions: Dict[str, Dict[str, int]] = {}

        self.relationship_details: Dict[str, Dict[str, Any]] = {}

        self.groundwater: Dict[str, float] = {}

        self.weather: Dict[str, Any] = {

            "condition": "clear",

            "cloud_cover": 0.25,

            "rain_intensity": 0.0,

            "next_change_tick": 60,

        }


    def _remember_production_origin(self, agent: AgentSchema, kind: str, x: Optional[int] = None, y: Optional[int] = None):

        anchor_x = agent.x if x is None else int(x)

        anchor_y = agent.y if y is None else int(y)

        if kind == "livestock":

            if getattr(agent, "livestock_origin_x", None) is None or getattr(agent, "livestock_origin_y", None) is None:

                agent.livestock_origin_x = anchor_x

                agent.livestock_origin_y = anchor_y

        elif kind == "farm":

            if getattr(agent, "farm_origin_x", None) is None or getattr(agent, "farm_origin_y", None) is None:

                agent.farm_origin_x = anchor_x

                agent.farm_origin_y = anchor_y


    def _sync_production_origins(self, agent: AgentSchema):

        if not agent or not agent.is_alive:

            return

        has_house = bool(self._owned_house(agent))

        has_settlement = self._owned_settlement(agent.id) is not None

        if has_house or has_settlement:

            return


        livestock_total = max(0, int(agent.inventory.pig)) + max(0, int(agent.inventory.cow)) + max(0, int(agent.inventory.chicken))

        farm_total = max(0, int(agent.inventory.crop)) + max(0, int(agent.inventory.fruit))


        if livestock_total > 0:

            self._remember_production_origin(agent, "livestock")

        if farm_total > 0:

            self._remember_production_origin(agent, "farm")



    def _build_world_seed(self, preset: str, env_params: dict) -> int:

        payload = {

            "preset": preset,

            "fertility": int(env_params.get("fertility", 50)),

            "abundance": int(env_params.get("abundance", 50)),

            "water": int(env_params.get("water", 50)),

            "population": 40,

        }

        digest = hashlib.sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()

        return int(digest[:16], 16) % (2**32)



    def _reset_world_rng(self):

        self.world_rng = np.random.default_rng(self.world_seed)

        np.random.seed(self.world_seed)



    def format_calendar_date(self, tick: Optional[int] = None) -> str:

        current_tick = self.tick if tick is None else max(0, tick)

        if current_tick <= 0:

            return "Y000 M01 D01"

        day_index = (current_tick - 1) // TICKS_PER_DAY

        year = day_index // 360

        month = (day_index % 360) // 30 + 1

        day = day_index % 30 + 1

        return f"Y{year:03d} M{month:02d} D{day:02d}"



    def format_age(self, age_days: int) -> str:

        years = age_days // 360

        months = (age_days % 360) // 30

        days = age_days % 30

        return f"{years}y {months}m {days}d"



    def _quest_resource_options(self) -> set[str]:

        return {"wood", "stone", "food", "crop", "fruit", "herb", "fish"}


    def _clamp01(self, value: float) -> float:

        return float(max(0.0, min(1.0, value)))


    def _safe_ratio(self, numerator: float, denominator: float) -> float:

        if denominator <= 0:

            return 0.0

        return float(numerator / denominator)


    def _next_era_target(self) -> Optional[EraEnum]:

        if self.era == EraEnum.PREHISTORIC:

            return EraEnum.ANCIENT

        if self.era == EraEnum.ANCIENT:

            return EraEnum.MEDIEVAL

        if self.era == EraEnum.MEDIEVAL:

            return EraEnum.MODERN

        return None


    def get_civilization_transition_context(self) -> Dict[str, Any]:

        """Build readiness indicators for the next-era transition.

        Indicator themes align with widely used development dimensions: food security,
        settlement/urban infrastructure, mobility/trade, institutions/social coordination,
        knowledge/education, and socioeconomic complexity.
        """

        alive_agents = [a for a in self.agents.values() if a.is_alive]

        pop = len(alive_agents)

        houses = list(self.houses)

        settlements = list(self.settlements)

        metrics = self.compute_metrics()


        total_food_stock = sum(max(0, int(a.inventory.food + a.inventory.crop + a.inventory.fruit)) for a in alive_agents)

        avg_food_per_capita = self._safe_ratio(float(total_food_stock), float(max(1, pop)))

        food_security = self._clamp01(avg_food_per_capita / 24.0)


        avg_house_level = self._safe_ratio(float(sum(max(1, int(h.level)) for h in houses)), float(max(1, len(houses))))

        house_coverage = self._clamp01(self._safe_ratio(float(len(houses)), float(max(1, pop))) * 1.8)

        level_score = self._clamp01((avg_house_level - 1.0) / 3.0)

        road_tiles = 0

        if self.terrain:

            road_tiles = sum(1 for row in self.terrain for tile in row if tile == TerrainType.ROAD.value)

        total_tiles = float(max(1, self.map_size * self.map_size))

        road_score = self._clamp01(self._safe_ratio(float(road_tiles), total_tiles) / 0.06)

        settlement_infrastructure = self._clamp01((house_coverage * 0.5) + (level_score * 0.3) + (road_score * 0.2))


        mobile_households = sum(

            1

            for a in alive_agents

            if a.inventory.has_boat or a.inventory.has_horse or a.inventory.has_cart or a.inventory.has_car

        )

        mobility_ratio = self._clamp01(self._safe_ratio(float(mobile_households), float(max(1, pop))))

        market_houses = sum(1 for h in houses if h.type == BuildingTypeEnum.MARKET)

        port_houses = sum(1 for h in houses if h.type == BuildingTypeEnum.PORT)

        trade_infra = self._clamp01(self._safe_ratio(float(market_houses + port_houses), float(max(1, pop))) * 2.8)

        mobility_trade = self._clamp01((mobility_ratio * 0.6) + (trade_infra * 0.4))


        social_density = float(metrics.get("social_density", 0.0))

        alliance_edges = int(metrics.get("alliance_edges", 0))

        alliance_ratio = self._clamp01(self._safe_ratio(float(alliance_edges), float(max(1, pop))))

        settlement_ratio = self._clamp01(self._safe_ratio(float(len(settlements)), float(max(1, pop))) * 4.0)

        governance_coordination = self._clamp01((social_density * 0.45) + (alliance_ratio * 0.25) + (settlement_ratio * 0.30))


        avg_intellect = self._safe_ratio(float(sum(float(a.personality.intellect) for a in alive_agents)), float(max(1, pop)))

        intellect_score = self._clamp01((avg_intellect + 1.0) / 2.0)

        school_houses = sum(1 for h in houses if h.type == BuildingTypeEnum.SCHOOL)

        school_access = self._clamp01(self._safe_ratio(float(school_houses), float(max(1, pop))) * 3.2)

        avg_medicine_skill = self._safe_ratio(float(sum(float(a.skills.get("medicine", 0.0)) for a in alive_agents)), float(max(1, pop)))

        medicine_score = self._clamp01(avg_medicine_skill / 55.0)

        knowledge_institutions = self._clamp01((intellect_score * 0.45) + (school_access * 0.30) + (medicine_score * 0.25))


        coin_per_capita = self._safe_ratio(float(sum(max(0, int(a.inventory.coin)) for a in alive_agents)), float(max(1, pop)))

        coin_score = self._clamp01(coin_per_capita / 55.0)

        jobs = [str(getattr(a, "job", "none") or "none") for a in alive_agents]

        job_diversity = self._clamp01(self._safe_ratio(float(len(set(jobs))), float(max(1, pop))) * 6.0)

        avg_trade_skill = self._safe_ratio(float(sum(float(a.skills.get("trading", 0.0)) for a in alive_agents)), float(max(1, pop)))

        trade_skill_score = self._clamp01(avg_trade_skill / 60.0)

        socioeconomic_complexity = self._clamp01((coin_score * 0.35) + (job_diversity * 0.35) + (trade_skill_score * 0.30))


        indicator_scores = {

            "food_security": round(food_security, 3),

            "settlement_infrastructure": round(settlement_infrastructure, 3),

            "mobility_trade": round(mobility_trade, 3),

            "governance_coordination": round(governance_coordination, 3),

            "knowledge_institutions": round(knowledge_institutions, 3),

            "socioeconomic_complexity": round(socioeconomic_complexity, 3),

        }


        transition_thresholds: Dict[str, Dict[str, float]] = {

            "prehistoric_to_ancient": {

                "food_security": 0.35,

                "settlement_infrastructure": 0.24,

                "mobility_trade": 0.20,

                "governance_coordination": 0.18,

                "knowledge_institutions": 0.14,

                "socioeconomic_complexity": 0.14,

            },

            "ancient_to_medieval": {

                "food_security": 0.48,

                "settlement_infrastructure": 0.44,

                "mobility_trade": 0.38,

                "governance_coordination": 0.36,

                "knowledge_institutions": 0.32,

                "socioeconomic_complexity": 0.40,

            },

            "medieval_to_modern": {

                "food_security": 0.62,

                "settlement_infrastructure": 0.62,

                "mobility_trade": 0.58,

                "governance_coordination": 0.54,

                "knowledge_institutions": 0.60,

                "socioeconomic_complexity": 0.60,

            },

        }


        source_notes = [

            "UN DESA World Urbanization Prospects (urbanization and settlement transitions): https://population.un.org/wup/",

            "UNESCO Institute for Statistics (education/literacy as development foundations): https://www.uis.unesco.org/en/themes/education-literacy",

            "UNESCO GEM Literacy for Life (literacy as a poverty-reduction foundation): https://www.unesco.org/gem-report/en/literacy-life",

            "Our World in Data Literacy (historical literacy expansion and modernization): https://ourworldindata.org/literacy",

            "Our World in Data Economic Growth (structural transformation and productivity): https://ourworldindata.org/economic-growth",

            "World Bank Urban Development (cities/infrastructure and growth): https://www.worldbank.org/en/topic/urbandevelopment/overview",

        ]


        target_era = self._next_era_target()

        transition_key = None

        if self.era == EraEnum.PREHISTORIC:

            transition_key = "prehistoric_to_ancient"

        elif self.era == EraEnum.ANCIENT:

            transition_key = "ancient_to_medieval"

        elif self.era == EraEnum.MEDIEVAL:

            transition_key = "medieval_to_modern"


        indicators: Dict[str, Dict[str, Any]] = {}

        top_gaps: List[str] = []

        readiness = 1.0


        if transition_key and transition_key in transition_thresholds:

            thresholds = transition_thresholds[transition_key]

            readiness_scores: List[float] = []

            for name, needed in thresholds.items():

                score = float(indicator_scores.get(name, 0.0))

                gap = round(max(0.0, needed - score), 3)

                progress = self._clamp01(score / max(needed, 1e-6))

                readiness_scores.append(progress)

                indicators[name] = {

                    "score": round(score, 3),

                    "needed": round(needed, 3),

                    "gap": gap,

                    "status": "ready" if gap <= 0.0 else "needs_work",

                }

            readiness = round(self._safe_ratio(sum(readiness_scores), float(max(1, len(readiness_scores)))), 3)

            top_gaps = [

                k

                for k, _ in sorted(

                    ((name, float(meta.get("gap", 0.0))) for name, meta in indicators.items()),

                    key=lambda item: item[1],

                    reverse=True,

                )

                if indicators[k]["gap"] > 0

            ][:3]

        else:

            indicators = {name: {"score": value, "needed": None, "gap": 0.0, "status": "sustain"} for name, value in indicator_scores.items()}

            top_gaps = []


        resource_levers = {

            "wood": ["settlement_infrastructure", "mobility_trade"],

            "stone": ["settlement_infrastructure", "governance_coordination"],

            "food": ["food_security", "socioeconomic_complexity"],

            "crop": ["food_security", "socioeconomic_complexity"],

            "fruit": ["food_security", "knowledge_institutions"],

            "herb": ["knowledge_institutions", "food_security"],

            "fish": ["food_security", "mobility_trade"],

        }


        return {

            "current_era": self.era.value,

            "target_era": target_era.value if target_era else None,

            "transition_key": transition_key,

            "readiness": readiness,

            "indicators": indicators,

            "top_gaps": top_gaps,

            "resource_levers": resource_levers,

            "sources": source_notes,

        }



    def _default_global_quest(self) -> Dict[str, Any]:

        population = len([a for a in self.agents.values() if a.is_alive])

        resource = str(self.world_rng.choice(list(self._quest_resource_options())))

        era_factor = {

            EraEnum.PREHISTORIC: 0,

            EraEnum.ANCIENT: 8,

            EraEnum.MEDIEVAL: 14,

            EraEnum.MODERN: 20,

        }.get(self.era, 0)

        target_amount = int(max(20, min(220, population * 2 + era_factor + int(self.world_rng.integers(0, 12)))))

        reward_coin = int(max(25, min(420, target_amount + int(self.world_rng.integers(20, 90)))))

        deadline = int(max(90, min(700, 180 + target_amount * 2)))

        return {

            "title": f"Guild Quest: Gather {target_amount} {resource}",

            "resource": resource,

            "target_amount": target_amount,

            "reward_coin": reward_coin,

            "deadline_ticks": deadline,

            "description": f"All citizens cooperate to gather {target_amount} {resource}; coins are split by contribution share.",

        }



    def _start_new_global_quest(self):

        alive = [a for a in self.agents.values() if a.is_alive]

        if not alive:

            return

        llm_payload = query_llm_for_global_quest(self)

        base = llm_payload if isinstance(llm_payload, dict) else self._default_global_quest()

        fallback = self._default_global_quest()

        resource = str(base.get("resource", fallback["resource"])).lower().strip()

        if resource not in self._quest_resource_options():

            resource = fallback["resource"]

        target_amount = int(base.get("target_amount", fallback["target_amount"]))

        reward_coin = int(base.get("reward_coin", fallback["reward_coin"]))

        deadline_ticks = int(base.get("deadline_ticks", fallback["deadline_ticks"]))

        target_amount = int(max(20, min(220, target_amount)))

        reward_coin = int(max(20, min(500, reward_coin)))

        deadline_ticks = int(max(80, min(800, deadline_ticks)))

        title = str(base.get("title") or f"Guild Quest: Gather {target_amount} {resource}").strip()

        description = str(base.get("description") or f"Gather {target_amount} {resource} together; coin rewards are proportional.").strip()

        self.global_quest = {

            "id": str(uuid.uuid4())[:8],

            "title": title,

            "description": description,

            "resource": resource,

            "target_amount": target_amount,

            "reward_coin": reward_coin,

            "created_tick": self.tick,

            "deadline_tick": self.tick + deadline_ticks,

            "progress_amount": 0,

            "contributors": {},

            "status": "active",

        }

        self.add_log(

            LogCategoryEnum.SYSTEM,

            f"📜 New global quest: {title} | Target: {target_amount} {resource} | Reward: {reward_coin} coin.",

        )



    def _finalize_global_quest(self, completed: bool):

        quest = self.global_quest

        if not quest:

            return

        contributors = dict(quest.get("contributors", {}))

        target_amount = max(1, int(quest.get("target_amount", 1)))

        reward_coin = int(max(0, quest.get("reward_coin", 0)))

        distributed = 0

        if completed and reward_coin > 0 and contributors:

            for aid, amount in contributors.items():

                share = int(max(0, amount))

                if share <= 0:

                    continue

                reward = int((share / target_amount) * reward_coin)

                if reward <= 0:

                    continue

                agent = self.agents.get(aid)

                if agent and agent.is_alive:

                    agent.inventory.coin += reward

                    distributed += reward

                    self.add_log(

                        LogCategoryEnum.ECONOMY,

                        f"🏆 Quest reward: {agent.name} contributed {share} {quest['resource']} and earned {reward} coin.",

                        interaction_type="quest_reward",

                        participant_ids=[aid],

                        source_agent_id=aid,

                    )

        quest_record = {

            **quest,

            "status": "completed" if completed else "expired",

            "completed_tick": self.tick,

            "distributed_coin": distributed,

        }

        self.quest_history.append(quest_record)

        self.quest_history = self.quest_history[-20:]

        if completed:

            self.add_log(

                LogCategoryEnum.SYSTEM,

                f"✅ Quest completed: {quest['title']} (progress {quest['progress_amount']}/{quest['target_amount']}).",

            )

        else:

            self.add_log(

                LogCategoryEnum.SYSTEM,

                f"⌛ Quest expired: {quest['title']} (progress {quest['progress_amount']}/{quest['target_amount']}).",

            )

        self.global_quest = None

        self.next_quest_tick = self.tick + QUEST_COOLDOWN_TICKS



    def _record_quest_contribution(self, agent: AgentSchema, resource_name: str, amount: int):

        quest = self.global_quest

        if not quest or amount <= 0:

            return

        if str(quest.get("status")) != "active":

            return

        if str(quest.get("resource")) != str(resource_name):

            return

        contributors = quest.setdefault("contributors", {})

        contributors[agent.id] = int(contributors.get(agent.id, 0)) + int(amount)

        quest["progress_amount"] = int(quest.get("progress_amount", 0)) + int(amount)

        if int(quest.get("progress_amount", 0)) >= int(quest.get("target_amount", 1)):

            self._finalize_global_quest(completed=True)



    def _update_global_quest(self):

        if self.global_quest is None and self.tick >= self.next_quest_tick:

            self._start_new_global_quest()

        quest = self.global_quest

        if quest and int(quest.get("deadline_tick", 0)) <= self.tick:

            self._finalize_global_quest(completed=False)



    def get_agent_model(self, agent_id: str) -> str:

        agent = self.agents.get(agent_id)

        if self.active_model == "mixed" and agent:

            return normalize_model_name(agent.model_name or self.model_assignments.get(agent_id, DEFAULT_MODEL))

        return normalize_model_name(self.active_model)



    def _assign_agent_models(self):

        if self.active_model != "mixed":

            self.model_assignments = {}

            for agent in self.agents.values():

                agent.model_slot = "A"

                agent.model_name = normalize_model_name(self.active_model)

            return



        # Mixed mode cycles equally across A/B/C/D model slots.

        model_cycle = [

            ("A", "qwen2.5:1.5b"),

            ("B", "qwen3:4b"),

            ("C", "gemma3:4b"),

            ("D", "deepseek-coder:1.3b"),

        ]

        self.model_assignments = {}

        alive_agents = list(self.agents.values())

        for index, agent in enumerate(alive_agents):

            slot, model_name = model_cycle[index % len(model_cycle)]

            agent.model_slot = slot

            agent.model_name = model_name

            self.model_assignments[agent.id] = model_name



    def init_map(self, preset: str = "realistic", env_params: dict = None, num_agents: int = 30):

        """Generate a new map and save the original state."""

        self.map_preset = preset

        if env_params:

            self.env_params = env_params

        self.world_seed = self._build_world_seed(preset, self.env_params)

        self._reset_world_rng()

        self.terrain, self.elevation, self.island_infos = generate_terrain(self.map_size, preset, self.env_params, rng=self.world_rng)

        # Deep copy terrain as backup

        self.original_terrain = [row[:] for row in self.terrain]

        self.original_elevation = self.elevation.copy()

        self._init_hydrology()

        self.populate(num_agents=num_agents)



    def _tile_key(self, x: int, y: int) -> str:

        return f"{x},{y}"



    def _init_hydrology(self):

        self.groundwater.clear()

        for y in range(self.map_size):

            for x in range(self.map_size):

                tile = self.terrain[y][x]

                if tile in [TerrainType.GRASS.value, TerrainType.FOREST.value, TerrainType.BEACH.value, TerrainType.ROAD.value]:

                    base = 72.0

                    if tile == TerrainType.FOREST.value:

                        base = 85.0

                    elif tile == TerrainType.BEACH.value:

                        base = 62.0

                    elif tile == TerrainType.ROAD.value:

                        base = 56.0

                    self.groundwater[self._tile_key(x, y)] = float(np.clip(base + self.world_rng.uniform(-8.0, 8.0), 8.0, 100.0))



        self.weather = {

            "condition": "clear",

            "cloud_cover": 0.25,

            "rain_intensity": 0.0,

            "next_change_tick": 60,

        }



    def _update_weather_and_hydrology(self):

        if not self.groundwater:

            return



        changed = False

        if self.tick >= int(self.weather.get("next_change_tick", 0)):

            water_factor = float(self.env_params.get("water", 50)) / 100.0

            rain_prob = 0.18 + (0.35 * water_factor)

            cloud_prob = 0.30

            roll = float(self.world_rng.random())



            if roll < rain_prob:

                self.weather["condition"] = "rain"

                self.weather["cloud_cover"] = float(np.clip(self.world_rng.uniform(0.7, 1.0), 0.0, 1.0))

                self.weather["rain_intensity"] = float(np.clip(self.world_rng.uniform(0.45, 1.0), 0.0, 1.0))

                self.weather["next_change_tick"] = self.tick + int(self.world_rng.integers(35, 90))

            elif roll < rain_prob + cloud_prob:

                self.weather["condition"] = "cloudy"

                self.weather["cloud_cover"] = float(np.clip(self.world_rng.uniform(0.45, 0.85), 0.0, 1.0))

                self.weather["rain_intensity"] = 0.0

                self.weather["next_change_tick"] = self.tick + int(self.world_rng.integers(30, 80))

            else:

                self.weather["condition"] = "clear"

                self.weather["cloud_cover"] = float(np.clip(self.world_rng.uniform(0.08, 0.35), 0.0, 1.0))

                self.weather["rain_intensity"] = 0.0

                self.weather["next_change_tick"] = self.tick + int(self.world_rng.integers(40, 120))

            changed = True



        if self.weather.get("condition") == "rain":

            rain_intensity = float(self.weather.get("rain_intensity", 0.0))

            recharge = 0.45 + (rain_intensity * 1.45)

            for key, value in list(self.groundwater.items()):

                self.groundwater[key] = float(min(100.0, value + recharge + float(self.world_rng.uniform(0.0, 0.25))))



            if self.tick % 25 == 0:

                self.add_log(LogCategoryEnum.SYSTEM, "Rainfall is recharging groundwater across the land.", interaction_type="rain_recharge")



        if changed:

            condition = self.weather.get("condition", "clear")

            if condition == "rain":

                self.add_log(LogCategoryEnum.SYSTEM, "Clouds gather and rain starts to fall.", interaction_type="weather_rain")

            elif condition == "cloudy":

                self.add_log(LogCategoryEnum.SYSTEM, "Cloud cover increases across the sky.", interaction_type="weather_cloudy")

            else:

                self.add_log(LogCategoryEnum.SYSTEM, "Skies clear up and the weather stabilizes.", interaction_type="weather_clear")



    def get_hydrology_status(self) -> Dict[str, float]:

        if not self.groundwater:

            return {"avg_groundwater": 0.0, "low_groundwater_tiles": 0}

        levels = list(self.groundwater.values())

        low_tiles = sum(1 for level in levels if level < 20.0)

        return {

            "avg_groundwater": round(float(np.mean(levels)), 2),

            "low_groundwater_tiles": int(low_tiles),

        }



    def _refresh_agent_relationship_views(self):

        for agent in self.agents.values():

            agent.relationships = {}



        for rel_key, value in self.relationships.items():

            ids = rel_key.split("::")

            if len(ids) != 2:

                continue

            a_id, b_id = ids[0], ids[1]

            if a_id not in self.agents or b_id not in self.agents:

                continue



            detail = self.relationship_details.get(rel_key, {})

            shared_payload = {

                "value": float(value),

                "friendship": float(detail.get("friendship", value)),

                "romance": float(detail.get("romance", 0.0)),

                "interactions": list(detail.get("interactions", []))[-8:],

                "last_interaction_tick": int(detail.get("last_tick", self.tick)),

            }

            self.agents[a_id].relationships[b_id] = dict(shared_payload)

            self.agents[b_id].relationships[a_id] = dict(shared_payload)



    def _is_walkable(self, x: int, y: int, has_boat: bool = False) -> bool:

        if x < 0 or x >= self.map_size or y < 0 or y >= self.map_size:

            return False

        t = self.terrain[y][x]

        if t == TerrainType.SNOW.value:

            return False

        if t == TerrainType.OCEAN.value and not has_boat:

            return False

        return True



    def _is_land(self, x: int, y: int) -> bool:

        if x < 0 or x >= self.map_size or y < 0 or y >= self.map_size:

            return False

        return self.terrain[y][x] not in [TerrainType.OCEAN.value, TerrainType.SNOW.value]



    def _is_spawnable_land(self, x: int, y: int) -> bool:

        if x < 0 or x >= self.map_size or y < 0 or y >= self.map_size:

            return False

        return self.terrain[y][x] in [

            TerrainType.BEACH.value,

            TerrainType.GRASS.value,

            TerrainType.FOREST.value,

            TerrainType.MOUNTAIN.value,

            TerrainType.ROAD.value,

        ]



    def _resource_food_preference(self, resource_type: ResourceTypeEnum) -> Optional[str]:

        mapping = {

            ResourceTypeEnum.FOOD: "food",

            ResourceTypeEnum.FISH: "fish",

            ResourceTypeEnum.PIG: "pork",

            ResourceTypeEnum.COW: "beef",

            ResourceTypeEnum.CHICKEN: "chicken",

            ResourceTypeEnum.CROP: "crop",

            ResourceTypeEnum.FRUIT: "fruit",

        }

        return mapping.get(resource_type)



    def _ensure_agent_skills(self, agent: AgentSchema):

        if not isinstance(agent.skills, dict):

            agent.skills = {}

        for key, base in DEFAULT_SKILL_PROFILE.items():

            if key not in agent.skills:

                agent.skills[key] = float(base)



    def get_skill(self, agent: AgentSchema, skill: str) -> float:

        self._ensure_agent_skills(agent)

        return float(agent.skills.get(skill, 0.0))



    def gain_skill(self, agent: AgentSchema, skill: str, amount: float):

        self._ensure_agent_skills(agent)

        current = float(agent.skills.get(skill, 0.0))

        agent.skills[skill] = float(np.clip(current + amount, 0.0, 100.0))



    def _skill_multiplier(self, skill_value: float) -> float:

        # 0..100 skill -> 1.0x .. 2.0x productivity

        return 1.0 + (max(0.0, min(100.0, skill_value)) / 100.0)



    def _apply_profession_income_and_skill_growth(self, agent: AgentSchema):

        if agent.life_phase not in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT, LifePhaseEnum.ELDER]:

            return

        if self.tick % 12 != 0:

            return



        era_rank = {

            EraEnum.PREHISTORIC: 1,

            EraEnum.ANCIENT: 2,

            EraEnum.MEDIEVAL: 3,

            EraEnum.MODERN: 4,

        }.get(self.era, 1)



        if agent.job == "Trader":

            trading = self.get_skill(agent, "trading")

            diplomacy = self.get_skill(agent, "diplomacy")

            gain = int((1 + era_rank) * self._skill_multiplier((trading + diplomacy) * 0.5) * 0.8)

            gain = max(1, gain)

            agent.inventory.coin += gain

            self.gain_skill(agent, "trading", 0.9)

            self.gain_skill(agent, "diplomacy", 0.5)

            if self.tick % 36 == 0:

                self.add_log(LogCategoryEnum.ECONOMY, f"💱 {agent.name} completed profitable trades (+{gain} coin).", interaction_type="trade_income", source_agent_id=agent.id)



        elif agent.job == "Fisher":

            fishing = self.get_skill(agent, "fishing")

            if 0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size:

                terrain_here = self.terrain[agent.y][agent.x]

                if terrain_here in [TerrainType.RIVER.value, TerrainType.BEACH.value, TerrainType.OCEAN.value]:

                    fish_gain = max(1, int(self._skill_multiplier(fishing) * 1.2))

                    agent.inventory.food += fish_gain

                    agent.inventory.coin += max(0, fish_gain - 1)

                    self.gain_skill(agent, "fishing", 0.8)



        elif agent.job == "Doctor":

            medicine = self.get_skill(agent, "medicine")

            if agent.inventory.herb > 0:

                patient = None

                for other in self.agents.values():

                    if not other.is_alive or other.id == agent.id:

                        continue

                    if abs(other.x - agent.x) + abs(other.y - agent.y) <= 2 and (other.vitals.energy < 60 or other.vitals.hydration < 55):

                        patient = other

                        break

                if patient:

                    heal = 6.0 + (medicine / 12.0)

                    agent.inventory.herb -= 1

                    patient.vitals.energy = min(100.0, patient.vitals.energy + heal)

                    patient.vitals.hydration = min(100.0, patient.vitals.hydration + (heal * 0.6))

                    agent.inventory.coin += max(1, int(heal / 4.0))

                    self.gain_skill(agent, "medicine", 1.1)

                    self.add_log(LogCategoryEnum.SOCIAL, f"🩺 {agent.name} treated {patient.name} using herbs.", interaction_type="medical_treatment", participant_ids=[agent.id, patient.id], source_agent_id=agent.id)



        elif agent.job == "Farmer":

            farming = self.get_skill(agent, "farming")

            if agent.inventory.crop > 0:

                bonus = max(1, int(self._skill_multiplier(farming)))

                agent.inventory.food += bonus

                self.gain_skill(agent, "farming", 0.7)



        elif agent.job == "Miner":

            construction = self.get_skill(agent, "construction")

            haul = max(1, int(self._skill_multiplier(construction) * 1.3))

            agent.inventory.stone += haul

            if self.tick % 24 == 0:

                coin_gain = max(1, haul // 2)

                agent.inventory.coin += coin_gain

            self.gain_skill(agent, "construction", 0.8)

            self.gain_skill(agent, "gathering", 0.3)



        elif agent.job == "Rancher":

            livestock = agent.inventory.pig + agent.inventory.cow + agent.inventory.chicken

            if livestock > 0:

                food_gain = max(1, min(4, livestock // 3))

                agent.inventory.food += food_gain

                if self.tick % 24 == 0:

                    agent.inventory.coin += max(1, food_gain // 2)

                self.gain_skill(agent, "farming", 0.7)

                self.gain_skill(agent, "hunting", 0.4)



        elif agent.job == "Lumberjack":

            construction = self.get_skill(agent, "construction")

            wood_gain = max(1, int(self._skill_multiplier(construction) * 1.5))

            agent.inventory.wood += wood_gain

            if self.tick % 24 == 0:

                agent.inventory.coin += max(1, wood_gain // 2)

            self.gain_skill(agent, "construction", 0.9)

            self.gain_skill(agent, "gathering", 0.4)



        elif agent.job == "Builder":

            self.gain_skill(agent, "construction", 0.5)

            if era_rank >= 3:

                agent.inventory.coin += 1



        elif agent.job == "Guard":

            self.gain_skill(agent, "leadership", 0.2)

            self.gain_skill(agent, "diplomacy", 0.1)



    def _update_royal_lineage(self):

        if self.tick % 60 != 0:

            return



        royals = [a for a in self.agents.values() if a.is_alive and a.social_class == SocialClassEnum.ROYALTY]

        for ruler in royals:

            # keep ruler title coherent

            if ruler.royal_title not in {"king", "queen"}:

                ruler.royal_title = "king" if ruler.gender == GenderEnum.MALE else "queen"



            heirs = [self.agents[cid] for cid in ruler.children if cid in self.agents and self.agents[cid].is_alive]

            if not heirs:

                continue

            heir = max(heirs, key=lambda c: c.age)

            desired_title = "crown_prince" if heir.gender == GenderEnum.MALE else "crown_princess"

            if heir.royal_title != desired_title:

                heir.royal_title = desired_title

                self.add_log(

                    LogCategoryEnum.SOCIAL,

                    f"👑 Succession update: {heir.name} is now {desired_title.replace('_', ' ')} of {ruler.name}'s line.",

                    interaction_type="crown_heir_updated",

                    participant_ids=[ruler.id, heir.id],

                    source_agent_id=ruler.id,

                )



    def get_vision_radius(self, agent: AgentSchema) -> int:

        base = 7

        if agent.life_phase == LifePhaseEnum.CHILD:

            base = 5

        elif agent.life_phase == LifePhaseEnum.TEEN:

            base = 6

        elif agent.life_phase == LifePhaseEnum.ELDER:

            base = 6



        intellect_bonus = 1 if agent.personality.intellect > 0.45 else 0

        return max(3, min(10, base + intellect_bonus))



    def _ensure_agent_world_memory(self, agent_id: str):

        if agent_id not in self.agent_world_memory:

            self.agent_world_memory[agent_id] = {

                "tile_knowledge": {},

                "resource_spots": {},

                "recent_events": [],

            }



    def _remember_event(self, agent_id: str, text: str):

        self._ensure_agent_world_memory(agent_id)

        events = self.agent_world_memory[agent_id]["recent_events"]

        events.append(f"t{self.tick}: {text}")

        self.agent_world_memory[agent_id]["recent_events"] = events[-12:]



    def _remember_resource_spot(self, agent_id: str, x: int, y: int, resource_type: str):

        self._ensure_agent_world_memory(agent_id)

        key = f"{x},{y}"

        spots = self.agent_world_memory[agent_id]["resource_spots"]

        entry = spots.get(key, {"types": {}, "last_seen": self.tick, "seen_count": 0})

        seen_types = dict(entry.get("types", {}))

        seen_types[resource_type] = int(seen_types.get(resource_type, 0)) + 1

        entry["types"] = seen_types

        entry["last_seen"] = self.tick

        entry["seen_count"] = int(entry.get("seen_count", 0)) + 1

        spots[key] = entry



    def _remember_tile_visit(self, agent_id: str, x: int, y: int, terrain: str):

        self._ensure_agent_world_memory(agent_id)

        key = f"{x},{y}"

        tiles = self.agent_world_memory[agent_id]["tile_knowledge"]

        entry = tiles.get(key, {

            "visits": 0,

            "terrain": terrain,

            "crop_sign": 0,

            "fruit_sign": 0,

            "livestock_sign": 0,

            "last_seen": self.tick,

        })

        entry["visits"] = int(entry.get("visits", 0)) + 1

        entry["terrain"] = terrain

        entry["last_seen"] = self.tick

        tiles[key] = entry



    def _record_visible_resource_knowledge(self, agent: AgentSchema):

        self._ensure_agent_world_memory(agent.id)

        if not (0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size):

            return



        terrain_here = self.terrain[agent.y][agent.x]

        self._remember_tile_visit(agent.id, agent.x, agent.y, terrain_here)



        vision = self.get_vision_radius(agent)

        for res in self.resources:

            dist = abs(res.x - agent.x) + abs(res.y - agent.y)

            if dist > vision:

                continue

            self._remember_resource_spot(agent.id, res.x, res.y, res.type.value)



            tile_key = f"{res.x},{res.y}"

            tiles = self.agent_world_memory[agent.id]["tile_knowledge"]

            tile_entry = tiles.get(tile_key, {

                "visits": 0,

                "terrain": self.terrain[res.y][res.x] if 0 <= res.x < self.map_size and 0 <= res.y < self.map_size else "unknown",

                "crop_sign": 0,

                "fruit_sign": 0,

                "livestock_sign": 0,

                "last_seen": self.tick,

            })

            if res.type in [ResourceTypeEnum.CROP, ResourceTypeEnum.FOOD]:

                tile_entry["crop_sign"] = int(tile_entry.get("crop_sign", 0)) + 1

            if res.type in [ResourceTypeEnum.FRUIT, ResourceTypeEnum.FISH]:

                tile_entry["fruit_sign"] = int(tile_entry.get("fruit_sign", 0)) + 1

            if res.type in [ResourceTypeEnum.PIG, ResourceTypeEnum.COW, ResourceTypeEnum.CHICKEN]:

                tile_entry["livestock_sign"] = int(tile_entry.get("livestock_sign", 0)) + 1

            tile_entry["last_seen"] = self.tick

            tiles[tile_key] = tile_entry



    def get_agent_memory_summary(self, agent_id: str, limit: int = 6) -> Dict[str, Any]:

        self._ensure_agent_world_memory(agent_id)

        mem = self.agent_world_memory[agent_id]



        spots = []

        for coord, info in mem.get("resource_spots", {}).items():

            age = self.tick - int(info.get("last_seen", self.tick))

            if age > 900:

                continue

            types = info.get("types", {})

            main_type = max(types.items(), key=lambda item: item[1])[0] if types else "unknown"

            spots.append({

                "coord": coord,

                "type": main_type,

                "seen_count": int(info.get("seen_count", 0)),

                "age": age,

            })

        spots.sort(key=lambda item: (item["age"], -item["seen_count"]))



        tile_notes = []

        for coord, info in mem.get("tile_knowledge", {}).items():

            visits = int(info.get("visits", 0))

            if visits < 2:

                continue

            tile_notes.append({

                "coord": coord,

                "terrain": info.get("terrain", "unknown"),

                "visits": visits,

                "fertility_hint": int(info.get("crop_sign", 0)) + int(info.get("fruit_sign", 0)),

                "livestock_hint": int(info.get("livestock_sign", 0)),

            })

        tile_notes.sort(key=lambda item: (-item["visits"], -item["fertility_hint"], -item["livestock_hint"]))



        return {

            "resource_spots": spots[:limit],

            "tile_notes": tile_notes[:limit],

            "recent_events": mem.get("recent_events", [])[-6:],

        }



    def _assign_food_preferences(self, index: int) -> Tuple[List[str], List[str]]:

        food_pool = ["food", "fish", "chicken", "beef", "pork", "crop", "fruit", "meat"]

        shuffled = list(self.world_rng.permutation(food_pool))

        likes = shuffled[:2]

        dislikes = [shuffled[2 + (index % 2)]]

        return likes, dislikes



    def _owned_house(self, agent: AgentSchema) -> Optional[HouseNode]:

        if not agent.house_id:

            return None

        return next((house for house in self.houses if house.id == agent.house_id), None)



    def _is_near_home(self, agent: AgentSchema, radius: int = 1) -> bool:

        house = self._owned_house(agent)

        if not house:

            return False

        return abs(agent.x - house.x) + abs(agent.y - house.y) <= radius



    def _step_towards(self, sx: int, sy: int, tx: int, ty: int) -> Tuple[int, int]:

        dx = 0 if tx == sx else (1 if tx > sx else -1)

        dy = 0 if ty == sy else (1 if ty > sy else -1)

        return dx, dy



    def _movement_direction_label(self, delta_x: int, delta_y: int) -> str:

        north_south = ""

        east_west = ""

        if delta_y < 0:

            north_south = "north"

        elif delta_y > 0:

            north_south = "south"

        if delta_x < 0:

            east_west = "west"

        elif delta_x > 0:

            east_west = "east"

        if north_south and east_west:

            return f"{north_south}-{east_west}"

        if north_south:

            return north_south

        if east_west:

            return east_west

        return "stationary"



    def _record_movement_progress(self, agent: AgentSchema, from_x: int, from_y: int, moved_steps: int):

        if moved_steps <= 0:

            return

        session = self.agent_movement_sessions.get(agent.id)

        if not session:

            session = {

                "start_x": int(from_x),

                "start_y": int(from_y),

                "total_steps": 0,

            }

            self.agent_movement_sessions[agent.id] = session

        session["total_steps"] = int(session.get("total_steps", 0)) + int(moved_steps)



    def _flush_movement_summary(self, agent: AgentSchema):

        session = self.agent_movement_sessions.pop(agent.id, None)

        if not session:

            return

        total_steps = int(session.get("total_steps", 0))

        if total_steps <= 0:

            return

        start_x = int(session.get("start_x", agent.x))

        start_y = int(session.get("start_y", agent.y))

        end_x = int(agent.x)

        end_y = int(agent.y)

        direction = self._movement_direction_label(end_x - start_x, end_y - start_y)

        self.add_log(

            LogCategoryEnum.SPATIAL,

            f"🧭 {agent.name} reached ({end_x},{end_y}) after moving {total_steps} squares toward {direction}.",

            interaction_type="movement_summary",

            participant_ids=[agent.id],

            source_agent_id=agent.id,

        )



    def _find_nearest_visible_tile(self, agent: AgentSchema, tile_types: List[str]) -> Optional[Tuple[int, int]]:

        vision = self.get_vision_radius(agent)

        best_target: Optional[Tuple[int, int]] = None

        best_dist = 10**9

        for y in range(max(0, agent.y - vision), min(self.map_size, agent.y + vision + 1)):

            for x in range(max(0, agent.x - vision), min(self.map_size, agent.x + vision + 1)):

                if self.terrain[y][x] not in tile_types:

                    continue

                dist = abs(agent.x - x) + abs(agent.y - y)

                if 0 < dist < best_dist:

                    best_dist = dist

                    best_target = (x, y)

        return best_target



    def _find_nearest_visible_resource(self, agent: AgentSchema, allowed_types: List[ResourceTypeEnum]) -> Optional[Tuple[int, int, str]]:

        vision = self.get_vision_radius(agent)

        best = None

        best_dist = 10**9

        for res in self.resources:

            if res.type not in allowed_types:

                continue

            dist = abs(agent.x - res.x) + abs(agent.y - res.y)

            if dist <= vision and dist < best_dist:

                best_dist = dist

                best = (res.x, res.y, res.type.value)

        return best



    def _apply_reactive_combo(self, agent: AgentSchema, must_go_home: bool = False) -> bool:

        if must_go_home:

            return False



        # Critical safety layer: intervene only when survival risk or prolonged idle is detected.

        idle_ticks = self.agent_idle_ticks.get(agent.id, 0)

        critical = (agent.vitals.hydration < 40 or agent.vitals.hunger < 20 or agent.vitals.energy < 24)

        if not critical and idle_ticks < 12:

            return False



        if agent.vitals.hydration < 40:

            water_tile = self._find_nearest_visible_tile(agent, [TerrainType.RIVER.value])

            if water_tile:

                agent.dx, agent.dy = self._step_towards(agent.x, agent.y, water_tile[0], water_tile[1])

                agent.currentThought = "I must secure water now."

                return True



        if agent.vitals.hunger < 22:

            food_target = self._find_nearest_visible_resource(

                agent,

                [

                    ResourceTypeEnum.FOOD,

                    ResourceTypeEnum.FISH,

                    ResourceTypeEnum.CROP,

                    ResourceTypeEnum.FRUIT,

                    ResourceTypeEnum.PIG,

                    ResourceTypeEnum.COW,

                    ResourceTypeEnum.CHICKEN,

                ],

            )

            if food_target:

                agent.dx, agent.dy = self._step_towards(agent.x, agent.y, food_target[0], food_target[1])

                agent.currentThought = f"I should gather {food_target[2]} before I get too hungry."

                return True



        if agent.vitals.social < 35:

            nearest = None

            nearest_dist = 10**9

            for other in self.agents.values():

                if not other.is_alive or other.id == agent.id:

                    continue

                dist = abs(other.x - agent.x) + abs(other.y - agent.y)

                if 0 < dist < nearest_dist:

                    nearest = other

                    nearest_dist = dist

            if nearest and nearest_dist > 1:

                agent.dx, agent.dy = self._step_towards(agent.x, agent.y, nearest.x, nearest.y)

                agent.currentThought = f"I need social contact. Heading toward {nearest.name}."

                return True



        house = self._owned_house(agent)

        if house and agent.vitals.energy < 24:

            agent.dx, agent.dy = self._step_towards(agent.x, agent.y, house.x, house.y)

            agent.currentThought = "I need to return home and recover energy."

            return True



        return False



    def _movement_profile(self, agent: AgentSchema, must_go_home: bool = False) -> Tuple[int, bool]:

        steps = 1

        is_running = False



        if agent.inventory.has_car:

            steps = 3

        elif agent.inventory.has_horse:

            steps = 2

        elif agent.inventory.has_cart:

            steps = 2

        elif agent.inventory.has_boat and 0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size:

            if self.terrain[agent.y][agent.x] in [TerrainType.OCEAN.value, TerrainType.RIVER.value]:

                steps = 2



        has_vehicle = any([

            agent.inventory.has_car,

            agent.inventory.has_horse,

            agent.inventory.has_cart,

            agent.inventory.has_boat,

        ])

        urgent_move = (

            must_go_home

            or agent.vitals.hunger < 22

            or agent.vitals.hydration < 38

            or agent.vitals.social < 25

        )

        if not has_vehicle and urgent_move and agent.vitals.energy > 45 and self.world_rng.random() < 0.55:

            steps = 2

            is_running = True



        return steps, is_running



    def _rel_key(self, a: str, b: str) -> str:

        return "::".join(sorted([a, b]))



    def get_relationship(self, a: str, b: str) -> float:

        return social.get_relationship(self, a, b)



    def add_relationship(self, a: str, b: str, amount: float):

        social.add_relationship(self, a, b, amount)



    def _find_land_on_island(self, island_idx: int) -> Tuple[int, int]:

        if island_idx < len(self.island_infos):

            land = self.island_infos[island_idx].get("land_tiles", [])

            if land:

                probe_order = self.world_rng.permutation(len(land))

                for i in probe_order[: min(len(land), 400)]:

                    x, y = land[int(i)]

                    if self._is_spawnable_land(x, y):

                        return x, y

            info = self.island_infos[island_idx]

            return self._find_land_near(info.get("cx", self.map_size // 2), info.get("cy", self.map_size // 2), max(8, int(info.get("radius", 12))))

        return self._find_any_land()



    def _find_land_near(self, cx: int, cy: int, radius: int) -> Tuple[int, int]:

        for _ in range(500):

            dx = int(self.world_rng.integers(-radius, radius + 1))

            dy = int(self.world_rng.integers(-radius, radius + 1))

            x = max(0, min(self.map_size - 1, cx + dx))

            y = max(0, min(self.map_size - 1, cy + dy))

            if self._is_spawnable_land(x, y):

                return x, y

        return self._find_any_land()



    def _find_any_land(self) -> Tuple[int, int]:

        for _ in range(1000):

            x = int(self.world_rng.integers(0, self.map_size))

            y = int(self.world_rng.integers(0, self.map_size))

            if self._is_spawnable_land(x, y):

                return x, y



        # Fallback: pick any spawnable tile closest to center.

        center = self.map_size // 2

        best = (center, center)

        best_dist = float("inf")

        for y in range(self.map_size):

            for x in range(self.map_size):

                if self._is_spawnable_land(x, y):

                    dist = abs(x - center) + abs(y - center)

                    if dist < best_dist:

                        best_dist = dist

                        best = (x, y)

        if best_dist < float("inf"):

            return best



        # Emergency fallback for edge-case maps with no spawnable land:

        # carve a tiny safe patch at center so citizens never start in ocean.

        for dy in range(-1, 2):

            for dx in range(-1, 2):

                nx = max(0, min(self.map_size - 1, center + dx))

                ny = max(0, min(self.map_size - 1, center + dy))

                self.terrain[ny][nx] = TerrainType.GRASS.value

        return center, center



    def reset(self):

        """Restart civilization but keep the SAME map."""

        self.tick = 0

        self.agents.clear()

        self.logs.clear()

        self.resources.clear()

        self.settlements.clear()

        self.houses.clear()

        self.gravestones.clear()

        self.relationships.clear()

        self.relationship_details.clear()

        self.social_pair_last_log.clear()

        self.social_links.clear()

        self.log_signature_last_tick.clear()

        self.pending_cognitive_tasks.clear()

        self.think_turn_cursor = 0

        self.agent_world_memory.clear()

        self.agent_idle_ticks.clear()

        self.era = EraEnum.PREHISTORIC

        self.target_tick = 0

        self._reset_world_rng()

        # Restore original terrain instead of regenerating

        self.terrain = [row[:] for row in self.original_terrain]

        self.elevation = self.original_elevation.copy()

        self._init_hydrology()

        self.populate()



    def populate(self, num_agents: int = 40):

        self.agents.clear()

        num_agents = int(num_agents or 30)

        if num_agents <= 0:

            num_agents = 30



        spawn_points: List[Tuple[int, int, str]] = []

        if self.island_infos:

            island_count = len(self.island_infos)

            base_quota = num_agents // island_count

            remainder = num_agents % island_count

            for idx, island in enumerate(self.island_infos):

                quota = base_quota + (1 if idx < remainder else 0)

                land_tiles = list(island.get("land_tiles", []))

                if not land_tiles:

                    continue

                order = self.world_rng.permutation(len(land_tiles))

                for tile_idx in order[:quota]:

                    x, y = land_tiles[int(tile_idx)]

                    spawn_points.append((x, y, island.get("name", f"Island_{idx + 1}")))



        if len(spawn_points) < num_agents:

            fallback_tiles: List[Tuple[int, int]] = []

            for y in range(self.map_size):

                for x in range(self.map_size):

                    if self._is_spawnable_land(x, y):

                        fallback_tiles.append((x, y))

            if fallback_tiles:

                order = self.world_rng.permutation(len(fallback_tiles))

                for tile_idx in order:

                    if len(spawn_points) >= num_agents:

                        break

                    x, y = fallback_tiles[int(tile_idx)]

                    spawn_points.append((x, y, "Unknown"))



        while len(spawn_points) < num_agents:

            x, y = self._find_any_land()

            spawn_points.append((x, y, "Unknown"))



        # Strategy for personality distribution:

        # - Citizen 01-05: Altruists (high kindness) in social clusters -> cooperation

        # - Citizen 06-10: Neutral/balanced in spread -> explorers & builders

        # - Citizen 11-15: Troublemakers (low kindness) isolated initially -> conflict potential

        # - Citizen 16-20: Intelligent socials (high intellect + sociability) -> leaders

        # - Citizen 21-25: Cowards (low bravery) protective -> safe groups

        # - Citizen 26-30: Ambitious brave risk-takers (high bravery+ambition) -> adventurers



        def get_personality_profile(index: int) -> Personality:

            """Generate deterministic personality based on citizen index."""

            profile = index % 6  # 6 personality archetypes

            

            if profile == 0:  # Altruists (01-05)

                return Personality(

                    kindness=round(float(self.world_rng.uniform(0.5, 1.0)), 2),

                    bravery=round(float(self.world_rng.uniform(-0.2, 0.6)), 2),

                    sociability=round(float(self.world_rng.uniform(0.3, 0.9)), 2),

                    intellect=round(float(self.world_rng.uniform(-0.1, 0.7)), 2),

                    empathy=round(float(self.world_rng.uniform(0.4, 1.0)), 2),

                )

            elif profile == 1:  # Balanced explorers (06-10)

                return Personality(

                    kindness=round(float(self.world_rng.uniform(-0.2, 0.5)), 2),

                    bravery=round(float(self.world_rng.uniform(0.2, 0.8)), 2),

                    sociability=round(float(self.world_rng.uniform(-0.3, 0.5)), 2),

                    intellect=round(float(self.world_rng.uniform(0.0, 0.8)), 2),

                    creativity=round(float(self.world_rng.uniform(0.1, 0.7)), 2),

                )

            elif profile == 2:  # Troublemakers (11-15) - isolated

                return Personality(

                    kindness=round(float(self.world_rng.uniform(-1.0, -0.3)), 2),

                    bravery=round(float(self.world_rng.uniform(-0.5, 0.5)), 2),

                    sociability=round(float(self.world_rng.uniform(-0.9, -0.2)), 2),

                    intellect=round(float(self.world_rng.uniform(-0.3, 0.4)), 2),

                    cunning=round(float(self.world_rng.uniform(0.2, 0.9)), 2),

                )

            elif profile == 3:  # Intelligent socials (16-20) - leader types

                return Personality(

                    kindness=round(float(self.world_rng.uniform(-0.1, 0.8)), 2),

                    bravery=round(float(self.world_rng.uniform(0.3, 0.9)), 2),

                    sociability=round(float(self.world_rng.uniform(0.5, 1.0)), 2),

                    intellect=round(float(self.world_rng.uniform(0.6, 1.0)), 2),

                    ambition=round(float(self.world_rng.uniform(0.4, 1.0)), 2),

                )

            elif profile == 4:  # Cowards (21-25) - protective types

                return Personality(

                    kindness=round(float(self.world_rng.uniform(0.2, 0.9)), 2),

                    bravery=round(float(self.world_rng.uniform(-0.8, -0.1)), 2),

                    sociability=round(float(self.world_rng.uniform(0.1, 0.8)), 2),

                    intellect=round(float(self.world_rng.uniform(-0.2, 0.6)), 2),

                    empathy=round(float(self.world_rng.uniform(0.4, 1.0)), 2),

                )

            else:  # profile == 5, Ambitious risk-takers (26-30)

                return Personality(

                    kindness=round(float(self.world_rng.uniform(-0.5, 0.4)), 2),

                    bravery=round(float(self.world_rng.uniform(0.7, 1.0)), 2),

                    sociability=round(float(self.world_rng.uniform(-0.3, 0.7)), 2),

                    intellect=round(float(self.world_rng.uniform(0.1, 0.9)), 2),

                    ambition=round(float(self.world_rng.uniform(0.6, 1.0)), 2),

                )



        for index in range(num_agents):

            a_id = f"agent_{index + 1:02d}"

            x, y, island_name = spawn_points[index]

            gender = GenderEnum.MALE if index % 2 == 0 else GenderEnum.FEMALE

            model_slot = "A"

            model_name = self.active_model

            if self.active_model == "mixed":

                model_cycle = [

                    ("A", "llama3.1:latest"),

                    ("B", "qwen3:4b"),

                    ("C", "gemma3:4b"),

                    ("D", "mistral:latest"),

                ]

                model_slot, model_name = model_cycle[index % len(model_cycle)]

            

            personality = get_personality_profile(index)

            likes, dislikes = self._assign_food_preferences(index)

            age = int(self.world_rng.integers(601, 1201))

            max_age = int(self.world_rng.integers(max(age + 240, 1440), 2801))

            

            self.agents[a_id] = AgentSchema(

                id=a_id,

                name=f"Citizen {index + 1:02d}",

                gender=gender,

                model_slot=model_slot,

                model_name=model_name,

                x=x,

                y=y,

                age=age,

                max_age=max_age,

                personality=personality,

                skills={

                    "gathering": float(np.clip(12 + self.world_rng.uniform(-3, 8), 0, 100)),

                    "farming": float(np.clip(8 + self.world_rng.uniform(-2, 8), 0, 100)),

                    "hunting": float(np.clip(8 + self.world_rng.uniform(-2, 8), 0, 100)),

                    "fishing": float(np.clip(8 + self.world_rng.uniform(-2, 8), 0, 100)),

                    "trading": float(np.clip(6 + self.world_rng.uniform(-2, 8), 0, 100)),

                    "construction": float(np.clip(6 + self.world_rng.uniform(-2, 8), 0, 100)),

                    "medicine": float(np.clip(4 + self.world_rng.uniform(-1, 6), 0, 100)),

                    "diplomacy": float(np.clip(6 + self.world_rng.uniform(-2, 8), 0, 100)),

                    "leadership": float(np.clip(5 + self.world_rng.uniform(-2, 8), 0, 100)),

                },

                likes=likes,

                dislikes=dislikes,

                vitals=Vitals(energy=100.0, hunger=100.0, social=100.0, happiness=72.0),

                inventory=Inventory(wood=5, food=5, coin=10, stone=2, tools=0, herb=0, has_boat=False),

                royal_title="",

                currentThought=f"I live on {island_name}.",

                actionState=ActionStateEnum.IDLE,

                dx=0,

                dy=0,

                is_alive=True,

                is_thinking=False,

                last_thought_tick=0,

                birth_tick=self.tick,

            )

            self._ensure_agent_skills(self.agents[a_id])

            self._ensure_agent_world_memory(a_id)

            self.agent_idle_ticks[a_id] = 0

        self._assign_agent_models()

        for _ in range(max(40, num_agents)):

            self.spawn_resource(force=True)



    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    #  SAVE / LOAD

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    #  SAVE / LOAD / RES SPAWN (Delegated)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def load_snapshot(self, filename: str) -> bool:

        return save_load.load_snapshot(self, filename)

        

    def save_snapshot(self, label: str = "") -> str:

        return save_load.save_snapshot(self, label)



    def list_saves(self):

        return save_load.list_saves()



    def spawn_resource(self, force=False):

        economy.spawn_resource(self, force)



    def build_road(self, x: int, y: int):

        if 0 <= x < self.map_size and 0 <= y < self.map_size:

            t = self.terrain[y][x]

            if t in [TerrainType.GRASS.value, TerrainType.BEACH.value, TerrainType.FOREST.value]:
                self.terrain[y][x] = TerrainType.ROAD.value



    def add_log(self, category, msg: str, interaction_type: str = None, participant_ids: list = None, 

                relationship_change: float = None, source_agent_id: str = None):

        if isinstance(category, str):

            category = LogCategoryEnum(category)



        # Prevent immediate repeated log spam for identical messages.

        if self.logs:

            last = self.logs[-1]

            if last.message == msg and self.tick - last.tick < LOG_DUPLICATE_COOLDOWN:

                return



        # Prevent the same exact message from repeating too often across ticks.

        signature = f"{category}:{msg}"

        last_tick = self.log_signature_last_tick.get(signature, -9999)

        if self.tick - last_tick < LOG_DUPLICATE_COOLDOWN:

            return



        log = SimulationLog(

            id=str(uuid.uuid4())[:8],

            tick=self.tick,

            calendar_date=self.format_calendar_date(),

            category=category,

            message=msg,

            timestamp=0.0,

            interaction_type=interaction_type,

            participant_ids=participant_ids or [],

            relationship_change=relationship_change,

            source_agent_id=source_agent_id,

        )

        self.logs.append(log)

        self.log_signature_last_tick[signature] = self.tick

        if len(self.log_signature_last_tick) > 4000:

            threshold = self.tick - 500

            self.log_signature_last_tick = {

                key: value for key, value in self.log_signature_last_tick.items() if value >= threshold

            }

        if len(self.logs) > 150:

            self.logs.pop(0)



    def _execute_trade(self, responder_id: str, offer_data: dict):

        economy.execute_trade(self, responder_id, offer_data)



    def _normalize_thought_for_vitals(self, agent: AgentSchema, thought: str) -> str:

        if not thought:

            return thought



        normalized = thought

        fullness = float(agent.vitals.hunger)



        # Guard against contradictory hunger language when fullness is still high.

        if fullness >= 70.0:

            hunger_terms = [

                "hungry",

                "starving",

                "too hungry",

                "going hungry",

                "lapar",

                "kelaparan",

            ]

            lower = normalized.lower()

            if any(term in lower for term in hunger_terms):

                normalized = "I should gather useful resources and maintain my reserves while conditions are good."



        # Remove stale embedded fullness numbers produced by older reasoning steps.

        normalized = re.sub(r"my fullness is\s*\d+(?:\.\d+)?%?", "my fullness is stable", normalized, flags=re.IGNORECASE)

        return normalized



    def process_cognitive_result(self, agent_id: str, new_action: dict):

        agent = self.agents.get(agent_id)

        if not agent or not agent.is_alive:

            return

        agent.is_thinking = False

        proposed_thought = new_action.get("thought", agent.currentThought)

        agent.currentThought = self._normalize_thought_for_vitals(agent, proposed_thought)

        agent.desire = new_action.get("desire", agent.desire)

        requested_dx = max(-1, min(1, int(new_action.get("move_x", 0))))

        requested_dy = max(-1, min(1, int(new_action.get("move_y", 0))))

        agent.last_thought_tick = self.tick

        raw_state = new_action.get("action", "moving").lower()



        # Correct common directional bias from LLM outputs by nudging movement

        # toward visible objectives when the requested step goes the wrong way.

        if raw_state in {"moving", "gathering", "working", "trading", "claim_territory", "contest_territory"}:

            visible_target = self._find_nearest_visible_resource(

                agent,

                [

                    ResourceTypeEnum.WOOD,

                    ResourceTypeEnum.STONE,

                    ResourceTypeEnum.COIN,

                    ResourceTypeEnum.FOOD,

                    ResourceTypeEnum.FISH,

                    ResourceTypeEnum.CROP,

                    ResourceTypeEnum.FRUIT,

                    ResourceTypeEnum.PIG,

                    ResourceTypeEnum.COW,

                    ResourceTypeEnum.CHICKEN,

                    ResourceTypeEnum.HERB,

                ],

            )

            if visible_target:

                current_dist = abs(agent.x - visible_target[0]) + abs(agent.y - visible_target[1])

                next_dist = abs((agent.x + requested_dx) - visible_target[0]) + abs((agent.y + requested_dy) - visible_target[1])

                if next_dist > current_dist:

                    requested_dx, requested_dy = self._step_towards(agent.x, agent.y, visible_target[0], visible_target[1])



        # If requested direction is blocked/outside map, pick a valid nearby fallback

        # so agents do not keep pressing toward one border (for example, west edge).

        proposed_nx, proposed_ny = agent.x + requested_dx, agent.y + requested_dy

        if (requested_dx != 0 or requested_dy != 0) and not self._is_walkable(proposed_nx, proposed_ny, agent.inventory.has_boat):

            fallback_dirs = [

                (1, 0),

                (-1, 0),

                (0, 1),

                (0, -1),

                (1, 1),

                (-1, -1),

                (1, -1),

                (-1, 1),

            ]

            for idx in self.world_rng.permutation(len(fallback_dirs)):

                fdx, fdy = fallback_dirs[int(idx)]

                if self._is_walkable(agent.x + fdx, agent.y + fdy, agent.inventory.has_boat):

                    requested_dx, requested_dy = fdx, fdy

                    break

            else:

                requested_dx, requested_dy = 0, 0



        agent.dx = requested_dx

        agent.dy = requested_dy

        

        # Async Trade Handshake

        if raw_state == "trading":

            target_id = new_action.get("trade_target")

            offer = new_action.get("trade_offer")

            if target_id and offer and target_id in self.agents and self.agents[target_id].is_alive:

                dist = abs(agent.x - self.agents[target_id].x) + abs(agent.y - self.agents[target_id].y)

                if dist <= 3:

                    self.agents[target_id].incoming_trade_offer = {

                        "from": agent_id,

                        "from_name": agent.name,

                        "give": offer.get("give", {}),

                        "take": offer.get("take", {})

                    }

                    agent.currentThought = f"Proposed trade to {self.agents[target_id].name}. Waiting for answer."

                    self.add_log(

                        LogCategoryEnum.ECONOMY,

                        f"Trade offer: {agent.name} -> {self.agents[target_id].name} (give {offer.get('give', {})}, take {offer.get('take', {})}).",

                        interaction_type="trade_offer_sent",

                        participant_ids=[agent.id, target_id],

                        source_agent_id=agent.id,

                    )

        elif raw_state == "accept_trade" and getattr(agent, "incoming_trade_offer", None):

            initiator_id = agent.incoming_trade_offer.get("from")

            self._execute_trade(agent_id, agent.incoming_trade_offer)

            if initiator_id and initiator_id in self.agents:

                self.add_log(

                    LogCategoryEnum.ECONOMY,

                    f"Trade accepted: {agent.name} accepted {self.agents[initiator_id].name}'s offer.",

                    interaction_type="trade_offer_accepted",

                    participant_ids=[agent.id, initiator_id],

                    source_agent_id=agent.id,

                )

            agent.incoming_trade_offer = None

        elif raw_state == "reject_trade":

            initiator_id = agent.incoming_trade_offer.get("from") if getattr(agent, "incoming_trade_offer", None) else None

            if initiator_id and initiator_id in self.agents:

                self.add_log(

                    LogCategoryEnum.ECONOMY,

                    f"Trade rejected: {agent.name} rejected {self.agents[initiator_id].name}'s offer.",

                    interaction_type="trade_offer_rejected",

                    participant_ids=[agent.id, initiator_id],

                    source_agent_id=agent.id,

                )

            agent.incoming_trade_offer = None

        elif raw_state == "working":

            economy.process_labor_action(self, agent)

        elif raw_state == "marrying":

            target_id = new_action.get("trade_target")

            self._try_marry(agent, target_id)

        elif raw_state == "claim_territory":

            self._try_claim_territory(agent)

        elif raw_state == "form_alliance":

            target_id = new_action.get("trade_target")

            self._try_form_alliance(agent, target_id)

        elif raw_state == "contest_territory":

            target_owner_id = new_action.get("trade_target")

            self._try_contest_territory(agent, target_owner_id)

        elif raw_state == "steal":

            target_id = new_action.get("trade_target")

            victim = self.agents.get(target_id) if target_id else None

            if victim and victim.is_alive and abs(agent.x - victim.x) + abs(agent.y - victim.y) <= 2:

                # Steal a random portion of victim's coin

                stolen = min(victim.inventory.coin, max(1, int(victim.inventory.coin * 0.3)))

                if stolen > 0:

                    victim.inventory.coin -= stolen

                    agent.inventory.coin += stolen

                    self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ¦¹ {agent.name} stole {stolen} Coin from {victim.name}!")

                    agent.personality.kindness = max(-1.0, agent.personality.kindness - 0.1)

                    

                    # Check if crime happened inside a Lord's territory

                    for h in self.houses:

                        if h.territory_radius > 0 and not h.is_under_construction:

                            if abs(agent.x - h.x) + abs(agent.y - h.y) <= h.territory_radius:

                                lord = self.agents.get(h.owner_id)

                                if lord and lord.is_alive and lord.id != agent.id:

                                    lord.pending_judgments.append({

                                        "thief_id": agent.id,

                                        "thief_name": agent.name,

                                        "victim_id": target_id,

                                        "victim_name": victim.name,

                                        "amount": stolen

                                    })

                                    self.add_log(LogCategoryEnum.SOCIAL, f"âš–ï¸ Crime reported to Lord {lord.name}!")

                                break

        elif raw_state == "judge":

            target_id = new_action.get("trade_target")

            judgment = new_action.get("judgment", "forgive").lower()

            criminal = self.agents.get(target_id) if target_id else None

            if criminal and criminal.is_alive and agent.pending_judgments:

                agent.pending_judgments = [j for j in agent.pending_judgments if j["thief_id"] != target_id]

                if judgment == "fine":

                    fine_amount = criminal.inventory.coin

                    criminal.inventory.coin = 0

                    agent.inventory.coin += fine_amount

                    self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ‘‘ Lord {agent.name} fined {criminal.name}: {fine_amount} Coins confiscated!")

                elif judgment == "jail":

                    criminal.jailed_timer = 50

                    criminal.dx = 0

                    criminal.dy = 0

                    self.add_log(LogCategoryEnum.SOCIAL, f"â›“ï¸ Lord {agent.name} imprisoned {criminal.name} for 50 ticks!")

                elif judgment == "execute":

                    self._kill_agent(criminal, f"executed by Lord {agent.name}")

                    self.add_log(LogCategoryEnum.SOCIAL, f"âš”ï¸ Lord {agent.name} executed {criminal.name}!")

                elif judgment == "forgive":

                    self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ•Šï¸ Lord {agent.name} forgave {criminal.name} and showed mercy.")

                    agent.personality.kindness = min(1.0, agent.personality.kindness + 0.05)



        valid_actions = {

            "idle", "moving", "trading", "gathering", "thinking", "marrying",

            "accept_trade", "reject_trade", "working", "steal", "judge",

            "claim_territory", "form_alliance", "contest_territory",

        }

        if raw_state not in valid_actions:

            raw_state = "moving"



        try:

            agent.actionState = ActionStateEnum(raw_state)

        except ValueError:

            agent.actionState = ActionStateEnum.MOVING



    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    #  HOUSING SYSTEM

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _try_build_buildings(self, agent: AgentSchema):

        economy.try_build_buildings(self, agent)



    def _owned_settlement(self, owner_id: str) -> Optional[SettlementNode]:

        for settlement in self.settlements:

            if settlement.owner_id == owner_id:

                return settlement

        return None



    def _land_power(self, owner_id: str) -> int:

        return int(sum(max(0, int(getattr(s, "territory_radius", 0))) for s in self.settlements if s.owner_id == owner_id))



    def _count_close_friends(self, agent_id: str, min_rel: float = 45.0) -> int:

        total = 0

        for key, detail in self.relationship_details.items():

            ids = key.split("::")

            if agent_id not in ids:

                continue

            value = float(detail.get("value", 0.0))

            if value < min_rel:

                continue

            other_id = ids[1] if ids[0] == agent_id else ids[0]

            other = self.agents.get(other_id)

            if other and other.is_alive:

                total += 1

        return total



    def _leadership_score(self, agent: AgentSchema) -> float:

        alive_allies = len([aid for aid in agent.allies if aid in self.agents and self.agents[aid].is_alive])

        close_friends = self._count_close_friends(agent.id, min_rel=40.0)

        land_power = self._land_power(agent.id)

        return (

            (close_friends * 1.0)

            + (alive_allies * 1.35)

            + (land_power * 0.85)

            + (max(0.0, agent.personality.sociability) * 2.0)

            + (max(0.0, agent.personality.ambition) * 1.2)

        )



    def _find_common_enemy_id(self, *members: AgentSchema) -> Optional[str]:

        candidate_scores: Dict[str, float] = {}

        fallback_owner: Optional[str] = None

        for member in members:

            if not member or not member.is_alive:

                continue

            nearby_foreign = self._nearest_foreign_settlement(member)

            if nearby_foreign and nearby_foreign.owner_id != member.id:

                fallback_owner = nearby_foreign.owner_id

            for other_id, other in self.agents.items():

                if other_id == member.id or not other.is_alive:

                    continue

                if other_id in member.allies:

                    continue

                rel = self.get_relationship(member.id, other_id)

                if rel > -18:

                    continue

                score = abs(rel)

                if self._owned_settlement(other_id):

                    score += 8.0

                if self._nearest_foreign_settlement(member, target_owner_id=other_id):

                    score += 6.0

                candidate_scores[other_id] = candidate_scores.get(other_id, 0.0) + score



        if not candidate_scores:

            return fallback_owner

        return max(candidate_scores.items(), key=lambda kv: kv[1])[0]



    def _coordinate_allied_actions(self, agent: AgentSchema) -> bool:

        if not agent.allies or (self.tick % 3 != 0):

            return False



        live_allies = [

            self.agents[ally_id]

            for ally_id in agent.allies

            if ally_id in self.agents and self.agents[ally_id].is_alive

        ]

        if not live_allies:

            return False



        nearby_allies = [ally for ally in live_allies if abs(ally.x - agent.x) + abs(ally.y - agent.y) <= 8]

        if not nearby_allies:

            return False



        common_enemy_id = self._find_common_enemy_id(agent, *nearby_allies[:3])

        if common_enemy_id:

            enemy_settlement = self._nearest_foreign_settlement(agent, target_owner_id=common_enemy_id)

            if enemy_settlement:

                agent.dx, agent.dy = self._step_towards(agent.x, agent.y, enemy_settlement.x, enemy_settlement.y)

                if self.world_rng.random() < 0.2:

                    self.add_log(

                        LogCategoryEnum.SOCIAL,

                        f"⚔️ Alliance maneuver: {agent.name} moved with allies against a shared enemy.",

                        interaction_type="alliance_joint_war_march",

                        participant_ids=[agent.id] + [a.id for a in nearby_allies[:2]],

                        source_agent_id=agent.id,

                    )

                return True



        if self.world_rng.random() < 0.35:

            cx = int(round((agent.x + sum(a.x for a in nearby_allies)) / (len(nearby_allies) + 1)))

            cy = int(round((agent.y + sum(a.y for a in nearby_allies)) / (len(nearby_allies) + 1)))

            agent.dx, agent.dy = self._step_towards(agent.x, agent.y, cx, cy)

            if self.world_rng.random() < 0.25:

                self.add_log(

                    LogCategoryEnum.SOCIAL,

                    f"🗣️ Alliance coordination: {agent.name} gathered with allies to plan next moves.",

                    interaction_type="alliance_joint_discussion",

                    participant_ids=[agent.id] + [a.id for a in nearby_allies[:2]],

                    source_agent_id=agent.id,

                )

            return True



        return False



    def _build_road_toward(self, agent: AgentSchema, tx: int, ty: int, max_segments: int = 4):

        if agent.inventory.wood <= 0:

            return

        if not self._is_land(tx, ty):

            return



        cx, cy = agent.x, agent.y

        built = 0

        for _ in range(max_segments):

            if built >= agent.inventory.wood:

                break

            if (cx, cy) == (tx, ty):

                break



            step_x = 0 if tx == cx else (1 if tx > cx else -1)

            step_y = 0 if ty == cy else (1 if ty > cy else -1)

            primary = (step_x, 0) if abs(tx - cx) >= abs(ty - cy) else (0, step_y)

            secondary = (0, step_y) if primary[0] != 0 else (step_x, 0)



            moved = False

            for dx, dy in (primary, secondary):

                nx, ny = cx + dx, cy + dy

                if dx == 0 and dy == 0:

                    continue

                if not self._is_spawnable_land(nx, ny):

                    continue

                tile = self.terrain[ny][nx]

                if tile != TerrainType.ROAD.value:

                    self.terrain[ny][nx] = TerrainType.ROAD.value

                    agent.inventory.wood -= 1

                    built += 1

                cx, cy = nx, ny

                moved = True

                break

            if not moved:

                break



        if built > 0 and self.world_rng.random() < 0.3:

            self.add_log(

                LogCategoryEnum.ECONOMY,

                f"🛣️ {agent.name} paved {built} road tiles toward a strategic route.",

                interaction_type="strategic_road_building",

                participant_ids=[agent.id],

                source_agent_id=agent.id,

            )



    def _nearest_foreign_settlement(self, agent: AgentSchema, target_owner_id: Optional[str] = None) -> Optional[SettlementNode]:

        nearest = None

        nearest_dist = 10**9

        for settlement in self.settlements:

            if settlement.owner_id == agent.id:

                continue

            if target_owner_id and settlement.owner_id != target_owner_id:

                continue

            dist = abs(agent.x - settlement.x) + abs(agent.y - settlement.y)

            if dist <= settlement.territory_radius + 2 and dist < nearest_dist:

                nearest = settlement

                nearest_dist = dist

        return nearest



    def _generate_territory_name(self, agent: AgentSchema, x: int, y: int) -> str:

        """Generate creative territory name based on agent and location."""

        # Name prefixes based on personality/social class

        if agent.personality.bravery > 0.6:

            prefix_options = ["Fort", "Strong", "Bold", "Valor", "Brave", "Iron"]

        elif agent.personality.intellect > 0.6:

            prefix_options = ["Wise", "Scholar", "Lore", "Sage", "Thought", "Mind"]

        elif agent.personality.sociability > 0.6:

            prefix_options = ["Fair", "Peace", "Harmony", "Unity", "Bond", "Friend"]

        else:

            prefix_options = ["New", "Rising", "Free", "Wild", "Haven", "Land"]

        

        # Suffixes based on terrain or position

        terrain = self.terrain[y][x] if 0 <= x < self.map_size and 0 <= y < self.map_size else "grass"

        suffix_map = {

            "forest": ["Wood", "Grove", "Shade", "Green"],

            "mountain": ["Peak", "Ridge", "Height", "Stone"],

            "river": ["Ford", "Stream", "Flow", "Water"],

            "beach": ["Shore", "Coast", "Sand", "Bay"],

            "lake": ["Haven", "Lake", "Deep", "Pool"],

            "grass": ["Field", "Plain", "Valley", "Mead"],

        }

        suffix_options = suffix_map.get(terrain, ["Land", "Hold", "Realm"])

        

        prefix = prefix_options[int(self.world_rng.integers(0, len(prefix_options)))]

        suffix = suffix_options[int(self.world_rng.integers(0, len(suffix_options)))]

        

        return f"{prefix}{suffix}"



    def _try_claim_territory(self, agent: AgentSchema):

        if agent.life_phase not in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT, LifePhaseEnum.ELDER]:

            return

        if not self._is_spawnable_land(agent.x, agent.y):

            return



        owned = self._owned_settlement(agent.id)

        if owned:

            # Expansion intent: spend resources to widen influence.

            if abs(agent.x - owned.x) + abs(agent.y - owned.y) <= 2 and (agent.inventory.wood >= 4 or agent.inventory.stone >= 3):

                if agent.inventory.wood >= 4:

                    agent.inventory.wood -= 4

                elif agent.inventory.stone >= 3:

                    agent.inventory.stone -= 3

                owned.territory_radius = min(12, owned.territory_radius + 1)

                if agent.inventory.crop >= 4:

                    owned.is_farming = True

                self.gain_skill(agent, "leadership", 0.9)

                self.gain_skill(agent, "diplomacy", 0.3)

                self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ³ï¸ {agent.name} expanded territory to radius {owned.territory_radius}.")

            return



        # Can't claim too close to an existing claim (unless contesting through explicit action).

        for settlement in self.settlements:

            dist = abs(agent.x - settlement.x) + abs(agent.y - settlement.y)

            if dist <= max(4, settlement.territory_radius + 1):
                return



        if agent.inventory.wood < 3 and agent.inventory.stone < 2 and agent.inventory.coin < 5:

            return



        if agent.inventory.wood >= 3:

            agent.inventory.wood -= 3

        if agent.inventory.stone >= 2:

            agent.inventory.stone -= 2

        if agent.inventory.coin >= 2:

            agent.inventory.coin -= 2



        radius = 3 + (1 if agent.personality.bravery > 0.45 else 0)

        territory_name = self._generate_territory_name(agent, agent.x, agent.y)

        

        settlement = SettlementNode(

            id=str(uuid.uuid4())[:8],

            owner_id=agent.id,

            x=agent.x,

            y=agent.y,

            name=territory_name,

            is_farming=agent.inventory.crop >= 4,

            territory_radius=radius,

            allied_with=[],

        )

        self.settlements.append(settlement)

        self.gain_skill(agent, "leadership", 1.4)

        self.gain_skill(agent, "diplomacy", 0.4)

        self.add_log(LogCategoryEnum.SOCIAL, f"Castle {agent.name} claimed territory '{territory_name}' at ({agent.x},{agent.y}) with radius {radius}.")

        self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ´ {agent.name} claimed territory at ({agent.x},{agent.y}) with radius {radius}.")



    def _generate_alliance_name(self, agent: AgentSchema, other: AgentSchema) -> str:

        """Generate creative alliance name based on both agents."""

        # Combine names or create union name

        names_options = [

            f"{agent.name} & {other.name}",

            f"The {agent.name}-{other.name} Accord",

            f"Union of {agent.name} and {other.name}",

            f"{agent.name}'s League",

            f"The Pact of {agent.name} and {other.name}",

        ]

        

        # If both have territories with names, use them

        agent_settlement = self._owned_settlement(agent.id)

        other_settlement = self._owned_settlement(other.id)

        

        if agent_settlement and agent_settlement.name and other_settlement and other_settlement.name:

            names_options.extend([

                f"{agent_settlement.name} & {other_settlement.name} Alliance",

                f"The {agent_settlement.name}-{other_settlement.name} Confederacy",

                f"United {agent_settlement.name} Territories",

            ])

        

        return names_options[int(self.world_rng.integers(0, len(names_options)))]



    def _try_form_alliance(self, agent: AgentSchema, target_id: Optional[str]):

        if not target_id or target_id == agent.id:

            return

        other = self.agents.get(target_id)

        if not other or not other.is_alive:

            return

        if abs(agent.x - other.x) + abs(agent.y - other.y) > 4:

            return

        if target_id in agent.allies:

            return



        rel = self.get_relationship(agent.id, target_id)

        avg_soc = (agent.personality.sociability + other.personality.sociability) / 2.0

        agent_lead = self._leadership_score(agent)

        other_lead = self._leadership_score(other)

        land_synergy = 0.09 if self._land_power(agent.id) > 0 and self._land_power(other.id) > 0 else 0.0

        alliance_chance = (

            0.22

            + max(0.0, avg_soc) * 0.2

            + (max(rel, 0.0) / 180.0)

            + min(0.22, agent_lead / 55.0)

            + min(0.16, other_lead / 70.0)

            + land_synergy

        )

        alliance_roll = float(self.world_rng.random())



        if rel >= 24 and alliance_roll < min(0.95, alliance_chance):

            agent.allies.append(target_id)

            other.allies.append(agent.id)

            self.add_relationship(agent.id, target_id, 8.0)



            agent_settlement = self._owned_settlement(agent.id)

            other_settlement = self._owned_settlement(other.id)

            

            # Generate and set alliance name

            alliance_name = self._generate_alliance_name(agent, other)

            

            if agent_settlement and other.id not in agent_settlement.allied_with:

                agent_settlement.allied_with.append(other.id)

                agent_settlement.alliance_name = alliance_name

            if other_settlement and agent.id not in other_settlement.allied_with:

                other_settlement.allied_with.append(agent.id)

                other_settlement.alliance_name = alliance_name



            self.gain_skill(agent, "diplomacy", 1.0)

            self.gain_skill(other, "diplomacy", 0.8)

            self.gain_skill(agent, "leadership", 0.5)

            self.gain_skill(other, "leadership", 0.4)



            self.add_log(

                LogCategoryEnum.SOCIAL,

                f"Alliance formed: '{alliance_name}' - {agent.name} and {other.name} now united.",

                interaction_type="alliance_formed_influence",

                participant_ids=[agent.id, other.id],

                source_agent_id=agent.id,

            )



            shared_enemy_id = self._find_common_enemy_id(agent, other)

            if shared_enemy_id:

                enemy = self.agents.get(shared_enemy_id)

                if enemy and enemy.is_alive:

                    self.add_relationship(agent.id, shared_enemy_id, -6.0)

                    self.add_relationship(other.id, shared_enemy_id, -6.0)

                    self.add_log(

                        LogCategoryEnum.SOCIAL,

                        f"🎯 Shared enemy formed: alliance of {agent.name} and {other.name} now opposes {enemy.name}.",

                        interaction_type="alliance_shared_enemy",

                        participant_ids=[agent.id, other.id, enemy.id],

                        source_agent_id=agent.id,

                    )

        else:

            self.add_relationship(agent.id, target_id, -2.0)

            self.add_log(

                LogCategoryEnum.SOCIAL,

                f"🙅 Alliance rejected: {agent.name}'s proposal to {other.name} failed.",

                interaction_type="alliance_rejected",

                participant_ids=[agent.id, other.id],

                source_agent_id=agent.id,

            )



    def _try_marry(self, agent: AgentSchema, target_id: Optional[str]):

        if not target_id or target_id == agent.id:

            return

        other = self.agents.get(target_id)

        if not other or not other.is_alive:

            return

        if abs(agent.x - other.x) + abs(agent.y - other.y) > 2:

            return

        can_marry = (

            agent.life_phase in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT]

            and other.life_phase in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT]

            and agent.gender != other.gender

            and agent.partner_id is None

            and other.partner_id is None

        )

        if not can_marry:

            return

        rel = self.get_relationship(agent.id, other.id)

        rel_key = self._rel_key(agent.id, other.id)

        rel_detail = self.relationship_details.get(rel_key, {})

        friendship = float(rel_detail.get("friendship", rel))

        romance = float(rel_detail.get("romance", 0.0))

        marriage_ready = rel >= 75 and (romance >= 40 or friendship >= 85)

        if not marriage_ready:

            self.add_log(

                LogCategoryEnum.SOCIAL,

                f"💔 Marriage proposal paused: {agent.name} and {other.name} are not close enough yet.",

                interaction_type="marriage_not_ready",

                participant_ids=[agent.id, other.id],

                source_agent_id=agent.id,

            )

            return

        if agent.inventory.food < 3 or other.inventory.food < 3:

            self.add_log(

                LogCategoryEnum.SOCIAL,

                f"🍞 Marriage delayed: {agent.name} and {other.name} need more food reserves.",

                interaction_type="marriage_lack_food",

                participant_ids=[agent.id, other.id],

                source_agent_id=agent.id,

            )

            return

        agent.partner_id = other.id

        other.partner_id = agent.id

        social.add_relationship(self, agent.id, other.id, 12.0, relationship_type="romance", interaction_tag="married")

        social.add_relationship(self, agent.id, other.id, 4.0, relationship_type="friendship", interaction_tag="marriage_trust")

        agent.inventory.food -= 3

        other.inventory.food -= 3

        female = agent if agent.gender == GenderEnum.FEMALE else other

        female.is_pregnant = True

        female.pregnancy_timer = 80

        self.add_log(

            LogCategoryEnum.SOCIAL,

            f"💍 {agent.name} & {other.name} married!",

            interaction_type="married",

            participant_ids=[agent.id, other.id],

            source_agent_id=agent.id,

        )

        for partner in [agent, other]:

            if partner.house_id:

                spouse = other if partner == agent else agent

                spouse.house_id = partner.house_id

                break



    def _try_contest_territory(self, agent: AgentSchema, target_owner_id: Optional[str]):

        candidate = self._nearest_foreign_settlement(agent, target_owner_id=target_owner_id)

        if not candidate:

            return



        owner = self.agents.get(candidate.owner_id)

        if owner and owner.is_alive and owner.id in agent.allies:

            self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ¤ {agent.name} avoided contesting ally {owner.name}'s territory.")

            return



        allied_attackers = [

            self.agents[ally_id]

            for ally_id in agent.allies

            if ally_id in self.agents

            and self.agents[ally_id].is_alive

            and abs(self.agents[ally_id].x - agent.x) + abs(self.agents[ally_id].y - agent.y) <= 6

        ]



        attacker_power = (

            1.0

            + max(0.0, agent.personality.bravery)

            + max(0.0, agent.personality.cunning)

            + (agent.inventory.tools * 0.07)

            + (agent.inventory.coin * 0.015)

            + (len(agent.allies) * 0.25)

        )

        for ally in allied_attackers:

            attacker_power += 0.45 + max(0.0, ally.personality.bravery) * 0.25 + (ally.inventory.tools * 0.03)



        defender_power = 0.8 + (candidate.territory_radius * 0.2)

        if owner and owner.is_alive:

            defending_allies = [

                self.agents[ally_id]

                for ally_id in owner.allies

                if ally_id in self.agents

                and self.agents[ally_id].is_alive

                and abs(self.agents[ally_id].x - candidate.x) + abs(self.agents[ally_id].y - candidate.y) <= 6

            ]

            defender_power += (

                max(0.0, owner.personality.bravery)

                + max(0.0, owner.personality.cunning)

                + (owner.inventory.tools * 0.07)

                + (owner.inventory.coin * 0.012)

                + (len(owner.allies) * 0.2)

            )

            for ally in defending_allies:

                defender_power += 0.38 + max(0.0, ally.personality.bravery) * 0.2 + (ally.inventory.tools * 0.02)



        win_prob = attacker_power / (attacker_power + max(0.5, defender_power))

        if np.random.rand() < win_prob:

            old_owner_id = candidate.owner_id

            candidate.owner_id = agent.id

            candidate.allied_with = [ally for ally in candidate.allied_with if ally != agent.id]

            self.add_relationship(agent.id, old_owner_id, -20.0)

            if old_owner_id in agent.allies:

                agent.allies = [a for a in agent.allies if a != old_owner_id]

            self.gain_skill(agent, "leadership", 1.2)

            self.gain_skill(agent, "diplomacy", 0.6)

            self.add_log(LogCategoryEnum.SOCIAL, f"âš”ï¸ {agent.name} seized territory from {self.agents.get(old_owner_id).name if old_owner_id in self.agents else old_owner_id}.")

            if allied_attackers:

                self.add_log(

                    LogCategoryEnum.SOCIAL,

                    f"🛡️ Allied assault: {agent.name} captured territory with support from {len(allied_attackers)} allies.",

                    interaction_type="allied_territory_assault",

                    participant_ids=[agent.id] + [ally.id for ally in allied_attackers[:3]],

                    source_agent_id=agent.id,

                )

        else:

            agent.vitals.energy = max(0.0, agent.vitals.energy - 15.0)

            if owner and owner.is_alive:

                self.add_relationship(agent.id, owner.id, -8.0)

            self.gain_skill(agent, "leadership", 0.2)

            self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ›¡ï¸ {agent.name} failed to seize territory and retreated.")



    def _social_class_rank(self, social_class: SocialClassEnum) -> int:

        order = {

            SocialClassEnum.NOMAD: 0,

            SocialClassEnum.PEASANT: 1,

            SocialClassEnum.CITIZEN: 2,

            SocialClassEnum.NOBLE: 3,

            SocialClassEnum.ROYALTY: 4,

        }

        return int(order.get(social_class, 0))



    def _log_social_class_progression(self, agent: AgentSchema, old_class: SocialClassEnum, new_class: SocialClassEnum):

        if self._social_class_rank(new_class) <= self._social_class_rank(old_class):

            return



        close_friends = self._count_close_friends(agent.id, min_rel=45.0)

        land_power = self._land_power(agent.id)



        if new_class == SocialClassEnum.CITIZEN:

            reason = "earned recognition as a community figure"

        elif new_class == SocialClassEnum.NOBLE:

            reason = "rose as a leader through strong alliances"

            if land_power >= 7:

                reason = "rose as a landlord with expanding estates"

        elif new_class == SocialClassEnum.ROYALTY:

            reason = "founded a kingdom from land power and loyal allies"

        else:

            reason = "advanced in social standing"



        self.add_log(

            LogCategoryEnum.SOCIAL,

            f"👑 Social rise: {agent.name} advanced {old_class.value} → {new_class.value} and {reason} (friends={close_friends}, land={land_power}).",

            interaction_type="social_class_rise",

            participant_ids=[agent.id],

            source_agent_id=agent.id,

        )



    def compute_metrics(self) -> Dict[str, Any]:

        alive_agents = [a for a in self.agents.values() if a.is_alive]

        pop = len(alive_agents)

        coins = sorted([max(0, int(a.inventory.coin)) for a in alive_agents])



        gini = 0.0

        if pop > 1:

            total = float(sum(coins))

            if total > 0:

                weighted_sum = sum((idx + 1) * value for idx, value in enumerate(coins))

                gini = (2.0 * weighted_sum) / (pop * total) - ((pop + 1) / pop)

                gini = float(max(0.0, min(1.0, gini)))



        possible_pairs = (pop * (pop - 1)) / 2 if pop > 1 else 0

        social_density = float(len(self.social_links) / possible_pairs) if possible_pairs > 0 else 0.0



        alliance_pairs = set()

        for a in alive_agents:

            for ally_id in a.allies:

                if ally_id == a.id:

                    continue

                if ally_id not in self.agents or not self.agents[ally_id].is_alive:

                    continue

                alliance_pairs.add(tuple(sorted((a.id, ally_id))))



        return {

            "population": pop,

            "gini_coin": round(gini, 4),

            "social_density": round(social_density, 4),

            "social_links": len(self.social_links),

            "alliance_edges": len(alliance_pairs),

            "territories": len(self.settlements),

        }



    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    #  MAIN STEP

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def step(self):

        self.tick += 1

        self.pending_cognitive_tasks.clear()

        think_candidates: List[Tuple[float, float, str]] = []

        self._update_weather_and_hydrology()

        self._update_global_quest()

        

        # Era progression

        new_era = life_cycle.calc_era(self)

        if new_era != self.era:

            old_era = self.era

            self.era = new_era

            self.add_log(LogCategoryEnum.SYSTEM, f"ðŸŒ… A new era dawns: {old_era.value.title()} â†’ {new_era.value.title()}!")

            

            # Era-based personality evolution for all living citizens

            for aid, agent in self.agents.items():

                if not agent.is_alive:

                    continue

                p = agent.personality

                # Global intellect boost per era

                p.intellect = min(1.0, p.intellect + 0.05)

                

                if new_era in [EraEnum.ANCIENT, EraEnum.MEDIEVAL, EraEnum.MODERN]:

                    # Unlock creativity & ambition

                    if p.creativity == 0.0:

                        p.creativity = round(float(np.random.uniform(-0.3, 0.5)), 2)

                    if p.ambition == 0.0:

                        p.ambition = round(float(np.random.uniform(-0.2, 0.6)), 2)

                

                if new_era in [EraEnum.MEDIEVAL, EraEnum.MODERN]:

                    # Unlock empathy & cunning

                    if p.empathy == 0.0:

                        p.empathy = round(float(np.clip(p.kindness + np.random.uniform(-0.2, 0.3), -1, 1)), 2)

                    if p.cunning == 0.0:

                        p.cunning = round(float(np.random.uniform(-0.3, 0.7)), 2)

        

        self.spawn_resource()

        

        # Government Taxation

        economy.execute_taxation(self)



        # Passive Resource Generation (Farming, Market, Port)

        if self.tick % 40 == 0:

            for s in self.settlements:

                if s.is_farming and len(self.resources) < 45:

                    self.resources.append(ResourceNode(

                        id=str(uuid.uuid4())[:8], type=ResourceTypeEnum("food"), x=s.x, y=s.y

                    ))

            

            for h in self.houses:

                # Residence Farming (level 2+)

                if getattr(h, "type", BuildingTypeEnum.RESIDENCE) == BuildingTypeEnum.RESIDENCE and h.level >= 2 and len(self.resources) < 45:

                    self.resources.append(ResourceNode(

                        id=str(uuid.uuid4())[:8], type=ResourceTypeEnum("food"), x=h.x, y=h.y

                    ))

                # Market Passive Income

                elif getattr(h, "type", BuildingTypeEnum.RESIDENCE) == BuildingTypeEnum.MARKET:

                    owner = self.agents.get(h.owner_id)

                    if owner and owner.is_alive:

                        owner.inventory.coin += 2

                # Port Passive Income

                elif getattr(h, "type", BuildingTypeEnum.RESIDENCE) == BuildingTypeEnum.PORT:

                    owner = self.agents.get(h.owner_id)

                    if owner and owner.is_alive:

                        owner.inventory.food += 2

                        owner.inventory.coin += 1



        self.gravestones = [g for g in self.gravestones if self.tick - g.death_tick < 200]



        # World events

        if self.tick % 500 == 0 and self.tick > 0:

            self._process_world_events()

        if self.tick % 800 == 0 and self.tick > 0:

            disaster = str(self.world_rng.choice(["earthquake", "flood", "wildfire"]))

            disaster_logs = apply_disaster(self.terrain, self.elevation, self.map_size, disaster, rng=self.world_rng)

            for dl in disaster_logs:

                self.add_log(LogCategoryEnum.SYSTEM, dl)

            for aid, agent in self.agents.items():

                if agent.is_alive and not self._is_walkable(agent.x, agent.y):

                    self._kill_agent(agent, f"natural disaster ({disaster})")



        # Agent life loop

        day_advanced = (self.tick % TICKS_PER_DAY) == 0

        for aid, agent in list(self.agents.items()):

            if not agent.is_alive:

                continue



            self._record_visible_resource_knowledge(agent)



            if day_advanced:

                agent.age += 1

            agent.life_phase = life_cycle.calc_life_phase(agent.age)

            previous_social_class = agent.social_class

            agent.social_class = social.calc_social_class(self, agent)

            if agent.social_class != previous_social_class:

                self._log_social_class_progression(agent, previous_social_class, agent.social_class)

            # Biological progression follows calendar days, including while waiting on LLM thinking.

            if agent.is_pregnant and day_advanced:

                agent.pregnancy_timer -= 1

                agent.vitals.energy = max(0.0, agent.vitals.energy - 0.1)

                if agent.pregnancy_timer <= 0:

                    self._birth_child(agent)

                    agent.is_pregnant = False

                    agent.pregnancy_timer = 0

            if agent.is_thinking:

                self._flush_movement_summary(agent)

                continue

            

            # Jail timer

            if agent.jailed_timer > 0:

                self._flush_movement_summary(agent)

                agent.jailed_timer -= 1

                agent.dx = 0

                agent.dy = 0

                agent.actionState = ActionStateEnum.IDLE

                if agent.jailed_timer == 0:

                    self.add_log(LogCategoryEnum.SOCIAL, f"ðŸ”“ {agent.name} has been released from jail.")

                continue  # Skip all other actions while jailed

            

            # Job Evaluator

            job = "Nomad"

            if agent.life_phase in [LifePhaseEnum.BABY, LifePhaseEnum.CHILD]:

                job = "Child"

            elif agent.life_phase == LifePhaseEnum.TEEN:

                job = "Teen"

            else:

                inv = agent.inventory

                self._ensure_agent_skills(agent)

                fishing_skill = self.get_skill(agent, "fishing")

                trading_skill = self.get_skill(agent, "trading")

                medicine_skill = self.get_skill(agent, "medicine")

                farming_skill = self.get_skill(agent, "farming")

                hunting_skill = self.get_skill(agent, "hunting")

                construction_skill = self.get_skill(agent, "construction")

                diplomacy_skill = self.get_skill(agent, "diplomacy")

                leadership_skill = self.get_skill(agent, "leadership")



                near_water = False

                near_forest = False

                near_mountain = False

                if 0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size:

                    near_water = self.terrain[agent.y][agent.x] in [TerrainType.RIVER.value, TerrainType.BEACH.value, TerrainType.OCEAN.value]

                    near_forest = self.terrain[agent.y][agent.x] == TerrainType.FOREST.value

                    near_mountain = self.terrain[agent.y][agent.x] == TerrainType.MOUNTAIN.value



                livestock_total = inv.pig + inv.cow + inv.chicken



                if agent.social_class in [SocialClassEnum.ROYALTY, SocialClassEnum.NOBLE]:

                    if leadership_skill >= 45 or diplomacy_skill >= 40:

                        job = "Ruler"

                    else:

                        job = "Lord"

                elif self.era in [EraEnum.MEDIEVAL, EraEnum.MODERN] and medicine_skill >= 35 and inv.herb >= 1:

                    job = "Doctor"

                elif self.era in [EraEnum.ANCIENT, EraEnum.MEDIEVAL, EraEnum.MODERN] and trading_skill >= 30 and inv.coin >= 8:

                    job = "Trader"

                elif near_water and fishing_skill >= 28:

                    job = "Fisher"

                elif (near_mountain and (construction_skill >= 24 or inv.tools >= 1)) or inv.stone >= 18:

                    job = "Miner"

                elif livestock_total >= 5 or (farming_skill >= 26 and livestock_total >= 2):

                    job = "Rancher"

                elif (near_forest and construction_skill >= 22) or inv.wood >= 18:

                    job = "Lumberjack"

                elif construction_skill >= 35 and inv.stone > 10 and inv.tools > 1:

                    job = "Builder"

                elif farming_skill >= 32 and inv.crop > 8:

                    job = "Farmer"

                elif hunting_skill >= 30 and inv.meat > 8:

                    job = "Hunter"

                elif diplomacy_skill >= 34 and len(agent.allies) >= 2:

                    job = "Diplomat"

                elif agent.personality.bravery > 0.4 and inv.coin < 10 and agent.social_class == SocialClassEnum.PEASANT:

                    job = "Guard"

                elif agent.personality.intellect > 0.4 and self.era == EraEnum.MODERN:

                    job = "Scholar"

                else:

                    job = "Gatherer"

                

            # School Buff

            near_school = any(h for h in self.houses if getattr(h, "type", "") == "school" and abs(agent.x - h.x) + abs(agent.y - h.y) <= 8)

            if near_school and agent.life_phase in [LifePhaseEnum.CHILD, LifePhaseEnum.TEEN]:

                job = "Student"

                agent.personality.intellect = min(1.0, agent.personality.intellect + 0.05)

                self.gain_skill(agent, "diplomacy", 0.2)

                self.gain_skill(agent, "gathering", 0.2)

            agent.job = job



            self._apply_profession_income_and_skill_growth(agent)

            

            if agent.age >= agent.max_age:

                self._kill_agent(agent, "old age")

                continue



            # Metabolism

            hunger_drain, energy_drain, social_drain, hydration_drain = 0.5, 0.2, 0.4, 0.6

            if agent.life_phase == LifePhaseEnum.BABY:

                hunger_drain, energy_drain, social_drain, hydration_drain = 0.3, 0.1, 0.1, 0.3

            elif agent.life_phase == LifePhaseEnum.CHILD:

                hunger_drain, social_drain, hydration_drain = 0.4, 0.2, 0.4

            elif agent.life_phase == LifePhaseEnum.ELDER:

                energy_drain, hunger_drain, hydration_drain = 0.4, 0.3, 0.5



            # Pacing guard: needs drain is scaled down so agents have enough time

            # to think/act through LLM decisions before entering critical states.

            hunger_drain *= NEEDS_DRAIN_SCALE

            energy_drain *= NEEDS_DRAIN_SCALE

            social_drain *= NEEDS_DRAIN_SCALE

            hydration_drain *= NEEDS_DRAIN_SCALE



            # Terrain effects

            if 0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size:

                ct = self.terrain[agent.y][agent.x]

                if ct == TerrainType.MOUNTAIN.value:

                    energy_drain *= 2.0

                elif ct == TerrainType.ROAD.value:

                    energy_drain *= 0.5

                elif ct == TerrainType.RIVER.value:

                    energy_drain *= 1.5

                elif ct == TerrainType.OCEAN.value:

                    if agent.inventory.has_boat:

                        energy_drain *= 0.8

                    else:

                        energy_drain *= 4.0

                        if agent.vitals.energy < 10:

                            self._kill_agent(agent, "drowning")

                            continue



            # Vehicle terrain modifiers

            if agent.inventory.has_car:

                energy_drain *= 0.15

            elif agent.inventory.has_horse:

                energy_drain *= 0.4

            elif agent.inventory.has_cart:

                energy_drain *= 0.7



            # House energy bonus

            if self._is_near_home(agent, radius=2):

                energy_drain *= 0.3  # Resting at home



            sociability = float(np.clip(agent.personality.sociability, -1.0, 1.0))
            social_need_factor = 1.0 + (max(0.0, sociability) * 0.55) - (max(0.0, -sociability) * 0.35)
            social_drain *= max(0.45, min(1.8, social_need_factor))

            agent.vitals.hunger = max(0.0, agent.vitals.hunger - hunger_drain)

            agent.vitals.hydration = max(0.0, agent.vitals.hydration - hydration_drain)

            agent.vitals.energy = max(0.0, agent.vitals.energy - energy_drain)

            agent.vitals.social = max(0.0, agent.vitals.social - social_drain)



            if agent.vitals.hunger <= 0:

                agent.vitals.energy = max(0.0, agent.vitals.energy - 1.8)



            happiness_shift = -0.05

            if agent.vitals.hunger < 20:

                happiness_shift -= 0.8

            if agent.vitals.hydration < 40:

                happiness_shift -= 1.0

            if agent.vitals.energy < 25:

                happiness_shift -= 0.7

            if agent.vitals.social < 30:

                happiness_shift -= 0.5

            if self._is_near_home(agent, radius=1):

                happiness_shift += 0.35

            if agent.partner_id and agent.partner_id in self.agents:

                partner = self.agents[agent.partner_id]

                if partner.is_alive and abs(agent.x - partner.x) + abs(agent.y - partner.y) <= 2:

                    happiness_shift += 0.25

            agent.vitals.happiness = float(np.clip(agent.vitals.happiness + happiness_shift, 0.0, 100.0))



            if agent.vitals.hydration < DEHYDRATION_DEATH_THRESHOLD and np.random.rand() < DEHYDRATION_DEATH_CHANCE:

                self._kill_agent(agent, "dehydration")

                continue



            # Auto-eat & Auto-drink

            if agent.vitals.hunger < 45:

                likes = set(agent.likes)

                dislikes = set(agent.dislikes)

                consumed_food = None



                # Emergency conversion: livestock can be slaughtered when food is critically low.

                if agent.vitals.hunger < 22 and agent.inventory.meat == 0:

                    if agent.inventory.chicken > 0:

                        agent.inventory.chicken -= 1

                        agent.inventory.meat += 2

                        self.add_log(LogCategoryEnum.ECONOMY, f"🍗 {agent.name} slaughtered a chicken for food.")

                    elif agent.inventory.pig > 0:

                        agent.inventory.pig -= 1

                        agent.inventory.meat += 3

                        self.add_log(LogCategoryEnum.ECONOMY, f"🥓 {agent.name} slaughtered a pig for food.")

                    elif agent.inventory.cow > 0:

                        agent.inventory.cow -= 1

                        agent.inventory.meat += 5

                        self.add_log(LogCategoryEnum.ECONOMY, f"🥩 {agent.name} slaughtered cattle for food.")



                if agent.inventory.meat > 0 and "meat" not in dislikes:

                    agent.inventory.meat -= 1

                    agent.vitals.hunger = min(100.0, agent.vitals.hunger + 40)

                    consumed_food = "meat"

                elif agent.inventory.food > 0 and "food" not in dislikes:

                    agent.inventory.food -= 1

                    agent.vitals.hunger = min(100.0, agent.vitals.hunger + 40)

                    consumed_food = "food"

                elif agent.inventory.crop > 0 and "crop" not in dislikes:

                    agent.inventory.crop -= 1

                    agent.vitals.hunger = min(100.0, agent.vitals.hunger + 25)

                    consumed_food = "crop"

                elif agent.inventory.fruit > 0 and "fruit" not in dislikes:

                    agent.inventory.fruit -= 1

                    agent.vitals.hunger = min(100.0, agent.vitals.hunger + 15)

                    consumed_food = "fruit"



                if consumed_food:

                    if consumed_food in likes:

                        agent.vitals.happiness = min(100.0, agent.vitals.happiness + 0.9)

                    elif consumed_food in dislikes:

                        agent.vitals.happiness = max(0.0, agent.vitals.happiness - 1.2)

            

            if agent.vitals.hydration < HYDRATION_AUTODRINK_TRIGGER:

                if agent.inventory.fruit > 0 and "fruit" not in set(agent.dislikes):

                    agent.inventory.fruit -= 1

                    agent.vitals.hydration = min(100.0, agent.vitals.hydration + 20)

                elif 0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size and self.terrain[agent.y][agent.x] == TerrainType.RIVER.value:

                    agent.vitals.hydration = 100.0

                # Try to build a well if on land with stone

                elif 0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size:

                    terrain_here = self.terrain[agent.y][agent.x]

                    if terrain_here in [TerrainType.GRASS.value, TerrainType.FOREST.value] and agent.inventory.stone >= 1:

                        tile_key = self._tile_key(agent.x, agent.y)

                        available = float(self.groundwater.get(tile_key, 0.0))

                        if available >= 10.0:

                            draw_amount = min(30.0, available)

                            self.groundwater[tile_key] = max(0.0, available - draw_amount)

                            agent.inventory.stone -= 1

                            hydration_gain = 18.0 + draw_amount

                            agent.vitals.hydration = min(100.0, agent.vitals.hydration + hydration_gain)

                            self.add_log(LogCategoryEnum.ECONOMY, f"💧 {agent.name} drew water from a well.", interaction_type="well_built")

                        else:

                            self.add_log(LogCategoryEnum.SYSTEM, f"{agent.name} found a dry well spot. Waiting for rain.", interaction_type="well_dry")



            # Crafting (tools, boat, cart, horse, car)

            if agent.life_phase in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT]:

                if agent.inventory.stone >= 2 and agent.inventory.wood >= 2 and agent.inventory.tools < 10:

                    agent.inventory.stone -= 2

                    agent.inventory.wood -= 2

                    agent.inventory.tools += 1

                    self.add_log(LogCategoryEnum.ECONOMY, f"🔨 {agent.name} crafted tools!")

                if agent.inventory.wood >= 10 and agent.inventory.tools >= 2 and not agent.inventory.has_boat:

                    agent.inventory.wood -= 10

                    agent.inventory.tools -= 2

                    agent.inventory.has_boat = True

                    self.add_log(LogCategoryEnum.ECONOMY, f"⛵ {agent.name} built a boat!")

                if agent.inventory.wood >= 15 and agent.inventory.tools >= 3 and not agent.inventory.has_cart:

                    agent.inventory.wood -= 15

                    agent.inventory.tools -= 3

                    agent.inventory.has_cart = True

                if not agent.inventory.has_horse and (agent.inventory.crop >= 8 or agent.inventory.fruit >= 8):

                    if agent.inventory.crop >= 8:

                        agent.inventory.crop -= 8

                        feed_source = "crop"

                    else:

                        agent.inventory.fruit -= 8

                        feed_source = "apple"

                    agent.inventory.has_horse = True

                    self.add_log(LogCategoryEnum.ECONOMY, f"🐴 {agent.name} tamed a horse using {feed_source} feed!")

                if agent.inventory.tools >= 10 and agent.inventory.stone >= 20 and agent.inventory.coin >= 50 and not agent.inventory.has_car:

                    agent.inventory.tools -= 10

                    agent.inventory.stone -= 20

                    agent.inventory.coin -= 50

                    agent.inventory.has_car = True

                    self.add_log(LogCategoryEnum.ECONOMY, f"🚗 {agent.name} built a car! Modern Era transport achieved!")



                # Husbandry: livestock can grow when fed, but only if the agent has a base (house or settlement).

                total_livestock = agent.inventory.pig + agent.inventory.cow + agent.inventory.chicken

                has_feed = agent.inventory.crop > 0 or agent.inventory.fruit > 0

                owns_settlement = self._owned_settlement(agent.id) is not None

                owns_house = self._owned_house(agent) is not None

                has_livestock_base = owns_settlement or owns_house

                if total_livestock > 0 and has_feed and has_livestock_base and (self.tick % 6 == 0 or self.world_rng.random() < 0.18):

                    if agent.inventory.crop > 0:

                        agent.inventory.crop -= 1

                    else:

                        agent.inventory.fruit -= 1



                    breed_roll = float(self.world_rng.random())

                    if breed_roll < 0.50:

                        agent.inventory.chicken += 1

                        self.add_log(LogCategoryEnum.ECONOMY, f"🐣 {agent.name}'s flock grew by 1 chicken.")

                        self._remember_production_origin(agent, "livestock")

                    elif breed_roll < 0.78:

                        agent.inventory.pig += 1

                        self.add_log(LogCategoryEnum.ECONOMY, f"🐖 {agent.name} expanded their pig herd.")

                        self._remember_production_origin(agent, "livestock")

                    else:

                        agent.inventory.cow += 1

                        self.add_log(LogCategoryEnum.ECONOMY, f"🐄 {agent.name} expanded their cattle herd.")

                        self._remember_production_origin(agent, "livestock")

                    self.gain_skill(agent, "farming", 0.7)

                    self.gain_skill(agent, "gathering", 0.3)

                

                # Housing & Commerce

                self._try_build_buildings(agent)

                self._sync_production_origins(agent)



                # Farming expansion: farmers can open new land for fields/orchards around their own settlement.

                owned_settlement = self._owned_settlement(agent.id)

                if job == "Farmer" and owned_settlement:

                    near_settlement = abs(agent.x - owned_settlement.x) + abs(agent.y - owned_settlement.y) <= max(2, owned_settlement.territory_radius)

                    can_prepare_land = farming_skill >= 28 and near_settlement and (agent.inventory.wood >= 2 or agent.inventory.stone >= 1)

                    if can_prepare_land and (self.tick % 6 == 0 or self.world_rng.random() < 0.35):

                        if agent.inventory.wood >= 2:

                            agent.inventory.wood -= 2

                        if agent.inventory.stone >= 1 and self.world_rng.random() < 0.55:

                            agent.inventory.stone -= 1

                        owned_settlement.is_farming = True

                        if owned_settlement.territory_radius < 12 and self.world_rng.random() < 0.25:

                            owned_settlement.territory_radius += 1

                        self.gain_skill(agent, "farming", 1.0)

                        self.add_log(LogCategoryEnum.SOCIAL, f"🌾 {agent.name} opened farmland around {owned_settlement.name or 'their settlement'}.")

                

                # Strategic road building toward visible resources or owned territory.

                should_plan_road = (self.tick % 5 == 0) or (np.random.rand() < (0.10 + min(0.18, self.get_skill(agent, "construction") / 340.0)))

                if agent.inventory.wood >= 2 and should_plan_road:

                    plan_segments = max(1, min(4, int(agent.inventory.wood)))

                    strategic_target = self._find_nearest_visible_resource(

                        agent,

                        [

                            ResourceTypeEnum.FOOD,

                            ResourceTypeEnum.FISH,

                            ResourceTypeEnum.CROP,

                            ResourceTypeEnum.FRUIT,

                            ResourceTypeEnum.HERB,

                            ResourceTypeEnum.WOOD,

                            ResourceTypeEnum.STONE,

                            ResourceTypeEnum.COIN,

                        ],

                    )

                    if strategic_target and abs(strategic_target[0] - agent.x) + abs(strategic_target[1] - agent.y) >= 4:

                        self._build_road_toward(agent, strategic_target[0], strategic_target[1], max_segments=plan_segments)

                    else:

                        owned_settlement = self._owned_settlement(agent.id)

                        if owned_settlement and abs(owned_settlement.x - agent.x) + abs(owned_settlement.y - agent.y) >= 5:

                            self._build_road_toward(agent, owned_settlement.x, owned_settlement.y, max_segments=plan_segments)

                        elif np.random.rand() < 0.25:

                            self.build_road(agent.x, agent.y)

                            agent.inventory.wood -= 1

            # Cognitive trigger

            house = self._owned_house(agent)

            house_dist = abs(agent.x - house.x) + abs(agent.y - house.y) if house else 9999

            low_energy_home = house is not None and agent.vitals.energy < 30

            comfort_home = house is not None and agent.vitals.energy < 65 and self.world_rng.random() < 0.04

            must_go_home = bool(house and house_dist > 1 and (low_energy_home or comfort_home))

            if must_go_home:

                agent.dx, agent.dy = self._step_towards(agent.x, agent.y, house.x, house.y)

                if low_energy_home:

                    agent.currentThought = "Returning home to rest before energy runs out."

            elif agent.dx == 0 and agent.dy == 0:

                self._coordinate_allied_actions(agent)



            can_think = agent.life_phase not in [LifePhaseEnum.BABY]

            vision_radius = self.get_vision_radius(agent)

            visible_people_count = sum(

                1

                for oid, oa in self.agents.items()

                if oid != aid and oa.is_alive and abs(agent.x - oa.x) + abs(agent.y - oa.y) <= vision_radius

            )

            social_need_trigger = max(

                20.0,

                min(

                    70.0,

                    35.0

                    + (max(0.0, float(agent.personality.sociability)) * 18.0)

                    - (max(0.0, float(-agent.personality.sociability)) * 10.0),

                ),

            )

            social_opportunity_boost = max(0.0, float(agent.personality.sociability)) * min(1.0, visible_people_count / 3.0) * 14.0

            effective_social_need_trigger = min(85.0, social_need_trigger + social_opportunity_boost)

            needs = (agent.vitals.energy < 30 or agent.vitals.hunger < 20 or agent.vitals.social < effective_social_need_trigger)

            nearby_people_alert = any(

                oid != aid and oa.is_alive and abs(agent.x - oa.x) + abs(agent.y - oa.y) <= 3

                for oid, oa in self.agents.items()

            )

            visible_resource_alert = any(

                abs(res.x - agent.x) + abs(res.y - agent.y) <= self.get_vision_radius(agent)

                for res in self.resources

            )

            territory_alert = any(

                s.owner_id != aid and abs(agent.x - s.x) + abs(agent.y - s.y) <= s.territory_radius + 1

                for s in self.settlements

            )

            spontaneous_reflection = np.random.rand() < (0.015 + max(0.0, agent.personality.intellect) * 0.03)

            cd_window = 8 if visible_resource_alert else 14

            cd_ok = (self.tick - agent.last_thought_tick > cd_window)

            should_request_think = can_think and (not must_go_home) and cd_ok and (needs or nearby_people_alert or visible_resource_alert or territory_alert or spontaneous_reflection)

            if should_request_think:

                think_priority = 0.0

                if agent.vitals.energy < 24:

                    think_priority += 3.0

                if agent.vitals.hydration < 35:

                    think_priority += 2.5

                if agent.vitals.hunger < 20:

                    think_priority += 2.0

                if agent.vitals.social < effective_social_need_trigger:

                    think_priority += 1.2

                if agent.vitals.social < max(18.0, effective_social_need_trigger - 18.0):

                    think_priority += 1.4

                if visible_people_count > 0 and agent.personality.sociability > 0:

                    think_priority += min(2.0, visible_people_count * 0.45 * float(agent.personality.sociability))

                if nearby_people_alert:

                    think_priority += 0.4

                if visible_resource_alert:

                    think_priority += 0.3

                think_priority += min(2.0, self.agent_idle_ticks.get(aid, 0) * 0.08)

                think_candidates.append((think_priority, float(self.world_rng.random()), aid))



            if (agent.dx == 0 and agent.dy == 0):

                self._apply_reactive_combo(agent, must_go_home=must_go_home)



            if agent.life_phase == LifePhaseEnum.BABY:

                self._flush_movement_summary(agent)

                agent.actionState = ActionStateEnum.IDLE

                agent.vitals.energy = min(100.0, agent.vitals.energy + 3.0)

            elif agent.dx != 0 or agent.dy != 0:

                if agent.vitals.energy <= 0.5:

                    self._flush_movement_summary(agent)

                    agent.dx, agent.dy = 0, 0

                    agent.actionState = ActionStateEnum.IDLE

                    if self._is_near_home(agent, radius=1):

                        agent.vitals.energy = min(100.0, agent.vitals.energy + 3.2)

                    else:

                        agent.vitals.energy = min(100.0, agent.vitals.energy + 0.8)

                else:

                    move_start_x, move_start_y = agent.x, agent.y

                    max_steps, is_running = self._movement_profile(agent, must_go_home=must_go_home)

                    moved_steps = 0

                    for _ in range(max_steps):

                        nx, ny = agent.x + agent.dx, agent.y + agent.dy

                        if self._is_walkable(nx, ny, agent.inventory.has_boat):

                            agent.x = nx

                            agent.y = ny

                            moved_steps += 1

                            if must_go_home and house and abs(agent.x - house.x) + abs(agent.y - house.y) <= 1:

                                break

                        else:

                            agent.dx, agent.dy = 0, 0

                            break



                    if moved_steps > 0:

                        self._record_movement_progress(agent, move_start_x, move_start_y, moved_steps)

                        agent.actionState = ActionStateEnum.MOVING

                    else:

                        self._flush_movement_summary(agent)

                        agent.actionState = ActionStateEnum.IDLE



                    if moved_steps > 1:

                        extra_steps = moved_steps - 1

                        if agent.inventory.has_car:

                            move_penalty = 0.15 * extra_steps

                        elif agent.inventory.has_horse:

                            move_penalty = 0.25 * extra_steps

                        elif agent.inventory.has_cart:

                            move_penalty = 0.35 * extra_steps

                        elif agent.inventory.has_boat:

                            move_penalty = 0.2 * extra_steps

                        elif is_running:

                            move_penalty = 0.9 * extra_steps

                        else:

                            move_penalty = 0.5 * extra_steps

                        agent.vitals.energy = max(0.0, agent.vitals.energy - move_penalty)



                    if is_running and moved_steps > 0:

                        agent.vitals.energy = max(0.0, agent.vitals.energy - 0.6)

                        agent.vitals.hunger = max(0.0, agent.vitals.hunger - 0.4)

                        agent.vitals.hydration = max(0.0, agent.vitals.hydration - 0.6)



                    if moved_steps == 0:

                        agent.dx, agent.dy = 0, 0

            else:

                self._flush_movement_summary(agent)

                agent.actionState = ActionStateEnum.IDLE

                if self._is_near_home(agent, radius=1):

                    agent.vitals.energy = min(100.0, agent.vitals.energy + 2.8)

                    agent.vitals.happiness = min(100.0, agent.vitals.happiness + 0.45)

                else:

                    agent.vitals.happiness = max(0.0, agent.vitals.happiness - 0.2)



            if agent.actionState == ActionStateEnum.IDLE and agent.dx == 0 and agent.dy == 0:

                self.agent_idle_ticks[aid] = self.agent_idle_ticks.get(aid, 0) + 1

            else:

                self.agent_idle_ticks[aid] = 0



            # Resource gathering

            if agent.life_phase not in [LifePhaseEnum.BABY]:

                # Drink from river

                if 0 <= agent.x < self.map_size and 0 <= agent.y < self.map_size:

                    if self.terrain[agent.y][agent.x] == TerrainType.RIVER.value:

                        agent.vitals.hydration = 100.0



                for res in list(self.resources):

                    if agent.x == res.x and agent.y == res.y:

                        pref_tag = self._resource_food_preference(res.type)

                        if pref_tag and pref_tag in set(agent.dislikes):

                            continue



                        amount = 1



                        if res.type in [ResourceTypeEnum.FOOD, ResourceTypeEnum.FISH]:

                            gather_skill = self.get_skill(agent, "fishing" if res.type == ResourceTypeEnum.FISH else "farming")

                            amount = max(3, int(round(4.0 * self._skill_multiplier(gather_skill))))

                            agent.inventory.food += amount

                            self.gain_skill(agent, "gathering", 0.6)

                            if res.type == ResourceTypeEnum.FISH:

                                self.gain_skill(agent, "fishing", 1.1)

                            else:

                                self.gain_skill(agent, "farming", 0.4)

                            self._remember_production_origin(agent, "farm", res.x, res.y)

                        elif res.type in [ResourceTypeEnum.PIG, ResourceTypeEnum.COW, ResourceTypeEnum.CHICKEN]:

                            amount = max(1, int(round(2.0 * self._skill_multiplier(self.get_skill(agent, "hunting")))))

                            if res.type == ResourceTypeEnum.PIG:

                                agent.inventory.pig += amount

                            elif res.type == ResourceTypeEnum.COW:

                                agent.inventory.cow += amount

                            else:

                                agent.inventory.chicken += amount

                            self.gain_skill(agent, "hunting", 0.7)

                            self.gain_skill(agent, "farming", 0.5)

                            self.gain_skill(agent, "gathering", 0.4)

                            self._remember_production_origin(agent, "livestock", res.x, res.y)

                        elif res.type == ResourceTypeEnum.CROP:

                            amount = max(3, int(round(4.0 * self._skill_multiplier(self.get_skill(agent, "farming")))))

                            agent.inventory.crop += amount

                            self.gain_skill(agent, "farming", 1.0)

                            self.gain_skill(agent, "gathering", 0.4)

                            self._remember_production_origin(agent, "farm", res.x, res.y)

                        elif res.type == ResourceTypeEnum.FRUIT:

                            amount = max(3, int(round(4.0 * self._skill_multiplier(self.get_skill(agent, "farming")))))

                            agent.inventory.fruit += amount

                            self.gain_skill(agent, "farming", 0.5)

                            self.gain_skill(agent, "gathering", 0.5)

                            self._remember_production_origin(agent, "farm", res.x, res.y)

                        elif res.type == ResourceTypeEnum.HERB:

                            amount = max(2, int(round(3.0 * self._skill_multiplier(self.get_skill(agent, "medicine")))))

                            agent.inventory.herb += amount

                            self.gain_skill(agent, "medicine", 0.8)

                            self.gain_skill(agent, "gathering", 0.5)

                        elif res.type == ResourceTypeEnum.WOOD:

                            amount = max(3, int(round(4.0 * self._skill_multiplier(self.get_skill(agent, "construction")))))

                            agent.inventory.wood += amount

                            self.gain_skill(agent, "construction", 0.6)

                            self.gain_skill(agent, "gathering", 0.5)

                        elif res.type == ResourceTypeEnum.COIN:

                            amount = max(2, int(round(3.0 * self._skill_multiplier(self.get_skill(agent, "trading")))))

                            agent.inventory.coin += amount

                            self.gain_skill(agent, "trading", 0.5)

                            self.gain_skill(agent, "gathering", 0.4)

                        elif res.type == ResourceTypeEnum.STONE:

                            amount = max(3, int(round(4.0 * self._skill_multiplier(self.get_skill(agent, "construction")))))

                            agent.inventory.stone += amount

                            self.gain_skill(agent, "construction", 0.7)

                            self.gain_skill(agent, "gathering", 0.4)

                        elif res.type == ResourceTypeEnum.HORSE:

                            if not agent.inventory.has_horse:

                                # Wild horse still needs feed bait (crop or fruit/apple) to tame.

                                if agent.inventory.crop >= 4 or agent.inventory.fruit >= 4:

                                    if agent.inventory.crop >= 4:

                                        agent.inventory.crop -= 4

                                        feed_source = "crop"

                                    else:

                                        agent.inventory.fruit -= 4

                                        feed_source = "apple"

                                    agent.inventory.has_horse = True

                                    amount = 1

                                    self.gain_skill(agent, "hunting", 0.4)

                                    self.gain_skill(agent, "gathering", 0.6)

                                    self.add_log(LogCategoryEnum.ECONOMY, f"🐎 {agent.name} tamed a wild horse using {feed_source} bait.")

                                else:

                                    amount = 0

                                    self.add_log(LogCategoryEnum.SYSTEM, f"{agent.name} found a wild horse but lacked crop/apple bait.")

                            else:

                                amount = 0



                        if pref_tag and pref_tag in set(agent.likes):

                            agent.vitals.happiness = min(100.0, agent.vitals.happiness + 0.8)



                        self._record_quest_contribution(agent, res.type.value, amount)



                        if res.type != ResourceTypeEnum.HORSE or not agent.inventory.has_horse:

                            self.add_log(LogCategoryEnum.ECONOMY, f"{agent.name} gathered {amount} {res.type.value}.")

                        self.resources.remove(res)



        if think_candidates:

            think_budget = max(1, min(6, len([a for a in self.agents.values() if a.is_alive]) // 8 + 1))

            eligible_order = [

                agent_id

                for agent_id, agent in self.agents.items()

                if agent.is_alive and (not agent.is_thinking) and agent.life_phase != LifePhaseEnum.BABY

            ]

            selected: List[str] = []

            if eligible_order:

                start_idx = self.think_turn_cursor % len(eligible_order)

                rotated = eligible_order[start_idx:] + eligible_order[:start_idx]

                candidate_ids = {candidate_id for _, _, candidate_id in think_candidates}

                for candidate_id in rotated:

                    if candidate_id in candidate_ids:

                        selected.append(candidate_id)

                        if len(selected) >= think_budget:

                            break



            if not selected:

                ranked = sorted(think_candidates, key=lambda item: (item[0], item[1]), reverse=True)

                selected = [candidate_id for _, _, candidate_id in ranked[:think_budget]]



            for candidate_id in selected:

                target = self.agents.get(candidate_id)

                if not target or not target.is_alive or target.is_thinking:

                    continue

                target.is_thinking = True

                target.actionState = ActionStateEnum.THINKING

                self.pending_cognitive_tasks.append(candidate_id)



            if eligible_order and selected:

                try:

                    last_idx = eligible_order.index(selected[-1])

                    self.think_turn_cursor = (last_idx + 1) % len(eligible_order)

                except ValueError:

                    self.think_turn_cursor = (self.think_turn_cursor + len(selected)) % max(1, len(eligible_order))

        # Hybrid mode keeps proximity-based social simulation;
        # full_llm mode delegates social outcomes to LLM-triggered actions.

        if self.social_mode != "full_llm":

            social.process_social_interactions(self)

            # Marriage (automatic only in hybrid mode)

            alive = [a for a in self.agents.values() if a.is_alive]

            for i in range(len(alive)):

                for j in range(i + 1, len(alive)):

                    a1, a2 = alive[i], alive[j]

                    if a1.x == a2.x and a1.y == a2.y and not a1.is_thinking and not a2.is_thinking:

                        can_marry = (

                            a1.life_phase in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT] and

                            a2.life_phase in [LifePhaseEnum.YOUNG_ADULT, LifePhaseEnum.ADULT] and

                            a1.gender != a2.gender and a1.partner_id is None and a2.partner_id is None

                        )

                        rel = self.get_relationship(a1.id, a2.id)

                        rel_key = self._rel_key(a1.id, a2.id)

                        rel_detail = self.relationship_details.get(rel_key, {})

                        friendship = float(rel_detail.get("friendship", rel))

                        romance = float(rel_detail.get("romance", 0.0))

                        marriage_ready = rel >= 75 and (romance >= 40 or friendship >= 85)

                        if can_marry and marriage_ready and a1.inventory.food >= 3 and a2.inventory.food >= 3:

                            a1.partner_id = a2.id

                            a2.partner_id = a1.id

                            social.add_relationship(self, a1.id, a2.id, 12.0, relationship_type="romance", interaction_tag="married")

                            social.add_relationship(self, a1.id, a2.id, 4.0, relationship_type="friendship", interaction_tag="marriage_trust")

                            a1.inventory.food -= 3

                            a2.inventory.food -= 3

                            female = a1 if a1.gender == GenderEnum.FEMALE else a2

                            female.is_pregnant = True

                            female.pregnancy_timer = 80

                            self.add_log(LogCategoryEnum.SOCIAL, f"💍 {a1.name} & {a2.name} married!")

                            # Share house if one has

                            for partner in [a1, a2]:

                                if partner.house_id:

                                    other = a2 if partner == a1 else a1

                                    other.house_id = partner.house_id

                                    h = next((h for h in self.houses if h.id == partner.house_id), None)

                                    if h and other.id not in h.residents:

                                        h.residents.append(other.id)

        self._update_royal_lineage()



        self._refresh_agent_relationship_views()



        # Check target tick

        reached_target = False

        if self.target_tick > 0 and self.tick >= self.target_tick:

            reached_target = True



        return self.agents, self.logs, self.resources, reached_target



    def _birth_child(self, mother: AgentSchema):

        life_cycle.birth_child(self, mother)



    def _kill_agent(self, agent: AgentSchema, cause: str):

        self.agent_movement_sessions.pop(agent.id, None)

        life_cycle.kill_agent(self, agent, cause)



    def _process_world_events(self):

        life_cycle.process_world_events(self)



