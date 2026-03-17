import os
import sys
from typing import Optional

import pandas as pd
from pandas import DataFrame

# Allow importing project-level utilities
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from utils.func import extract_before_parenthesis


class Buses:
    """Simple wrapper around the local bus database.

    Backed by Dataset_v1/bus.csv by default. Exposes basic search helpers by
    source/destination city (and optionally journey date).
    """

    def __init__(self, path: Optional[str] = None) -> None:
        if path is None:
            # Go up 3 levels from comman_metrices/tools/bus/
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            path = os.path.join(base_dir, "Dataset_v1", "bus.csv")

        self.path = path
        self.data: Optional[DataFrame] = None

        try:
            self.load_db()
            print("Buses loaded.")
        except Exception as e:
            print(f"Error loading Buses DB: {e}")
            self.data = None

    def load_db(self) -> None:
        """Load the buses CSV into a DataFrame."""
        df = pd.read_csv(self.path)
        self.data = df

    def run(self, origin: str, destination: str, journey_date: Optional[str] = None) -> DataFrame:
        """Return all bus options between origin and destination cities.

        Uses 'source city' and 'destination city' columns from bus.csv.
        If journey_date is provided, it is matched against the 'journey_date'
        column (YYYY-MM-DD as in the dataset).
        """
        if self.data is None:
            return "Database not loaded."

        origin_clean = extract_before_parenthesis(origin)
        dest_clean = extract_before_parenthesis(destination)

        cols = self.data.columns
        if "source city" not in cols or "destination city" not in cols:
            return "Required columns not found in bus DB."

        results = self.data[
            (self.data["source city"] == origin_clean)
            & (self.data["destination city"] == dest_clean)
        ]

        if journey_date is not None and "journey_date" in cols:
            results = results[results["journey_date"] == journey_date]

        if len(results) == 0:
            if journey_date is not None:
                return (
                    f"There is no bus from {origin_clean} to {dest_clean} on {journey_date}."
                )
            return f"There is no bus from {origin_clean} to {dest_clean}."

        return results

    def run_for_annotation(self, origin: str, destination: str, journey_date: Optional[str] = None) -> DataFrame:
        """Same as run(), but kept for interface symmetry with other tools."""
        return self.run(origin, destination, journey_date)