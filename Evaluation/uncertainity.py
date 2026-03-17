"""
uncertainty_metrics.py
======================
Callable BAS, CATS, TDAS functions that take the standard JSONL plan format.
Place in common_metrics/ alongside eval.py.

All formulas follow the PhD Evaluation Methodology document exactly.

Dependencies
------------
    pip install scipy numpy pandas
"""

import re
import os
import json

from scipy.stats import norm


# ─── module-level dataset cache (thread-safe for reads) ──────────────��────────

_DATASETS_CACHE = None


# ─── helpers ──────────────────────────────────────────────────────────────────

def _get_minutes(time_str):
    """Convert 'HH:MM' (with optional date annotation) to total minutes from midnight."""
    if not time_str or str(time_str).strip() in ("-", ""):
        return None
    try:
        clean = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)", "", str(time_str)).strip()
        if ":" in clean:
            parts = clean.split(":")
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        pass
    return None


def _duration(start_str, end_str):
    """
    Duration in minutes between two HH:MM strings.
    Handles midnight crossover by adding 1440 when end < start.
    """
    s = _get_minutes(start_str)
    e = _get_minutes(end_str)
    if s is None or e is None:
        return 0.0
    d = e - s
    return float(d + 1440 if d < 0 else d)


def _clean_float(val):
    """Safely extract a float from a value that may be string/numeric/None."""
    try:
        m = re.search(r"([\d.]+)", str(val))
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


def _parse_poi_section(poi_str, poi_name):
    """Return the raw semicolon-delimited section text for a named POI, or None."""
    if not poi_name or poi_name in ("-", ""):
        return None
    esc = re.escape(poi_name.split(",")[0].strip())
    m = re.search(rf"{esc},[^;]*", poi_str, re.I)
    return m.group(0) if m else None


def _crowd_risk(poi_str, poi_name):
    """
    Return crowd risk R for a named POI.

    Methodology §2.2 mapping:
        Below Average → 0.0
        Average       → 0.3
        Above Average → 0.6
        High          → 1.0
    Default (unknown) → 0.3  (treated as Average)

    Note: longer/more-specific tokens are checked before shorter ones
    to avoid 'above average' matching on 'average'.
    """
    sec = _parse_poi_section(poi_str, poi_name)
    if sec:
        sec_low = sec.lower()
        for tier, risk in (
            ("below average", 0.0),
            ("above average", 0.6),
            ("high crowd",    1.0),
            ("high",          1.0),
            ("average",       0.3),
            ("low",           0.0),
        ):
            if tier in sec_low:
                return risk
    return 0.3   # default: Average


def _congestion_factor(poi_str, poi_name):
    """
    Return congestion-tier factor C_f for a named POI.

    Updated congestion factors:
        Low           → 1.0
        Below Average → 1.25
        Average       → 1.5
        Above Average → 1.75
        High          → 2.0
    """
    sec = _parse_poi_section(poi_str, poi_name)
    if sec:
        sec_low = sec.lower()
        for tier, cf in (
            ("below average", 1.25),
            ("above average", 1.75),
            ("high crowd",    2.0),
            ("high",          2.0),
            ("average",       1.5),
            ("low",           1.0),
        ):
            if tier in sec_low:
                return cf
    return 1.5   # default: Average


def _is_peak(start_min, end_min):
    """
    Return True if [start_min, end_min] overlaps any peak window.

    Peak windows (empirically derived from popular-hours data):
        Morning : 08:00–10:00  (480–600 min)
        Evening : 17:00–20:00  (1020–1200 min)
    """
    for p_s, p_e in [(480, 600), (1020, 1200)]:
        if max(start_min, p_s) < min(end_min, p_e):
            return True
    return False


