"""Conservative, deliberately limited financial text verifier.

No claim of multilingual completeness. Unsupported / ambiguous requests HOLD.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

NUM = re.compile(r"(?<![\w.])(?:[$₹]\s*)?\d[\d,]*(?:\.\d{1,2})?(?![\w]|\.\d)")
WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
         "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALE = {"hundred": 100, "thousand": 1000, "lakh": 100000}
WORD_PATTERN = re.compile(r"\b(?:"+"|".join(WORDS | SCALE)+r")(?:[ -](?:"+"|".join(WORDS | SCALE)+r"))*\b", re.I)
DANGER = re.compile(r"\b(?:around|about|approximately|roughly|under|over|between|"
                    r"up\s+to|at\s+least|at\s+most|either|unless|if|"
                    r"per\s+(?:item|month|day)|refund|cancel|reverse|transfer|send|"
                    r"split|installment|recurring|subscription)\b", re.I)
NEGATE = re.compile(r"(?:\bnot|\binstead\s+of|\bdon't|\bdo\s+not|\bnever)\s*(?:charge\s*|bill\s*|invoice\s*|pay\s*|for\s*)?$", re.I)
ACTION = re.compile(r"\b(?:charge|invoice|bill|checkout|collect|pay|purchase)\b", re.I)
@dataclass(frozen=True)
class Verdict:
    status: str
    amount: str | None
    currency: str | None
    reason: str

def normalize(value) -> str:
    try:
        amount = Decimal(str(value).strip().replace(",", "").replace("$", "").replace("₹", ""))
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2 or amount >= 100000000:
            raise ValueError("Invalid payment amount")
        return str(amount.quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid payment amount") from exc

def parse_words(text: str):
    total, part = 0, 0
    for word in re.split(r"[ -]+", text.lower()):
        if word in WORDS:
            part += WORDS[word]
        elif word == "hundred":
            part = max(part, 1) * 100
        elif word in SCALE:
            total += max(part, 1) * SCALE[word]
            part = 0
    return total + part

def source(instruction: str) -> Verdict:
    t = instruction.strip().lower()
    if not t or not ACTION.search(t):
        return Verdict("HOLD", None, None, "Explicit checkout action required")
    if DANGER.search(t):
        return Verdict("HOLD", None, None, "Conditional, approximate or unsupported operation")
    usd = bool(re.search(r"\$|\b(?:usd|dollars?)\b", t))
    inr = bool(re.search(r"₹|\b(?:inr|rupees?|rupaye)\b", t))
    if usd == inr:
        return Verdict("HOLD", None, None, "Currency missing or conflicting")
    currency = "USD" if usd else "INR"
    hits = []
    for match in NUM.finditer(t):
        try:
            hits.append((match.start(), match.end(), normalize(match.group()), match.group()))
        except ValueError:
            return Verdict("HOLD", None, currency, "Invalid numeric amount")
    for match in WORD_PATTERN.finditer(t):
        # Number words must be connected to currency. Do not interpret unrelated
        # English words, or use guessed Romanized Indic numbers.
        nearby = t[max(0, match.start()-24):match.end()+24]
        if not re.search(r"\b(?:dollars?|usd|rupees?|inr|rupaye)\b", nearby):
            continue
        value = parse_words(match.group())
        if value > 0:
            hits.append((match.start(), match.end(), normalize(value), match.group()))
    hits.sort()
    eligible = []
    for start, end, value, raw in hits:
        prefix = t[max(0, start-35):start]
        if NEGATE.search(prefix):
            continue
        eligible.append(value)
    if not eligible or len(set(eligible)) != 1:
        return Verdict("HOLD", None, currency, "No unique non-negated amount established")
    return Verdict("PASS", eligible[0], currency, "Unambiguous supported financial instruction")

def compare(instruction: str, amount, currency) -> Verdict:
    base = source(instruction)
    if base.status != "PASS":
        return base
    try:
        proposed = normalize(amount)
    except ValueError:
        return Verdict("HOLD", base.amount, base.currency, "Invalid model amount")
    if proposed != base.amount or str(currency).upper() != base.currency:
        return Verdict("HOLD", base.amount, base.currency,
                       "Model proposal conflicts with independent source extraction")
    return base
