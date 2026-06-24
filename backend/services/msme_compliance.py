from datetime import datetime
from typing import Dict, Any, Optional

BANK_RATE = 0.0675  # 6.75% base rate
INTEREST_RATE = 3 * BANK_RATE  # 20.25% compounded monthly per Section 16

def calculate_43bh_compliance(
    invoice_date_str: str,
    payment_date_str: Optional[str],
    enterprise_type: str,
    has_agreement: bool,
    amount: float
) -> Dict[str, Any]:
    """
    Computes Section 43B(h) Income Tax disallowances and MSMED Act Section 16 interest penalties.
    
    Parameters:
      - invoice_date_str: Invoice date (YYYY-MM-DD)
      - payment_date_str: Payment date (YYYY-MM-DD), or None if unpaid
      - enterprise_type: Classification (MICRO, SMALL, MEDIUM, LARGE, UNKNOWN)
      - has_agreement: Toggle for written billing agreement (influences 15 vs 45 days limit)
      - amount: Principal invoice ledger value
    """
    # 1. Parse dates
    try:
        inv_date = datetime.strptime(invoice_date_str.strip(), "%Y-%m-%d")
    except ValueError:
        # Fallback if bad format
        inv_date = datetime.today()
        
    if payment_date_str and payment_date_str.strip():
        try:
            pay_date = datetime.strptime(payment_date_str.strip(), "%Y-%m-%d")
            is_unpaid = False
        except ValueError:
            pay_date = datetime.today()
            is_unpaid = True
    else:
        pay_date = datetime.today()
        is_unpaid = True
        
    # 2. Calculate calendar days elapsed
    delta = pay_date - inv_date
    days_elapsed = max(0, delta.days)
    
    # 3. Determine statutory limit days
    # 45 days if written agreement, 15 days if no agreement
    limit_days = 45 if has_agreement else 15
    delay_days = max(0, days_elapsed - limit_days)
    
    # 4. Check eligibility
    # Section 43B(h) and MSMED Section 16 apply ONLY to MICRO and SMALL enterprises
    enterprise_type_upper = enterprise_type.upper().strip()
    is_eligible_msme = enterprise_type_upper in ["MICRO", "SMALL"]
    
    is_delayed = delay_days > 0
    
    # 5. Compute Income Tax Disallowance
    # Purchases from Micro & Small are disallowed if delayed beyond the limit (15/45 days)
    disallowed_amount = amount if (is_eligible_msme and is_delayed) else 0.0
    
    # 6. Compute Section 16 Interest Penalty
    # Compound interest at three times bank rate, compounded monthly on delay days
    interest_penalty = 0.0
    if is_eligible_msme and is_delayed:
        # A = P * (1 + r/12) ^ n
        # n = days elapsed / 30.417 (fractional months)
        P = amount
        r = INTEREST_RATE
        n = days_elapsed / 30.417
        compounded_total = P * ((1 + r / 12) ** n)
        interest_penalty = max(0.0, compounded_total - P)
        
    return {
        "days_elapsed": days_elapsed,
        "limit_days": limit_days,
        "delay_days": delay_days,
        "is_delayed": is_delayed,
        "is_eligible_msme": is_eligible_msme,
        "disallowed_amount": float(round(disallowed_amount, 2)),
        "interest_penalty": float(round(interest_penalty, 2)),
        "is_unpaid": is_unpaid
    }
