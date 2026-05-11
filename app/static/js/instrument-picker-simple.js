/**
 * Instrument picker for Add Trade — categories, instant search, recents & pins.
 */

class SimpleInstrumentPicker {
    constructor(options = {}) {
        this.apiUrl = options.apiUrl || '/api/instruments';
        this.selectedInstrument = null;
        this.currentCategory = 'forex';
        this.instruments = {};
        this._initialCategorySet = false;
        this._searchTimer = null;
        this._lastSearchQuery = '';
        this.init();
    }

    _userId() {
        const b = document.body && document.body.getAttribute('data-user-id');
        return (b && String(b).trim()) ? String(b).trim() : 'anon';
    }

    _recentsKey() {
        return `tradev_inst_recents_${this._userId()}`;
    }

    _pinsKey() {
        return `tradev_inst_pins_${this._userId()}`;
    }

    _readJson(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            if (!raw) return fallback;
            const v = JSON.parse(raw);
            return Array.isArray(v) ? v : fallback;
        } catch (e) {
            return fallback;
        }
    }

    _writeJson(key, arr) {
        try {
            localStorage.setItem(key, JSON.stringify(arr.slice(0, 48)));
        } catch (e) { /* quota */ }
    }

    getPins() {
        return this._readJson(this._pinsKey(), []);
    }

    getRecents() {
        return this._readJson(this._recentsKey(), []);
    }

    isPinned(id) {
        const s = String(id);
        return this.getPins().some((x) => String(x.id) === s);
    }

    togglePin(id, symbol, name) {
        const pins = this.getPins();
        const s = String(id);
        const next = pins.some((x) => String(x.id) === s)
            ? pins.filter((x) => String(x.id) !== s)
            : [{ id, symbol, name: name || symbol }, ...pins].slice(0, 24);
        this._writeJson(this._pinsKey(), next);
        this.renderQuickChips();
        this.loadInstrumentsForCategory(this.currentCategory);
    }

    addRecent(obj) {
        if (!obj || !obj.id || !obj.symbol) return;
        const rec = this.getRecents().filter((x) => String(x.id) !== String(obj.id));
        rec.unshift({ id: obj.id, symbol: obj.symbol, name: obj.name || obj.symbol });
        this._writeJson(this._recentsKey(), rec.slice(0, 12));
        this.renderQuickChips();
    }

    renderQuickChips() {
        const recEl = document.getElementById('tv-inst-recents');
        const pinEl = document.getElementById('tv-inst-pinned');
        if (!recEl || !pinEl) return;
        recEl.textContent = '';
        pinEl.textContent = '';
        const mk = (container, items, isPinRow) => {
            if (!items.length) {
                const s = document.createElement('span');
                s.className = 'text-muted fst-italic';
                s.textContent = isPinRow ? 'Tap ★ on a symbol to pin' : 'Your picks appear here';
                container.appendChild(s);
                return;
            }
            items.forEach((it) => {
                const chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'tv-inst-chip' + (isPinRow ? ' is-pinned' : '');
                chip.dataset.id = String(it.id);
                chip.dataset.symbol = String(it.symbol || '');
                chip.dataset.name = String(it.name || it.symbol || '');
                const sym = document.createElement('span');
                this._fillSymbolSpan(sym, it.symbol || '');
                chip.appendChild(sym);
                const star = document.createElement('span');
                star.className = 'tv-chip-pin';
                star.innerHTML = isPinRow ? '<i class="fas fa-star"></i>' : '<i class="far fa-star"></i>';
                star.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    this.togglePin(it.id, it.symbol, it.name);
                });
                chip.appendChild(star);
                chip.addEventListener('click', () => {
                    this.selectInstrument(String(it.id), String(it.symbol), String(it.name || it.symbol));
                });
                container.appendChild(chip);
            });
        };
        mk(recEl, this.getRecents(), false);
        mk(pinEl, this.getPins(), true);
    }

    _fillSymbolSpan(el, symbol) {
        el.textContent = '';
        const s = String(symbol || '').toUpperCase();
        if (/^[A-Z]{6}$/.test(s)) {
            const a = document.createElement('span');
            a.className = 'tv-sym-base';
            a.textContent = s.slice(0, 3);
            const b = document.createElement('span');
            b.className = 'tv-sym-quote';
            b.textContent = s.slice(3);
            el.appendChild(a);
            el.appendChild(b);
        } else {
            el.textContent = symbol || '';
        }
    }

    async init() {
        this.setupEventListeners();
        this.setupSearch();
        this.renderQuickChips();
        await this.loadCategories();
        await this.loadInstrumentsForCategory(this.currentCategory);
    }

    setupSearch() {
        const el = document.getElementById('instrument-search');
        if (!el) return;
        el.addEventListener('input', () => {
            clearTimeout(this._searchTimer);
            const q = el.value.trim();
            const hint = document.getElementById('instrument-search-hint');
            if (q.length < 1) {
                if (hint) hint.classList.add('d-none');
                this.loadInstrumentsForCategory(this.currentCategory);
                return;
            }
            if (hint) hint.classList.remove('d-none');
            this._searchTimer = setTimeout(() => this.runSearch(q), 100);
        });
    }

    async runSearch(q) {
        this._lastSearchQuery = q;
        try {
            const resp = await fetch(`/api/db/instruments/search?q=${encodeURIComponent(q)}&limit=60`);
            if (!resp.ok) {
                this.renderInstruments([], null);
                return;
            }
            const data = await resp.json();
            const instruments = (data && data.results) ? data.results : [];
            if (String(q) !== String(this._lastSearchQuery).trim()) return;
            this.renderInstruments(instruments, null);
        } catch (e) {
            console.warn('[InstrumentPicker] search failed', e);
        }
    }

    async loadCategories() {
        try {
            const resp = await fetch('/api/db/instruments/categories');
            if (!resp.ok) return;
            const data = await resp.json();
            const categories = data && data.categories ? data.categories : null;
            if (!categories) return;
            const categoryKeys = Object.keys(categories);
            const templateTabs = document.querySelectorAll('.category-tab');
            const templateCount = templateTabs.length;
            if (categoryKeys.length >= templateCount) {
                this.renderCategoryTabs(categories);
            } else {
                const currentTabExists = categoryKeys.includes(this.currentCategory);
                if (!currentTabExists && categoryKeys.length > 0) {
                    this.currentCategory = categoryKeys[0];
                    await this.loadInstrumentsForCategory(this.currentCategory);
                }
            }
        } catch (error) {
            console.error('[InstrumentPicker] Failed to load categories:', error);
        }
    }

    renderCategoryTabs(categories) {
        const container = document.querySelector('.instrument-categories');
        if (!container) return;
        const entries = Object.entries(categories);
        if (entries.length === 0) return;
        const keys = entries.map((e) => e[0]);
        if (!keys.includes(this.currentCategory)) {
            this.currentCategory = keys[0];
        }
        container.textContent = '';
        entries.forEach(([key, val]) => {
            const rawName = (val && val.name) ? String(val.name) : String(key);
            const n = rawName.toLowerCase();
            let icon = 'fas fa-square-question';
            if (n.includes('forex') && !n.includes('indicator')) icon = 'fas fa-exchange-alt';
            else if (n.includes('crypto') && n.includes('cross')) icon = 'fas fa-share-alt';
            else if (n.includes('crypto')) icon = 'fab fa-bitcoin';
            else if (n.includes('energy') || n.includes('ener')) icon = 'fas fa-bolt';
            else if (n.includes('index') || n.includes('indices') || n.includes('idx')) icon = 'fas fa-chart-line';
            else if (n.includes('stock') || n.includes('stocks')) icon = 'fas fa-building';
            else if (n.includes('metal') || n.includes('commodity')) icon = 'fas fa-gem';
            else if (n.includes('forex indicator') || n.includes('indicator')) icon = 'fas fa-wave-square';
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `category-tab ${key === this.currentCategory ? 'active' : ''}`.trim();
            btn.dataset.category = key;
            const i = document.createElement('i');
            i.className = icon;
            btn.appendChild(i);
            btn.appendChild(document.createTextNode(' ' + rawName));
            container.appendChild(btn);
        });
    }

    setupEventListeners() {
        document.addEventListener('click', (e) => {
            if (e.target.closest('.category-tab')) {
                const tab = e.target.closest('.category-tab');
                const category = tab.dataset.category;
                this.switchCategory(category);
            }
        });
        document.addEventListener('click', (e) => {
            const pinBtn = e.target.closest('.inst-pin-btn');
            if (pinBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = pinBtn.dataset.id;
                const symbol = pinBtn.dataset.symbol;
                const name = pinBtn.dataset.name;
                this.togglePin(id, symbol, name);
                return;
            }
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
        const searchEl = document.getElementById('instrument-search');
        if (searchEl) searchEl.value = '';
        const hint = document.getElementById('instrument-search-hint');
        if (hint) hint.classList.add('d-none');
        this.currentCategory = category;
        document.querySelectorAll('.category-tab').forEach((tab) => {
            try {
                tab.classList.toggle('active', tab.dataset.category === category);
            } catch (err) {
                tab.classList.remove('active');
            }
        });
        await this.loadInstrumentsForCategory(category);
    }

    async loadInstrumentsForCategory(category) {
        try {
            const response = await fetch(`/api/db/instruments?category=${encodeURIComponent(category)}&limit=200&offset=0`);
            if (!response.ok) {
                this.renderInstruments([], null);
                return;
            }
            const data = await response.json();
            const instruments = (data && data.results) ? data.results : [];
            this.renderInstruments(instruments, data);
        } catch (error) {
            console.error('Failed to load instruments:', error);
        }
    }

    _appendInstrumentRow(container, instrument) {
        const item = document.createElement('div');
        item.className = 'instrument-item';
        item.dataset.id = String(instrument.id);
        item.dataset.symbol = String(instrument.symbol || '');
        item.dataset.name = String(instrument.name || '');
        const pin = document.createElement('button');
        pin.type = 'button';
        pin.className = 'inst-pin-btn' + (this.isPinned(instrument.id) ? ' is-pinned' : '');
        pin.dataset.id = String(instrument.id);
        pin.dataset.symbol = String(instrument.symbol || '');
        pin.dataset.name = String(instrument.name || '');
        pin.title = this.isPinned(instrument.id) ? 'Unpin' : 'Pin favorite';
        pin.innerHTML = this.isPinned(instrument.id) ? '<i class="fas fa-star text-warning"></i>' : '<i class="far fa-star"></i>';
        const sym = document.createElement('div');
        sym.className = 'instrument-symbol';
        this._fillSymbolSpan(sym, instrument.symbol || '');
        const name = document.createElement('div');
        name.className = 'instrument-name';
        name.textContent = String(instrument.name || '');
        item.appendChild(pin);
        item.appendChild(sym);
        item.appendChild(name);
        container.appendChild(item);
    }

    renderInstruments(instruments, meta = null) {
        const container = document.getElementById('instrument-list');
        if (!container) return;
        container.textContent = '';

        if (!Array.isArray(instruments) || instruments.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            const icon = document.createElement('i');
            icon.className = 'fas fa-search';
            const text = document.createElement('div');
            text.className = 'mt-2';
            text.textContent = 'No instruments match';
            empty.appendChild(icon);
            empty.appendChild(text);
            container.appendChild(empty);
            return;
        }

        instruments.forEach((instrument) => {
            this._appendInstrumentRow(container, instrument);
        });

        if (meta && meta.has_more) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-outline-secondary btn-sm mt-3 w-100';
            btn.textContent = 'Load more';
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                btn.textContent = 'Loading...';
                try {
                    const nextOffset = Number(meta.offset || 0) + Number(meta.limit || 200);
                    const resp = await fetch(`/api/db/instruments?category=${encodeURIComponent(this.currentCategory)}&limit=200&offset=${nextOffset}`);
                    if (!resp.ok) return;
                    const next = await resp.json();
                    const nextResults = (next && next.results) ? next.results : [];
                    nextResults.forEach((instrument) => {
                        this._appendInstrumentRow(container, instrument);
                    });
                    meta = next;
                    if (!next.has_more) {
                        btn.remove();
                    } else {
                        btn.disabled = false;
                        btn.textContent = 'Load more';
                    }
                } catch (err) {
                    btn.disabled = false;
                    btn.textContent = 'Load more';
                }
            });
            container.appendChild(btn);
        }
    }

    selectInstrument(id, symbol, name) {
        this.selectedInstrument = { id, symbol, name };
        const idInput = document.getElementById('instrument_id');
        const symbolInput = document.getElementById('symbol');
        if (idInput) idInput.value = id;
        if (symbolInput) symbolInput.value = symbol;

        const display = document.getElementById('selected-instrument');
        if (display) {
            display.textContent = '';
            const wrap = document.createElement('span');
            wrap.className = 'fw-semibold';
            this._fillSymbolSpan(wrap, symbol || '');
            display.appendChild(wrap);
            display.appendChild(document.createTextNode(' · ' + String(name || '')));
        }

        const headerCode = document.getElementById('header-instrument-code');
        if (headerCode) {
            headerCode.textContent = '';
            this._fillSymbolSpan(headerCode, symbol || '');
        }

        document.querySelectorAll('.instrument-item').forEach((item) => {
            item.classList.toggle('selected', String(item.dataset.id) === String(id));
        });

        this.addRecent({ id, symbol, name: name || symbol });

        if (window.tradeCalculator) {
            window.tradeCalculator.calculate();
        }
    }

    async syncFromHiddenInputs() {
        const idInput = document.getElementById('instrument_id');
        const symbolInput = document.getElementById('symbol');
        if (!idInput || !symbolInput) return;
        const id = String(idInput.value || '').trim();
        let sym = String(symbolInput.value || '').trim();
        if (!id) return;

        let name = sym || '';
        let frontendCat = null;
        let apiSymbol = null;
        try {
            const r = await fetch(`/api/db/instruments/by-id/${encodeURIComponent(id)}`);
            if (r.ok) {
                const j = await r.json();
                if (j && j.success) {
                    if (j.name) name = String(j.name);
                    if (j.frontend_category) frontendCat = String(j.frontend_category);
                    if (j.symbol) apiSymbol = String(j.symbol).trim();
                }
            }
        } catch (e) { /* ignore */ }

        if (apiSymbol) {
            if (!sym || sym.toUpperCase() !== apiSymbol.toUpperCase()) {
                symbolInput.value = apiSymbol;
                sym = apiSymbol;
            }
        }

        if (!sym) return;

        const targetCat = frontendCat || this.currentCategory;
        if (targetCat && targetCat !== this.currentCategory) {
            await this.switchCategory(targetCat);
        } else {
            await this.loadInstrumentsForCategory(this.currentCategory);
        }

        this.selectInstrument(id, sym, name || sym);
    }

    clearSelection() {
        this.selectedInstrument = null;
        const idInput = document.getElementById('instrument_id');
        const symbolInput = document.getElementById('symbol');
        if (idInput) idInput.value = '';
        if (symbolInput) symbolInput.value = '';
        const display = document.getElementById('selected-instrument');
        if (display) {
            display.innerHTML = '<span class="text-muted">No instrument selected</span>';
        }
        const headerCode = document.getElementById('header-instrument-code');
        if (headerCode) headerCode.textContent = 'No symbol';
        document.querySelectorAll('.instrument-item').forEach((item) => {
            item.classList.remove('selected');
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const picker = new SimpleInstrumentPicker();
    window.instrumentPicker = picker;
    if (window.TradeCalculator) {
        window.tradeCalculator = new TradeCalculator();
    }
    setTimeout(() => {
        if (typeof picker.syncFromHiddenInputs === 'function') {
            picker.syncFromHiddenInputs();
        }
    }, 50);
});
