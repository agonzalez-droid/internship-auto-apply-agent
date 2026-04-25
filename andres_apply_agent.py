"""
Andres Gonzalez — Internship Auto-Apply Agent (Phase 2)
=========================================================
SETUP (one time):
  1. Install Python 3.10+ from python.org
  2. Open Terminal and run:
       pip install playwright anthropic twilio
       playwright install chromium
  3. Fill in your credentials in the CONFIG section below
  4. Run with: python andres_apply_agent.py

The agent will:
  - Search for open internships matching your profile
  - Navigate to each application page
  - Fill every field using your profile data
  - Handle EEO/diversity disclosure forms automatically
  - Text you at (214) 482-2277 whenever it applies or hits an issue
  - Log every application to applications_log.json
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

# ── INSTALL CHECK ──────────────────────────────────────────────────────────────
try:
    from playwright.async_api import async_playwright
    import anthropic
    from twilio.rest import Client as TwilioClient
except ImportError as e:
    print(f"\nMissing package: {e}")
    print("Run: pip install playwright anthropic twilio && playwright install chromium\n")
    exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG — fill these in before running
# ══════════════════════════════════════════════════════════════════════════════

ANTHROPIC_API_KEY   = "YOUR_ANTHROPIC_API_KEY"       # platform.anthropic.com
TWILIO_ACCOUNT_SID  = "YOUR_TWILIO_ACCOUNT_SID"      # console.twilio.com
TWILIO_AUTH_TOKEN   = "YOUR_TWILIO_AUTH_TOKEN"
TWILIO_FROM_NUMBER  = "+1XXXXXXXXXX"                  # your Twilio phone number
MY_PHONE            = "+1xxxxxxxxxx"                  # Andres's number

# LinkedIn credentials (for Easy Apply)
LINKEDIN_EMAIL      = "YOUR_EMAIL"
LINKEDIN_PASSWORD   = "YOUR_LINKEDIN_PASSWORD"

HEADLESS = False   # Set True to run browser invisibly; False to watch it work

# ══════════════════════════════════════════════════════════════════════════════
#  CANDIDATE PROFILE — pre-loaded with Andres's full background
# ══════════════════════════════════════════════════════════════════════════════

PROFILE = {
    "first_name":   "YOUR_FIRST_NAME",
    "last_name":    "YOUR_LAST_NAME",
    "full_name":    "YOUR_FULL_NAME",
    "email":        "YOUR_EMAIL",
    "phone":        "YOUR_PHONE_10_DIGITS",
    "phone_fmt":    "YOUR_PHONE_FORMATTED",
    "address":      "YOUR_STREET_ADDRESS",
    "city":         "YOUR_CITY",
    "state":        "YOUR_STATE",
    "zip":          "YOUR_ZIP",
    "linkedin":     "YOUR_LINKEDIN_URL",
    "school":       "Benedictine College",
    "degree":       "Bachelor of Arts",
    "major":        "Finance and International Business",
    "gpa":          "3.28",
    "grad_year":    "2027",
    "grad_month":   "May",
    "citizenship":  "U.S. Citizen",
    "authorized":   "Yes",
    "veteran":      "I am not a protected veteran",
    "disability":   "I do not wish to answer",
    # EEO disclosures
    "ethnicity":    "Hispanic or Latino",
    "gender":       "Male",
    "lgbtq":        "Yes",       # disclose where asked
    # Relocate preferences
    "relocate":     "Yes",
    "target_locations": ["Dallas TX", "Washington DC", "Atlanta GA",
                         "Tampa FL", "Miami FL", "Charlotte SC",
                         "Atchison KS", "Remote"],
    # Skills for short-answer fields
    "skills_list":  "Financial Statement Analysis, Capital Budgeting, Valuation, "
                    "Risk Assessment, Microsoft Excel (Advanced), Data Analysis, "
                    "Microsoft Office Suite, Business Statistics",
    "salary_expect": "Paid / open to discussion",
    "start_date":   "June 2026",
}

TARGET_ROLES = [
    "Summer 2026 Financial Analyst Intern",
    "Summer 2026 Investment Banking Analyst Intern",
    "Summer 2026 Advisory Intern",
    "Summer 2026 Deals Intern",
    "Summer 2026 Finance Intern",
]

TARGET_COMPANIES = [
    # Feeder tier
    "PwC", "Deloitte", "EY", "KPMG",
    "S&P Global", "Moody's", "Fidelity Investments",
    "Raymond James", "Baird", "Houlihan Lokey", "Jefferies",
    # Government
    "Federal Reserve", "U.S. Treasury", "SEC",
    # Reach
    "Goldman Sachs", "JP Morgan", "Citi",
]

LOG_FILE = Path("applications_log.json")

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []

def save_log(entries):
    LOG_FILE.write_text(json.dumps(entries, indent=2))

def log_application(company, role, url, status, notes=""):
    entries = load_log()
    entries.append({
        "timestamp":  datetime.now().isoformat(),
        "company":    company,
        "role":       role,
        "url":        url,
        "status":     status,
        "notes":      notes,
    })
    save_log(entries)
    print(f"  [LOG] {status.upper()} — {company}: {role}")

# ══════════════════════════════════════════════════════════════════════════════
#  SMS VIA TWILIO
# ══════════════════════════════════════════════════════════════════════════════

def sms(message: str):
    """Send Andres a text update."""
    try:
        twilio = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        twilio.messages.create(body=message, from_=TWILIO_FROM_NUMBER, to=MY_PHONE)
        print(f"  [SMS] Sent: {message[:80]}")
    except Exception as e:
        print(f"  [SMS ERROR] {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  CLAUDE — the AI brain
# ══════════════════════════════════════════════════════════════════════════════

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def ask_claude(prompt: str, system: str = "") -> str:
    """Ask Claude a question and return the text response."""
    messages = [{"role": "user", "content": prompt}]
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system or "You are a helpful AI assistant.",
        messages=messages,
    )
    return resp.content[0].text.strip()

def claude_fill_field(label: str, field_type: str, options: list = None) -> str:
    """
    Ask Claude what to enter for a given application field
    given Andres's profile.
    """
    opts_str = f"\nAvailable options: {options}" if options else ""
    prompt = f"""You are filling out a job application for Andres Gonzalez.
