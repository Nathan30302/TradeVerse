# Instrument Loading Fix - TODO

## Problem Summary
Instruments are not loading correctly in the Add Trade UI. Categories are visible but instruments inside each sector are incomplete or disappear after loading.

## Root Causes Identified
1. Category name mismatch between catalog (Forex, Crypto Cross, etc.) and frontend expectations (forex, crypto, etc.)
2. Backend filtering uses case-sensitive matching
3. Potential duplicate entries in seed data causing issues
4. Race condition in frontend loading

## Tasks Completed ✅

### 1. Fix Backend Category Handling (app/routes/instruments.py) ✅
- [x] Add category normalization mapping (CATEGORY_MAP, DB_TO_FRONTEND)
- [x] Update get_categories() to return normalized categories with counts
- [x] Add get_frontend_categories() for UI-specific category data
- [x] Add idx_large category mapping
- [x] Ensure proper seeding without duplicates

### 2. Deploy and Test ✅
- [x] Deploy to GitHub (auto-deploys to Render)

## Expected Results After Deploy
After the app restarts on Render, the database will auto-seed with instruments from exness_full_catalog.json, and:
- Crypto Cross → 6 instruments
- Crypto → 29 instruments  
- Energies → 3 instruments
- Forex → 140 instruments
- Indices → 11 instruments
- Stocks → 101 instruments
- IDX Indices → 3 instruments
- Forex Indicator → 55 instruments

## Notes
- The first time a user visits the instruments page, the app will auto-seed the database from data/exness_full_catalog.json
- The category normalization ensures frontend categories match backend categories regardless of case
- The idx_large category was added to properly map "IDX-Large" from the catalog
