/**
 * Simple Horizontal Instrument Picker
 * Category-based selection with horizontal scrolling
 * 
 * FIXED: Now properly handles category loading without overriding template tabs
 * when database has fewer categories than template.
 */

class SimpleInstrumentPicker {
    constructor(options = {}) {
        this.apiUrl = options.apiUrl || '/api/instruments';
        this.selectedInstrument = null;
        this.currentCategory = 'forex';
        this.instruments = {};
        // Store the initial category from template to prevent switching
        this._initialCategorySet = false;
        this.init();
    }

    async init() {
        // Setup event listeners FIRST before any async operations
        this.setupEventListeners();
        
        // THEN load categories - but DON'T replace if DB has fewer
        await this.loadCategories();
        
        // Load instruments for current category
        this.loadInstrumentsForCategory(this.currentCategory);
        
        // Add debug logging
        console.log('[InstrumentPicker] Initialized with category:', this.currentCategory);
    }

    async loadCategories() {
        try {
            console.log('[InstrumentPicker] Loading categories from API...');
            
            // Use DB-backed categories endpoint
            const resp = await fetch('/api/db/instruments/categories');
            if (!resp.ok) {
                console.warn('[InstrumentPicker] Could not load categories, status=', resp.status);
                return;
            }

            const data = await resp.json();
            console.log('[InstrumentPicker] API response:', data);

            // API returns { success: True, categories: { key: {name: '...'}} }
            const categories = data && data.categories ? data.categories : null;

            // If categories not present, leave existing tabs in the template intact
            if (!categories) {
                console.log('[InstrumentPicker] No categories in API response, keeping template tabs');
                return;
            }

            const categoryKeys = Object.keys(categories);
            console.log('[InstrumentPicker] Categories from DB:', categoryKeys.length, categoryKeys);

            // FIXED: Only update tabs if DB has MORE or EQUAL categories than template
            // This prevents replacing 8 sectors with 5
            const templateTabs = document.querySelectorAll('.category-tab');
            const templateCount = templateTabs.length;
            
            console.log(`[InstrumentPicker] Template has ${templateCount} tabs, DB has ${categoryKeys.length} categories`);

            if (categoryKeys.length >= templateCount) {
                // DB has same or more categories - safe to update
                this.renderCategoryTabs(categories);
                console.log('[InstrumentPicker] Updated tabs from DB');
            } else {
                // DB has fewer categories - keep template tabs to show all 8 sectors
                console.log('[InstrumentPicker] Keeping template tabs (DB has fewer categories)');
                
                // But still try to switch to first available category from DB if current not found
                const currentTabExists = categoryKeys.includes(this.currentCategory);
                if (!currentTabExists && categoryKeys.length > 0) {
                    console.log('[InstrumentPicker] Switching to first available DB category:', categoryKeys[0]);
                    this.currentCategory = categoryKeys[0];
                    this.loadInstrumentsForCategory(this.currentCategory);
                }
            }
        } catch (error) {
            console.error('[InstrumentPicker] Failed to load categories:', error);
        }
    }

    renderCategoryTabs(categories) {
        const container = document.querySelector('.instrument-categories');
        if (!container) return;
        // Build tabs from returned categories object (key -> {name})
        const entries = Object.entries(categories);

        if (entries.length === 0) return;

        // If currentCategory is not present in keys, pick first available
        const keys = entries.map(e => e[0]);
        if (!keys.includes(this.currentCategory)) {
            this.currentCategory = keys[0];
        }

        const tabs = entries.map(([key, val]) => {
            const rawName = (val && val.name) ? String(val.name) : String(key);
            const name = rawName;
            const n = name.toLowerCase();

            // Determine icon by matching known keywords
            let icon = 'fas fa-square-question';
            if (n.includes('forex') || n.includes('fx')) icon = 'fas fa-exchange-alt';
            else if (n.includes('crypto') && n.includes('cross')) icon = 'fas fa-share-alt';
            else if (n.includes('crypto')) icon = 'fab fa-bitcoin';
            else if (n.includes('energy') || n.includes('ener')) icon = 'fas fa-bolt';
            else if (n.includes('index') || n.includes('indices') || n.includes('idx')) icon = 'fas fa-chart-line';
            else if (n.includes('stock') || n.includes('stocks')) icon = 'fas fa-building';
            else if (n.includes('metal') || n.includes('commodity')) icon = 'fas fa-gem';
            else if (n.includes('forex indicator') || n.includes('indicator')) icon = 'fas fa-wave-square';

            const isActive = (key === this.currentCategory) ? 'active' : '';
            return `
                <button type="button" class="category-tab ${isActive}" data-category="${key}">
                    <i class="${icon}"></i> ${name}
                </button>
            `;
        });

        container.innerHTML = tabs.join('');
    }

