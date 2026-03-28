 # TradeVerse Trial & Planner Fixes - TODO
Status: ✅ Plan approved. Implementing...

## Breakdown & Progress

### 1. [✅ COMPLETE] Create TODO.md
   - Track progress

### 2. [✅ COMPLETE] Reset User Trials (app/__init__.py)
   - Added idempotent trial reset: expired/null → free + created_at+90d, logs count
   - Runs on SQLite dev startup

### 3. [✅ COMPLETE] Billing Display (app/templates/auth/account_settings.html)
   - Dynamic trial_ends_at → "90-Day Active" + days + "$3.99/mo"
   - Pro $3.99

### 4. [✅ COMPLETE] Pricing Template (app/templates/monetization/pricing.html)
   - FAQ: "90-day free trial"

### 5. [✅ COMPLETE] Pro Plan Data (app/routes/monetization.py)
   - '$3.99', desc "90-Day Free Trial then $3.99/month"

### 6. [✅ COMPLETE] Trial Info Template (app/templates/monetization/trial_info.html)
   - aria-valuemax="90"

### 7. [✅ COMPLETE] Planner PnL Sync (app/routes/planner.py)
   - execute_plan(): Auto-close executed_trade + calculate_pnl → My Trades/PnL totals/dashboard sync, no 404 (user_id protected)

**Next:** #8 Final verification

### 8. [PENDING] Final Verification
   - `python app.py` or restart → [TRIAL-FIX] logs resets
   - `check_db.py` → users.trial_ends_at set
   - Login → settings "90-Day Active" + days + $3.99
   - Planner new→start→execute/review → My Trades shows, PnL updates, detail view OK
   - Pricing shows $3.99/90-day

**Ready: attempt_completion**

### 3. [PENDING] Update Billing Display (app/templates/auth/account_settings.html)
   - Replace hardcoded 30-day → dynamic trial_ends_at calc
   - Show "90-Day Free Trial Active" + days + "$3.99/mo"

### 4. [PENDING] Fix Pricing Page (app/templates/monetization/pricing.html)
   - Pro: '$3.99/month'
   - FAQ: "90-day free trial"

### 5. [PENDING] Update Pro Plan Data (app/routes/monetization.py)
   - pricing(): '$3.99', desc="90-Day Free Trial then $3.99/month"

### 6. [PENDING] Fix Trial Info Template (app/templates/monetization/trial_info.html)
   - trial_days=90 for progress

### 7. [PENDING] Ensure Planner PnL Sync (app/routes/planner.py)
   - execute_plan(): Auto-close executed_trade if actual_exit set → triggers PnL/CLOSED

### 8. [PENDING] Final Verification
   - Restart app → trials reset
   - Test planner full flow: plan→execute→review→check My Trades/PnL/dashboard no 404
   - Settings/pricing show correct 90-day/$3.99

**Next:** Edit app/__init__.py (trial reset)

