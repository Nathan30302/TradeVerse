/**
 * Instrument Picker & Trade Calculator
 * Category-first instrument selector with automatic P&L calculations
 */

class InstrumentPicker {
    constructor(options = {}) {
        this.apiUrl = options.apiUrl || '/api/instruments';
        this.pickerId = options.pickerId || 'instrument-picker';
        this.selectedInstrument = null;
        this.categories = [];
        this.currentCategory = null;
        this.instruments = [];
        this._abortController = null;
        this.init();
    }

    async init() {
        await this.loadCategories();
        this.setupEventListeners();
        this.preselectInstrumentIfPresent();
    }

    async loadCategories() {
        try {
            const response = await fetch(`${this.apiUrl}/categories`);
            if (response.ok) {
                const categoryCounts = await response.json();
                this.categories = Object.keys(categoryCounts).sort();
            } else {
                // Fallback categories
                this.categories = ['forex', 'crypto_cross', 'crypto', 'indices', 'stocks', 'commodity', 'forexindicator'];
            }
        } catch (error) {
            console.error('Failed to load categories:', error);
            this.categories = ['forex', 'crypto_cross', 'crypto', 'indices', 'stocks', 'commodity', 'forexindicator'];
        }
    }

    setupEventListeners() {
        const selectorBtn = document.getElementById('instrument-selector');
        const dropdown = document.getElementById('instrument-dropdown');
        const clearBtn = document.getElementById('clear-instrument-selection');

        if (selectorBtn) {
            selectorBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.toggleDropdown();
            });
        }

        if (dropdown) {
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.instrument-picker-container')) {
                    this.closeDropdown();
                }
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.clearSelection();
            });
        }
    }

    toggleDropdown() {
        const dropdown = document.getElementById('instrument-dropdown');
        if (!dropdown) return;

        if (dropdown.classList.contains('show')) {
            this.closeDropdown();
        } else {
            this.showCategories();
        }
    }

    closeDropdown() {
        const dropdown = document.getElementById('instrument-dropdown');
        if (dropdown) {
            dropdown.classList.remove('show');
            this.currentCategory = null;
        }
    }

    showCategories() {
        const dropdown = document.getElementById('instrument-dropdown');
        if (!dropdown) return;

        let html = '<div class="category-header">Select Category</div>';
        html += '<div class="category-grid">';

        this.categories.forEach(category => {
            const label = this.getCategoryLabel(category);
            const icon = this.getCategoryIcon(category);
            html += `<button type="button" class="category-btn" data-category="${category}">
                <i class="${icon}"></i>
                <span>${label}</span>
            </button>`;
        });

        html += '</div>';
        dropdown.innerHTML = html;
        dropdown.classList.add('show');

        // Add category button handlers
        dropdown.querySelectorAll('.category-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const category = e.currentTarget.dataset.category;
                this.showInstrumentsForCategory(category);
            });
        });
    }

    async showInstrumentsForCategory(category) {
        this.currentCategory = category;
        const dropdown = document.getElementById('instrument-dropdown');
        if (!dropdown) return;

        // Show loading
        dropdown.innerHTML = '<div class="dropdown-hint">Loading instruments...</div>';

        // Abort previous request
        if (this._abortController) this._abortController.abort();
        this._abortController = new AbortController();

        try {
            const response = await fetch(`${this.apiUrl}?category=${encodeURIComponent(category)}&limit=10000`, {
                signal: this._abortController.signal
            });

            if (!response.ok) {
                dropdown.innerHTML = '<div class="dropdown-hint">Error loading instruments</div>';
                return;
            }

            const instruments = await response.json();
            this.renderInstruments(instruments, category);

        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('Failed to load instruments:', error);
            dropdown.innerHTML = '<div class="dropdown-hint">Error loading instruments</div>';
        }
    }

    renderInstruments(instruments, category) {
        const dropdown = document.getElementById('instrument-dropdown');
        if (!dropdown) return;

        if (instruments.length === 0) {
            dropdown.innerHTML = '<div class="dropdown-hint">No instruments found</div>';
            return;
        }

        const categoryLabel = this.getCategoryLabel(category);
        let html = `<div class="category-header">
            <button type="button" class="back-btn" data-action="back">
                <i class="fas fa-arrow-left"></i>
            </button>
            ${categoryLabel} Instruments
        </div>`;

        html += '<div class="instruments-list">';

        instruments.forEach(inst => {
            const safe = JSON.stringify(inst).replace(/</g, '<');
            html += `<div class="instrument-item" data-id="${inst.id}" data-json='${safe}'>
                <div class="instrument-symbol">${inst.symbol}</div>
                <div class="instrument-name">${inst.name || inst.symbol}</div>
            </div>`;
        });

        html += '</div>';

        dropdown.innerHTML = html;

        // Add back button handler
        const backBtn = dropdown.querySelector('.back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => this.showCategories());
        }

        // Add instrument selection handlers
        dropdown.querySelectorAll('.instrument-item').forEach(item => {
            item.addEventListener('click', () => this.selectInstrument(item));
        });
    }

    selectInstrument(element) {
        const jsonData = element.dataset.json;
        let inst = null;
        try {
            inst = jsonData ? JSON.parse(jsonData) : null;
        } catch (e) {
            inst = null;
        }

        if (!inst) return;

        this.selectedInstrument = inst;

        // Update form fields
        const hiddenInput = document.getElementById('instrument_id');
        const symbolInput = document.getElementById('symbol');
        const selectorBtn = document.getElementById('instrument-selector');

        if (hiddenInput) hiddenInput.value = inst.id;
        if (symbolInput) symbolInput.value = inst.symbol;
        if (selectorBtn) {
            selectorBtn.innerHTML = `<i class="fas fa-check"></i> ${inst.symbol} - ${inst.name || inst.symbol}`;
            selectorBtn.classList.remove('btn-outline-primary');
            selectorBtn.classList.add('btn-success');
        }

        this.closeDropdown();

        // Trigger recalculation
        this.triggerPnLRecalculation();

        // Update metadata display
        this.updateMetadataDisplay(inst);
    }

    updateMetadataDisplay(inst) {
        const meta = document.getElementById('instrument-meta');
        if (meta && inst) {
            meta.innerHTML = `
                <div class="instrument-meta-row"><strong>${inst.name || inst.symbol}</strong> <span class="text-muted">(${inst.symbol})</span></div>
                <div class="instrument-meta-row small text-muted">Type: ${inst.type || 'unknown'} | Category: ${this.getCategoryLabel(inst.category || 'unknown')}</div>
                <div class="instrument-meta-row small text-muted">Pip/Tick: ${inst.pip_size || inst.tick_value || '-'} | Contract Size: ${inst.contract_size || '-'}</div>
                <div class="instrument-meta-row small text-muted">Price Decimals: ${typeof inst.price_decimals !== 'undefined' ? inst.price_decimals : '-'}</div>
            `;
        }
    }

    clearSelection() {
        this.selectedInstrument = null;
        const hiddenInput = document.getElementById('instrument_id');
        const symbolInput = document.getElementById('symbol');
        const selectorBtn = document.getElementById('instrument-selector');
        const meta = document.getElementById('instrument-meta');

        if (hiddenInput) hiddenInput.value = '';
        if (symbolInput) symbolInput.value = '';
        if (selectorBtn) {
            selectorBtn.innerHTML = '<i class="fas fa-search"></i> Select Instrument';
            selectorBtn.classList.remove('btn-success');
            selectorBtn.classList.add('btn-outline-primary');
        }
        if (meta) meta.innerHTML = '';

        this.closeDropdown();
        this.triggerPnLRecalculation();
    }

    preselectInstrumentIfPresent() {
        // If form has an instrument_id prefilled (edit page), set metadata and symbol
        const instId = document.getElementById('instrument_id')?.value;
        const symbolInput = document.getElementById('symbol');
        const selectorBtn = document.getElementById('instrument-selector');
        if (instId) {
            // fetch instrument by id to get full metadata
            fetch(`${this.apiUrl}/${encodeURIComponent(instId)}`)
                .then(r => r.ok ? r.json() : null)
                .then(inst => {
                    if (!inst) return;
                    this.selectedInstrument = inst;
                    if (symbolInput && !symbolInput.value) symbolInput.value = inst.symbol;
                    if (selectorBtn) {
                        selectorBtn.innerHTML = `<i class="fas fa-check"></i> ${inst.symbol} - ${inst.name || inst.symbol}`;
                        selectorBtn.classList.remove('btn-outline-primary');
                        selectorBtn.classList.add('btn-success');
                    }
                    this.updateMetadataDisplay(inst);
                })
                .catch(err => console.error('Failed to fetch instrument for preselect:', err));
        }
    }

    triggerPnLRecalculation() {
        const event = new Event('instrumentChanged', { bubbles: true });
        document.getElementById('symbol')?.dispatchEvent(event);
    }

    getCategoryLabel(category) {
        const labels = {
            'forex': 'Forex',
            'index': 'Indices',
            'indices': 'Indices',
            'crypto': 'Cryptocurrency',
            'crypto_cross': 'Crypto Cross',
            'commodity': 'Energies',
            'energies': 'Energies',
            'stock': 'Stocks',
            'stocks': 'Stocks',
            'forexindicator': 'Forex Indicator',
            'forex_indicator': 'Forex Indicator'
        };
        return labels[category] || category.charAt(0).toUpperCase() + category.slice(1);
    }

    getCategoryIcon(category) {
        const icons = {
            'forex': 'fas fa-exchange-alt',
            'index': 'fas fa-chart-line',
            'indices': 'fas fa-chart-line',
            'crypto': 'fab fa-bitcoin',
            'crypto_cross': 'fab fa-bitcoin',
            'commodity': 'fas fa-oil-can',
            'energies': 'fas fa-oil-can',
            'stock': 'fas fa-building',
            'stocks': 'fas fa-building',
            'forexindicator': 'fas fa-chart-line',
            'forex_indicator': 'fas fa-chart-line'
        };
        return icons[category] || 'fas fa-question';
    }
}

