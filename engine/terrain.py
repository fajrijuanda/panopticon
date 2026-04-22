import numpy as np
from typing import List, Tuple, Dict
from enum import Enum
class TerrainType(str, Enum):
    OCEAN = "ocean"
    BEACH = "beach"
    GRASS = "grass"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    SNOW = "snow"
    RIVER = "river"
    ROAD = "road"
    LAKE = "lake"

TERRAIN_COLORS = {
    TerrainType.OCEAN:    "#1e6091",
    TerrainType.BEACH:    "#f0d9a0",
    TerrainType.GRASS:    "#7ec850",
    TerrainType.FOREST:   "#2d6a1e",
    TerrainType.MOUNTAIN: "#8b7355",
    TerrainType.SNOW:     "#e8e8e8",
    TerrainType.RIVER:    "#4a9bd9",
    TerrainType.ROAD:     "#a0896c",
    TerrainType.LAKE:     "#3a7fb8",
}

def _smooth(grid: np.ndarray, iterations: int = 2) -> np.ndarray:
    result = grid.copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode='edge')
        result = (
            padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:] +
            padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:] +
            padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
        ) / 9.0
    return result

def _randint(rng, low: int, high: int | None = None) -> int:
    if hasattr(rng, "integers"):
        return int(rng.integers(low, high))
    return int(rng.randint(low, high))

def _noise_layer(size: int, scale: int, rng=None) -> np.ndarray:
    rng = rng or np.random
    if hasattr(rng, "random"):
        small = rng.random((scale, scale))
    else:
        small = np.random.rand(scale, scale)
    rows = np.linspace(0, scale - 1, size)
    cols = np.linspace(0, scale - 1, size)
    row_idx = np.clip(rows.astype(int), 0, scale - 1)
    col_idx = np.clip(cols.astype(int), 0, scale - 1)
    upscaled = small[np.ix_(row_idx, col_idx)]
    return _smooth(upscaled, iterations=3)

def _draw_water_path(
    terrain: List[List[str]],
    elevation: np.ndarray,
    start: Tuple[float, float],
    end: Tuple[float, float],
    size: int,
    rng,
    thickness: int = 1,
    steps_factor: float = 1.35,
    meander: float = 0.9,
) -> None:
    """Carve a natural meandering water path between two points."""
    sx, sy = start
    ex, ey = end
    steps = max(40, int(size * steps_factor))
    prev_x = int(np.clip(round(sx), 0, size - 1))
    prev_y = int(np.clip(round(sy), 0, size - 1))

    for i in range(steps + 1):
        t = i / max(1, steps)
        base_x = sx + (ex - sx) * t
        base_y = sy + (ey - sy) * t

        wave_x = np.sin(t * np.pi * 3.2 + 0.8) * (meander * size * 0.010)
        wave_y = np.sin(t * np.pi * 2.4 + 2.1) * (meander * size * 0.008)
        jitter_x = float(rng.random() - 0.5) * meander * 0.9
        jitter_y = float(rng.random() - 0.5) * meander * 0.7

        x = int(np.clip(round(base_x + wave_x + jitter_x), 0, size - 1))
        y = int(np.clip(round(base_y + wave_y + jitter_y), 0, size - 1))

        # Fill gaps so the river is continuous.
        gap = max(abs(x - prev_x), abs(y - prev_y))
        for g in range(gap + 1):
            lerp = g / max(1, gap)
            gx = int(round(prev_x + (x - prev_x) * lerp))
            gy = int(round(prev_y + (y - prev_y) * lerp))
            local_thickness = thickness + (1 if t > 0.72 and float(rng.random()) < 0.35 else 0)
            for dy in range(-local_thickness, local_thickness + 1):
                for dx in range(-local_thickness, local_thickness + 1):
                    ny = gy + dy
                    nx = gx + dx
                    if not (0 <= nx < size and 0 <= ny < size):
                        continue
                    if dx * dx + dy * dy > (local_thickness + 0.35) ** 2:
                        continue
                    if terrain[ny][nx] != TerrainType.OCEAN.value:
                        terrain[ny][nx] = TerrainType.RIVER.value

        prev_x, prev_y = x, y

