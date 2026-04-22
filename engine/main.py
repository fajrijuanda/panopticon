import asyncio
import os
import socketio
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from spatial_engine import SpatialEngine
from cognitive_loop import evaluate_agent
import systems.save_load as save_load
from terrain import MAP_PRESETS
from pydantic import BaseModel

DEFAULT_MODEL = "qwen2.5:1.5b"
MODEL_ALIASES = {
    "llama3.1": "qwen2.5:1.5b",
    "qwen2.5": "qwen2.5:1.5b",
    "qwen3": "qwen2.5:1.5b",
    "gemma": "gemma3:4b",
    "mistral": "deepseek-coder:1.3b",
}
SUPPORTED_MODELS = ["qwen2.5:1.5b", "qwen3:4b", "gemma3:4b", "deepseek-coder:1.3b", "mixed"]


def normalize_model_name(model_name: str) -> str:
    return MODEL_ALIASES.get(model_name, model_name)

class NewGameConfig(BaseModel):
    fertility: int = 50
    abundance: int = 50
    water: int = 50
    model: str = DEFAULT_MODEL
    target_tick: int = 0
    citizen_count: int = 30
    violence_level: Optional[str] = None

class SaveRequest(BaseModel):
    save_name: Optional[str] = None
    overwrite_file: Optional[str] = None
    screenshot_data_url: Optional[str] = None
    export_excel: bool = True

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
app_asgi = socketio.ASGIApp(sio, app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = SpatialEngine()  # No map loaded yet
engine_is_running = False
engine_speed = 1.0

# ═══════════════════════════════════════
#  SOCKET EVENTS
# ═══════════════════════════════════════
@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)
    # Send current state (may be empty if no game loaded)
    await _emit_full_state(sid)

@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)

async def _emit_full_state(sid=None):
    metrics = engine.compute_metrics()
    agents_dict = {a_id: a.model_dump(mode='json') for a_id, a in engine.agents.items() if a.is_alive}
    logs_list = [log_entry.model_dump(mode='json') for log_entry in engine.logs]
    resources_list = [r.model_dump(mode='json') for r in engine.resources]
    settlements_list = [s.model_dump(mode='json') for s in engine.settlements]
    gravestones_list = [g.model_dump(mode='json') for g in engine.gravestones]
    houses_list = [h.model_dump(mode='json') for h in engine.houses]
    payload = {
        'agents': agents_dict, 'tick': engine.tick,
        'logs': logs_list,
        'resources': resources_list, 'settlements': settlements_list,
        'gravestones': gravestones_list, 'houses': houses_list,
        'global_quest': getattr(engine, 'global_quest', None),
        'terrain': engine.terrain, 'map_size': engine.map_size,
        'era': engine.era.value, 'active_model': engine.active_model,
        'target_tick': engine.target_tick, 'map_preset': engine.map_preset,
        'calendar_date': engine.format_calendar_date(),
        'weather': getattr(engine, 'weather', {}),
        'violence_level': getattr(engine, 'violence_level', 'normal'),
        'hydrology': engine.get_hydrology_status() if hasattr(engine, 'get_hydrology_status') else {},
        'metrics': metrics,
    }
    if sid:
        await sio.emit('init_state', payload, to=sid)
    else:
        await sio.emit('sync_state', payload)


@app.get("/state")
async def get_state():
    """Return the current in-memory simulation state summary."""
    return {
        "has_map": bool(engine.terrain),
        "is_running": engine_is_running,
        "engine": {
            "tick": engine.tick,
            "calendar_date": engine.format_calendar_date(),
            "era": engine.era.value,
            "active_model": engine.active_model,
            "target_tick": engine.target_tick,
            "map_preset": engine.map_preset,
            "map_size": engine.map_size,
        },
    }

# ═══════════════════════════════════════
#  GAME LIFECYCLE ENDPOINTS
# ═══════════════════════════════════════
@app.get("/maps")
async def get_maps():
    """Return available map presets."""
    result = []
    for key, cfg in MAP_PRESETS.items():
        result.append({
            "id": key,
            "name": cfg["name"],
            "description": cfg["description"],
            "icon": cfg["icon"],
        })
    return {"maps": result}

