import pandas as pd
from pandas import DataFrame
from typing import Optional
import os
import sys
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from utils.func import extract_before_parenthesis


class Accommodations:
    def __init__(self, path: Optional[str] = None):
        """Accommodation API backed by local Dataset_v1/acco.csv.

        We normalize key columns such as 'City', 'house_rules', 'max_occupancy',
        and 'pricing' so that existing evaluation code keeps working.
        """

        if path is None:
            # Go up 3 levels from comman_metrices/tools/accommodations/
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            path = os.path.join(project_root, "Dataset_v1", "acco.csv")

        self.path = path
        self.data: Optional[DataFrame] = None

        try:
            self.load_db()
            print("Accommodations loaded.")
        except Exception as e:
            print(f"Error loading Accommodations DB: {e}")

    def load_db(self):
        """Load the accommodation database and normalize columns."""
        df = pd.read_csv(self.path)

        # Normalise columns for consistent lookup
        if "city" in df.columns:
            df["City"] = df["city"].apply(extract_before_parenthesis)
        
        # Ensure City column exists even if 'city' was used
        if "City" in df.columns and "city" not in df.columns:
             df["city"] = df["City"]

        # Normalize house rules column name.
        if "house_rules" not in df.columns and "HOUSE_RULES" in df.columns:
            df["house_rules"] = df["HOUSE_RULES"]

        # Provide a default max occupancy if missing.
        if "max_occupancy" not in df.columns:
            df["max_occupancy"] = 2

        # Build a simple JSON pricing field from estimated price.
        if "pricing" not in df.columns:
            if "Estimated Price(INR)" in df.columns:
                def _make_pricing(val):
                    try:
                        price = float(val)
                    except Exception:
                        return json.dumps({})
                    return json.dumps({"price": str(price)})

                df["pricing"] = df["Estimated Price(INR)"].apply(_make_pricing)
            else:
                df["pricing"] = json.dumps({})

        self.data = df

    def run(self,
            city: str,
            ) -> DataFrame:
        """Search for accommodations by city."""
        if self.data is None: return "Database not loaded."
        
        results = self.data[self.data["city"] == city]
        if len(results) == 0:
            return "There is no attraction in this city." # Original message said 'attraction' likely copy paste error
        
        return results
    
    def run_for_annotation(self,
            city: str,
            ) -> DataFrame:
        """Search for accommodations by city."""
        if self.data is None: return "Database not loaded."
        results = self.data[self.data["city"] == extract_before_parenthesis(city)]
        return results
