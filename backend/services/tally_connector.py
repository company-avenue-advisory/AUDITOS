"""
tally_connector.py — TallyPrime XML-over-HTTP connector for AuditOS.

Connects to TallyPrime's built-in HTTP server (default port 9000) over LAN.
Pure read operations first (company info, ledgers, vouchers); write (push
approved vouchers) is gated behind Auditor_Approved and built separately.

TallyPrime exposes an XML-over-HTTP interface:
  POST http://<host>:9000  with Content-Type: text/xml
  Body is a TDL (Tally Definition Language) XML request.
  Response is XML.

This connector handles:
  1. Connection test (license info / server status)
  2. List companies
  3. Pull chart of accounts (ledgers + groups)
  4. Pull vouchers (Sales / Purchase) for a date range
  5. Map vouchers to AuditOS canonical schema
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_PORT = 9000
TIMEOUT_SECONDS = 15


@dataclass
class TallyConfig:
    host: str
    port: int = DEFAULT_PORT
    company: Optional[str] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class TallyLedger:
    name: str
    parent: str
    gstin: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    opening_balance: float = 0.0


@dataclass
class TallyPushResult:
    success: bool
    created: int = 0
    exceptions: int = 0
    error: Optional[str] = None


@dataclass
class TallyVoucher:
    number: str
    date: str
    voucher_type: str
    party_name: str
    party_gstin: Optional[str] = None
    place_of_supply: Optional[str] = None
    narration: Optional[str] = None
    invoice_no: Optional[str] = None
    line_items: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# XML request templates (TDL)
# ---------------------------------------------------------------------------

_XML_HEADER = '<?xml version="1.0" encoding="utf-8"?>'

_LICENSE_INFO_REQ = f"""{_XML_HEADER}
<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>LicenseInfo</ID></HEADER>
  <BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES></DESC></BODY>
</ENVELOPE>"""

_LIST_COMPANIES_REQ = f"""{_XML_HEADER}
<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CompanyCollection</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="CompanyCollection" ISMODIFY="No">
            <TYPE>Company</TYPE>
            <FETCH>Name, FormalName</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""


def _ledger_request(company: str) -> str:
    return f"""{_XML_HEADER}
<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>LedgerCollection</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="LedgerCollection" ISMODIFY="No">
            <TYPE>Ledger</TYPE>
            <FETCH>Name, Parent, LedgerGSTRegistrationNumber, Address, LedgerStateName, OpeningBalance</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""


def _voucher_request(company: str, voucher_type: str, from_date: str, to_date: str) -> str:
    """Voucher export request. Dates in Tally format: YYYYMMDD."""
    return f"""{_XML_HEADER}
<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>VoucherCollection</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
        <SVFROMDATE>{from_date}</SVFROMDATE>
        <SVTODATE>{to_date}</SVTODATE>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="VoucherCollection" ISMODIFY="No">
            <TYPE>Voucher</TYPE>
            <CHILDOF>{voucher_type}</CHILDOF>
            <FETCH>VoucherNumber, Date, VoucherTypeName, PartyLedgerName, BasicPartyGSTIN, PlaceOfSupply, Narration, Reference, AllInventoryEntries.StockItemName, AllInventoryEntries.Rate, AllInventoryEntries.Amount, AllInventoryEntries.BilledQty, AllLedgerEntries.LedgerName, AllLedgerEntries.Amount, AllLedgerEntries.IsPartyLedger</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""


