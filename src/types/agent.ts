export type AgentId = string;

export interface Inventory {
  wood: number;
  food: number;
  coin: number;
  stone: number;
  tools: number;
  meat: number;
  pig: number;
  cow: number;
  chicken: number;
  crop: number;
  fruit: number;
  herb: number;
  has_boat: boolean;
  has_horse: boolean;
  has_cart: boolean;
  has_car: boolean;
}

export interface Vitals {
  energy: number;
  hunger: number;
  social: number;
  hydration: number;
  happiness: number;
}

export interface Personality {
  kindness: number;
  bravery: number;
  sociability: number;
  intellect: number;
  creativity: number;
  ambition: number;
  empathy: number;
  cunning: number;
}

export interface ResourceNode {
  id: string;
  type: "wood" | "food" | "coin" | "stone" | "fish" | "pig" | "cow" | "chicken" | "crop" | "fruit" | "herb" | "horse";
  x: number;
  y: number;
}

export interface SettlementNode {
  id: string;
  owner_id: string;
  x: number;
  y: number;
  name?: string;
  is_farming: boolean;
  territory_radius: number;
  allied_with: string[];
  alliance_name?: string;
}

export interface HouseNode {
  id: string;
  owner_id: string;
  type: "residence" | "market" | "port" | "school";
  x: number;
  y: number;
  level: number;
  residents: string[];
  territory_radius: number;
  is_under_construction: boolean;
  labor_required: number;
  labor_contributed: number;
}

export interface GravestoneNode {
  id: string;
  name: string;
  x: number;
  y: number;
  death_tick: number;
  age_at_death: number;
}

export interface GlobalQuest {
  id: string;
  title: string;
  description: string;
  resource: "wood" | "stone" | "food" | "crop" | "fruit" | "herb" | "fish";
  target_amount: number;
  reward_coin: number;
  created_tick: number;
  deadline_tick: number;
  progress_amount: number;
  contributors: Record<string, number>;
  status: "active" | "completed" | "expired";
}

export interface Agent {
  id: AgentId;
  name: string;
  gender: "male" | "female";
  model_slot: string;
  model_name: string;
  x: number;
  y: number;
  age: number;
  max_age: number;
  life_phase: "baby" | "child" | "teen" | "young_adult" | "adult" | "elder";
  social_class: "nomad" | "peasant" | "citizen" | "noble" | "royalty";
  personality: Personality;
  skills: Record<string, number>;
  vitals: Vitals;
  royal_title: string;
  inventory: Inventory;
  currentThought: string;
  livestock_origin_x?: number | null;
  livestock_origin_y?: number | null;
  farm_origin_x?: number | null;
  farm_origin_y?: number | null;
  actionState:
    | "idle"
    | "moving"
    | "trading"
    | "gathering"
    | "thinking"
    | "marrying"
    | "accept_trade"
    | "reject_trade"
    | "working"
    | "steal"
    | "judge"
    | "claim_territory"
    | "form_alliance"
    | "contest_territory";
  is_alive: boolean;
  is_pregnant: boolean;
  pregnancy_timer: number;
  partner_id: string | null;
  house_id: string | null;
  parents: string[];
  children: string[];
  job: string;
  birth_tick: number;
    last_thought_tick?: number;
  incoming_trade_offer: {
    from: string;
    from_name: string;
    give: Record<string, number>;
    take: Record<string, number>;
  } | null;
  likes: string[];
  dislikes: string[];
  desire: string;
  jailed_timer: number;
  pending_judgments: Array<{
    thief_id: string;
    thief_name: string;
    victim_id: string;
    victim_name: string;
    amount: number;
  }>;
  allies: string[];
  relationships?: Record<string, {value: number; friendship?: number; romance?: number; interactions: string[]; last_interaction_tick: number}>;
}

export interface SimulationLog {
  id: string;
  tick: number;
  calendar_date: string;
  category: "ECONOMY" | "SOCIAL" | "SPATIAL" | "SYSTEM";
  message: string;
  timestamp: number;
  interaction_type?: string;
  participant_ids?: string[];
  relationship_change?: number;
  source_agent_id?: string;
}