def _normalized_deviation(b_actual, a_c, b_c):
    """
    Normalized quantitative deviation Q from expected buffer range [a_c, b_c].

    Methodology §2.1 Step 3.2:
        D = 0                                        if b_actual ∈ [a_c, b_c]
        D = min(|b_actual − a_c|, |b_actual − b_c|) otherwise
        Q = D / (b_c − a_c), clamped to [0, 1]
    """
    width = b_c - a_c
    if width <= 0:
        return 0.0
    if a_c <= b_actual <= b_c:
        return 0.0
    d = min(abs(b_actual - a_c), abs(b_actual - b_c))
    q = d / width
    return min(1.0, q)  # Clamp Q to maximum of 1.0


def _bas_category(entry_raw):
    """Classify a POI entry string into a BAS buffer-range category."""
    low = entry_raw.lower()
    if any(kw in low for kw in ("visit", "attraction", "museum", "temple", "fort", "palace")):
        return "attraction"
    if any(kw in low for kw in ("restaurant", "lunch", "dinner", "breakfast", "cafe")):
        return "restaurant"
    if any(kw in low for kw in ("flight", "train", "bus", "cab", "station", "airport")):
        return "transport"
    return "default"


def _extract_transport_mode(transport_str):
    """Return the transport mode string ('Flight', 'Train', 'Cab', 'Bus') or ''."""
    if not transport_str or transport_str == "-":
        return ""
    for mode in ("Flight", "Train", "Cab", "Bus"):
        if mode.lower() in transport_str.lower():
            return mode
    return ""


def _extract_transport_no(transport_str):
    """Return the transport number (flight/train) or None for road modes."""
    mode = _extract_transport_mode(transport_str)
    if mode in ("Cab", "Bus", ""):
        return None
    m = re.search(r"(?:Number|No)[:\s]+([A-Z0-9-]+)", transport_str, re.I)
    if m:
        return m.group(1)
    m = re.search(r"([A-Z]{1,3}-\d{2,5}|\d{5})", transport_str)
    return m.group(1) if m else None


def _extract_transport_timing(transport_str):
    """Return (dep_str, arr_str) parsed from a transportation field string."""
    dep = re.search(r"Departure Time:\s*([\d:]+(?:\s*\([\d-]+\))?)", transport_str)
    arr = re.search(r"Arrival Time:\s*([\d:]+(?:\s*\([\d-]+\))?)", transport_str)
    clean = lambda s: re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)", "", s).strip()
    dep_t = clean(dep.group(1)) if dep else None
    arr_t = clean(arr.group(1)) if arr else None
    return dep_t, arr_t


def _parse_itinerary(poi_str):
    """
    Extract an ordered list of POI dicts from a semicolon-delimited POI string.
    Each dict: {name, start, end, raw}.
    Only entries that contain a 'from HH:MM to HH:MM' pattern are included.
    """
    entries = [e.strip() for e in poi_str.split(";") if e.strip()]
    itinerary = []
    for entry in entries:
        name_part = entry.split(",")[0].strip()
        m = re.search(r"from ([\d:]+) to ([\d:]+)", entry)
        if m:
            itinerary.append({
                "name":  name_part,
                "start": m.group(1),
                "end":   m.group(2),
                "raw":   entry,
            })
    return itinerary


def dest_fallback(query_data):
    """Return destination string even when stored as a list in query_data."""
    d = query_data.get("dest", "")
    if isinstance(d, list):
        return d[0] if d else ""
    return str(d)


def _load_datasets():
    """
    Load transport and attraction CSV datasets once and cache at module level.
    Looks for Dataset_v1/ one directory above this file (i.e., project root).
    """
    global _DATASETS_CACHE
    if _DATASETS_CACHE is not None:
        return _DATASETS_CACHE
    import pandas as pd
    THIS_DIR    = os.path.dirname(os.path.abspath(__file__))
    DATASET_DIR = os.path.normpath(os.path.join(THIS_DIR, "Dataset_v1"))
    try:
        attraction_df = pd.read_csv(os.path.join(DATASET_DIR, "attraction.csv"))
        attraction_df["name_clean"] = attraction_df["name"].str.strip().str.lower()
        
        _DATASETS_CACHE = {
            "flight":     pd.read_csv(os.path.join(DATASET_DIR, "flight.csv")),
            "train":      pd.read_csv(os.path.join(DATASET_DIR, "train.csv")),
            "road":       pd.read_csv(os.path.join(DATASET_DIR, "road_delay.csv")),
            "attraction": attraction_df,
        }
    except Exception as exc:
        _DATASETS_CACHE = {
            "_load_error": f"Path: {DATASET_DIR} | Error: {exc}"
        }
    return _DATASETS_CACHE


