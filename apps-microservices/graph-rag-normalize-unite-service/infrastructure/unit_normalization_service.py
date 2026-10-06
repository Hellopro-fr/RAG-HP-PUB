"""Unit normalization wiring. The engine and the frozen tables now live in libs/unit-registry;
this module owns the process-wide state that the event consumer keeps in sync."""
from unit_registry.engine import Normalizer

from infrastructure.unit_state import UnitStateHolder

unit_state = UnitStateHolder()
unit_normalizer = Normalizer(unit_state.current)