# ═══════════════════════════════════════════
#  MAP PRESETS
# ═══════════════════════════════════════════
MAP_PRESETS = {
    "realistic": {
        "name": "Realistic Continent",
        "description": "Vast continent with mountains in north/east, water only in west/southwest.",
        "icon": "🏔️",
        "sea_level": 0.035,  # Slightly lower so the ocean does not dominate the map
        "islands": [
            {"center": (0.6, 0.4), "radius": 0.50, "biome_bias": {"forest": 0.25, "mountain": 0.45}},  # Main continent, eastern mountains
        ],
    },
}

def generate_terrain(size: int = 120, preset: str = "realistic", env_params: dict = None, rng=None) -> Tuple[List[List[str]], np.ndarray, List[Dict]]:
    cfg = MAP_PRESETS.get(preset, MAP_PRESETS["realistic"])
    rng = rng or np.random
    
    env = env_params or {"fertility": 50, "abundance": 50, "water": 50}
    water_mult = env["water"] / 50.0 # 0.2 to 2.0
    fertility_bonus = (env["fertility"] - 50) / 200.0 # -0.25 to 0.25
    
    sea_level = cfg["sea_level"] * water_mult
    island_configs = cfg["islands"]
    
    elevation = np.full((size, size), -0.1)
    island_mask = np.full((size, size), -1, dtype=int)
    island_infos = []
    
    for idx, icfg in enumerate(island_configs):
        cx_rel, cy_rel = icfg["center"]
        cx = int(cx_rel * size)
        cy = int(cy_rel * size)
        radius_px = int(icfg["radius"] * size)
        
        island_noise = np.zeros((size, size))
        for scale, weight in [(4, 0.5), (8, 0.3), (16, 0.15), (32, 0.05)]:
            island_noise += _noise_layer(size, scale, rng=rng) * weight
        
        for y in range(size):
            for x in range(size):
                dist = np.sqrt((x - cx)**2 + (y - cy)**2)
                if dist < radius_px * 1.3:
                    falloff = max(0.0, 1.0 - (dist / radius_px)**1.8)
                    val = island_noise[y][x] * falloff * 0.9
                    if val > elevation[y][x]:
                        elevation[y][x] = val
                        if val > sea_level + 0.02:
                            island_mask[y][x] = idx
        
        island_land = []
        for y in range(size):
            for x in range(size):
                if island_mask[y][x] == idx and elevation[y][x] > sea_level + 0.05:
                    island_land.append((x, y))
        
        island_infos.append({
            "name": f"Island_{idx+1}",
            "cx": cx, "cy": cy, "radius": radius_px,
            "biome_bias": icfg["biome_bias"],
            "land_tiles": island_land,
        })
    
    # For "realistic" preset: mountains on north/east, land shelf on west/northwest, water only in southwest
    if preset == "realistic":
        # Northern mountains (top 25%)
        north_y_end = int(size * 0.25)
        for y in range(north_y_end):
            for x in range(size):
                y_normalized = 1.0 - (y / north_y_end)  # 1 at north edge, 0 at boundary
                x_dist = abs(x - size / 2.0) / (size / 2.0)
                mountain_height = y_normalized * 0.7 * (1.0 - x_dist ** 1.5)
                if elevation[y][x] > sea_level:
                    elevation[y][x] = max(elevation[y][x], mountain_height)

        # Western / northwestern land shelf so the map stays mostly dry on the left side.
        west_shelf_end = int(size * 0.65)
        north_shelf_end = int(size * 0.70)
        for y in range(north_shelf_end):
            for x in range(west_shelf_end):
                x_factor = 1.0 - (x / west_shelf_end)
                y_factor = 1.0 - (y / north_shelf_end)
                shelf_boost = 0.30 * x_factor * y_factor
                elevation[y][x] = elevation[y][x] + shelf_boost
        
        # Eastern mountains (rightmost 40%)
        east_x_start = int(size * 0.60)
        for y in range(size):
            for x in range(east_x_start, size):
                x_normalized = (x - east_x_start) / (size - east_x_start)  # 0 to 1 from east start to edge
                distance_from_center_y = abs(y - size / 2.0) / (size / 2.0)  # 0 at center, 1 at top/bottom
                
                # Create mountain ridge with valleys for variety
                ridge_base = x_normalized * 0.85  # Higher elevation further east
                valley_factor = np.sin(y * np.pi / size * 4) * 0.12  # 4 valleys across height
                mountain_height = ridge_base + valley_factor * (1.0 - distance_from_center_y ** 1.3)
                
                if elevation[y][x] > sea_level:
                    elevation[y][x] = max(elevation[y][x], mountain_height)
        
        # Southwest ocean basin: wider/deeper to support a broad delta estuary.
        basin_cx = int(size * 0.10)
        basin_cy = int(size * 0.92)
        basin_rx = size * 0.42
        basin_ry = size * 0.34
        for y in range(size):
            for x in range(size):
                dx = (x - basin_cx) / max(1.0, basin_rx)
                dy = (y - basin_cy) / max(1.0, basin_ry)
                dist2 = dx * dx + dy * dy
                if dist2 >= 1.25:
                    continue
                # Core basin gets deeper; fringe stays shallow to form natural beach arcs.
                basin_strength = max(0.0, 1.0 - dist2)
                depression = (basin_strength ** 1.25) * 0.55
                elevation[y][x] = elevation[y][x] - depression
    
    elevation = _smooth(elevation, iterations=2)
    
    terrain: List[List[str]] = []
    for y in range(size):
        row = []
        for x in range(size):
            e = elevation[y][x]
            isl_idx = island_mask[y][x]
            forest_thresh = 0.35
            mountain_thresh = 0.65
            if isl_idx >= 0 and isl_idx < len(island_configs):
                bias = island_configs[isl_idx]["biome_bias"]
                forest_thresh = 0.40 - bias.get("forest", 0) * 0.3 + fertility_bonus
                mountain_thresh = 0.70 - bias.get("mountain", 0) * 0.3 + fertility_bonus
            
            # Additional global fertility bonus
            forest_thresh += fertility_bonus / 2.0
            
            local_slope = 0.0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= nx < size and 0 <= ny < size:
                        local_slope = max(local_slope, abs(e - elevation[ny][nx]))

            if e < sea_level:
                row.append(TerrainType.OCEAN.value)
            elif e < sea_level + (0.018 if local_slope < 0.03 else 0.008):
                row.append(TerrainType.BEACH.value)
            elif e < forest_thresh:
                row.append(TerrainType.GRASS.value)
            elif e < mountain_thresh:
                row.append(TerrainType.FOREST.value)
            elif e < 0.82:
                row.append(TerrainType.MOUNTAIN.value)
            else:
                row.append(TerrainType.SNOW.value)
        terrain.append(row)

    # Keep ocean constrained to the southwest basin only, with smooth curved bounds.
    if preset == "realistic":
        basin_cx = int(size * 0.10)
        basin_cy = int(size * 0.92)
        basin_rx = size * 0.42
        basin_ry = size * 0.34
        for y in range(size):
            for x in range(size):
                dx = (x - basin_cx) / max(1.0, basin_rx)
                dy = (y - basin_cy) / max(1.0, basin_ry)
                dist2 = dx * dx + dy * dy
                in_southwest_basin = dist2 <= 1.08
                if terrain[y][x] == TerrainType.OCEAN.value and not in_southwest_basin:
                    if elevation[y][x] < sea_level + 0.010:
                        terrain[y][x] = TerrainType.BEACH.value
                    else:
                        terrain[y][x] = TerrainType.GRASS.value

        # Remove inland sand flats: keep beaches only where they touch ocean.
        beach_to_grass: List[Tuple[int, int]] = []
        for y in range(size):
            for x in range(size):
                if terrain[y][x] != TerrainType.BEACH.value:
                    continue
                touches_ocean = False
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if 0 <= nx < size and 0 <= ny < size and terrain[ny][nx] == TerrainType.OCEAN.value:
                            touches_ocean = True
                            break
                    if touches_ocean:
                        break
                if not touches_ocean:
                    beach_to_grass.append((x, y))

        for x, y in beach_to_grass:
            terrain[y][x] = TerrainType.GRASS.value
    
    # Generate lakes in low-elevation valleys (natural water accumulation)
    lake_centers = []
    for y in range(5, size - 5):
        for x in range(5, size - 5):
            if terrain[y][x] in [TerrainType.GRASS.value, TerrainType.FOREST.value]:
                # Find local minima - if surrounded by higher elevation, make a lake
                center_elev = elevation[y][x]
                is_local_min = True
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        ny, nx = y + dy, x + dx
                        if 0 <= nx < size and 0 <= ny < size and (dx != 0 or dy != 0):
                            if elevation[ny][nx] < center_elev - 0.05:
                                is_local_min = False
                                break
                    if not is_local_min: break
                if is_local_min and center_elev < 0.22 and center_elev > sea_level + 0.14:
                    lake_centers.append((x, y, center_elev))
    
    # Create lakes at these centers
    rng_obj = rng if hasattr(rng, 'permutation') else np.random
    if preset == "realistic":
        num_lakes = max(1, len(lake_centers) // 120)
    else:
        num_lakes = max(1, len(lake_centers) // 35)
    if lake_centers:
        selected_lakes = rng_obj.choice(len(lake_centers), min(num_lakes, len(lake_centers)), replace=False)
        for lake_idx in selected_lakes:
            lx, ly, _ = lake_centers[int(lake_idx)]
            lake_radius = _randint(rng_obj, 1, 4)
            for dy in range(-lake_radius, lake_radius + 1):
                for dx in range(-lake_radius, lake_radius + 1):
                    ny, nx = ly + dy, lx + dx
                    if 0 <= nx < size and 0 <= ny < size:
                        dist = np.sqrt(dx**2 + dy**2)
                        if dist <= lake_radius:
                            if terrain[ny][nx] not in [TerrainType.MOUNTAIN.value, TerrainType.SNOW.value]:
                                terrain[ny][nx] = TerrainType.LAKE.value
    
    # Generate rivers
    rng_choice = rng if hasattr(rng, 'random') else np.random

    if preset == "realistic":
        # Target look: one dominant river from north to southwest, then split into delta channels.
        trunk_start = (size * 0.60, size * 0.06)
        trunk_mid_1 = (size * 0.66, size * 0.20)
        trunk_mid_2 = (size * 0.55, size * 0.36)
        trunk_mid_3 = (size * 0.44, size * 0.52)
        trunk_mouth = (size * 0.33, size * 0.70)

        _draw_water_path(terrain, elevation, trunk_start, trunk_mid_1, size, rng_choice, thickness=1, meander=1.15)
        _draw_water_path(terrain, elevation, trunk_mid_1, trunk_mid_2, size, rng_choice, thickness=1, meander=1.10)
        _draw_water_path(terrain, elevation, trunk_mid_2, trunk_mid_3, size, rng_choice, thickness=2, meander=1.00)
        _draw_water_path(terrain, elevation, trunk_mid_3, trunk_mouth, size, rng_choice, thickness=2, meander=0.95)

        # Distributary branches near the mouth to mimic estuary/delta geometry.
        branch_starts = [
            (size * 0.40, size * 0.62),
            (size * 0.37, size * 0.66),
            (size * 0.34, size * 0.69),
            (size * 0.31, size * 0.72),
        ]
        branch_ends = [
            (size * 0.24, size * 0.74),
            (size * 0.18, size * 0.79),
            (size * 0.13, size * 0.84),
            (size * 0.08, size * 0.89),
        ]
        for (sx, sy), (ex, ey) in zip(branch_starts, branch_ends):
            _draw_water_path(terrain, elevation, (sx, sy), (ex, ey), size, rng_choice, thickness=1, meander=1.25)

        # Add shallow tidal channels and lagoons in the southwest sea to get irregular coastlines.
        basin_cx = int(size * 0.11)
        basin_cy = int(size * 0.90)
        basin_rx = size * 0.44
        basin_ry = size * 0.36
        for y in range(size):
            for x in range(size):
                dx = (x - basin_cx) / max(1.0, basin_rx)
                dy = (y - basin_cy) / max(1.0, basin_ry)
                dist2 = dx * dx + dy * dy
                if dist2 > 1.16:
                    continue
                tidal_pattern = np.sin((x / size) * np.pi * 8.0) + np.cos((y / size) * np.pi * 7.0)
                if elevation[y][x] < sea_level + 0.045 and tidal_pattern > 0.16:
                    terrain[y][x] = TerrainType.OCEAN.value

        # Force a broad estuary fan with semi-random ocean pockets (delta islands look).
        estuary_cx = int(size * 0.24)
        estuary_cy = int(size * 0.79)
        estuary_rx = size * 0.23
        estuary_ry = size * 0.16
        for y in range(size):
            for x in range(size):
                dx = (x - estuary_cx) / max(1.0, estuary_rx)
                dy = (y - estuary_cy) / max(1.0, estuary_ry)
                dist2 = dx * dx + dy * dy
                if dist2 > 1.0:
                    continue
                channel_wave = np.sin((x + y) * 0.23) + np.cos((x - y) * 0.19)
                if channel_wave > -0.08 or elevation[y][x] < sea_level + 0.02:
                    if terrain[y][x] != TerrainType.MOUNTAIN.value and terrain[y][x] != TerrainType.SNOW.value:
                        terrain[y][x] = TerrainType.OCEAN.value

    else:
        num_rivers_global = 8 if env["water"] < 30 else (12 if env["water"] < 70 else 20)
    
        # Get all high-elevation sources (mountains)
        all_sources: List[Tuple[int, int, float]] = []
        for y in range(size):
            for x in range(size):
                if terrain[y][x] in [TerrainType.MOUNTAIN.value, TerrainType.SNOW.value]:
                    if elevation[y][x] > 0.4:
                        all_sources.append((x, y, elevation[y][x]))

        if all_sources:
            all_sources.sort(key=lambda s: s[2], reverse=True)
            rng_obj = rng if hasattr(rng, 'permutation') else np.random
            selected_sources = rng_obj.choice(len(all_sources), min(num_rivers_global, len(all_sources)), replace=False)
            for idx in selected_sources:
                sx, sy, _ = all_sources[int(idx)]
                cx_r, cy_r = sx, sy
                visited = set()
                river_length = 0
                max_river_length = size * 2
                
                for _ in range(max_river_length):
                    if river_length > max_river_length: break
                    if (cx_r, cy_r) in visited: break
                    visited.add((cx_r, cy_r))
                    
                    # Stop if reached ocean or lake
                    if 0<=cx_r<size and 0<=cy_r<size:
                        if terrain[cy_r][cx_r] in [TerrainType.OCEAN.value, TerrainType.LAKE.value]:
                            break
                        # Paint river (except on mountains)
                        if terrain[cy_r][cx_r] not in [TerrainType.MOUNTAIN.value, TerrainType.SNOW.value]:
                            terrain[cy_r][cx_r] = TerrainType.RIVER.value
                            river_length += 1
                    
                    # Flow to lowest neighbor (8-directional for natural curves)
                    best = None
                    best_elev = elevation[cy_r][cx_r] if 0<=cx_r<size and 0<=cy_r<size else 0
                    
                    for dy in range(-1, 2):
                        for dx in range(-1, 2):
                            if dx == 0 and dy == 0: continue
                            nx, ny = cx_r + dx, cy_r + dy
                            if 0 <= nx < size and 0 <= ny < size and (nx, ny) not in visited:
                                neighbor_elev = elevation[ny][nx]
                                # Prefer flowing downhill with slight randomness for meandering
                                if neighbor_elev < best_elev - 0.001:
                                    # 85% chance to follow elevation, 15% random for natural curves
                                    if rng_choice.random() < 0.85 or best is None:
                                        best_elev = neighbor_elev
                                        best = (nx, ny)
                    
                    if best is None: break
                    cx_r, cy_r = best
    
    # Add scattered small lakes for water diversity
    small_lakes_added = 0
    max_small_lakes = int(size * size * (0.00015 if preset == "realistic" else 0.0015))
    for _ in range(max_small_lakes * 4):
        if small_lakes_added >= max_small_lakes: break
        x = _randint(rng_choice, 5, size - 5)
        y = _randint(rng_choice, 5, size - 5)
        if terrain[y][x] in [TerrainType.GRASS.value, TerrainType.FOREST.value]:
            if float(rng_choice.random()) < 0.5:
                # Create small pond
                pond_size = _randint(rng_choice, 1, 3)
                for dy in range(-pond_size, pond_size + 1):
                    for dx in range(-pond_size, pond_size + 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= nx < size and 0 <= ny < size:
                            if terrain[ny][nx] in [TerrainType.GRASS.value, TerrainType.FOREST.value]:
                                terrain[ny][nx] = TerrainType.LAKE.value
                                small_lakes_added += 1

    # Refresh island land tiles after smoothing + river/lake generation
    for idx, info in enumerate(island_infos):
        refreshed_land: List[Tuple[int, int]] = []
        for y in range(size):
            for x in range(size):
                if island_mask[y][x] != idx:
                    continue
                if terrain[y][x] in [
                    TerrainType.BEACH.value,
                    TerrainType.GRASS.value,
                    TerrainType.FOREST.value,
                    TerrainType.MOUNTAIN.value,
                    TerrainType.ROAD.value,
                    TerrainType.LAKE.value,
                ]:
                    refreshed_land.append((x, y))
        info["land_tiles"] = refreshed_land
    
    return terrain, elevation, island_infos

def _carve_rivers(terrain, elevation, size, num_rivers=1, cx=40, cy=40, radius=20):
    rng = np.random
    sources = []
    for y in range(max(0, cy-radius), min(size, cy+radius)):
        for x in range(max(0, cx-radius), min(size, cx+radius)):
            if terrain[y][x] in [TerrainType.MOUNTAIN.value, TerrainType.SNOW.value, TerrainType.FOREST.value]:
                if elevation[y][x] > 0.5:
                    sources.append((x, y, elevation[y][x]))
    if not sources: return
    sources.sort(key=lambda s: s[2], reverse=True)
    rng.shuffle(sources)
    for sx, sy, _ in sources[:num_rivers]:
        cx_r, cy_r = sx, sy
        visited = set()
        for _ in range(size * 2):
            if (cx_r, cy_r) in visited: break
            visited.add((cx_r, cy_r))
            if terrain[cy_r][cx_r] == TerrainType.OCEAN.value: break
            if terrain[cy_r][cx_r] not in [TerrainType.MOUNTAIN.value, TerrainType.SNOW.value]:
                terrain[cy_r][cx_r] = TerrainType.RIVER.value
            best, best_elev = None, elevation[cy_r][cx_r]
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, ny = cx_r+dx, cy_r+dy
                if 0<=nx<size and 0<=ny<size and (nx,ny) not in visited:
                    if elevation[ny][nx] < best_elev:
                        best_elev = elevation[ny][nx]
                        best = (nx, ny)
            if best is None:
                edge_dx = 1 if cx_r < size//2 else -1
                edge_dy = 1 if cy_r < size//2 else -1
                nx, ny = cx_r+edge_dx, cy_r+edge_dy
                if 0<=nx<size and 0<=ny<size: best = (nx, ny)
                else: break
            cx_r, cy_r = best

def apply_disaster(terrain, elevation, size, disaster_type, rng=None):
    rng = rng or np.random
    logs = []
    if disaster_type == "earthquake":
        cx, cy = _randint(rng, 5, size - 5), _randint(rng, 5, size - 5)
        radius = _randint(rng, 3, 8)
        for y in range(max(0,cy-radius), min(size,cy+radius)):
            for x in range(max(0,cx-radius), min(size,cx+radius)):
                if float(rng.random()) < 0.4:
                    if terrain[y][x] == TerrainType.MOUNTAIN.value:
                        terrain[y][x] = TerrainType.GRASS.value
                    elif terrain[y][x] == TerrainType.GRASS.value and elevation[y][x] > 0.15:
                        terrain[y][x] = TerrainType.MOUNTAIN.value
        logs.append(f"🌋 Earthquake near ({cx},{cy})!")
    elif disaster_type == "flood":
        new_water = []
        for y in range(size):
            for x in range(size):
                if terrain[y][x] in [TerrainType.RIVER.value, TerrainType.OCEAN.value]:
                    for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nx, ny = x+dx, y+dy
                        if 0<=nx<size and 0<=ny<size:
                            if terrain[ny][nx] in [TerrainType.GRASS.value, TerrainType.BEACH.value] and float(rng.random()) < 0.12:
                                new_water.append((nx,ny))
        for wx,wy in new_water: terrain[wy][wx] = TerrainType.RIVER.value
        if new_water: logs.append(f"🌊 Flood! {len(new_water)} tiles submerged.")
    elif disaster_type == "wildfire":
        cx, cy = _randint(rng, 5, size - 5), _randint(rng, 5, size - 5)
        radius = _randint(rng, 3, 7)
        burned = 0
        for y in range(max(0,cy-radius), min(size,cy+radius)):
            for x in range(max(0,cx-radius), min(size,cx+radius)):
                if terrain[y][x] == TerrainType.FOREST.value and float(rng.random()) < 0.6:
                    terrain[y][x] = TerrainType.GRASS.value
                    burned += 1
        if burned: logs.append(f"🔥 Wildfire near ({cx},{cy})! {burned} tiles burned.")
    return logs
