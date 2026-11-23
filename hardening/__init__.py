"""Tools for hardening program-writing tasks for terminal agents: a task interface, automatic gates,
frozen references, mutation-based negative controls, failure review and a difficulty screen."""
from .task import Case, Check, Claim, HardTask, Score
from .gates import GateReport, run_gates
from .freeze import freeze, verify

__all__ = ["Case", "Check", "Claim", "HardTask", "Score", "GateReport", "run_gates", "freeze", "verify"]
__version__ = "0.1.0"