    setupEventListeners() {
        // Category tab clicks
        document.addEventListener('click', (e) => {
            if (e.target.closest('.category-tab')) {
                const tab = e.target.closest('.category-tab');
                const category = tab.dataset.category;
                this.switchCategory(category);
            }
        });

        // Instrument selection
        document.addEventListener('click', (e) => {
            if (e.target.closest('.instrument-item')) {
                const item = e.target.closest('.instrument-item');
                const instrumentId = item.dataset.id;
                const symbol = item.dataset.symbol;
                const name = item.dataset.name;
                this.selectInstrument(instrumentId, symbol, name);
            }
        });
    }

    async switchCategory(category) {
        this.currentCategory = category;

        // Update active tab safely (compare dataset)
        document.querySelectorAll('.category-tab').forEach(tab => {
            try { tab.classList.toggle('active', tab.dataset.category === category); } catch(e) { tab.classList.remove('active'); }
        });

        // Load instruments for category
        await this.loadInstrumentsForCategory(category);
    }

    async loadInstrumentsForCategory(category) {
        try {
            const response = await fetch(`/api/db/instruments?category=${encodeURIComponent(category)}&limit=10000`);
            if (!response.ok) {
                console.warn('Failed to fetch instruments for', category, response.status);
                this.renderInstruments([]);
                return;
            }

            const data = await response.json();
            // API returns { success: True, results: [...] }
            const instruments = (data && data.results) ? data.results : [];
            this.renderInstruments(instruments);
        } catch (error) {
            console.error('Failed to load instruments:', error);
        }
    }

    renderInstruments(instruments) {
        const container = document.getElementById('instrument-list');
        if (!container) return;
        // Clear then render
        container.innerHTML = '';

        if (!Array.isArray(instruments) || instruments.length === 0) {
            // Use consistent empty state styling
            container.innerHTML = `<div class="empty-state"><i class="fas fa-search"></i><div class="mt-2">No instruments found</div></div>`;
            return;
        }

        const frag = instruments.map(instrument => `
            <div class="instrument-item" data-id="${instrument.id}" data-symbol="${instrument.symbol}" data-name="${instrument.name}">
                <div class="instrument-symbol">${instrument.symbol}</div>
                <div class="instrument-name">${instrument.name}</div>
            </div>
        `).join('');

        container.innerHTML = frag;
    }

    selectInstrument(id, symbol, name) {
        this.selectedInstrument = { id, symbol, name };

        // Update hidden inputs
        const idInput = document.getElementById('instrument_id');
        const symbolInput = document.getElementById('symbol');
        if (idInput) idInput.value = id;
        if (symbolInput) symbolInput.value = symbol;

        // Update display
        const display = document.getElementById('selected-instrument');
        if (display) {
            display.innerHTML = `<strong>${symbol}</strong> - ${name}`;
        }

        // Update header instrument code if present
        const headerCode = document.getElementById('header-instrument-code');
        if (headerCode) headerCode.textContent = symbol;

        // Remove selection from all items
        document.querySelectorAll('.instrument-item').forEach(item => {
            item.classList.remove('selected');
        });

        // Add selection to clicked item
        const selectedItem = document.querySelector(`[data-id="${id}"]`);
        if (selectedItem) {
            selectedItem.classList.add('selected');
        }

        // Trigger P&L calculation if calculator exists
        if (window.tradeCalculator) {
            window.tradeCalculator.calculate();
        }
    }

    clearSelection() {
        this.selectedInstrument = null;

        // Clear inputs
        const idInput = document.getElementById('instrument_id');
        const symbolInput = document.getElementById('symbol');
        if (idInput) idInput.value = '';
        if (symbolInput) symbolInput.value = '';

        // Clear display
        const display = document.getElementById('selected-instrument');
        if (display) {
            display.innerHTML = '<small class="text-muted">No instrument selected</small>';
        }

        // Remove selection styling
        document.querySelectorAll('.instrument-item').forEach(item => {
            item.classList.remove('selected');
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    const picker = new SimpleInstrumentPicker();

    // Make it globally available for P&L calculator
    window.instrumentPicker = picker;

    // Initialize P&L calculator if it exists
    if (window.TradeCalculator) {
        window.tradeCalculator = new TradeCalculator();
    }
});
