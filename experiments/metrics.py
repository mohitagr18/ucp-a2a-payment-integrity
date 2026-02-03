import csv
import time
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ExperimentResult:
    run_id: str
    scenario: str           # e.g. "retry_storm", "concurrent_race"
    mode: str               # "hardened" 
    total_requests: int
    success_count: int
    failure_count: int
    integrity_violation: bool # True if double spend detected
    duration_ms: float
    notes: str = ""

class CSVWriter:
    def __init__(self, filename: str = "experiment_results.csv"):
        self.filepath = Path(filename)
        self.headers = [
            "timestamp", "run_id", "scenario", "mode", 
            "total_requests", "success_count", "failures", 
            "integrity_violation", "duration_ms", "notes"
        ]
        self._init_file()

    def _init_file(self):
        if not self.filepath.exists():
            with open(self.filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)

    def write(self, result: ExperimentResult):
        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                result.run_id,
                result.scenario,
                result.mode,
                result.total_requests,
                result.success_count,
                result.failure_count,
                result.integrity_violation,
                f"{result.duration_ms:.2f}",
                result.notes
            ])
