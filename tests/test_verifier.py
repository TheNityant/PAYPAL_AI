from intentparity.verification import source, compare, normalize
import pytest

@pytest.mark.parametrize("instruction,amount,currency", [
    ("Invoice Priya for $75, not $750.", "75.00", "USD"),
    ("Charge $7, not $7000.", "7.00", "USD"),
    ("Bill 1,500 rupees, not 15,000 rupees.", "1500.00", "INR"),
    ("Collect $42.50.", "42.50", "USD"),
])
def test_authorized_amount(instruction, amount, currency):
    v = source(instruction)
    assert (v.status,v.amount,v.currency)==("PASS",amount,currency)

@pytest.mark.parametrize("instruction", [
    "Charge $7000, not $7", "Charge about $7", "Refund $7", "Transfer $7",
    "Charge $7 or $9", "Charge $7 and $9", "Charge 7", "Do not charge $7",
    "Pay $7 if the delivery arrives", "Charge $7 per month",
])
def test_unsafe_instructions_are_held(instruction):
    assert source(instruction).status == "HOLD"

def test_conflicts_held():
    assert compare("Charge $7, not $7000.", "7000", "USD").status == "HOLD"
    assert compare("Charge $7, not $7000.", "7", "INR").status == "HOLD"

@pytest.mark.parametrize("bad", ["NaN","Infinity","-1","0","5.001","a"])
def test_invalid_amounts(bad):
    with pytest.raises(ValueError):
        normalize(bad)