# ─── BAS ──────────────────────────────────────────────────────────────────────

# Risk multipliers based on traveller type for dynamic buffer calculation
_RISK_MULTIPLIERS = {
    "risk-tolerant":  (0.50, 1.00),
    "risk-optimized": (1.00, 1.25),
    "risk-averse":    (1.25, 2.00),
}

# Restaurant visit durations by meal type (in minutes)
_RESTAURANT_DURATION = {
    "breakfast": 50,
    "lunch":     60,
    "dinner":    75,
}


def _get_risk_multipliers(traveller_type):
    """
    Return (low_mult, high_mult) based on traveller type.
    Default to 'risk-optimized' if type is unrecognized.
    """
    t = str(traveller_type).lower().replace(" ", "-")
    if "tolerant" in t:
        return _RISK_MULTIPLIERS["risk-tolerant"]
    elif "averse" in t:
        return _RISK_MULTIPLIERS["risk-averse"]
    elif "optimized" in t or "neutral" in t:
        return _RISK_MULTIPLIERS["risk-optimized"]
    else:
        return _RISK_MULTIPLIERS["risk-optimized"]


def _get_meal_type(start_minutes):
    """Return meal type (breakfast/lunch/dinner) based on start time in minutes."""
    if start_minutes is None:
        return "lunch"
    hour = start_minutes // 60
    if 6 <= hour < 11:
        return "breakfast"
    elif 11 <= hour < 16:
        return "lunch"
    else:
        return "dinner"


def _get_visit_duration(poi_name, poi_raw, attraction_duration_map):
    """
    Get visit duration (v) from attraction dataset or calculated from restaurant type.
    
    For attractions: Look up in attraction.csv visit_duration column (stored in hours, convert to minutes)
    For restaurants: Calculate based on meal type (breakfast=50, lunch=60, dinner=75)
    
    Returns duration in minutes, or None if not found.
    """
    # Determine if this is a restaurant or attraction
    poi_low = poi_raw.lower()
    is_restaurant = any(kw in poi_low for kw in ("restaurant", "lunch", "dinner", "breakfast", "cafe"))
    
    if is_restaurant:
        # Restaurant: calculate based on meal time
        # Extract start time from poi_raw
        m = re.search(r"from ([\d:]+)", poi_raw)
        if m:
            start_min = _get_minutes(m.group(1))
            meal_type = _get_meal_type(start_min)
            return _RESTAURANT_DURATION[meal_type]
        return 60.0  # default lunch duration
    else:
        # Attraction: look up in dataset (stored in hours, convert to minutes)
        key = poi_name.strip().lower()
        duration_hours = attraction_duration_map.get(key)
        if duration_hours is not None and not (isinstance(duration_hours, float) and duration_hours != duration_hours):  # check for NaN
            return float(duration_hours) * 60.0  # Convert hours to minutes
        return None  # No data available


# Expected buffer ranges [a_c, b_c] in minutes per POI category.
# Derived from human-annotated corpus (mean ± 1 SD per category).
# Run calibration.py:calibrate_from_corpus() to update these from your dataset.
# NOTE: These are NOT used in the current BAS implementation which uses dynamic
#       ranges based on: a_c = low_mult × v × Cf, b_c = high_mult × v × Cf

