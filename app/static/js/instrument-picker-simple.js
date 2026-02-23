/**
 * Simple Horizontal Instrument Picker
 * Category-based selection with horizontal scrolling
 */

class SimpleInstrumentPicker {
    constructor(options = {}) {
        this.apiUrl = options.apiUrl || '/api/instruments';
        this.selectedInstrument = null;
        this.currentCategory = 'forex';
        this.instruments = {};
        this.init();
    }

    async init() {
        await this.loadCategories();
        this.setupEventListeners();
        this.loadInstrumentsForCategory(this.currentCategory);
    }

    async loadCategories() {
        try {
            // Use DB-backed categories endpoint
            const resp = await fetch('/api/db/instruments/categories');
            if (!resp.ok) {
                console.warn('Could not load categories, status=', resp.status);
                return;
            }

            const data = await resp.json();

            // API returns { success: True, categories: { key: {name: '...'}} }
            const categories = data && data.categories ? data.categories : null;

            // If categories not present, leave existing tabs in the template intact
            if (!categories) {
                return;
            }

            this.renderCategoryTabs(categories);
        } catch (error) {
            console.error('Failed to load categories:', error);
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