/**
 * Trade P&L Calculator
 * Real-time P&L calculations with type-specific formulas
 */
class TradeCalculator {
    constructor() {
        this.instrumentData = null;
        this.setupCalculatorListeners();
    }

    setupCalculatorListeners() {
        const fields = ['entry_price', 'exit_price', 'lot_size'];

        fields.forEach(fieldId => {
            const field = document.getElementById(fieldId);
            if (field) {
                field.addEventListener('change', () => this.calculatePnL());
                field.addEventListener('input', () => this.calculatePnL());
            }
        });

        // Listen for instrument changes
        document.addEventListener('instrumentChanged', () => this.calculatePnL());
    }

    async calculatePnL() {
        const entryPrice = parseFloat(document.getElementById('entry_price')?.value) || 0;
        const exitPrice = parseFloat(document.getElementById('exit_price')?.value) || 0;
        const lotSize = parseFloat(document.getElementById('lot_size')?.value) || 1;
        const tradeType = document.getElementById('trade_type')?.value || 'BUY';
        const instrumentId = document.getElementById('instrument_id')?.value;

        if (!entryPrice || !exitPrice || !instrumentId) {
            this.updateDisplay({});
            return;
        }

        try {
            const response = await fetch('/api/calculate-pnl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': document.querySelector('[name="csrf_token"]')?.value
                },
                body: JSON.stringify({
                    instrument_id: instrumentId,
                    entry_price: entryPrice,
                    exit_price: exitPrice,
                    lot_size: lotSize,
                    trade_type: tradeType
                })
            });