def compute_bas(query_data, plan):
    """
    Buffer Adequacy Score (BAS) — methodology §2.1.

    For each consecutive POI pair (i, i+1):
        t_arrival   = start time of current POI
        t_departure = end time of current POI
        v           = base visit duration from attraction.csv or restaurant meal type
        B_actual    = (t_departure − t_arrival) − v   (actual buffer time)
        
        C_f         = congestion factor for current POI
        
        Dynamic buffer ranges based on traveller type:
        a_c = low_mult × v × C_f
        b_c = high_mult × v × C_f
        
        Q_i = normalized_deviation(B_actual, a_c, b_c)

    Trip score:
        BAS = 1 − (1/N) Σ Q_i    ∈ [0, 1]

    Parameters
    ----------
    query_data : dict  — must contain 'Traveller type'.
    plan       : list  — list of day-plan dicts.

    Returns
    -------
    (trip_bas : float | None, detail_lines : list[str])
    """
    lines     = []
    total_q   = 0.0
    seg_count = 0
    
    # Load datasets and build attraction duration map
    dfs = _load_datasets()
    if "_load_error" in dfs:
        return None, [f"  Warning: could not load BAS datasets: {dfs['_load_error']}"]
    
    attraction_df = dfs.get("attraction")
    if attraction_df is None:
        return None, ["  Error: attraction dataset not found"]
    
    # Build attraction duration map: {name_clean: visit_duration}
    attraction_duration_map = dict(zip(
        attraction_df["name_clean"],
        attraction_df["visit_duration"]
    ))
    
    # Get risk multipliers from traveller type
    traveller_type = query_data.get("Traveller type", "risk-optimized")
    low_mult, high_mult = _get_risk_multipliers(traveller_type)

    for day_plan in plan:
        day     = day_plan.get("days", "?")
        poi_str = (
            day_plan.get("point_of_interest")
            or day_plan.get("point_of_interest_list")
            or ""
        )
        itinerary = _parse_itinerary(poi_str)
        if len(itinerary) < 2:
            continue

        for i in range(len(itinerary) - 1):
            curr = itinerary[i]
            nxt  = itinerary[i + 1]

            t_a            = _get_minutes(curr["start"])
            t_next_arrival = _get_minutes(nxt["start"])

            if t_a is None or t_next_arrival is None:
                continue

            # Step 1: Get v from attraction dataset or restaurant meal type
            v = _get_visit_duration(curr["name"], curr["raw"], attraction_duration_map)
            if v is None:
                continue  # Skip if no visit duration data available

            # Step 2: Calculate actual buffer = time_at_location - visit_duration
            # B_actual = (t_departure - t_arrival) - v
            t_departure = _get_minutes(curr["end"])
            if t_departure is None:
                continue
            
            b_actual = (t_departure - t_a) - v
            if b_actual < 0:
                b_actual = 0

            # Step 3: Get congestion factor and calculate expected range
            # a_c = low_mult × v × Cf,  b_c = high_mult × v × Cf
            c_f = _congestion_factor(poi_str, curr["name"])
            a_c = low_mult * v * c_f
            b_c = high_mult * v * c_f

            # Step 4: normalized deviation
            q_i = _normalized_deviation(b_actual, a_c, b_c)

            lines.append(
                f"  Day {day} | {curr['name']} → {nxt['name']}: "
                f"v={v:.0f}min, C_f={c_f:.2f}, "
                f"B_actual={b_actual:.1f}min, range=[{a_c:.1f},{b_c:.1f}], Q_i={q_i:.4f}"
            )
            total_q   += q_i
            seg_count += 1

    if seg_count == 0:
        return None, ["  No valid activity transitions found for BAS."]

    # Step 5: BAS = 1 − mean(Q), clipped to [0, 1]
    trip_bas = max(0.0, 1.0 - (total_q / seg_count))
    lines.append(
        f"\n  BAS = 1 − {total_q / seg_count:.4f} = {trip_bas:.4f}"
        f"  (N={seg_count} transitions)"
    )
    return trip_bas, lines


# ─── CATS ─────────────────────────────────────────────────────────────────────

# Crowd intensity levels mapped to numeric values
_CROWD_INTENSITY = {
    "L":  0.00,
    "BA": 0.25,
    "A":  0.50,
    "AA": 0.75,
    "H":  1.00,
}


