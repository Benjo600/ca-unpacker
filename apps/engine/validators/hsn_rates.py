"""Advisory HSN/SAC -> GST rate check.

Why this exists
---------------
A wrong rate charged against the right code (or the right rate against the
wrong code) is the most common way a GST notice starts. ``hsn_flags()`` in
``gstin.py`` only checks that a code has a plausible number of digits; this
module adds the other half of the check: does the rate printed on the document
look like the rate that code normally carries?

This check is ADVISORY ONLY. It returns a flag for the pack's Flags column and
must never block, reject or rewrite a pack, a parsed row, or an amount.

Sources and attribution
-----------------------
The seed table below is a hand-curated subset of the published CBIC GST rate
schedules (Schedule I-V of Notification No. 1/2017-Central Tax (Rate) as
amended, including the two-slab rationalisation effective September 2025). The
code -> rate mapping was informed in part by the HSN/SAC rate data published by
the MIT-licensed "Free GST Billing Software" project. No source code was
copied; only the publicly published classification -> rate mapping is
represented here, and every label is our own wording.

Rates move by notification. A flagged row means "worth a second look", never
"wrong". Update the table when the schedules change; keep the tolerance at
half a percentage point so a rounded printed rate is not flagged.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

FLAG = "hsn_rate_suspect"
# Percentage points of slack before a charged rate is called suspect. A rate
# printed as 18 against an expected 18 must never flag, and neither should 17.6.
TOLERANCE = 0.5

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_WHOLE_NUMBER_RE = re.compile(r"^(\d+)\.0+$")

# Goods: 4-digit headings for the broad categories a CA actually sees, plus a
# handful of 6-digit codes where a heading alone is too coarse.
GOODS_RATES: dict[str, tuple[int, str]] = {
    # --- food, grocery, agricultural ---
    "0401": (0, "Fresh milk and cream"),
    "0402": (5, "Milk powder and other milk solids"),
    "0405": (5, "Butter, ghee and butter oil"),
    "0701": (0, "Fresh potatoes"),
    "0703": (0, "Fresh onions, garlic and leeks"),
    "0713": (0, "Dried pulses and leguminous vegetables"),
    "0901": (5, "Coffee, roasted and ground"),
    "0902": (5, "Tea, whether or not flavoured"),
    "1001": (0, "Wheat and meslin"),
    "1006": (0, "Rice, non-branded"),
    "1101": (0, "Wheat or meslin flour (atta)"),
    "1206": (0, "Sunflower seeds"),
    "1507": (5, "Soya-bean oil, edible"),
    "1511": (5, "Palm oil, edible"),
    "1512": (5, "Sunflower and safflower oil"),
    "1701": (5, "Cane or beet sugar"),
    "1806": (18, "Chocolate and cocoa preparations"),
    "1905": (5, "Bread, biscuits, rusks and pastry"),
    "2009": (5, "Fruit and vegetable juices"),
    "2105": (18, "Ice cream and edible ice"),
    "2202": (40, "Aerated waters with added sugar"),
    "220299": (5, "Other non-alcoholic beverages"),
    "2402": (40, "Cigarettes, cigars and cigarillos"),
    "2403": (40, "Other manufactured tobacco"),
    # --- construction materials and building hardware ---
    "2505": (5, "Natural sands of all kinds"),
    "2523": (18, "Portland cement and aluminous cement"),
    "3208": (18, "Paints and varnishes, polymer based"),
    "3209": (18, "Paints and varnishes, aqueous medium"),
    "3215": (18, "Printing ink"),
    "6904": (5, "Ceramic building bricks and blocks"),
    "6907": (18, "Unglazed ceramic tiles and flags"),
    "6908": (18, "Glazed ceramic tiles"),
    "7005": (18, "Float glass and surface ground glass"),
    "7210": (18, "Flat-rolled iron or steel, coated"),
    "7214": (18, "Iron or steel bars and rods"),
    "7219": (18, "Flat-rolled stainless steel"),
    "7308": (18, "Structures and parts of iron or steel"),
    "7318": (18, "Screws, bolts, nuts and washers"),
    "7601": (18, "Unwrought aluminium"),
    # --- chemicals, fertilisers, pharma ---
    "2710": (18, "Lubricating oils and greases"),
    "3004": (5, "Medicaments, formulated doses"),
    "3102": (5, "Nitrogenous mineral fertilisers"),
    "3105": (5, "Mineral fertilisers in packs"),
    "3204": (18, "Synthetic organic dyes and pigments"),
    "3401": (5, "Soap and organic surface-active products"),
    "3808": (18, "Insecticides, fungicides and herbicides"),
    # --- plastics and rubber ---
    "3901": (18, "Polymers of ethylene, primary forms"),
    "3917": (18, "Plastic tubes, pipes and fittings"),
    "3920": (18, "Plastic sheets, film and foil"),
    "3923": (18, "Plastic packing articles and containers"),
    "3924": (18, "Plastic household and tableware"),
    "3926": (18, "Other articles of plastics"),
    "4011": (18, "New pneumatic tyres of rubber"),
    # --- wood, paper, printing ---
    "4411": (18, "Fibreboard and MDF of wood"),
    "4412": (18, "Plywood and veneered wood panels"),
    "4418": (18, "Builders' joinery and carpentry of wood"),
    "4801": (5, "Newsprint, in rolls or sheets"),
    "4802": (5, "Uncoated writing and printing paper"),
    "4819": (18, "Cartons, boxes and paper packing"),
    "4820": (5, "Registers, account books and note books"),
    "4901": (0, "Printed books, brochures and leaflets"),
    "4902": (0, "Newspapers and periodicals"),
    # --- textiles, apparel, footwear, stationery ---
    "5208": (5, "Woven cotton fabrics"),
    "5211": (5, "Woven cotton fabrics, mixed"),
    "5407": (5, "Woven fabrics of synthetic filament yarn"),
    "5515": (5, "Woven fabrics of synthetic staple fibres"),
    "6109": (5, "T-shirts and vests, knitted (MRP up to 2,500)"),
    "6110": (5, "Jerseys and pullovers, knitted (MRP up to 2,500)"),
    "6203": (18, "Men's suits and trousers (MRP above 2,500)"),
    "6205": (5, "Men's shirts (MRP up to 2,500)"),
    "6302": (5, "Bed linen, table linen and towels"),
    "6403": (5, "Footwear, leather uppers (MRP up to 2,500)"),
    "6404": (5, "Footwear, textile uppers (MRP up to 2,500)"),
    "9608": (5, "Ball pens, pens, pencils and refills"),
    # --- machinery, IT, electrical ---
    "8207": (18, "Interchangeable tools for hand tools"),
    "8302": (18, "Base metal fittings for furniture and doors"),
    "8413": (18, "Pumps for liquids and liquid elevators"),
    "8414": (18, "Air pumps, compressors and fans"),
    "8418": (18, "Refrigerators, freezers and heat pumps"),
    "8421": (18, "Filtering and purifying machinery"),
    "8422": (18, "Dishwashing and packing machinery"),
    "8443": (18, "Printers, copiers and multifunction machines"),
    "8471": (18, "Computers, laptops and servers"),
    "847130": (18, "Portable computers and tablets"),
    "8473": (18, "Parts and accessories of computers"),
    "8481": (18, "Taps, cocks, valves and regulators"),
    "8482": (18, "Ball and roller bearings"),
    "848340": (18, "Gears, gearing and gear boxes"),
    "848390": (18, "Parts of gearing and transmission shafts"),
    "8504": (18, "Transformers, converters and chargers"),
    "8507": (18, "Electric accumulators and batteries"),
    "8517": (18, "Telephones, smartphones and network gear"),
    "8536": (18, "Switches, plugs and sockets up to 1,000 V"),
    "8544": (18, "Insulated wire, cable and conductors"),
    # --- vehicles and parts ---
    "8708": (18, "Parts and accessories of motor vehicles"),
    # --- furniture and lighting ---
    "9401": (18, "Seats and parts thereof"),
    "9403": (18, "Other furniture and parts"),
    "9405": (18, "Lamps, light fittings and parts"),
}

# Services (SAC): the codes that show up on a service provider's invoices.
SAC_RATES: dict[str, tuple[int, str]] = {
    "9954": (18, "Construction services (works contract)"),
    "996311": (5, "Hotel accommodation, tariff up to 7,500"),
    "996331": (5, "Restaurant services, without input credit"),
    "996335": (18, "Restaurant services in hotel, tariff above 7,500"),
    "996421": (5, "Air travel, economy class, domestic"),
    "996511": (5, "Road transport of goods (GTA, forward charge)"),
    "996512": (5, "Rail transport of goods"),
    "996812": (18, "Courier services, other than postal"),
    "997119": (18, "Financial and related services"),
    "997212": (18, "Rental of commercial and industrial property"),
    "997311": (18, "Legal services"),
    "997312": (18, "Accounting, audit and bookkeeping services"),
    "997313": (18, "Tax consultancy services"),
    "997314": (18, "Leasing of machinery and equipment, no operator"),
    "997331": (18, "Management consulting services"),
    "998311": (18, "Business advisory and consulting services"),
    "998313": (18, "IT consulting and support services"),
    "998314": (18, "IT design and development services"),
    "998315": (18, "IT infrastructure and hosting services"),
    "998361": (18, "Advertising and market research services"),
    "998541": (18, "Security services"),
    "998596": (18, "Event management services"),
    "998714": (18, "Maintenance and repair of machinery"),
    "998716": (18, "Maintenance and repair of computers"),
    "9988": (18, "Manufacturing services on physical inputs (job work)"),
    "9992": (0, "Education services of exempt institutions"),
    "9993": (0, "Health care services"),
}

RATES: dict[str, tuple[int, str]] = {**GOODS_RATES, **SAC_RATES}

# Headings whose rate legitimately depends on something we cannot see on the
# row — apparel and footwear by MRP band, hotels and restaurants by tariff.
# Both bands are correct, so both are accepted; picking one would accuse a
# perfectly good invoice on every row from the other band.
DUAL_RATES: dict[str, tuple[int, ...]] = {
    "6109": (5, 18),
    "6110": (5, 18),
    "6203": (5, 18),
    "6204": (5, 18),
    "6205": (5, 18),
    "6206": (5, 18),
    "6403": (5, 18),
    "6404": (5, 18),
    "996311": (5, 18),
    "996331": (5, 18),
    "996335": (5, 18),
}


def _accepted_for(key: str) -> tuple[int, ...] | None:
    dual = DUAL_RATES.get(key)
    if dual is not None:
        return dual
    entry = RATES.get(key)
    if entry is not None:
        return (entry[0],)
    return None


def accepted_rates(hsn: Any) -> tuple[int, ...]:
    """Every rate that is legitimate for *hsn*, or () when the code is unknown."""
    try:
        digits = _digits(hsn)
    except Exception:
        return ()
    if len(digits) < 4:
        return ()
    if len(digits) >= 6:
        exact = _accepted_for(digits[:6])
        if exact is not None:
            return exact
    heading = _accepted_for(digits[:4])
    if heading is not None:
        return heading
    prefix = _prefix_rate(digits[:4])
    return (prefix,) if prefix is not None else ()


def expected_rate(hsn: Any) -> int | None:
    """Return the standard GST rate for *hsn*, or None when the code is unknown.

    Lookup order: 6-digit exact, then 4-digit heading exact, then a 4-digit
    prefix scan over longer codes (used when only 6-digit codes are curated for
    that heading). Ambiguous prefixes return None rather than a guess.
    """
    try:
        digits = _digits(hsn)
    except Exception:
        return None
    if len(digits) < 4:
        return None
    if len(digits) >= 6:
        exact = RATES.get(digits[:6])
        if exact is not None:
            return exact[0]
    heading = RATES.get(digits[:4])
    if heading is not None:
        return heading[0]
    return _prefix_rate(digits[:4])


def rate_flags(hsn: Any, charged_rate: Any) -> list[str]:
    """Flag a charged rate that does not match the rate expected for *hsn*.

    Returns ``["hsn_rate_suspect"]`` when the charged rate is more than
    ``TOLERANCE`` percentage points away from EVERY rate that is legitimate for
    the code. Codes whose rate depends on value or description accept both
    bands (see ``DUAL_RATES``), so a correct invoice is never accused. Unknown
    codes, unreadable rates and a missing rate all return an empty list. Never
    raises.
    """
    try:
        rate = _number(charged_rate)
        accepted = accepted_rates(hsn)
    except Exception:
        return []
    if rate is None or not accepted:
        return []
    if all(abs(rate - value) > TOLERANCE for value in accepted):
        return [FLAG]
    return []


def derive_charged_rate(taxable: Any, tax: Any) -> float | None:
    """Rate implied by a tax amount over a taxable value, as a percentage."""
    taxable_value = _number(taxable)
    tax_value = _number(tax)
    if taxable_value is None or tax_value is None or taxable_value <= 0:
        return None
    return tax_value / taxable_value * 100.0


def hsn_rate_flags(
    hsn: Any,
    *,
    taxable: Any = None,
    tax: Any = None,
    tax_percent: Any = None,
) -> list[str]:
    """Convenience wrapper for parsers: prefer a source percent, else derive it."""
    rate = _number(tax_percent)
    if rate is None:
        rate = derive_charged_rate(taxable, tax)
    return rate_flags(hsn, rate)


def _prefix_rate(prefix: str) -> int | None:
    rates = {
        rate
        for code, (rate, _label) in RATES.items()
        if len(code) > len(prefix) and code.startswith(prefix)
    }
    if len(rates) == 1:
        return rates.pop()
    return None


def _digits(hsn: Any) -> str:
    if hsn is None:
        return ""
    text = str(hsn).strip()
    if not text:
        return ""
    # "1006.0" arrives when a spreadsheet hands the cell over as a float.
    whole = _WHOLE_NUMBER_RE.match(text)
    if whole:
        text = whole.group(1)
    return re.sub(r"\D", "", text)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
    elif isinstance(value, str):
        text = value.replace(",", "").replace("%", "").replace("₹", "").strip()
        if not text:
            return None
        match = _NUMBER_RE.search(text)
        if not match:
            return None
        try:
            number = float(match.group(0))
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number
