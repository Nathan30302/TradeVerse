/**
 * Instrument Picker & Trade Calculator
 * Category-first instrument selector with automatic P&L calculations
 *
 * Note: add-trade and similar screens use instrument-picker-simple.js; keep behavior aligned when changing APIs.
 *
 * FIXES APPLIED:
 *   1. renderInstruments: data-json now uses encodeURIComponent() to safely embed
 *      JSON in HTML attributes. The old replace(/</g, '<') did NOT escape single
 *      quotes — any instrument name/symbol containing a single quote (e.g. "Ivory
 *      Coast's CFD") would break the attribute boundary, causing JSON.parse() to
 *      throw silently and the instrument not to render at all. This explains why
 *      some categories showed 2–4 items instead of the full list.
 *
 *   2. selectInstrument: Updated to decodeURIComponent() before JSON.parse() to
 *      match Fix #1.
 *
 *   3. showInstrumentsForCategory: Added e.stopPropagation() to category button
 *      click handler so the click doesn't bubble up to the document-level outside-
 *      click listener, which was calling closeDropdown() and wiping the freshly
 *      rendered list (the "2-second flash" symptom).
 *
 *   4. The API call uses a capped limit to avoid huge payloads.
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
                e.stopPropagation(); // prevent bubbling to document close-handler
                this.toggleDropdown();
            });
        }

        if (dropdown) {
            // Close when clicking OUTSIDE the picker container
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

        // Safe DOM rendering (no innerHTML)
        dropdown.textContent = '';
        const header = document.createElement('div');
        header.className = 'category-header';
        header.textContent = 'Select Category';
        const grid = document.createElement('div');
        grid.className = 'category-grid';

        this.categories.forEach((category) => {
            const label = this.getCategoryLabel(category);
            const icon = this.getCategoryIcon(category);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'category-btn';
            btn.dataset.category = category;
            const i = document.createElement('i');
            i.className = icon;
            const span = document.createElement('span');
            span.textContent = label;
            btn.appendChild(i);
            btn.appendChild(document.createTextNode(' '));
            btn.appendChild(span);
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showInstrumentsForCategory(category);
            });
            grid.appendChild(btn);
        });

        dropdown.appendChild(header);
        dropdown.appendChild(grid);
        dropdown.classList.add('show');
    }

    async showInstrumentsForCategory(category) {
        this.currentCategory = category;
        const dropdown = document.getElementById('instrument-dropdown');
        if (!dropdown) return;

        // Show loading
        dropdown.textContent = '';
        const loading = document.createElement('div');
        loading.className = 'dropdown-hint';
        loading.textContent = 'Loading instruments...';
        dropdown.appendChild(loading);
        dropdown.classList.add('show'); // ensure it stays open during fetch

        // Abort previous request
        if (this._abortController) this._abortController.abort();
        this._abortController = new AbortController();

        try {
            // Cap payload size to keep UI responsive.
            const response = await fetch(
                `${this.apiUrl}?category=${encodeURIComponent(category)}&limit=500`,
                { signal: this._abortController.signal }
            );

            if (!response.ok) {
                dropdown.textContent = '';
                const err = document.createElement('div');
                err.className = 'dropdown-hint';
                err.textContent = 'Error loading instruments';
                dropdown.appendChild(err);
                return;
            }

            const instruments = await response.json();
            this.renderInstruments(instruments, category);

        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('Failed to load instruments:', error);
            dropdown.textContent = '';
            const err = document.createElement('div');
            err.className = 'dropdown-hint';
            err.textContent = 'Error loading instruments';
            dropdown.appendChild(err);
        }
    }

    renderInstruments(instruments, category) {
        const dropdown = document.getElementById('instrument-dropdown');
        if (!dropdown) return;

        if (instruments.length === 0) {
            dropdown.textContent = '';
            const hint = document.createElement('div');
            hint.className = 'dropdown-hint';
            hint.textContent = 'No instruments found';
            dropdown.appendChild(hint);
            return;
        }

        const categoryLabel = this.getCategoryLabel(category);
        dropdown.textContent = '';
        const header = document.createElement('div');
        header.className = 'category-header';
        const backBtn = document.createElement('button');
        backBtn.type = 'button';
        backBtn.className = 'back-btn';
        backBtn.dataset.action = 'back';
        const backIcon = document.createElement('i');
        backIcon.className = 'fas fa-arrow-left';
        backBtn.appendChild(backIcon);
        header.appendChild(backBtn);
        header.appendChild(document.createTextNode(' ' + categoryLabel + ' Instruments'));

        const list = document.createElement('div');
        list.className = 'instruments-list';

        instruments.forEach((inst) => {
            const item = document.createElement('div');
            item.className = 'instrument-item';
            item.dataset.id = String(inst.id);
            item.dataset.json = encodeURIComponent(JSON.stringify(inst));
            const sym = document.createElement('div');
            sym.className = 'instrument-symbol';
            sym.textContent = String(inst.symbol || '');
            const name = document.createElement('div');
            name.className = 'instrument-name';
            name.textContent = String(inst.name || inst.symbol || '');
            item.appendChild(sym);
            item.appendChild(name);
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectInstrument(item);
            });
            list.appendChild(item);
        });

        dropdown.appendChild(header);
        dropdown.appendChild(list);
        dropdown.classList.add('show'); // keep open after render

        // Add back button handler
        if (backBtn) {
            backBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showCategories();
            });
        }
    }

    selectInstrument(element) {
        const jsonData = element.dataset.json;
        let inst = null;
        try {
            // FIX #2: Decode the URI-encoded JSON string before parsing.
            // Matches the encodeURIComponent() encoding applied in renderInstruments.
            inst = jsonData ? JSON.parse(decodeURIComponent(jsonData)) : null;
        } catch (e) {
            console.error('Failed to parse instrument JSON:', e);
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
            selectorBtn.textContent = '';
            const i = document.createElement('i');
            i.className = 'fas fa-check';
            selectorBtn.appendChild(i);
            selectorBtn.appendChild(document.createTextNode(` ${inst.symbol} - ${inst.name || inst.symbol}`));
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
            meta.textContent = '';
            const row1 = document.createElement('div');
            row1.className = 'instrument-meta-row';
            const strong = document.createElement('strong');
            strong.textContent = String(inst.name || inst.symbol || '');
            const span = document.createElement('span');
            span.className = 'text-muted';
            span.textContent = ` (${inst.symbol || ''})`;
            row1.appendChild(strong);
            row1.appendChild(document.createTextNode(' '));
            row1.appendChild(span);

            const row2 = document.createElement('div');
            row2.className = 'instrument-meta-row small text-muted';
            row2.textContent = `Type: ${inst.type || 'unknown'} | Category: ${this.getCategoryLabel(inst.category || 'unknown')}`;

            const row3 = document.createElement('div');
            row3.className = 'instrument-meta-row small text-muted';
            row3.textContent = `Pip/Tick: ${inst.pip_size || inst.tick_value || '-'} | Contract Size: ${inst.contract_size || '-'}`;

            const row4 = document.createElement('div');
            row4.className = 'instrument-meta-row small text-muted';
            row4.textContent = `Price Decimals: ${typeof inst.price_decimals !== 'undefined' ? inst.price_decimals : '-'}`;

            meta.appendChild(row1);
            meta.appendChild(row2);
            meta.appendChild(row3);
            meta.appendChild(row4);
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
            selectorBtn.textContent = '';
            const i = document.createElement('i');
            i.className = 'fas fa-search';
            selectorBtn.appendChild(i);
            selectorBtn.appendChild(document.createTextNode(' Select Instrument'));
            selectorBtn.classList.remove('btn-success');
            selectorBtn.classList.add('btn-outline-primary');
        }
        if (meta) meta.textContent = '';

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
                        selectorBtn.textContent = '';
                        const i = document.createElement('i');
                        i.className = 'fas fa-check';
                        selectorBtn.appendChild(i);
                        selectorBtn.appendChild(document.createTextNode(` ${inst.symbol} - ${inst.name || inst.symbol}`));
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
            display.textContent = '';
            const div = document.createElement('div');
            div.className = 'text-muted';
            div.textContent = 'Enter prices to calculate P&L';
            display.appendChild(div);
            return;
        }

        const isProfit = data.profit_loss > 0;
        const color = isProfit ? '#28a745' : '#dc3545';

        display.textContent = '';
        const wrap = document.createElement('div');
        wrap.style.borderLeft = `4px solid ${color}`;
        wrap.style.padding = '1rem';
        wrap.style.background = 'rgba(0,0,0,0.02)';
        wrap.style.borderRadius = '4px';

        const value = document.createElement('div');
        value.className = 'pnl-value';
        value.style.color = color;
        value.style.fontSize = '1.5rem';
        value.style.fontWeight = 'bold';
        value.textContent = `${isProfit ? '+' : ''}${Number(data.profit_loss).toFixed(2)}`;

        const pips = document.createElement('div');
        pips.className = 'pnl-pips text-muted';
        pips.style.fontSize = '0.9rem';
        const pop = (typeof data.pips_or_points === 'number') ? data.pips_or_points : 0;
        pips.textContent = `${Number(pop).toFixed(1)} ${this.getUnitLabel(data.instrument_type)}`;

        wrap.appendChild(value);
        wrap.appendChild(pips);
        display.appendChild(wrap);
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