def _parse_besttime(avg_besttime_str):
    """
    Parse avg_besttime_analysis JSON string from attraction.csv.
    Returns parsed dict or None if invalid.
    """
    if not avg_besttime_str or (isinstance(avg_besttime_str, float) and avg_besttime_str != avg_besttime_str):
        return None   # NaN check
    try:
        if isinstance(avg_besttime_str, str):
            return json.loads(avg_besttime_str.replace('""', '"'))
        return avg_besttime_str
    except Exception:
        return None


def _get_weighted_intensity(cw, visit_start_min, visit_end_min):
    """
    Calculate weighted average intensity across all overlapping crowd windows.

    Formula: intensity = Σ(overlap_w × intensity_w) / visit_duration
    
    Returns: (intensity: float, dominant_level: str)
    """
    visit_dur = visit_end_min - visit_start_min
    if visit_dur <= 0:
        return 0.5, "A"

    weighted_sum   = 0.0
    total_overlap  = 0.0
    dominant_level = "A"
    max_overlap    = 0.0

    for window in cw:
        w_start_min = window[0] * 60
        w_end_min   = (window[1] + 1) * 60  # hour windows are inclusive
        level       = window[2]
        intensity_w = _CROWD_INTENSITY.get(level, 0.5)

        overlap = max(0, min(visit_end_min, w_end_min) - max(visit_start_min, w_start_min))

        if overlap > 0:
            weighted_sum  += overlap * intensity_w
            total_overlap += overlap
            if overlap > max_overlap:
                max_overlap    = overlap
                dominant_level = level

    if total_overlap == 0:
        return 0.5, "A"

    return round(weighted_sum / visit_dur, 4), dominant_level


def _get_hour_list_overlap_ratio(visit_start_min, visit_end_min, hour_list):
    """
    Calculate proportional overlap of visit time against a list of hours (quiet or peak).
    
    Each hour is treated as a 60-minute window: [h*60, h*60+60]
    
    Formula: ratio = Σ overlap(visit, hour_window) / visit_duration
    
    Returns ratio in [0, 1].
    """
    visit_dur = visit_end_min - visit_start_min
    if visit_dur <= 0 or not hour_list:
        return 0.0

    total_overlap = 0
    for h in hour_list:
        h_start = h * 60
        h_end   = h * 60 + 60
        overlap = max(0, min(visit_end_min, h_end) - max(visit_start_min, h_start))
        total_overlap += overlap

    return round(min(1.0, total_overlap / visit_dur), 4)


