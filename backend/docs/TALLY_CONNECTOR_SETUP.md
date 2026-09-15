# TallyPrime Direct Connector — Setup & Troubleshooting

## TL;DR

AuditOS talks to TallyPrime over its built-in XML-over-HTTP server (no cloud API, no Excel round-trip). This only works if AuditOS can reach that server over the network — most onboarding friction is network/firewall, not the connector itself. This doc is the checklist for getting a new client's Tally machine reachable, and what to do when it isn't.

## One-time setup on the Tally machine

### 1. Enable the Server (1 min)

In TallyPrime: **F1 → Settings → Connectivity**
- **Client/Server configuration → TallyPrime acting as:** `Server`
- **Port:** `9000` (default — only change if it conflicts, see below)
- Save

### 2. Confirm a company is open

The connector can only see whichever company is actually loaded in that Tally session — an empty/no-company state returns zero data, not an error. Open (or create) the company you intend to sync before testing.

### 3. Find the machine's LAN IP

On the Tally machine, Command Prompt:
```
ipconfig | findstr IPv4
```
Use the address under the active adapter (typically `192.168.x.x` on a home/office router). This is the host AuditOS will connect to.

## Common blockers (in the order we've actually hit them)

### "Cannot reach TallyPrime" / connection times out
Almost always one of:
1. **Different subnet.** AuditOS's machine and the Tally machine must be on the same LAN. Run `ipconfig` on both — if the first three octets differ (`192.168.1.x` vs `192.165.1.x`, or different Wi-Fi networks entirely), they can't reach each other directly. Get both onto the same network, or use whatever remote-desktop/VPN the client already has for that machine.
2. **Windows Firewall blocking inbound port 9000.** Add an inbound rule on the Tally machine:
   ```powershell
   New-NetFirewallRule -DisplayName "TallyPrime XML Server" -Direction Inbound -LocalPort 9000 -Protocol TCP -Action Allow
   ```
3. **Tally isn't actually running as Server** — re-check step 1 above; this setting doesn't always persist across a Tally restart.

### Tally is on a remote desktop / cloud instance, not a local LAN machine
This is common — many firms run Tally on a Windows RDP session (their own cloud provider, or a colleague's machine) rather than locally. In that case:
- AuditOS still connects to `localhost:9000` **from inside that same RDP session** — you can't reach it from outside the remote desktop's network.
- Practically, this means: whoever is setting up the connector needs to run the connectivity test **from within the RDP session itself** (e.g., via PowerShell inside that remote desktop), not from their own laptop.
- If RDP access is unreliable (session drops, single-session licensing kicks you out), Chrome Remote Desktop or AnyDesk are simpler alternatives that don't require Windows Pro/Enterprise-only "host" features.

### Port already in use — connection succeeds but returns the wrong company's data
**This is the one to watch for on any shared/multi-user machine.** If the Tally machine has more than one Windows user logged in simultaneously (common on a firm's shared bookkeeping PC), each user's TallyPrime instance competes for port 9000 — and whichever one grabbed it first wins, even if it's a completely different company than the one you're looking at on screen.

**Before sending any write (voucher push) command, always verify which company you're actually talking to:**
```powershell
$xml = '<?xml version="1.0" encoding="utf-8"?><ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CompanyCollection</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="CompanyCollection" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>Name</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'
(Invoke-WebRequest -Uri "http://localhost:9000" -Method POST -Body $xml -ContentType "text/xml" -UseBasicParsing).Content
```
Read the actual `<COMPANY NAME="...">` in the response. If it's not the company you expect — especially if it has a nonzero ledger/voucher count you don't recognize — **stop, do not send any write command.**

**Fix:** move your own Tally instance to a different port instead of touching anyone else's session:
1. F1 → Settings → Connectivity → change Port to `9001` (or any free port)
2. Point AuditOS's host config at that port instead
3. Re-run the company check to confirm it now shows the right company

**Never close or "Shut Company" on a company you didn't personally open**, even to resolve a port conflict — someone else may be actively working in it.

## Company setup checklist (test/demo companies)

When setting up a blank company for testing (not a real client's books), you'll need at minimum:
- `CGST`, `SGST`, `IGST` ledgers under **Duties & Taxes**
- `Sales Account` ledger under **Sales Accounts**
- `Purchase Account` ledger under **Purchase Accounts**
- Party ledgers auto-create on first push (see `services/tally_connector.py::ensure_party_ledger`) — you don't need to pre-create these

## Known Tally-side quirks

- **No built-in duplicate protection.** Pushing the same voucher payload twice creates two vouchers — Tally doesn't dedupe on content or even an explicit `VOUCHERNUMBER`. AuditOS's own idempotency check (`models.TallyPushLog`) is the only safeguard against this on a retried batch push.
- **Custom `VOUCHERNUMBER` is cosmetic only** — Tally may still auto-number vouchers using its own series for display, ignoring the value we send. Don't rely on it matching what's shown in the Tally UI.
- **Financial year matters.** A voucher dated outside the company's configured financial year fails with `LINEERROR: date is Out of Range` — check the company's FY before pushing historical data.