Candidate profile: {json.dumps(PROFILE, indent=2)}

Application field: "{label}"
Field type: {field_type}{opts_str}

Return ONLY the value to enter. No explanation. No quotes.
If it's a dropdown, return the exact option text that best matches.
If unsure, return the most neutral professional answer."""
    return ask_claude(prompt)

# ══════════════════════════════════════════════════════════════════════════════
#  JOB SEARCH
# ══════════════════════════════════════════════════════════════════════════════

def find_internships() -> list[dict]:
    """
    Use Claude with web search to find open internship listings.
    Returns a list of {company, role, url, tier} dicts.
    """
    print("\n[SEARCH] Looking for open internships...")
    prompt = f"""Search the web for real, currently open Summer 2026 internship positions 
for this candidate:
- School: Benedictine College, Finance & International Business, GPA 3.28
- Target companies: {', '.join(TARGET_COMPANIES)}
- Target roles: {', '.join(TARGET_ROLES)}
- Locations: {', '.join(PROFILE['target_locations'])}

Return a JSON array only — no explanation, no markdown. Format:
[
  {{"company": "...", "role": "...", "url": "...", "tier": "feeder|government|reach"}},
  ...
]

Only include positions with a direct application URL. Maximum 10 results."""

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    raw = " ".join(b.text for b in resp.content if b.type == "text")
    # Extract JSON array
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        print("  [SEARCH] No structured results found.")
        return []
    try:
        results = json.loads(match.group())
        print(f"  [SEARCH] Found {len(results)} listings.")
        return results
    except json.JSONDecodeError:
        print("  [SEARCH] Could not parse results.")
        return []

# ══════════════════════════════════════════════════════════════════════════════
#  EEO HANDLER
# ══════════════════════════════════════════════════════════════════════════════

async def fill_eeo_fields(page):
    """Detect and fill common EEO/diversity disclosure fields."""
    eeo_patterns = {
        "ethnicity|race|hispanic|latino": PROFILE["ethnicity"],
        "gender|sex":                     PROFILE["gender"],
        "veteran":                        PROFILE["veteran"],
        "disability":                     PROFILE["disability"],
        "citizen|authorized|work.*us":    PROFILE["citizenship"],
        "lgbtq|sexual.*orientation":      "I identify as LGBTQ+",
    }
    selects = await page.query_selector_all("select")
    for sel in selects:
        label_text = ""
        # Try to find associated label
        sel_id = await sel.get_attribute("id") or ""
        sel_name = await sel.get_attribute("name") or ""
        label_el = await page.query_selector(f"label[for='{sel_id}']")
        if label_el:
            label_text = (await label_el.inner_text()).lower()
        else:
            label_text = (sel_id + " " + sel_name).lower()

        for pattern, value in eeo_patterns.items():
            if re.search(pattern, label_text):
                options = await sel.query_selector_all("option")
                opt_texts = [await o.inner_text() for o in options]
                # Find closest matching option
                best = next(
                    (t for t in opt_texts
                     if value.lower() in t.lower() or t.lower() in value.lower()),
                    None
                )
                if best:
                    await sel.select_option(label=best)
                    print(f"  [EEO] Set '{label_text}' → '{best}'")
                break

# ══════════════════════════════════════════════════════════════════════════════
#  GENERIC FORM FILLER
# ══════════════════════════════════════════════════════════════════════════════

async def fill_form(page, company: str, role: str):
    """
    Smart form-filler: finds all visible inputs/selects/textareas,
    determines what each one is asking for, and fills it.
    """
    FIELD_MAP = {
        r"first.?name":          PROFILE["first_name"],
        r"last.?name":           PROFILE["last_name"],
        r"full.?name":           PROFILE["full_name"],
        r"email":                PROFILE["email"],
        r"phone|mobile":         PROFILE["phone"],
        r"address|street":       PROFILE["address"],
        r"city":                 PROFILE["city"],
        r"state":                PROFILE["state"],
        r"zip|postal":           PROFILE["zip"],
        r"linkedin":             PROFILE["linkedin"],
        r"university|school|college": PROFILE["school"],
        r"major|field.*study":   PROFILE["major"],
        r"gpa|grade":            PROFILE["gpa"],
        r"grad.*year|class.*of": PROFILE["grad_year"],
        r"degree":               PROFILE["degree"],
        r"start.*date|available": PROFILE["start_date"],
        r"relocat":              "Yes",
        r"citizen|authorized":   PROFILE["citizenship"],
        r"visa":                 "No",
        r"salary|compensation":  PROFILE["salary_expect"],
        r"how.*hear|source|referr": "Company website",
    }

    # Fill text inputs
    inputs = await page.query_selector_all("input:visible, textarea:visible")
    for inp in inputs:
        inp_type = await inp.get_attribute("type") or "text"
        if inp_type in ("submit", "button", "hidden", "file", "checkbox", "radio"):
            continue
        placeholder = (await inp.get_attribute("placeholder") or "").lower()
        name        = (await inp.get_attribute("name") or "").lower()
        inp_id      = (await inp.get_attribute("id") or "").lower()
        label_el    = await page.query_selector(f"label[for='{inp_id}']")
        label_text  = (await label_el.inner_text()).lower() if label_el else ""
        combined    = f"{placeholder} {name} {inp_id} {label_text}"

        value = None
        for pattern, fill in FIELD_MAP.items():
            if re.search(pattern, combined):
                value = fill
                break

        if value is None and len(combined.strip()) > 3:
            # Ask Claude for anything we don't recognize
            value = claude_fill_field(combined.strip(), "text input")

        if value:
            try:
                await inp.fill(str(value))
            except Exception:
                pass

    # Fill selects
    selects = await page.query_selector_all("select:visible")
    for sel in selects:
        sel_id   = await sel.get_attribute("id") or ""
        sel_name = await sel.get_attribute("name") or ""
        label_el = await page.query_selector(f"label[for='{sel_id}']")
        label_text = (await label_el.inner_text()).lower() if label_el else (sel_id + sel_name).lower()

        options  = await sel.query_selector_all("option")
        opt_texts = [await o.inner_text() for o in options if await o.get_attribute("value")]

        if not opt_texts:
            continue

        # Ask Claude which option to pick
        answer = claude_fill_field(label_text, "dropdown select", opt_texts)
        best   = next((t for t in opt_texts if answer.lower() in t.lower()), None)
        if best:
            try:
                await sel.select_option(label=best)
            except Exception:
                pass

    await fill_eeo_fields(page)

# ══════════════════════════════════════════════════════════════════════════════
#  LINKEDIN EASY APPLY
# ══════════════════════════════════════════════════════════════════════════════

async def linkedin_easy_apply(page, job: dict) -> bool:
    """Handle LinkedIn Easy Apply flow."""
    try:
        await page.goto(job["url"], timeout=30000)
        await page.wait_for_timeout(2000)

        # Click Easy Apply button
        easy_btn = await page.query_selector("button:has-text('Easy Apply'), .jobs-apply-button")
        if not easy_btn:
            return False
        await easy_btn.click()
        await page.wait_for_timeout(1500)

        # Step through multi-page application
        for step in range(10):
            await fill_form(page, job["company"], job["role"])
            await page.wait_for_timeout(1000)

            # Look for Next/Submit button
            next_btn = await page.query_selector(
                "button:has-text('Next'), button:has-text('Submit application'), "
                "button:has-text('Review')"
            )
            if not next_btn:
                break
            btn_text = await next_btn.inner_text()
            await next_btn.click()
            await page.wait_for_timeout(1500)

            if "Submit" in btn_text:
                return True  # Successfully submitted

        return False
    except Exception as e:
        print(f"  [LINKEDIN] Error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  GENERIC APPLY
# ══════════════════════════════════════════════════════════════════════════════

async def generic_apply(page, job: dict) -> bool:
    """Apply to a generic company careers page."""
    try:
        await page.goto(job["url"], timeout=30000)
        await page.wait_for_timeout(2000)

        # Look for Apply button
        apply_btn = await page.query_selector(
            "a:has-text('Apply'), button:has-text('Apply'), "
            "a:has-text('Apply Now'), button:has-text('Apply Now'), "
            "a:has-text('Start Application')"
        )
        if apply_btn:
            await apply_btn.click()
            await page.wait_for_timeout(2000)

        await fill_form(page, job["company"], job["role"])
        await page.wait_for_timeout(1000)

        # Look for submit
        submit_btn = await page.query_selector(
            "button:has-text('Submit'), button[type='submit'], "
            "input[type='submit'], button:has-text('Send Application')"
        )
        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(2000)
            return True

        return False
    except Exception as e:
        print(f"  [APPLY] Error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  ALREADY APPLIED CHECK
# ══════════════════════════════════════════════════════════════════════════════

def already_applied(url: str) -> bool:
    entries = load_log()
    return any(e["url"] == url and e["status"] == "applied" for e in entries)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

async def run():
    print("\n" + "="*60)
    print("  Andres Gonzalez — Internship Auto-Apply Agent")
    print("="*60)

    # Validate credentials
    if "YOUR_" in ANTHROPIC_API_KEY:
        print("\nERROR: Fill in your API credentials in the CONFIG section.\n")
        return

    sms("Agent started. Searching for internships now...")

    jobs = find_internships()
    if not jobs:
        sms("No new internship listings found this run. Will try again.")
        return

    sms(f"Found {len(jobs)} internship listings. Starting applications...")

    applied_count = 0
    failed_count  = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        # Log into LinkedIn once
        page = await context.new_page()
        print("\n[LINKEDIN] Logging in...")
        try:
            await page.goto("https://www.linkedin.com/login", timeout=20000)
            await page.fill("#username", LINKEDIN_EMAIL)
            await page.fill("#password", LINKEDIN_PASSWORD)
            await page.click("button[type='submit']")
            await page.wait_for_timeout(3000)
            print("  [LINKEDIN] Logged in.")
        except Exception as e:
            print(f"  [LINKEDIN] Login issue: {e}")

        for job in jobs:
            company = job.get("company", "Unknown")
            role    = job.get("role", "Internship")
            url     = job.get("url", "")
            tier    = job.get("tier", "feeder")

            if not url:
                continue
            if already_applied(url):
                print(f"\n[SKIP] Already applied: {company}")
                continue

            print(f"\n[APPLYING] {company} — {role}")
            print(f"  URL: {url}")

            try:
                page = await context.new_page()
                is_linkedin = "linkedin.com" in url

                if is_linkedin:
                    success = await linkedin_easy_apply(page, job)
                else:
                    success = await generic_apply(page, job)

                await page.close()

                if success:
                    applied_count += 1
                    log_application(company, role, url, "applied",
                                    f"Auto-applied by agent. Tier: {tier}")
                    sms(f"Applied: {role} at {company}. ({applied_count} total today)")
                else:
                    failed_count += 1
                    log_application(company, role, url, "needs_review",
                                    "Agent could not complete submission — review manually.")
                    sms(f"Needs your help: {company} ({role}) — couldn't auto-submit. Check the log.")

            except Exception as e:
                failed_count += 1
                print(f"  [ERROR] {e}")
                log_application(company, role, url, "error", str(e))
                sms(f"Error on {company} application. Check terminal for details.")

        await browser.close()

    summary = (
        f"Agent done. Applied: {applied_count}, "
        f"Needs review: {failed_count}. "
        f"Check applications_log.json for details."
    )
    print(f"\n{'='*60}\n{summary}\n{'='*60}\n")
    sms(summary)


if __name__ == "__main__":
    asyncio.run(run())