def compute_cats(query_data, plan):
    """
    Crowd-Aware Timing Score (CATS) — methodology §2.2.

    For each POI visit over interval [t_a, t_d]:
        Load avg_besttime_analysis from attraction.csv containing:
        - cw: crowd windows [[start_hour, end_hour, level], ...]
        - q: quiet hours list
        - p: peak hours list
        
        Calculate:
        1. intensity = weighted average across cw windows
        2. base_score = 1 - intensity
        3. quiet_bonus = quiet_ratio × (1 - intensity)
        4. peak_penalty = peak_ratio × intensity
        5. score = clip(base_score + quiet_bonus - peak_penalty, 0, 1)

    Trip score:
        CATS = (1/N) Σ score_poi    ∈ [0, 1]

    Returns
    -------
    (trip_cats : float | None, detail_lines : list[str])
    """
    lines      = []
    total_cats = 0.0
    poi_count  = 0

    # Load datasets and build besttime map
    dfs = _load_datasets()
    if "_load_error" in dfs:
        return None, [f"  Warning: could not load CATS datasets: {dfs['_load_error']}"]
    
    attraction_df = dfs.get("attraction")
    if attraction_df is None:
        return None, ["  Error: attraction dataset not found"]
    
    # Build besttime map: {name_clean: parsed_avg_besttime_analysis}
    besttime_map = {}
    for _, row in attraction_df.iterrows():
        parsed = _parse_besttime(row.get("avg_besttime_analysis"))
        if parsed:
            besttime_map[row["name_clean"]] = parsed

    for day_plan in plan:
        day     = day_plan.get("days", "?")
        poi_str = (
            day_plan.get("point_of_interest")
            or day_plan.get("point_of_interest_list")
            or ""
        )
        for entry in [e.strip() for e in poi_str.split(";") if e.strip()]:
            name_part = entry.split(",")[0].strip()
            m = re.search(r"from ([\d:]+) to ([\d:]+)", entry)
            if not m:
                continue
            s_min = _get_minutes(m.group(1))
            e_min = _get_minutes(m.group(2))
            if s_min is None or e_min is None:
                continue

            # Look up besttime data
            key      = name_part.strip().lower()
            besttime = besttime_map.get(key)
            
            if besttime is None:
                # No besttime data → skip this POI
                continue
            
            # Extract avg_day data (cw, q, p are nested in avg_day)
            avg_day     = besttime.get("avg_day", {})
            cw          = avg_day.get("cw", [])
            quiet_hours = avg_day.get("q", [])
            peak_hours  = avg_day.get("p", [])
            
            has_quiet = len(quiet_hours) > 0
            has_peak  = len(peak_hours)  > 0
            
            # Step 1: Weighted intensity across cw windows
            intensity, dominant_level = _get_weighted_intensity(cw, s_min, e_min)
            
            # Step 2: Base score
            base_score = 1.0 - intensity
            
            # Step 3: Quiet bonus = quiet_ratio × (1 - intensity)
            if has_quiet:
                quiet_ratio = _get_hour_list_overlap_ratio(s_min, e_min, quiet_hours)
                quiet_bonus = quiet_ratio * (1.0 - intensity)
            else:
                quiet_ratio = 0.0
                quiet_bonus = 0.0
            
            # Step 4: Peak penalty = peak_ratio × intensity
            if has_peak:
                peak_ratio   = _get_hour_list_overlap_ratio(s_min, e_min, peak_hours)
                peak_penalty = peak_ratio * intensity
            else:
                peak_ratio   = 0.0
                peak_penalty = 0.0
            
            # Step 5: Final score
            raw_score = base_score + quiet_bonus - peak_penalty
            cats_poi  = max(0.0, min(1.0, raw_score))

            lines.append(
                f"  Day {day} | {name_part}: "
                f"Crowd={dominant_level} (I={intensity:.2f}), BaseScore={base_score:.2f}, "
                f"QuietRatio={quiet_ratio:.2f}, QuietBonus={quiet_bonus:.2f}, "
                f"PeakRatio={peak_ratio:.2f}, PeakPenalty={peak_penalty:.2f}, "
                f"CATS={cats_poi:.4f}"
            )
            total_cats += cats_poi
            poi_count  += 1

    if poi_count == 0:
        return None, ["  No valid POIs found for CATS."]

    trip_cats = total_cats / poi_count
    lines.append(f"\n  CATS = {trip_cats:.4f}  (N={poi_count} POIs)")
    return trip_cats, lines


# ─── TDAS helpers ─────────────────────────────────────────────────────────────

# Safe-buffer ranges [a_m, b_m] in minutes per transport mode.
# Sources:


def _compute_transition_score(b_j, ed, low_mult, high_mult):
    """
    Compute soft adequacy score and normalized deviation Q for a transport buffer.
    
    a_c = low_mult * ed
    b_c = high_mult * ed
    
    Returns (soft, Q, a_c, b_c)
    """
    a_c   = low_mult * ed
    b_c   = high_mult * ed
    width = b_c - a_c

    if a_c <= b_j <= b_c:
        soft = 1
        Q    = 0.0
    else:
        soft = 0
        D    = min(abs(b_j - a_c), abs(b_j - b_c))
        Q    = (D / width) if width > 0 else 0.0
        Q    = min(1.0, Q)  # Clamp Q to maximum of 1.0

    return soft, round(Q, 4), round(a_c, 2), round(b_c, 2)


