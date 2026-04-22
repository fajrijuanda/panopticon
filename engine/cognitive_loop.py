from memory_stream import memory_db
from llm_client import query_llm_for_action

def evaluate_agent(agent, spatial_engine):
    """
    Algorithm 1 implementation for evaluating cognitive trigger
    """
    vision = spatial_engine.get_vision_radius(agent) if hasattr(spatial_engine, "get_vision_radius") else 8
    visible_resources = [
        f"{res.type.value}@({res.x},{res.y})"
        for res in spatial_engine.resources
        if abs(res.x - agent.x) + abs(res.y - agent.y) <= vision
    ]
    memory_summary = spatial_engine.get_agent_memory_summary(agent.id) if hasattr(spatial_engine, "get_agent_memory_summary") else {}
    remembered = memory_summary.get("resource_spots", [])[:3]

    # 1. Store observation
    obs_text = (
        f"Vitals: fullness={agent.vitals.hunger:.1f}, energy={agent.vitals.energy:.1f}, hydration={agent.vitals.hydration:.1f}. "
        f"Position=({agent.x},{agent.y}), vision={vision}. "
        f"Visible resources={visible_resources if visible_resources else 'none'}. "
        f"Remembered hotspots={remembered if remembered else 'none'}."
    )
    memory_db.insert_memory(agent.id, obs_text)

    # 2. Retrieve past context
    query_text = "Based on my visible resources, memory hotspots, fullness level, and survival vitals, what action should I take now?"
    retrieved_context = memory_db.retrieve_context(agent.id, query_text, k=5)

    # 3. Call LLM Client
    action_json = query_llm_for_action(agent, retrieved_context, spatial_engine)
    
    return action_json
