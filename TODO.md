# Trade Lifecycle 3-Stage Implementation TODO
Approved plan: Implement PLANNED → EXECUTED → REVIEWED with guards/UI/alerts.

## Steps to Complete:

### [x] Step 1: Edit app/routes/planner.py
- Add guard to start_execution ✓
- Update execute_plan guard to exact spec ✓
- Ensure single commit() ✓

### [x] Step 2: Edit app/templates/planner/index.html  
- Add status badge tooltips ✓
- Insert modal warning text ✓

### [x] Step 3: Edit app/templates/trade/list.html
- Add 📋 Planned badge to Symbol column ✓

### [x] Step 4: Edit app/templates/dashboard/index.html
- Add EXECUTED plans alert banner ✓

### [x] Step 5: Test full flow
- Create plan → Execute → Review ✓
- Verify guards, redirects, dashboard alert, trade badge, counts ✓

### [x] Step 6: Complete task ✓

**Progress: 6/6 - 3-stage lifecycle fully implemented per spec.**
