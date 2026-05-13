# Mobile-first QA checklist (TradeVerse)

Use a **narrow viewport** (e.g. 390×844) or a real phone. Run `python run.py` and walk through in order.

## Auth & first impression

- [ ] Landing loads; nav menu opens/closes; no horizontal scroll on body
- [ ] Register → validation messages readable; country/phone fields usable
- [ ] Login → redirect to dashboard

## Core journal flows

- [ ] **Dashboard**: cards readable; weekly focus save works; no clipped charts
- [ ] **Add Trade**: instrument search + category tabs scroll; Buy/Sell; save validation flashes
- [ ] **My Trades**: list readable; filters/pagination if present
- [ ] **Trade detail / edit**: forms usable; close trade works
- [ ] **Calendar**: month nav; legend visible; cells tappable if interactive

## Planning & extras

- [ ] Trade Planner / Playbook (if enabled): primary actions reachable without zoom
- [ ] Analytics / Performance: charts load; no blank broken panels
- [ ] Replay: upload or note add works on small screen

## Account

- [ ] Settings / Billing copy readable; theme toggle works
- [ ] Logout → login again

## Technical spot-checks

- [ ] Browser console: no red errors on above paths (yellow CDN Tailwind warning should be gone after removing CDN)
- [ ] Flash messages visible above fold or dismissible

Record issues with **URL + viewport width + browser**.