@app.post("/new_game/{map_preset}")
async def new_game(map_preset: str, config: NewGameConfig):
    """Start a new game with chosen map preset and env config."""
    global engine_is_running
    engine_is_running = False
    if map_preset not in MAP_PRESETS:
        return {"status": "error", "message": f"Invalid map: {map_preset}"}
    
    env_params = {
        "fertility": config.fertility,
        "abundance": config.abundance,
        "water": config.water
    }
    
    model_name = normalize_model_name(config.model)
    engine.active_model = model_name if model_name in SUPPORTED_MODELS else DEFAULT_MODEL
    engine.target_tick = max(0, int(config.target_tick or 0))
    num_citizens = max(1, min(40, int(config.citizen_count or 30)))
    engine.init_map(map_preset, env_params, num_agents=num_citizens)
    await _emit_full_state()
    return {
        "status": "ok",
        "map": map_preset,
        "active_model": engine.active_model,
        "target_tick": engine.target_tick,
    }

@app.post("/start")
async def start_engine():
    global engine_is_running
    if not engine.terrain:
        return {"status": "error", "message": "No map loaded. Start a new game first."}
    engine_is_running = True
    return {"status": "started"}

@app.post("/stop")
async def stop_engine():
    global engine_is_running
    engine_is_running = False
    return {"status": "stopped"}

@app.post("/restart")
async def restart_engine():
    """Restart civilization on the SAME map."""
    global engine_is_running, engine_speed
    engine_is_running = False
    engine_speed = 1.0
    engine.reset()
    await _emit_full_state()
    return {"status": "restarted"}

@app.post("/speed/{multiplier}")
async def set_speed(multiplier: int):
    global engine_speed
    if 1 <= multiplier <= 3:
        engine_speed = float(multiplier)
    return {"status": "speed updated", "speed": engine_speed}

@app.post("/model/{model_name}")
async def set_model(model_name: str):
    normalized = normalize_model_name(model_name)
    if normalized in SUPPORTED_MODELS:
        engine.active_model = normalized
        if hasattr(engine, "_assign_agent_models"):
            engine._assign_agent_models()
        return {"status": "ok", "model": normalized}
    return {"status": "error", "message": f"Invalid model. Use: {SUPPORTED_MODELS + list(MODEL_ALIASES.keys())}"}

@app.post("/target/{ticks}")
async def set_target(ticks: int):
    engine.target_tick = ticks
    return {"status": "ok", "target_tick": ticks}


@app.post("/violence/{level}")
async def set_violence_level(level: str):
    return {
        "status": "disabled",
        "message": "Violence level is now derived automatically from citizen personality and current era.",
        "requested": str(level or "").lower(),
    }

# ═══════════════════════════════════════
#  SAVE / LOAD / DELETE
# ═══════════════════════════════════════
@app.post("/save")
async def save_game(payload: SaveRequest):
    if payload.overwrite_file:
        json_file = save_load.save_snapshot(
            engine,
            label="manual",
            overwrite_filename=payload.overwrite_file,
        )
    else:
        json_file = save_load.save_snapshot(
            engine,
            label="manual",
            save_name=payload.save_name,
        )

    base_name = os.path.splitext(json_file)[0]
    image_file = None
    excel_file = None

    if payload.screenshot_data_url:
        image_file = save_load.save_screenshot(base_name, payload.screenshot_data_url)

    if payload.export_excel:
        excel_file = save_load.save_excel_report(engine, base_name)

    return {
        "status": "saved",
        "file": json_file,
        "save_name": base_name,
        "image_file": image_file,
        "excel_file": excel_file,
        "log_count": len(engine.logs),
    }

@app.post("/load")
async def load_game(req: Request):
    data = await req.json()
    filename = data.get("filename")
    success = save_load.load_snapshot(engine, filename)
    if success:
        return {"status": "loaded", "file": filename}
    else:
        return {"status": "error", "message": "Failed to load save."}

