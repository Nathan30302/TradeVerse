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
            const response = await fetch('/api/db/instruments/categories');
            if (response.ok) {
                const categories = await response.json();
                this.renderCategoryTabs(categories);
            }
        } catch (error) {
            console.error('Failed to load categories:', error);
        }
    }

    renderCategoryTabs(categories) {
        const container = document.querySelector('.instrument-categories');
        if (!container) return;

        // Map category names to display names and icons
        const categoryConfig = {
            forex: { name: 'Forex', icon: 'fas fa-exchange-alt' },
            index: { name: 'Indices', icon: 'fas fa-chart-line' },
            crypto: { name: 'Crypto', icon: 'fas fa-bitcoin-sign' },
            commodity: { name: 'Metals', icon: 'fas fa-oil-can' },
            stock: { name: 'Stocks', icon: 'fas fa-building' }
        };

        container.innerHTML = Object.keys(categories).map(category => {
            const config = categoryConfig[category] || { name: category, icon: 'fas fa-question' };
            const isActive = category === this.currentCategory ? 'active' : '';
            return `
                <button type="button" class="category-tab ${isActive}" data-category="${category}">
                    <i class="${config.icon}"></i> ${config.name}
                </button>
            `;
        }).join('');
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

        // Update active tab
        document.querySelectorAll('.category-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelector(`[data-category="${category}"]`).classList.add('active');

        // Load instruments for category
        await this.loadInstrumentsForCategory(category);
    }

    async loadInstrumentsForCategory(category) {
        try {
            const response = await fetch(`/api/db/instruments?category=${category}&limit=10000`);
            if (response.ok) {
                const instruments = await response.json();
                this.renderInstruments(instruments.results || []);
            }
        } catch (error) {
            console.error('Failed to load instruments:', error);
        }
    }

    renderInstruments(instruments) {
        const container = document.getElementById('instrument-list');
        if (!container) return;

        if (instruments.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-3">No instruments found</div>';
            return;
        }

        container.innerHTML = instruments.map(instrument => `
            <div class="instrument-item" data-id="${instrument.id}" data-symbol="${instrument.symbol}" data-name="${instrument.name}">
                <div class="instrument-symbol">${instrument.symbol}</div>
                <div class="instrument-name">${instrument.name}</div>
            </div>
        `).join('');
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