def _tdas_flight(b_j, p_on_time, mu_late, sigma_late):
    """
    Flight delay-absorption probability (methodology §2.3):
        TDAS_j = p_on_time + (1 − p_on_time) × Φ((B_j − μ_late) / σ_late)

    Returns a plain Python float in [0, 1].
    """
    if sigma_late <= 0:
        return 1.0 if b_j >= mu_late else float(p_on_time)
    phi = norm.cdf((b_j - mu_late) / sigma_late)
    return float(p_on_time + (1.0 - p_on_time) * phi)


def _tdas_train(b_j, row):
    """
    Train delay-absorption indicator (methodology §2.3):
        μ_train = Σ w_h × d_h   (normalized weights: Σ w_h = 1)
        TDAS_j  = I(B_j ≥ μ_train)

    Horizon weights (1+2+3+4+6 = 16 → each divided by 16):
        1w → 1/16,  1m → 2/16,  3m → 3/16,  6m → 4/16,  1y → 6/16

    Returns (tdas_j : float, mu_train : float).
    """
    weights = [
        (1 / 16, "avg_delay_1week"),
        (2 / 16, "avg_delay_1month"),
        (3 / 16, "avg_delay_3month"),
        (4 / 16, "avg_delay_6month"),
        (6 / 16, "avg_delay_1year"),
    ]
    mu_train = sum(w * _clean_float(row.get(col, 0)) for w, col in weights)
    return (1.0 if b_j >= mu_train else 0.0), float(mu_train)


def _tdas_road(b_j, mu_road, sigma_road):
    """
    Bus/Cab delay-absorption probability (methodology §2.3):
        TDAS_j = Φ((B_j − μ_road) / σ_road)

    Uses empirical road-delay distribution from dataset.
    Returns a plain Python float in [0, 1].
    """
    if sigma_road <= 0:
        return 1.0 if b_j >= mu_road else 0.0
    return float(norm.cdf((b_j - mu_road) / sigma_road))


# ─── TDAS ─────────────────────────────────────────────────────────────────────

