# Internship Auto-Apply Agent

An autonomous job application agent built in Python that automates the internship search and application process.

## What It Does

- Searches the web for open internship listings matching a defined candidate profile and target companies
- Navigates to each application page using browser automation (Playwright)
- Intelligently fills form fields using regex pattern matching, with Claude AI as a fallback for unrecognized fields
- Handles EEO/diversity disclosure forms automatically
- Sends real-time SMS updates via Twilio throughout the process
- Logs every application to a persistent JSON file to prevent duplicate submissions

## Tech Stack

- Python 3.10+
- Playwright — browser automation
- Anthropic Claude API — AI-powered field recognition and form filling
- Twilio — SMS notifications

## Setup

1. Install dependencies: pip install playwright anthropic twilio && playwright install chromium
2. Fill in your credentials and profile in the CONFIG and PROFILE sections of the script
3. Run: python andres_apply_agent.py

## Notes

- An earlier version included LinkedIn Easy Apply integration and SMS two-way communication — currently being rebuilt after API changes
- All personal profile data has been replaced with placeholders — fill in your own before running
- Applications are logged to applications_log.json (excluded from version control)
