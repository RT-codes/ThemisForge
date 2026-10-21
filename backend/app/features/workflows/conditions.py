from app.features.workflows.graph import (
    NodeError,
)
from app.features.workflows.walk import Prev


def evaluate_condition(config: dict[str, str], prev: Prev | None) -> tuple[bool, str]:
    """The answer, and a sentence explaining it for the log."""
    if prev is None:
        raise NodeError("This condition has nothing before it to check. Connect it after another node.")
    source = config.get("source", "result")
    operator = config.get("operator", "contains")
    value = config.get("value", "")
    actual = prev.result if source == "result" else prev.status
    a, v = actual.strip().casefold(), value.strip().casefold()
    answer = {
        "contains": v in a,
        "equals": a == v,
        "not_equals": a != v,
        "empty": not a,
    }.get(operator)
    if answer is None:
        raise NodeError(f"Unknown operator '{operator}'")
    shown = actual.strip().replace("\n", " ")
    shown = shown if len(shown) <= 120 else shown[:117] + "..."
    what = "previous result" if source == "result" else "previous status"
    return (
        answer,
        f"The {what} from '{prev.label}' is: {shown or '(empty)'}\nCheck: {operator.replace('_', ' ')} {value!r} -> {'yes' if answer else 'no'}",
    )
