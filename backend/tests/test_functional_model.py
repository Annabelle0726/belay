"""Focused tests for the functional-model -> gate-list compiler."""
from app.quantum import synthesize


def test_superpose_all_expands_to_h_on_each():
    syn = synthesize("allocate 3\nsuperpose all\nmeasure all")
    assert syn["ok"]
    assert syn["gates"] == [{"t": "H", "q": 0}, {"t": "H", "q": 1}, {"t": "H", "q": 2}]


def test_entangle_records_control_and_target():
    syn = synthesize("allocate 2\nsuperpose q0\nentangle q0 q1")
    assert syn["ok"]
    assert syn["gates"][-1] == {"t": "CX", "c": 0, "q": 1}


def test_gate_aliases():
    syn = synthesize("allocate 1\nflip q0\nphase q0\nsgate q0")
    assert [g["t"] for g in syn["gates"]] == ["X", "Z", "S"]


def test_duplicate_allocate_rejected():
    syn = synthesize("allocate 1\nallocate 2")
    assert not syn["ok"] and "Duplicate" in syn["error"]


def test_entangle_same_qubit_rejected():
    syn = synthesize("allocate 2\nentangle q0 q0")
    assert not syn["ok"] and "differ" in syn["error"]


def test_allocate_bounds():
    assert not synthesize("allocate 9")["ok"]
    assert not synthesize("allocate 0")["ok"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("functional model: all passed")
