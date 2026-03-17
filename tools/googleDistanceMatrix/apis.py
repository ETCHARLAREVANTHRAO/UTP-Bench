import pandas as pd
import numpy as np
import re
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from utils.func import extract_before_parenthesis

class GoogleDistanceMatrix:
    def __init__(self, subscription_key: str="") -> None:
        self.gplaces_api_key: str = subscription_key
        # Path to local distance matrix csv
        # Go up 3 levels from comman_metrices/tools/googleDistanceMatrix/
        base_dir_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.path = os.path.join(base_dir_root, "Dataset_v1", "road_delay.csv") # Assuming road_delay.csv contains distances if city_distances is missing
        try:
             # Try road_delay.csv first, if fails try other matches
             if not os.path.exists(self.path):
                 self.path = os.path.join(base_dir_root, "Dataset_v1", "final_city_state_lat_long.csv")
             self.data =  pd.read_csv(self.path)
             print(f"OSM_DistanceMatrix loaded from {os.path.basename(self.path)}.")
        except Exception as e:
            print(f"Error loading DistanceMatrix DB: {e}")
            self.data = None

    def run_for_evaluation(self, origin, destination, mode='driving'):
        origin = str(extract_before_parenthesis(origin))
        destination = str(extract_before_parenthesis(destination))
        info = {"origin": origin, "destination": destination,"cost": None, "duration": None, "distance": None}
        
        if self.data is None: return info

        if "road_delay.csv" in self.path:
            mask = self.data['Route'].str.contains(origin, case=False, na=False) & \
                   self.data['Route'].str.contains(destination, case=False, na=False)
            response = self.data[mask]
            
            if not response.empty:
                row = response.iloc[0]
                
                def parse_val(v):
                    if pd.isna(v) or v is None: return 0.0
                    if isinstance(v, (int, float)): return float(v)
                    # Extract number from string like '1731.44 km' or '2343.3 INR'
                    m = re.search(r"(\d+\.?\d*)", str(v))
                    return float(m.group(1)) if m else 0.0

                info["cost"] = parse_val(row.get('Estimated price', 0))
                info["distance"] = parse_val(row.get('Distance', 0))
                info["duration"] = parse_val(row.get('Total Travel Time (with traffic)', 0))
                return info
        else:
            # Legacy logic for other files
            try:
                response = self.data[(self.data['origin'] == origin) & (self.data['destination'] == destination)]
            except:
                response = pd.DataFrame()
            
            if not response.empty:
                info["duration"] = response['duration_min'].values[0]
                info["distance"] = response['distance_km'].values[0]
                if mode == "taxi":
                    info["cost"] = int(info["distance"])
                return info

        return info 
