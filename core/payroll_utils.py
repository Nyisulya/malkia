"""Statutory payroll calculations matching the company's payroll sheet.

Employee deductions: NSSF 10% of gross, then PAYE on (gross - NSSF) using TRA
monthly brackets. WCF 0.5% and SDL 3.5% are EMPLOYER costs — recorded on the
salary row but never deducted from the employee's net pay.
"""
from decimal import Decimal, ROUND_HALF_UP

PAYE_BRACKETS = [
    (Decimal('270000'), Decimal('0')),
    (Decimal('520000'), Decimal('0.08')),
    (Decimal('760000'), Decimal('0.20')),
    (Decimal('1000000'), Decimal('0.25')),
    (None, Decimal('0.30')),
]

NSSF_RATE = Decimal('0.10')
WCF_RATE = Decimal('0.005')
SDL_RATE = Decimal('0.035')


def _round2(value):
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def compute_paye(taxable):
    taxable = Decimal(taxable or 0)
    tax = Decimal('0')
    lower = Decimal('0')
    for upper, rate in PAYE_BRACKETS:
        if upper is None:
            if taxable > lower:
                tax += (taxable - lower) * rate
            break
        if taxable > lower:
            tax += (min(taxable, upper) - lower) * rate
            lower = upper
        else:
            break
    return _round2(tax)


def compute_statutory(gross):
    gross = Decimal(gross or 0)
    nssf = _round2(gross * NSSF_RATE)
    taxable = gross - nssf
    paye = compute_paye(taxable)
    wcf = _round2(gross * WCF_RATE)
    sdl = _round2(gross * SDL_RATE)
    return paye, nssf, wcf, sdl