            if (response.ok) {
                const result = await response.json();
                this.updateDisplay(result);
            }
        } catch (error) {
            console.error('P&L calculation error:', error);
        }
    }

    updateDisplay(data) {
        const display = document.getElementById('pnl-display');
        if (!display) return;

        if (!data.profit_loss) {
            display.innerHTML = '<div class="text-muted">Enter prices to calculate P&L</div>';
            return;
        }

        const isProfit = data.profit_loss > 0;
        const color = isProfit ? '#28a745' : '#dc3545';

        display.innerHTML = `
            <div style="border-left: 4px solid ${color}; padding: 1rem; background: rgba(0,0,0,0.02); border-radius: 4px;">
                <div class="pnl-value" style="color: ${color}; font-size: 1.5rem; font-weight: bold;">
                    ${isProfit ? '+' : ''}${data.profit_loss.toFixed(2)}
                </div>
                <div class="pnl-pips text-muted" style="font-size: 0.9rem;">
                    ${data.pips_or_points?.toFixed(1) || '0'} ${this.getUnitLabel(data.instrument_type)}
                </div>
            </div>
        `;
    }

    getUnitLabel(type) {
        const labels = {
            'forex': 'pips',
            'index': 'points',
            'crypto': 'units',
            'stock': 'units',
            'commodity': 'contracts'
        };
        return labels[type] || 'units';
    }
}

/**
 * Initialize on page load
 */
document.addEventListener('DOMContentLoaded', () => {
    const picker = new InstrumentPicker({
        pickerId: 'instrument-picker'
    });

    const calculator = new TradeCalculator();
});
