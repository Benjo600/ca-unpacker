"""Client profiles: profession catalog and per-profession accounting rule packs.

A profile does not post anything. It tells the engine which checks to raise and
which treatment notes to put in front of the CA. The CA keeps the final call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

RULES_AS_OF = "FY 2026-27"

RULES_DISCLAIMER = (
    "These notes point at treatment areas that commonly apply to this profession. "
    "They are prompts for review, not tax advice. Confirm thresholds, rates and "
    "exemptions for the year before relying on them."
)

CUSTOM_KEY = "custom"


@dataclass(frozen=True)
class TdsRule:
    code: str
    label: str
    keywords: tuple[str, ...]
    threshold: float
    threshold_basis: str
    rate: str
    law_ref: str
    annual_threshold: float | None = None
    monthly: bool = False


@dataclass(frozen=True)
class GstRule:
    status: str
    typical_rate: str
    note: str


@dataclass(frozen=True)
class PresumptiveRule:
    section: str
    label: str
    limit: float
    enhanced_limit: float
    cash_condition: str
    profit_note: str


@dataclass(frozen=True)
class Profession:
    key: str
    label: str
    group: str
    summary: str
    gst: GstRule
    tds: tuple[TdsRule, ...]
    presumptive: PresumptiveRule | None
    expense_heads: tuple[str, ...]
    capital_hint: str
    watch: str


TDS_194J = TdsRule(
    code="194J",
    label="Professional or technical fees",
    keywords=(
        "professional fee",
        "professional fees",
        "prof fee",
        "consultancy",
        "consultation fee",
        "legal fee",
        "advocate",
        "audit fee",
        "retainer",
        "technical fee",
        "design fee",
        "architect fee",
        "doctor fee",
    ),
    threshold=50000,
    threshold_basis="per payee per year",
    rate="10% (2% for technical services, call centres and royalty)",
    law_ref="s.194J; consolidated under s.393 of the Income Tax Act 2025",
)
TDS_194C = TdsRule(
    code="194C",
    label="Contractor or sub-contractor payments",
    keywords=(
        "contractor",
        "labour",
        "labor charges",
        "job work",
        "jobwork",
        "site work",
        "civil work",
        "freight",
        "transport charges",
        "cargo",
        "packing charges",
        "maintenance contract",
    ),
    threshold=30000,
    threshold_basis="per contract",
    annual_threshold=100000,
    rate="1% for individuals and HUF; 2% for others",
    law_ref="s.194C; consolidated under s.393 of the Income Tax Act 2025",
)
TDS_194H = TdsRule(
    code="194H",
    label="Commission or brokerage",
    keywords=(
        "commission",
        "brokerage",
        "broker",
        "referral fee",
        "channel partner",
        "sub-agent",
        "agent payout",
    ),
    threshold=20000,
    threshold_basis="per payee per year",
    rate="2%",
    law_ref="s.194H; consolidated under s.393 of the Income Tax Act 2025",
)
TDS_194I = TdsRule(
    code="194I",
    label="Rent of land, building, furniture or plant",
    keywords=(
        "rent",
        "lease",
        "licence fee",
        "license fee",
        "hire charges",
        "office rent",
        "shop rent",
        "godown rent",
        "warehouse rent",
    ),
    threshold=50000,
    threshold_basis="per month",
    monthly=True,
    rate="10% for land, building and furniture; 2% for plant and machinery",
    law_ref="s.194I; consolidated under s.393 of the Income Tax Act 2025",
)

P_44ADA = PresumptiveRule(
    section="44ADA",
    label="Presumptive income for specified professions",
    limit=5000000,
    enhanced_limit=7500000,
    cash_condition="cash receipts up to 5% of gross receipts",
    profit_note="At least 50% of gross receipts is offered as income.",
)
P_44AD = PresumptiveRule(
    section="44AD",
    label="Presumptive income for eligible businesses",
    limit=20000000,
    enhanced_limit=30000000,
    cash_condition="cash receipts up to 5% of turnover",
    profit_note="At least 6% of turnover is offered as income (8% for cash receipts).",
)
P_44AE = PresumptiveRule(
    section="44AE",
    label="Presumptive income for goods carriage",
    # 44AE is not a turnover test; the limit fields stay at zero on purpose.
    limit=0.0,
    enhanced_limit=0.0,
    cash_condition="up to 10 goods vehicles",
    profit_note="Income is presumed per vehicle per month, not as a percentage of turnover.",
)

GST_18 = GstRule("taxable", "18%", "Most services sit at 18%.")
GST_5 = GstRule("taxable", "5%", "Goods rate depends on the HSN; several staples sit at 5%.")
GST_MIXED = GstRule(
    "mixed",
    "Depends on the line",
    "Different lines carry different rates, and some are exempt. Read each invoice.",
)
GST_EXEMPT_HEALTH = GstRule(
    "exempt",
    "Exempt",
    "Health care services by a clinical establishment are generally exempt. "
    "Pharmacy sales, cosmetic procedures and wellness packages are separate, and "
    "services billed to a business entity can fall under reverse charge.",
)
GST_EXEMPT_EDU = GstRule(
    "exempt",
    "Exempt",
    "Education up to higher secondary is generally exempt. "
    "Coaching above that level and test-prep products need a separate check.",
)
GST_NONE = GstRule(
    "not_applicable",
    "Not applicable",
    "Salary and personal income are outside GST.",
)


ENTITY_TYPES: tuple[tuple[str, str], ...] = (
    ("proprietorship", "Proprietorship"),
    ("partnership", "Partnership firm"),
    ("llp", "LLP"),
    ("pvt_ltd", "Private limited company"),
    ("public_ltd", "Public limited company"),
    ("huf", "HUF"),
    ("trust", "Trust / society"),
    ("individual", "Individual (non-business)"),
)

ENTITY_LABELS = dict(ENTITY_TYPES)

# Presumptive schemes are open to individuals, HUF and partnership firms only.
_PRESUMPTIVE_ENTITIES = frozenset({"proprietorship", "partnership", "huf", "individual"})

PROFESSIONS: tuple[Profession, ...] = (
    Profession(
        key="doctor",
        label="Doctor / clinic",
        group="Professional services",
        summary="Medical practice, clinic or consulting room.",
        gst=GST_EXEMPT_HEALTH,
        tds=(TDS_194J, TDS_194I, TDS_194C),
        presumptive=P_44ADA,
        expense_heads=(
            "Medical consumables",
            "Clinic rent",
            "Staff salary",
            "Lab and diagnostics",
            "Equipment repair",
            "Professional indemnity insurance",
        ),
        capital_hint="Diagnostic machines, clinic fit-outs and equipment above your capitalisation limit.",
        watch="Visiting consultant fees, clinic rent and lab charges are the usual TDS lines to check.",
    ),
    Profession(
        key="lawyer",
        label="Advocate / law firm",
        group="Professional services",
        summary="Legal practice, chamber or law firm.",
        gst=GstRule(
            "taxable",
            "18%",
            "Legal services are taxable at 18%. Where an individual advocate bills a business "
            "entity, reverse charge can shift the liability to the recipient.",
        ),
        tds=(TDS_194J, TDS_194I, TDS_194H),
        presumptive=P_44ADA,
        expense_heads=(
            "Court and filing fees",
            "Chamber rent",
            "Clerk and junior salary",
            "Library and research",
            "Professional subscriptions",
            "Travel for hearings",
        ),
        capital_hint="Law library, chamber furniture and IT equipment above your capitalisation limit.",
        watch="Check who discharges GST on bills raised to business clients, and keep the RCM working papers.",
    ),
    Profession(
        key="architect",
        label="Architect",
        group="Professional services",
        summary="Architectural design and project consultancy.",
        gst=GST_18,
        tds=(TDS_194J, TDS_194C, TDS_194I),
        presumptive=P_44ADA,
        expense_heads=(
            "Site visits and travel",
            "Drafting and design software",
            "Sub-consultant fees",
            "Office rent",
            "Printing and model making",
            "Professional subscriptions",
        ),
        capital_hint="Workstations, plotter and survey equipment above your capitalisation limit.",
        watch="Payments to sub-consultants and site contractors are the common 194J and 194C lines.",
    ),
    Profession(
        key="consultant",
        label="Management consultant",
        group="Professional services",
        summary="Advisory, strategy or management consulting.",
        gst=GST_18,
        tds=(TDS_194J, TDS_194I, TDS_194H),
        presumptive=None,
        expense_heads=(
            "Subcontractor fees",
            "Travel and stay",
            "Software subscriptions",
            "Research and data",
            "Client meetings",
            "Office rent",
        ),
        capital_hint="Laptops, licences and office fit-out above your capitalisation limit.",
        watch="44ADA covers technical consultancy. If the work is pure management advisory, confirm eligibility before opting.",
    ),
    Profession(
        key="ca_firm",
        label="CA / accounting firm",
        group="Professional services",
        summary="Chartered accountancy, audit or bookkeeping practice.",
        gst=GST_18,
        tds=(TDS_194J, TDS_194I, TDS_194C),
        presumptive=P_44ADA,
        expense_heads=(
            "Staff salary",
            "Audit and tax software",
            "Institute and membership fees",
            "Office rent",
            "Filing and portal fees",
            "Client meeting costs",
        ),
        capital_hint="Laptops, servers and office fit-out above your capitalisation limit.",
        watch="Article stipends, visiting faculty and software subscriptions are the usual review lines.",
    ),
    Profession(
        key="engineer",
        label="Engineer / technical consultancy",
        group="Professional services",
        summary="Engineering or technical consultancy services.",
        gst=GST_18,
        tds=(TDS_194J, TDS_194C, TDS_194I),
        presumptive=P_44ADA,
        expense_heads=(
            "Site expenses",
            "Equipment hire",
            "Design software",
            "Sub-consultant fees",
            "Travel and stay",
            "Office rent",
        ),
        capital_hint="Instruments, testing equipment and workstations above your capitalisation limit.",
        watch="Equipment hire can fall under 194I for plant and machinery rather than 194C.",
    ),
    Profession(
        key="it_services",
        label="IT / software services",
        group="Professional services",
        summary="Software development, IT support or SaaS services.",
        gst=GstRule(
            "taxable",
            "18%",
            "IT and software services are generally taxable at 18%. "
            "Exports may be zero-rated with the right paperwork.",
        ),
        tds=(TDS_194J, TDS_194C, TDS_194I),
        presumptive=P_44ADA,
        expense_heads=(
            "Subcontractor and developer payments",
            "Cloud and hosting",
            "Software licences",
            "Hardware and peripherals",
            "Internet and telecom",
            "Office rent",
        ),
        capital_hint="Laptops, servers and networking gear above your capitalisation limit.",
        watch="Overseas cloud and licence bills raise import-of-service and equalisation questions. Check before treating them as plain expenses.",
    ),
    Profession(
        key="designer",
        label="Designer / creative services",
        group="Professional services",
        summary="Graphic, product, interior or fashion design.",
        gst=GST_18,
        tds=(TDS_194J, TDS_194H),
        presumptive=None,
        expense_heads=(
            "Stock and materials",
            "Design software",
            "Freelance creative help",
            "Studio rent",
            "Printing and samples",
            "Equipment repair",
        ),
        capital_hint="Cameras, workstations and studio equipment above your capitalisation limit.",
        watch="44ADA names interior decoration specifically. Other design work needs a check before opting in.",
    ),
    Profession(
        key="tuition",
        label="Tuition / coaching",
        group="Professional services",
        summary="Tuition classes, coaching centre or test prep.",
        gst=GST_EXEMPT_EDU,
        tds=(TDS_194C, TDS_194I, TDS_194J),
        presumptive=P_44AD,
        expense_heads=(
            "Coaching materials",
            "Classroom rent",
            "Tutor payments",
            "Electricity",
            "Marketing and admissions",
            "Furniture and fixtures",
        ),
        capital_hint="Classroom furniture, projectors and computers above your capitalisation limit.",
        watch="Coaching is treated as business income, so 44AD is the usual scheme rather than 44ADA.",
    ),
    Profession(
        key="freelancer",
        label="Freelancer / other professional",
        group="Professional services",
        summary="Independent professional whose work is not listed above.",
        gst=GST_MIXED,
        tds=(TDS_194J, TDS_194H),
        presumptive=None,
        expense_heads=(
            "Subcontractor fees",
            "Software subscriptions",
            "Internet and telecom",
            "Home office costs",
            "Travel",
            "Equipment repair",
        ),
        capital_hint="Laptops and equipment above your capitalisation limit.",
        watch="44ADA is limited to notified professions. Confirm the work falls inside the list before opting in.",
    ),
    Profession(
        key="trader_wholesale",
        label="Wholesale trader",
        group="Trading and manufacturing",
        summary="Buying and reselling goods in bulk.",
        gst=GST_MIXED,
        tds=(TDS_194C, TDS_194H, TDS_194I, TDS_194J),
        presumptive=P_44AD,
        expense_heads=(
            "Purchases",
            "Freight inward",
            "Godown rent",
            "Loading and unloading",
            "Sales commission",
            "Electricity",
        ),
        capital_hint="Racks, weighing scales, vehicles and warehouse equipment above your capitalisation limit.",
        watch="Purchases from unregistered suppliers and stock transfers are the usual completeness gaps.",
    ),
    Profession(
        key="trader_retail",
        label="Retail trader",
        group="Trading and manufacturing",
        summary="Retail shop, counter or showroom.",
        gst=GST_MIXED,
        tds=(TDS_194C, TDS_194H, TDS_194I),
        presumptive=P_44AD,
        expense_heads=(
            "Purchases",
            "Shop rent",
            "Staff salary",
            "Electricity",
            "Packing material",
            "Payment terminal charges",
        ),
        capital_hint="Shop fit-out, refrigeration and billing systems above your capitalisation limit.",
        watch="Daily cash sales are the hardest to evidence. Keep the day-book and terminal settlements together.",
    ),
    Profession(
        key="manufacturer",
        label="Manufacturer",
        group="Trading and manufacturing",
        summary="Making goods for sale.",
        gst=GST_MIXED,
        tds=(TDS_194C, TDS_194J, TDS_194I, TDS_194H),
        presumptive=P_44AD,
        expense_heads=(
            "Raw material",
            "Power and fuel",
            "Factory rent",
            "Wages",
            "Repairs and maintenance",
            "Job work charges",
        ),
        capital_hint="Plant, machinery and factory improvements above your capitalisation limit.",
        watch="Job work charges and factory wages are the common 194C lines. Check whether the worker is a contractor or an employee.",
    ),
    Profession(
        key="distributor",
        label="Distributor / dealer",
        group="Trading and manufacturing",
        summary="Distribution or dealership for a manufacturer or brand.",
        gst=GST_MIXED,
        tds=(TDS_194H, TDS_194C, TDS_194I),
        presumptive=P_44AD,
        expense_heads=(
            "Purchases",
            "Commission to sub-dealers",
            "Freight",
            "Warehousing",
            "Scheme and discount payouts",
            "Field staff salary",
        ),
        capital_hint="Delivery vehicles, warehouse equipment and IT above your capitalisation limit.",
        watch="Sub-dealer commission is the usual 194H line. Scheme discounts need a clear paper trail.",
    ),
    Profession(
        key="transporter",
        label="Transporter / goods carriage",
        group="Trading and manufacturing",
        summary="Goods carriage by road.",
        gst=GstRule(
            "taxable",
            "5% or 12%",
            "Goods transport agency service is 5% without input tax credit, or 12% with it. "
            "Reverse charge can apply when the recipient is a specified person.",
        ),
        tds=(TDS_194C, TDS_194I, TDS_194J),
        presumptive=P_44AE,
        expense_heads=(
            "Diesel and fuel",
            "Driver salary",
            "Tyres and repairs",
            "Vehicle insurance",
            "Permit and fitness",
            "Toll and route charges",
        ),
        capital_hint="Trucks, trailers and bodies above your capitalisation limit. 44AE is per vehicle, not a turnover test.",
        watch="44AE is capped at 10 goods vehicles. Track vehicle count and tonnage before applying it.",
    ),
    Profession(
        key="contractor",
        label="Works contractor",
        group="Trading and manufacturing",
        summary="Civil, electrical or other works contracts.",
        gst=GstRule(
            "taxable",
            "18%",
            "Works contracts are generally 18%. Immovable-property and government-contract rates can differ.",
        ),
        tds=(TDS_194C, TDS_194J, TDS_194I, TDS_194H),
        presumptive=P_44AD,
        expense_heads=(
            "Material at site",
            "Labour",
            "Subcontractor",
            "Equipment hire",
            "Site overheads",
            "Mobilisation and transport",
        ),
        capital_hint="Plant, machinery, scaffolding and site equipment above your capitalisation limit.",
        watch="Labour payments need a clear employee-versus-contractor call. That decides 194C and PF exposure.",
    ),
    Profession(
        key="ecommerce",
        label="E-commerce seller",
        group="Trading and manufacturing",
        summary="Selling goods or services through online marketplaces.",
        gst=GST_MIXED,
        tds=(TDS_194C, TDS_194H, TDS_194I),
        presumptive=P_44AD,
        expense_heads=(
            "Marketplace commission",
            "Shipping",
            "Packaging",
            "Returns and damages",
            "Advertising",
            "Warehousing",
        ),
        capital_hint="Stock handling equipment, computers and fit-out above your capitalisation limit.",
        watch="Marketplace statements net off fees, returns and ads. Reconcile gross sales before booking turnover.",
    ),
    Profession(
        key="commission_agent",
        label="Commission agent",
        group="Other",
        summary="Earning commission or brokerage on transactions.",
        gst=GST_18,
        tds=(TDS_194H, TDS_194J, TDS_194I),
        presumptive=P_44AD,
        expense_heads=(
            "Commission to sub-agents",
            "Lead generation",
            "Travel",
            "Telephone and internet",
            "Office rent",
            "Marketing",
        ),
        capital_hint="Office equipment and vehicles above your capitalisation limit.",
        watch="Commission received is turnover, not other income. Check whether GST applies on the full commission.",
    ),
    Profession(
        key="rental",
        label="Rent / property income",
        group="Other",
        summary="Letting residential or commercial property.",
        gst=GstRule(
            "mixed",
            "Exempt or 18%",
            "Letting a residential dwelling to an individual for personal use is exempt. "
            "Commercial letting and some serviced letting are taxable.",
        ),
        tds=(TDS_194H, TDS_194C, TDS_194J),
        presumptive=None,
        expense_heads=(
            "Repairs and maintenance",
            "Property tax",
            "Insurance",
            "Brokerage",
            "Society charges",
            "Utilities",
        ),
        capital_hint="Furniture, lifts, air conditioning and renovation above your capitalisation limit.",
        watch="TDS on rent received is deducted by the tenant. Check Form 26A for credits that never reached the bank.",
    ),
    Profession(
        key="restaurant",
        label="Restaurant / food service",
        group="Other",
        summary="Restaurant, cafe or catering business.",
        gst=GstRule(
            "taxable",
            "5% or 18%",
            "Restaurant service is 5% without input tax credit. Taking the 18% route restores credit but changes pricing.",
        ),
        tds=(TDS_194C, TDS_194I, TDS_194H, TDS_194J),
        presumptive=P_44AD,
        expense_heads=(
            "Food and beverage purchases",
            "Kitchen fuel",
            "Staff salary",
            "Premises rent",
            "Aggregator commission",
            "Crockery and cutlery",
        ),
        capital_hint="Kitchen equipment, refrigeration and interiors above your capitalisation limit.",
        watch="Aggregator statements net off commission and ads. Reconcile gross sales before booking turnover.",
    ),
    Profession(
        key="salaried",
        label="Salaried individual",
        group="Other",
        summary="Salary income, with no business or profession.",
        gst=GST_NONE,
        tds=(TDS_194I, TDS_194H, TDS_194J),
        presumptive=None,
        expense_heads=(
            "House rent",
            "Home loan interest",
            "Insurance premiums",
            "Children education",
            "Medical expenses",
            "Professional tax",
        ),
        capital_hint="Property, jewellery and vehicles are usually capital assets, not expenses.",
        watch="Salary TDS is deducted by the employer. Use Form 16 and Form 26A, not the bank statement, as the base.",
    ),
)


_PROFESSION_BY_KEY = {profession.key: profession for profession in PROFESSIONS}

GENERIC_PROFESSION = Profession(
    key=CUSTOM_KEY,
    label="Other profession",
    group="Other",
    summary="A profession that is not in the catalog.",
    gst=GstRule(
        "mixed",
        "Confirm",
        "The catalog has no preset for this work, so read each invoice and registration before deciding the rate.",
    ),
    tds=(TDS_194J, TDS_194C, TDS_194H, TDS_194I),
    presumptive=None,
    expense_heads=(
        "Purchases and direct costs",
        "Staff salary",
        "Rent",
        "Professional fees",
        "Travel",
        "Software and subscriptions",
    ),
    capital_hint="Set a capitalisation limit for this client and apply it consistently.",
    watch="Custom profile. Treat the notes as a generic checklist and confirm each one against the client's facts.",
)


def _safe_json(data: Any) -> dict:
    if isinstance(data, Mapping):
        return dict(data)
    if isinstance(data, str) and data.strip():
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _text(value: Any, *, limit: int = 0) -> str:
    cleaned = str(value or "").strip()
    if limit:
        cleaned = cleaned[:limit]
    return cleaned


def _tri_state(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"yes", "true", "1", "registered", "y"}:
        return True
    if text in {"no", "false", "0", "unregistered", "not_registered", "not registered", "n"}:
        return False
    raise ValueError("Say whether the client is registered for GST.")


def _banks(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;/\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        parts = list(value)
    else:
        raise ValueError("List the banks as names.")
    seen: list[str] = []
    for part in parts:
        name = _text(part, limit=40)
        if name and name.lower() not in {item.lower() for item in seen}:
            seen.append(name)
    return seen[:10]


def normalize_profile(raw: Any) -> dict:
    """Validate a profile coming from the UI or the database.

    Core fields live in their own columns; ``books``, ``banks``, ``broker`` and
    ``notes`` live in ``profile_json``. This function always returns all of them
    so callers do not have to care where they are stored.
    """
    data = _safe_json(raw)

    key = _text(data.get("profession_key"), limit=60)
    label = _text(data.get("profession_label"), limit=120)
    if not key and label:
        key = CUSTOM_KEY
    if key and key != CUSTOM_KEY and key not in _PROFESSION_BY_KEY:
        raise ValueError("That profession is not in the list.")
    if key == CUSTOM_KEY:
        if not label:
            raise ValueError("Describe the profession for a custom profile.")
    elif key:
        label = _PROFESSION_BY_KEY[key].label
    else:
        label = ""

    entity = _text(data.get("entity_type"), limit=40)
    if entity and entity not in ENTITY_LABELS:
        raise ValueError("Choose a valid entity type.")

    return {
        "profession_key": key,
        "profession_label": label,
        "entity_type": entity,
        "gst_registered": _tri_state(data.get("gst_registered")),
        "books": _text(data.get("books"), limit=40),
        "banks": _banks(data.get("banks")),
        "broker": _text(data.get("broker"), limit=60),
        "notes": _text(data.get("notes"), limit=500),
    }


CORE_FIELDS = ("profession_key", "profession_label", "entity_type", "gst_registered")
EXTRA_FIELDS = ("books", "banks", "broker", "notes")


def _field(client: Any, name: str, default: Any = None) -> Any:
    if isinstance(client, Mapping):
        return client.get(name, default)
    return getattr(client, name, default)


def _public_profession(profession: Profession, *, custom: bool = False) -> dict:
    return {
        "key": profession.key,
        "label": profession.label,
        "group": profession.group,
        "summary": profession.summary,
        "custom": custom,
        "gst": {
            "status": profession.gst.status,
            "typical_rate": profession.gst.typical_rate,
            "note": profession.gst.note,
        },
        "tds": [
            {
                "code": rule.code,
                "label": rule.label,
                "keywords": list(rule.keywords),
                "threshold": rule.threshold,
                "annual_threshold": rule.annual_threshold,
                "threshold_basis": rule.threshold_basis,
                "monthly": rule.monthly,
                "rate": rule.rate,
                "law_ref": rule.law_ref,
            }
            for rule in profession.tds
        ],
        "presumptive": (
            {
                "section": profession.presumptive.section,
                "label": profession.presumptive.label,
                "limit": profession.presumptive.limit,
                "enhanced_limit": profession.presumptive.enhanced_limit,
                "cash_condition": profession.presumptive.cash_condition,
                "profit_note": profession.presumptive.profit_note,
            }
            if profession.presumptive
            else None
        ),
        "expense_heads": list(profession.expense_heads),
        "capital_hint": profession.capital_hint,
        "watch": profession.watch,
    }


def resolve_profile(client: Any) -> dict:
    """Return the stored profile plus the rule pack that applies to it.

    Never raises: a hand-edited or legacy row should not break the desk.
    """
    stored = {
        "profession_key": _field(client, "profession_key", "") or "",
        "profession_label": _field(client, "profession_label", "") or "",
        "entity_type": _field(client, "entity_type", "") or "",
        "gst_registered": _field(client, "gst_registered", None),
    }
    extras = _safe_json(_field(client, "profile_json", "{}"))
    for name in EXTRA_FIELDS:
        stored[name] = extras.get(name)

    try:
        profile = normalize_profile(stored)
    except ValueError:
        profile = normalize_profile({})

    key = profile["profession_key"]
    custom = key == CUSTOM_KEY
    profession = _PROFESSION_BY_KEY.get(key) or GENERIC_PROFESSION
    if custom:
        profession = GENERIC_PROFESSION

    entity = profile["entity_type"]
    entity_label = ENTITY_LABELS.get(entity, "")
    if profile["gst_registered"] is True:
        gst_label = "GST registered"
    elif profile["gst_registered"] is False:
        gst_label = "Not GST registered"
    else:
        gst_label = "GST status not set"

    display_label = profile["profession_label"] or (profession.label if key else "")
    is_set = bool(key or entity or profile["gst_registered"] is not None)
    if is_set:
        parts = [part for part in (display_label, entity_label, gst_label) if part]
        summary = " · ".join(parts)
    else:
        summary = "No profile set"
    rule_pack = _public_profession(profession, custom=custom)
    if custom and profile["profession_label"]:
        rule_pack["label"] = profile["profession_label"]

    return {
        "is_set": is_set,
        "profession_key": key,
        "profession_label": display_label,
        "profession_group": profession.group,
        "entity_type": entity,
        "entity_type_label": entity_label,
        "gst_registered": profile["gst_registered"],
        "gstin": _text(_field(client, "gstin", ""), limit=15),
        "summary": summary,
        "details": {name: profile[name] for name in EXTRA_FIELDS},
        "rules": rule_pack,
        "custom": custom,
        "as_of": RULES_AS_OF,
        "disclaimer": RULES_DISCLAIMER,
    }


def presumptive_allowed(entity_type: str) -> bool:
    """44AD, 44ADA and 44AE are open to individuals, HUF and firms, not LLPs or companies."""
    if not entity_type:
        return True
    return entity_type in _PRESUMPTIVE_ENTITIES


def profession_options() -> list[dict]:
    return [
        {
            "key": profession.key,
            "label": profession.label,
            "group": profession.group,
            "summary": profession.summary,
        }
        for profession in PROFESSIONS
    ]


def entity_type_options() -> list[dict]:
    return [{"key": key, "label": label} for key, label in ENTITY_TYPES]


def profile_options() -> dict:
    return {
        "professions": profession_options(),
        "entity_types": entity_type_options(),
        "as_of": RULES_AS_OF,
        "disclaimer": RULES_DISCLAIMER,
    }