def _create_ledger_request(
    company: str,
    name: str,
    parent: str,
    gstin: Optional[str] = None,
    state: Optional[str] = None,
) -> str:
    """Ledger creation XML — confirmed working format (tested live: CGST/SGST/
    IGST + party ledger all created successfully with this shape)."""
    gstin_tag = f"<PARTYGSTIN>{_escape_xml(gstin)}</PARTYGSTIN>" if gstin else ""
    state_tag = f"<LEDGERSTATENAME>{_escape_xml(state)}</LEDGERSTATENAME>" if state else ""
    reg_type_tag = "<GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>" if gstin else ""
    return f"""{_XML_HEADER}
<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY>
    <DESC><STATICVARIABLES><SVCURRENTCOMPANY>{_escape_xml(company)}</SVCURRENTCOMPANY></STATICVARIABLES></DESC>
    <DATA>
      <TALLYMESSAGE>
        <LEDGER NAME="{_escape_xml(name)}" ACTION="Create">
          <NAME>{_escape_xml(name)}</NAME>
          <PARENT>{_escape_xml(parent)}</PARENT>
          {gstin_tag}
          {state_tag}
          {reg_type_tag}
        </LEDGER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _escape_xml(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _push_voucher_request(
    company: str,
    voucher_type: str,
    date: str,
    party_ledger: str,
    party_amount: float,
    credit_entries: List[Dict[str, Any]],
    narration: str = "",
    voucher_number: Optional[str] = None,
    reverse: bool = False,
) -> str:
    """Voucher import XML — confirmed working format (tested live against
    TallyPrime 2026-07-17): TALLYREQUEST=Import, ID=All Masters, plain
    ALLLEDGERENTRIES.LIST entries (no OLDAUDITENTRYIDS/inventory needed for
    a ledger-only sales/purchase voucher).

    credit_entries: list of {"ledger": str, "amount": float} — Sales/Purchase
    Account + CGST/SGST/IGST lines. Amounts are positive; the party entry is
    booked as the balancing negative (ISDEEMEDPOSITIVE=Yes) leg.

    reverse=True (Credit Note / Debit Note): every leg's sign is flipped
    relative to the Sales/Purchase case — a Credit Note is the exact
    accounting reversal of a Sale (same for Debit Note vs Purchase), so
    negating a balanced double-entry (sum=0) produces the correct reversed
    entry regardless of Tally's internal ISDEEMEDPOSITIVE sign convention.
    NOTE: this has not been live-tested against TallyPrime yet (only Sales/
    Purchase were) — verify against a real Credit Note before relying on it
    for a client's books; see feedback-extraction-debugging in memory.
    """
    sign = -1 if reverse else 1
    voucher_num_tag = f"<VOUCHERNUMBER>{_escape_xml(voucher_number)}</VOUCHERNUMBER>" if voucher_number else ""
    credit_xml = "".join(
        f"<ALLLEDGERENTRIES.LIST>"
        f"<LEDGERNAME>{_escape_xml(e['ledger'])}</LEDGERNAME>"
        f"<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        f"<AMOUNT>{sign * e['amount']:.2f}</AMOUNT>"
        f"</ALLLEDGERENTRIES.LIST>"
        for e in credit_entries
    )
    return f"""{_XML_HEADER}