@app.post("/load/{filename}")
async def load_game_by_filename(filename: str):
    success = save_load.load_snapshot(engine, filename)
    if success:
        return {"status": "loaded", "file": filename}
    return {"status": "error", "message": "Failed to load save."}

@app.get("/saves")
async def list_saves():
    saves = save_load.list_saves()
    return {"saves": saves}

@app.delete("/saves/{filename}")
async def delete_save(filename: str):
    if save_load.delete_save_bundle(filename):
        return {"status": "deleted", "filename": filename}
    return {"status": "error", "message": "File not found"}

# ═══════════════════════════════════════
#  ENGINE LOOP
# ═══════════════════════════════════════
async def async_agent_evaluator(agent_id: str):
    agent_data = engine.agents.get(agent_id)
    if not agent_data:
        return
    result = await asyncio.to_thread(evaluate_agent, agent_data, engine)
    engine.process_cognitive_result(agent_id, result)

async def engine_loop():
    global engine_is_running
    while True:
        if engine_is_running and engine.terrain:
            try:
                agents, logs, resources, reached_target = engine.step()

                for p_id in engine.pending_cognitive_tasks:
                    asyncio.create_task(async_agent_evaluator(p_id))

                agents_dict = {a_id: a.model_dump(mode='json') for a_id, a in agents.items() if a.is_alive}
                logs_list = [log_entry.model_dump(mode='json') for log_entry in logs]
                resources_list = [r.model_dump(mode='json') for r in resources]
                settlements_list = [s.model_dump(mode='json') for s in engine.settlements]
                gravestones_list = [g.model_dump(mode='json') for g in engine.gravestones]
                houses_list = [h.model_dump(mode='json') for h in engine.houses]
                metrics = engine.compute_metrics()

                payload = {
                    'agents': agents_dict, 'tick': engine.tick,
                    'logs': logs_list, 'resources': resources_list,
                    'settlements': settlements_list, 'gravestones': gravestones_list,
                    'houses': houses_list, 'era': engine.era.value,
                    'global_quest': getattr(engine, 'global_quest', None),
                    'active_model': engine.active_model,
                    'target_tick': engine.target_tick,
                    'calendar_date': engine.format_calendar_date(),
                    'weather': getattr(engine, 'weather', {}),
                    'violence_level': getattr(engine, 'violence_level', 'normal'),
                    'hydrology': engine.get_hydrology_status() if hasattr(engine, 'get_hydrology_status') else {},
                    'metrics': metrics,
                }
                if engine.tick % 800 == 0 or engine.tick <= 1:
                    payload['terrain'] = engine.terrain
                    payload['map_size'] = engine.map_size

                await sio.emit('sync_state', payload)

                if reached_target:
                    reached_at_tick = engine.tick
                    reached_model = engine.active_model
                    engine_is_running = False
                    engine.target_tick = 0

                    auto_json_file = None
                    auto_excel_file = None
                    try:
                        auto_json_file = save_load.save_snapshot(engine, label="target_reached")
                        auto_base_name = os.path.splitext(auto_json_file)[0]
                        auto_excel_file = save_load.save_excel_report(engine, auto_base_name)
                    except Exception as save_err:
                        print(f"[target-autosave] failed at tick {reached_at_tick}: {save_err}")

                    await sio.emit('simulation_complete', {
                        'type': 'complete',
                        'tick': reached_at_tick,
                        'model': reached_model,
                        'auto_save_file': auto_json_file,
                        'auto_excel_file': auto_excel_file,
                        'log_count': len(engine.logs),
                    })
            except Exception as loop_err:
                engine_is_running = False
                print(f"[engine-loop] crashed at tick {engine.tick}: {loop_err}")
                await sio.emit('simulation_complete', {
                    'type': 'error',
                    'tick': engine.tick,
                    'model': engine.active_model,
                    'auto_save_file': None,
                    'auto_excel_file': None,
                    'log_count': len(engine.logs),
                    'error': str(loop_err),
                })
            
        delay = 1.0 / engine_speed
        await asyncio.sleep(delay)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(engine_loop())

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app_asgi", host="0.0.0.0", port=8000, reload=True)
