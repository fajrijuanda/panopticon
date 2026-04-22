from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class ActionStateEnum(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    TRADING = "trading"
    GATHERING = "gathering"
    THINKING = "thinking"
    MARRYING = "marrying"
    ACCEPT_TRADE = "accept_trade"
    REJECT_TRADE = "reject_trade"
    WORKING = "working"
    STEAL = "steal"
    JUDGE = "judge"
    CLAIM_TERRITORY = "claim_territory"
    FORM_ALLIANCE = "form_alliance"
    CONTEST_TERRITORY = "contest_territory"

class LogCategoryEnum(str, Enum):
    ECONOMY = "ECONOMY"
    SOCIAL = "SOCIAL"
    SPATIAL = "SPATIAL"
    SYSTEM = "SYSTEM"

class ResourceTypeEnum(str, Enum):
    WOOD = "wood"
    FOOD = "food"
    COIN = "coin"
    STONE = "stone"
    FISH = "fish"
    PIG = "pig"
    COW = "cow"
    CHICKEN = "chicken"
    CROP = "crop"
    FRUIT = "fruit"
    HERB = "herb"
    HORSE = "horse"
    COPPER = "copper"        # Bronze Age (Ancient era)
    SILVER = "silver"        # Medieval era
    IRON = "iron"            # Medieval/Modern era

class GenderEnum(str, Enum):
    MALE = "male"
    FEMALE = "female"

class LifePhaseEnum(str, Enum):
    BABY = "baby"
    CHILD = "child"
    TEEN = "teen"
    YOUNG_ADULT = "young_adult"
    ADULT = "adult"
    ELDER = "elder"

class EraEnum(str, Enum):
    PREHISTORIC = "prehistoric"      # 0-1500 ticks
    ANCIENT = "ancient"              # 1501-4000
    MEDIEVAL = "medieval"            # 4001-8000
    MODERN = "modern"                # 8001+

class SocialClassEnum(str, Enum):
    NOMAD = "nomad"
    PEASANT = "peasant"
    CITIZEN = "citizen"
    NOBLE = "noble"
    ROYALTY = "royalty"

class Personality(BaseModel):
    # Core traits (available from Prehistoric)
    kindness: float = 0.0
    bravery: float = 0.0
    sociability: float = 0.0
    intellect: float = 0.0
    # Advanced traits (unlock in later eras)
    creativity: float = 0.0    # Ancient+
    ambition: float = 0.0      # Ancient+
    empathy: float = 0.0       # Medieval+
    cunning: float = 0.0       # Medieval+

class Vitals(BaseModel):
    energy: float = 100.0
    hunger: float = 0.0
    social: float = 100.0
    hydration: float = 100.0
    happiness: float = 70.0

class Inventory(BaseModel):
    wood: int = 0
    food: int = 0
    coin: int = 0
    stone: int = 0
    tools: int = 0
    meat: int = 0
    pig: int = 0
    cow: int = 0
    chicken: int = 0
    crop: int = 0
    fruit: int = 0
    herb: int = 0
    has_boat: bool = False
    has_horse: bool = False
    has_cart: bool = False
    has_car: bool = False

class ResourceNode(BaseModel):
    id: str
    type: ResourceTypeEnum
    x: int
    y: int

class SettlementNode(BaseModel):
    id: str
    owner_id: str
    x: int
    y: int
    name: str = ""  # Custom territory/settlement name chosen by owner
    is_farming: bool = False
    territory_radius: int = 3
    allied_with: list[str] = Field(default_factory=list)
    alliance_name: str = ""  # Name of alliance if multiple settlements allied

class BuildingTypeEnum(str, Enum):
    RESIDENCE = "residence"
    MARKET = "market"
    PORT = "port"
    SCHOOL = "school"

class HouseNode(BaseModel):
    id: str
    owner_id: str
    type: BuildingTypeEnum = BuildingTypeEnum.RESIDENCE
    x: int
    y: int
    level: int = 1         # 1=hut, 2=house, 3=mansion, 4=castle
    residents: list = Field(default_factory=list)   # agent IDs living here
    territory_radius: int = 0  # tiles claimed around house
    is_under_construction: bool = False
    labor_required: int = 0
    labor_contributed: int = 0

class GravestoneNode(BaseModel):
    id: str
    name: str
    x: int
    y: int
    death_tick: int
    age_at_death: int

class AgentSchema(BaseModel):
    id: str
    name: str
    gender: GenderEnum = GenderEnum.MALE
    model_slot: str = "A"
    model_name: str = "qwen2.5:1.5b"
    x: int = 0
    y: int = 0
    dx: int = 0
    dy: int = 0
    age: int = 0
    max_age: int = 2500
    life_phase: LifePhaseEnum = LifePhaseEnum.YOUNG_ADULT
    personality: Personality = Personality()
    skills: dict = Field(default_factory=dict)
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    desire: str = ""
    social_class: SocialClassEnum = SocialClassEnum.NOMAD
    royal_title: str = ""
    vitals: Vitals = Vitals()
    inventory: Inventory = Inventory()
    currentThought: str = ""
    actionState: ActionStateEnum = ActionStateEnum.IDLE
    is_alive: bool = True
    is_pregnant: bool = False
    pregnancy_timer: int = 0
    partner_id: Optional[str] = None
    house_id: Optional[str] = None
    livestock_origin_x: Optional[int] = None
    livestock_origin_y: Optional[int] = None
    farm_origin_x: Optional[int] = None
    farm_origin_y: Optional[int] = None
    parents: list = Field(default_factory=list)
    children: list = Field(default_factory=list)
    is_thinking: bool = False
    last_thought_tick: int = 0
    job: str = "Nomad"
    birth_tick: int = 0
    incoming_trade_offer: Optional[dict] = None
    jailed_timer: int = 0
    pending_judgments: list = Field(default_factory=list)
    allies: list[str] = Field(default_factory=list)
    relationships: dict = Field(default_factory=dict)  # {agent_id: {value, interactions[], last_tick}}

class SimulationLog(BaseModel):
    id: str
    tick: int
    calendar_date: str = ""
    category: LogCategoryEnum
    message: str
    timestamp: float = 0.0
    interaction_type: Optional[str] = None
    participant_ids: list[str] = Field(default_factory=list)
    relationship_change: Optional[float] = None
    source_agent_id: Optional[str] = None

# ── Save/Load ──
class SimulationSnapshot(BaseModel):
    """Full simulation state for save/load."""
    schema_version: int = 2
    model_name: str
    violence_level: str = "normal"
    tick: int
    era: str
    agents: dict
    terrain: list
    resources: list
    settlements: list
    houses: list
    gravestones: list
    relationships: dict
    relationship_details: dict = Field(default_factory=dict)
    groundwater: dict = Field(default_factory=dict)
    weather: dict = Field(default_factory=dict)
    global_quest: Optional[dict] = None
    quest_history: list = Field(default_factory=list)
    next_quest_tick: int = 0
    logs: list