<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY>
    <DESC><STATICVARIABLES><SVCURRENTCOMPANY>{_escape_xml(company)}</SVCURRENTCOMPANY></STATICVARIABLES></DESC>
    <DATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER VCHTYPE="{_escape_xml(voucher_type)}" ACTION="Create" OBJVIEW="Accounting Voucher View">
          <DATE>{date}</DATE>
          <NARRATION>{_escape_xml(narration)}</NARRATION>
          <VOUCHERTYPENAME>{_escape_xml(voucher_type)}</VOUCHERTYPENAME>
          {voucher_num_tag}
          <PARTYLEDGERNAME>{_escape_xml(party_ledger)}</PARTYLEDGERNAME>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>{_escape_xml(party_ledger)}</LEDGERNAME>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
            <AMOUNT>{sign * -abs(party_amount):.2f}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          {credit_xml}
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _day_book_request(company: str, from_date: str, to_date: str) -> str:
    """Day Book export — pulls ALL voucher types for a date range."""
    return f"""{_XML_HEADER}
<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Object</TYPE><ID>Day Book</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
        <SVFROMDATE>{from_date}</SVFROMDATE>
        <SVTODATE>{to_date}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""


# ---------------------------------------------------------------------------
# Core transport
# ---------------------------------------------------------------------------

class TallyConnectionError(Exception):
    pass


class TallyConnector:
    """Stateless connector — each call is one HTTP POST → XML response."""

    def __init__(self, config: TallyConfig):
        self.config = config

    def _post(self, xml_body: str) -> ET.Element:
        req = Request(
            self.config.url,
            data=xml_body.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        try:
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                raw = resp.read()
        except URLError as e:
            raise TallyConnectionError(
                f"Cannot reach TallyPrime at {self.config.url}. "
                f"Is TallyPrime running as Server on that machine? Error: {e}"
            ) from e
        except Exception as e:
            raise TallyConnectionError(f"Tally HTTP error: {e}") from e

        try:
            return ET.fromstring(raw)
        except ET.ParseError as e:
            logger.error(f"Tally returned non-XML: {raw[:500]}")
            raise TallyConnectionError(f"Invalid XML from Tally: {e}") from e

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test_connection(self) -> Dict[str, str]:
        """Ping Tally and return license/server info. Safest first call."""
        root = self._post(_LICENSE_INFO_REQ)
        info = {}
        for tag in ("SERIALNUMBER", "ACCOUNTID", "ADMINMAILID",
                     "ISSILVER", "ISGOLD", "ISADMIN", "PLANNAME"):
            el = root.find(f".//{tag}")
            if el is not None and el.text:
                info[tag.lower()] = el.text
        if not info:
            info["raw_tags"] = [el.tag for el in root.iter()][:20]
        return info

    def list_companies(self) -> List[Dict[str, str]]:
        """List all companies loaded in TallyPrime."""
        root = self._post(_LIST_COMPANIES_REQ)
        companies = []
        for comp in root.iter("COMPANY"):
            name = _text(comp, "NAME") or _text(comp, "FORMALNAME")
            if name:
                companies.append({
                    "name": name,
                    "formal_name": _text(comp, "FORMALNAME") or name,
                })
        if not companies:
            for comp in root.iter("COLLECTION"):
                for child in comp:
                    name = child.text or child.get("NAME")
                    if name:
                        companies.append({"name": name, "formal_name": name})
        return companies

    def get_ledgers(self, company: Optional[str] = None) -> List[TallyLedger]:
        """Pull the full chart of accounts (ledger master)."""
        company = company or self.config.company
        if not company:
            raise ValueError("No company specified — call list_companies() first or set config.company")
        root = self._post(_ledger_request(company))
        ledgers = []
        for ldg in root.iter("LEDGER"):
            name = _text(ldg, "NAME") or ldg.get("NAME", "")
            ledgers.append(TallyLedger(
                name=name,
                parent=_text(ldg, "PARENT") or "",
                gstin=_text(ldg, "LEDGERGSTREGISTRATIONNUMBER"),
                address=_text(ldg, "ADDRESS"),
                state=_text(ldg, "LEDGERSTATENAME"),
                opening_balance=_float(ldg, "OPENINGBALANCE"),
            ))
        return ledgers

    def get_vouchers(
        self,
        voucher_type: str,
        from_date: str,
        to_date: str,
        company: Optional[str] = None,
    ) -> List[TallyVoucher]:
        """Pull vouchers of a given type within a date range.

        Args:
            voucher_type: "Sales", "Purchase", "Credit Note", "Debit Note", etc.
            from_date: "YYYY-MM-DD" (converted to Tally's YYYYMMDD internally)
            to_date:   "YYYY-MM-DD"
        """
        company = company or self.config.company
        if not company:
            raise ValueError("No company specified")
        tally_from = from_date.replace("-", "")
        tally_to = to_date.replace("-", "")

        root = self._post(_voucher_request(company, voucher_type, tally_from, tally_to))
        return self._parse_vouchers(root, voucher_type)

    def ledger_exists(self, name: str, company: Optional[str] = None) -> bool:
        """Check whether a ledger name already exists in Tally (case-insensitive)."""
        company = company or self.config.company
        existing = {l.name.strip().lower() for l in self.get_ledgers(company)}
        return name.strip().lower() in existing

    def ensure_party_ledger(
        self,
        name: str,
        gstin: Optional[str] = None,
        state: Optional[str] = None,
        parent: str = "Sundry Debtors",
        company: Optional[str] = None,
    ) -> TallyPushResult:
        """Create the party ledger in Tally if it doesn't already exist.

        Called automatically by push_voucher() before booking a voucher for
        a vendor/customer AuditOS hasn't seen in Tally yet — avoids the
        voucher push failing on an unknown ledger name.
        """
        company = company or self.config.company
        if self.ledger_exists(name, company):
            return TallyPushResult(success=True, created=0)

        xml_body = _create_ledger_request(company, name, parent, gstin, state)
        root = self._post(xml_body)
        return self._parse_push_result(root)

    def push_voucher(
        self,
        canonical_row: Dict[str, Any],
        voucher_type: str,
        company: Optional[str] = None,
        auto_create_ledger: bool = True,
    ) -> TallyPushResult:
        """Push one AuditOS canonical line item (SalesLineItem/PurchaseLineItem
        row shape) to Tally as a voucher.

        This is the write path, gated behind Auditor_Approved at the caller
        level (main.py) — this method itself performs no approval check, it
        assumes the row it's given has already cleared review.

        Only handles ledger-only vouchers (no stock items) — matches how
        AuditOS invoices are booked today (taxable_value + CGST/SGST/IGST
        against the party ledger and a Sales/Purchase Account ledger).

        voucher_type: "Sales" | "Purchase" | "Credit Note" | "Debit Note".
        Credit Note reverses a Sales entry (customer-side, Sundry Debtors);
        Debit Note reverses a Purchase entry (vendor-side, Sundry Creditors)
        — see _push_voucher_request's `reverse` doc for why negating every
        leg is the correct reversal regardless of Tally's sign convention.
        The party-ledger base sign flips between sales-side and purchase-side
        (a debtor's normal balance is Dr, a creditor's is Cr) — `is_reversal`
        below is computed as `is_note XOR is_purchase_side`, not just
        `is_note`, or Purchase/Debit Note post in the wrong direction. All
        four types live-tested against TallyPrime, confirmed correct Dr/Cr.

        If `auto_create_ledger` is True (default) and the party ledger isn't
        already in Tally, it's created automatically under Sundry Debtors
        (sales/credit note) / Sundry Creditors (purchase/debit note) before
        the voucher is pushed — the push would otherwise fail with an
        unknown-ledger error.
        """
        company = company or self.config.company
        if not company:
            raise ValueError("No company specified")

        vtype = voucher_type.strip().lower()
        if vtype not in ("sales", "purchase", "credit note", "debit note"):
            return TallyPushResult(success=False, error=f"Unsupported voucher_type: {voucher_type!r}")

        is_sales_side = vtype in ("sales", "credit note")
        is_note = vtype in ("credit note", "debit note")
        # Sales' base pattern (party leg negative, ISDEEMEDPOSITIVE=Yes) posts
        # as Dr — correct for a debtor. Purchase needs the OPPOSITE base
        # pattern (Cr, correct for a creditor), so it can't just inherit
        # Sales' sign. `reverse` must flip relative to the correct base for
        # each side, not relative to "is this a Note": Credit Note reverses
        # Sales' Dr base -> Cr; Debit Note reverses Purchase's Cr base -> Dr,
        # which numerically equals Sales' own Dr base pattern. Net rule:
        # reverse = is_note XOR is_purchase_side. Confirmed live 2026-07-18 —
        # without this XOR, Debit Note posted as Cr (same as a normal
        # Purchase) instead of Dr; caught before this ever touched a real
        # client's Tally company.
        is_reversal = is_note != (not is_sales_side)

        date = _iso_date_to_tally(canonical_row.get("voucher_date", ""))
        if not date:
            return TallyPushResult(success=False, error="Missing or invalid voucher_date")

        party = canonical_row.get("party_ledger_name")
        if not party:
            return TallyPushResult(success=False, error="Missing party_ledger_name")

        if auto_create_ledger:
            parent = "Sundry Debtors" if is_sales_side else "Sundry Creditors"
            ledger_result = self.ensure_party_ledger(
                name=party,
                gstin=canonical_row.get("party_gstin"),
                state=canonical_row.get("place_of_supply"),
                parent=parent,
                company=company,
            )
            if not ledger_result.success:
                return TallyPushResult(
                    success=False,
                    error=f"Failed to auto-create party ledger '{party}': {ledger_result.error}",
                )

        taxable = float(canonical_row.get("taxable_value") or 0.0)
        cgst = float(canonical_row.get("cgst_amount") or 0.0)
        sgst = float(canonical_row.get("sgst_amount") or 0.0)
        igst = float(canonical_row.get("igst_amount") or 0.0)
        total = float(canonical_row.get("total_invoice_value") or (taxable + cgst + sgst + igst))

        account_ledger = "Sales Account" if is_sales_side else "Purchase Account"
        credit_entries = [{"ledger": account_ledger, "amount": taxable}]
        if cgst:
            credit_entries.append({"ledger": "CGST", "amount": cgst})
        if sgst:
            credit_entries.append({"ledger": "SGST", "amount": sgst})
        if igst:
            credit_entries.append({"ledger": "IGST", "amount": igst})

        xml_body = _push_voucher_request(
            company=company,
            voucher_type=voucher_type,
            date=date,
            party_ledger=party,
            party_amount=total,
            credit_entries=credit_entries,
            narration=canonical_row.get("narration", ""),
            voucher_number=canonical_row.get("invoice_no"),
            reverse=is_reversal,
        )

        root = self._post(xml_body)
        return self._parse_push_result(root)

    def _parse_push_result(self, root: ET.Element) -> TallyPushResult:
        result_el = root.find(".//IMPORTRESULT")
        if result_el is None:
            return TallyPushResult(success=False, error="No IMPORTRESULT in Tally response")

        created = int(_text(result_el, "CREATED") or 0)
        exceptions = int(_text(result_el, "EXCEPTIONS") or 0)
        line_error = _text(result_el, "LINEERROR")

        if created > 0 and exceptions == 0:
            return TallyPushResult(success=True, created=created, exceptions=exceptions)
        return TallyPushResult(
            success=False, created=created, exceptions=exceptions,
            error=line_error or "Voucher rejected by Tally (no LINEERROR given)",
        )

    def get_day_book(
        self,
        from_date: str,
        to_date: str,
        company: Optional[str] = None,
    ) -> List[TallyVoucher]:
        """Pull all voucher types for a date range (Day Book export)."""
        company = company or self.config.company
        if not company:
            raise ValueError("No company specified")
        tally_from = from_date.replace("-", "")
        tally_to = to_date.replace("-", "")

        root = self._post(_day_book_request(company, tally_from, tally_to))
        return self._parse_vouchers(root)

    # ------------------------------------------------------------------
    # Mapping to AuditOS canonical schema
    # ------------------------------------------------------------------

    def vouchers_to_canonical(
        self,
        vouchers: List[TallyVoucher],
        register_type: str = "purchase",
    ) -> List[Dict[str, Any]]:
        """Map Tally vouchers to AuditOS canonical field dict (same keys as
        SalesLineItem / PurchaseLineItem DB columns).

        Returns one dict per line item (a single voucher may have multiple
        inventory entries → multiple rows, matching how AuditOS stores them).
        """
        rows = []
        for v in vouchers:
            base = {
                "voucher_date": _tally_date_to_iso(v.date),
                "voucher_type": v.voucher_type,
                "invoice_no": v.invoice_no or v.number,
                "party_ledger_name": v.party_name,
                "party_gstin": v.party_gstin or "",
                "place_of_supply": v.place_of_supply or "",
                "narration": v.narration or "",
            }

            if v.line_items:
                for li in v.line_items:
                    row = {**base}
                    row["particulars"] = li.get("stock_item", "")
                    row["hsn"] = li.get("hsn", "")
                    row["qty"] = li.get("qty", 0.0)
                    row["rate"] = li.get("rate", 0.0)
                    row["taxable_value"] = li.get("amount", 0.0)
                    row["cgst_amount"] = li.get("cgst", 0.0)
                    row["sgst_amount"] = li.get("sgst", 0.0)
                    row["igst_amount"] = li.get("igst", 0.0)
                    total_tax = (li.get("cgst", 0.0) or 0) + (li.get("sgst", 0.0) or 0) + (li.get("igst", 0.0) or 0)
                    row["total_invoice_value"] = (li.get("amount", 0.0) or 0) + total_tax
                    if register_type == "purchase":
                        row["itc_eligibility"] = "Input Tax Credit"
                    else:
                        row["gstr1_category"] = _infer_gstr1_category(v)
                    rows.append(row)
            else:
                tax_entries = _extract_tax_from_ledger_entries(v)
                row = {**base}
                row["particulars"] = ""
                row["hsn"] = ""
                row["qty"] = 0.0
                row["rate"] = 0.0
                row["taxable_value"] = tax_entries.get("taxable", 0.0)
                row["cgst_amount"] = tax_entries.get("cgst", 0.0)
                row["sgst_amount"] = tax_entries.get("sgst", 0.0)
                row["igst_amount"] = tax_entries.get("igst", 0.0)
                row["total_invoice_value"] = tax_entries.get("total", 0.0)
                if register_type == "purchase":
                    row["itc_eligibility"] = "Input Tax Credit"
                else:
                    row["gstr1_category"] = _infer_gstr1_category(v)
                rows.append(row)

        return rows

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_vouchers(self, root: ET.Element, default_type: str = "") -> List[TallyVoucher]:
        vouchers = []
        for vch in root.iter("VOUCHER"):
            number = _text(vch, "VOUCHERNUMBER") or _text(vch, "NUMBER") or ""
            date_raw = _text(vch, "DATE") or ""
            vtype = _text(vch, "VOUCHERTYPENAME") or vch.get("VCHTYPE", default_type)
            party = _text(vch, "PARTYLEDGERNAME") or ""
            gstin = _text(vch, "BASICPARTYGSTIN") or _text(vch, "PARTYGSTIN") or ""
            pos = _text(vch, "PLACEOFSUPPLY") or ""
            narration = _text(vch, "NARRATION") or ""
            reference = _text(vch, "REFERENCE") or ""

            line_items = []
            for inv_entry in vch.iter("ALLINVENTORYENTRIES.LIST"):
                li = {
                    "stock_item": _text(inv_entry, "STOCKITEMNAME") or "",
                    "rate": _float(inv_entry, "RATE"),
                    "amount": abs(_float(inv_entry, "AMOUNT")),
                    "qty": abs(_float(inv_entry, "BILLEDQTY")),
                }
                for duty in inv_entry.iter("ACCOUNTINGALLOCATIONS.LIST"):
                    _classify_tax_entry(duty, li)
                line_items.append(li)

            vouchers.append(TallyVoucher(
                number=number,
                date=date_raw,
                voucher_type=vtype,
                party_name=party,
                party_gstin=gstin,
                place_of_supply=pos,
                narration=narration,
                invoice_no=reference or number,
                line_items=line_items,
            ))
        return vouchers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(el: ET.Element, tag: str) -> Optional[str]:
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    child = el.find(tag.upper())
    if child is not None and child.text:
        return child.text.strip()
    return None


def _float(el: ET.Element, tag: str) -> float:
    t = _text(el, tag)
    if not t:
        return 0.0
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _tally_date_to_iso(date_str: str) -> str:
    """Convert Tally date (YYYYMMDD) to ISO (YYYY-MM-DD)."""
    if not date_str or len(date_str) < 8:
        return date_str
    clean = date_str.replace("-", "").replace("/", "")[:8]
    try:
        return datetime.strptime(clean, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return date_str


def _iso_date_to_tally(date_str: str) -> Optional[str]:
    """Convert ISO date (YYYY-MM-DD) to Tally format (YYYYMMDD)."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        return None


def _classify_tax_entry(duty: ET.Element, li: dict) -> None:
    """Classify a ledger allocation as CGST/SGST/IGST based on ledger name."""
    name = (_text(duty, "LEDGERNAME") or "").upper()
    amt = abs(_float(duty, "AMOUNT"))
    if "CGST" in name:
        li["cgst"] = li.get("cgst", 0.0) + amt
    elif "SGST" in name or "UTGST" in name:
        li["sgst"] = li.get("sgst", 0.0) + amt
    elif "IGST" in name:
        li["igst"] = li.get("igst", 0.0) + amt


def _extract_tax_from_ledger_entries(v: TallyVoucher) -> Dict[str, float]:
    """For vouchers with no inventory entries, extract tax from ledger entries."""
    result: Dict[str, float] = {"taxable": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total": 0.0}
    for li in v.line_items:
        result["cgst"] += li.get("cgst", 0.0)
        result["sgst"] += li.get("sgst", 0.0)
        result["igst"] += li.get("igst", 0.0)
    result["total"] = result["taxable"] + result["cgst"] + result["sgst"] + result["igst"]
    return result


def _infer_gstr1_category(v: TallyVoucher) -> str:
    """Basic GSTR-1 category inference from voucher attributes."""
    gstin = v.party_gstin or ""
    pos = v.place_of_supply or ""
    if gstin.startswith("URP") or not gstin:
        return "B2C (Small)"
    return "B2B"


# ---------------------------------------------------------------------------
# CLI helper — run standalone to test connectivity
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

    config = TallyConfig(host=host, port=port)
    connector = TallyConnector(config)

    print(f"Testing connection to TallyPrime at {config.url} ...")
    try:
        info = connector.test_connection()
        print(f"  Connected. Server info: {json.dumps(info, indent=2)}")
    except TallyConnectionError as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("\nListing companies...")
    companies = connector.list_companies()
    if companies:
        for c in companies:
            print(f"  - {c['name']} ({c['formal_name']})")
        config.company = companies[0]["name"]
        print(f"\nUsing first company: {config.company}")

        print("\nPulling ledgers (first 10)...")
        ledgers = connector.get_ledgers()
        for ldg in ledgers[:10]:
            gstin_str = f" [GSTIN: {ldg.gstin}]" if ldg.gstin else ""
            print(f"  - {ldg.name} (under {ldg.parent}){gstin_str}")
        print(f"  ... {len(ledgers)} ledgers total")
    else:
        print("  No companies found. Open a company in TallyPrime first.")