def compute_tdas(query_data, plan):
    """
    Transport Delay Absorption Score (TDAS) — methodology §2.3.

    Per transport segment j:
        B_j = planned_dur - hist_dur (buffer in minutes)
        ed  = expected delay based on transport mode
        
        Using risk multipliers from traveller type:
        a_c = low_mult * ed
        b_c = high_mult * ed
        
        soft, Q = transition_score(B_j, ed, low_mult, high_mult)
        TDAS_j = 1 - Q

    Trip score:
        TDAS = (1/M) Σ TDAS_j    ∈ [0, 1]

    Returns
    -------
    (trip_tdas : float | None, detail_lines : list[str])
    """
    lines      = []
    total_tdas = 0.0
    seg_count  = 0

    dfs = _load_datasets()
    if "_load_error" in dfs:
        return None, [f"  Warning: could not load TDAS datasets: {dfs['_load_error']}"]

    org  = query_data.get("org", "")
    dest = dest_fallback(query_data)
    
    # Get risk multipliers from traveller type
    traveller_type = query_data.get("Traveller type", "risk-optimized")
    low_mult, high_mult = _get_risk_multipliers(traveller_type)

    for day_plan in plan:
        day   = day_plan.get("days", "?")
        trans = day_plan.get("transportation", "-") or "-"

        mode = _extract_transport_mode(trans)
        if not mode:
            continue

        dep_t, arr_t = _extract_transport_timing(trans)
        if not dep_t or not arr_t:
            continue

        planned_dur = _duration(dep_t, arr_t)
        trans_no    = _extract_transport_no(trans)

        b_j      = 0.0
        ed       = 0.0
        hist_dur = 0.0

        try:
            if mode == "Flight" and "flight" in dfs:
                df  = dfs["flight"]
                col = next(
                    (c for c in ("flight_no", "Flight Number") if c in df.columns),
                    df.columns[0],
                )
                row_df = df[df[col].astype(str) == str(trans_no)]
                if not row_df.empty:
                    r        = row_df.iloc[0]
                    hist_dur = _duration(
                        str(r.get("dep_time",        r.get("Departure Time", ""))),
                        str(r.get("arr_time",        r.get("Arrival Time",   ""))),
                    )
                    b_j = planned_dur - hist_dur
                    
                    # Calculate expected delay from JSON stats
                    try:
                        otp_json   = str(r.get("OnTimePerformance (JSON)", "{}"))
                        delay_json = str(r.get("DelayStats (JSON)", "{}"))
                        otp        = json.loads(otp_json) if otp_json != '{}' else {}
                        delay_stats = json.loads(delay_json) if delay_json != '{}' else {}
                        
                        N         = otp.get("total_flights", 1)
                        n_late    = otp.get("late", 0) + otp.get("very_late", 0) + otp.get("excessive", 0)
                        n_dis     = otp.get("cancelled", 0) + otp.get("diverted", 0)
                        
                        mu        = delay_stats.get("avg_delay_min", 0)
                        sigma     = delay_stats.get("std_delay_min", 0)
                        d_max     = delay_stats.get("max_delay_min", 0)
                        
                        p_delayed    = n_late / N if N > 0 else 0
                        p_disruption = n_dis / N if N > 0 else 0
                        
                        D_conservative = mu + sigma
                        D_disruption   = p_disruption * d_max
                        
                        ed = (p_delayed * D_conservative) + D_disruption
                    except (json.JSONDecodeError, TypeError, KeyError):
                        ed = 30.0  # fallback

            elif mode == "Train" and "train" in dfs:
                df  = dfs["train"]
                col = "train_no" if "train_no" in df.columns else df.columns[0]
                row_df = df[df[col].astype(str) == str(trans_no)]
                if not row_df.empty:
                    r        = row_df.iloc[0]
                    hist_dur = _duration(
                        str(r.get("departure", "")),
                        str(r.get("arrival",   "")),
                    )
                    b_j = planned_dur - hist_dur
                    
                    # Calculate weighted expected delay
                    w1 = _clean_float(r.get("avg_delay_1week",   0))
                    m1 = _clean_float(r.get("avg_delay_1month",  0))
                    m3 = _clean_float(r.get("avg_delay_3month",  0))
                    m6 = _clean_float(r.get("avg_delay_6month",  0))
                    y1 = _clean_float(r.get("avg_delay_1year",   0))
                    ed = (1*w1 + 2*m1 + 3*m3 + 4*m6 + 6*y1) / 16

            elif mode in ("Cab", "Bus") and "road" in dfs:
                df     = dfs["road"]
                route  = f"{org} to {dest}"
                row_df = df[df["Route"] == route]
                if not row_df.empty:
                    r         = row_df.iloc[0]
                    ff        = _clean_float(r.get("Free Flow Travel Time",              0))
                    tot       = _clean_float(r.get("Total Travel Time (with traffic)",   0))
                    ed        = tot - ff
                    hist_dur  = ff
                    b_j       = planned_dur - ff

        except Exception as exc:
            lines.append(f"  Day {day} | {mode}: lookup error — {exc}")
            continue

        if ed <= 0:
            ed = 15.0  # minimum fallback
        
        # Calculate transition score using risk multipliers
        soft, Q, a_c, b_c = _compute_transition_score(b_j, ed, low_mult, high_mult)
        
        # TDAS_j = 1 - Q
        tdas_j = 1.0 - Q

        lines.append(
            f"  Day {day} | {mode} ({trans_no or 'N/A'}): "
            f"Planned={planned_dur:.0f}min, Hist={hist_dur:.1f}min, "
            f"B={b_j:.1f}min, ED={ed:.1f}min, Range=[{a_c},{b_c}], "
            f"Soft={soft}, Q={Q:.4f}, TDAS_j={tdas_j:.4f}"
        )
        total_tdas += tdas_j
        seg_count  += 1

    if seg_count == 0:
        return None, ["  No valid transport segments found for TDAS."]

    trip_tdas = total_tdas / seg_count
    lines.append(f"\n  TDAS = {trip_tdas:.4f}  (M={seg_count} segments)")
    return trip_tdas, lines
