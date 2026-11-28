import * as config from '../configuration/config.js';
import { readStorageValue, removeStorageValue, writeStorageValue } from '../storage/storage.js';

export type Portions = Record<string, number>;
export interface VesselPortions {
    first: Portions;
    second: Portions;
    secondVisible: boolean;
    secondColor: string;
    firstType: config.LabState['currentVessel'];
}

const STORAGE_KEY = config.getLabStorageKey('twoVessels');
const PORTION = 30;
let vessels: VesselPortions = { first: {}, second: {}, secondVisible: false, secondColor: '#2b9ed8', firstType: 'flask' };
let destination: 'first' | 'second' = 'first';

export function chemicalIds(portions: Portions): string[] {
    return Object.keys(portions).filter(id => portions[id] > 0);
}

export function totalPortions(portions: Portions): number {
    return Object.values(portions).reduce((sum, count) => sum + count, 0);
}

export function canHold(portions: Portions): boolean {
    const ids = chemicalIds(portions);
    return ids.length <= 1 || (ids.length === 2 && config.isSupportedReactionSetup(ids));
}

export function transferHalf(current: VesselPortions, from: 'first' | 'second'): VesselPortions | null {
    if (!current.secondVisible) return null;
    const to = from === 'first' ? 'second' : 'first';
    const source = current[from];
    if (totalPortions(source) === 0) return null;
    const moved = Object.fromEntries(Object.entries(source).map(([id, amount]) => [id, Math.ceil(amount / 2)]));
    const nextSource = Object.fromEntries(Object.entries(source).map(([id, amount]) => [id, amount - moved[id]]));
    const nextTarget = { ...current[to] };
    for (const [id, amount] of Object.entries(moved)) nextTarget[id] = (nextTarget[id] || 0) + amount;
    if (totalPortions(nextTarget) > 210 || !canHold(nextTarget)) return null;
    return { ...current, [from]: nextSource, [to]: nextTarget };
}

function save(): void {
    writeStorageValue(STORAGE_KEY, JSON.stringify(vessels));
}

function announce(message: string): void {
    const status = document.getElementById('vessel-transfer-status');
    if (status) status.textContent = message;
}

function hasFirstVessel(): boolean {
    return ['flask', 'beaker', 'tube', 'cylinder'].some(type =>
        document.getElementById(`opt-${type}`)?.classList.contains('selected'));
}

function updateDisplay(): void {
    const second = document.getElementById('second-vessel');
    const add = document.getElementById('add-second-vessel') as HTMLButtonElement | null;
    const first = document.getElementById('select-first-vessel') as HTMLButtonElement | null;
    const selectSecond = document.getElementById('select-second-vessel') as HTMLButtonElement | null;
    const firstTransfer = document.getElementById('transfer-first-second') as HTMLButtonElement | null;
    const secondTransfer = document.getElementById('transfer-second-first') as HTMLButtonElement | null;
    const fill = document.getElementById('second-vessel-fill') as HTMLElement | null;
    const firstLabel = document.getElementById('first-vessel-contents');
    const secondLabel = document.getElementById('second-vessel-contents');
    if (second) second.hidden = !vessels.secondVisible;
    if (add) { add.hidden = vessels.secondVisible; add.disabled = !hasFirstVessel(); }
    if (first) first.setAttribute('aria-pressed', destination === 'first' ? 'true' : 'false');
    if (selectSecond) { selectSecond.hidden = !vessels.secondVisible; selectSecond.setAttribute('aria-pressed', destination === 'second' ? 'true' : 'false'); }
    const firstAmountMatches = Math.round(config.getLabState().targetLiquidVol) === totalPortions(vessels.first);
    if (firstTransfer) { firstTransfer.hidden = !vessels.secondVisible; firstTransfer.disabled = !firstAmountMatches || transferHalf(vessels, 'first') === null; }
    if (secondTransfer) { secondTransfer.hidden = !vessels.secondVisible; secondTransfer.disabled = !firstAmountMatches || transferHalf(vessels, 'second') === null; }
    if (fill) {
        fill.style.height = `${Math.min(82, totalPortions(vessels.second) / 2.1)}%`;
        fill.style.background = vessels.secondColor;
    }
    if (firstLabel) firstLabel.textContent = chemicalIds(vessels.first).join(' + ') || 'Empty';
    if (secondLabel) secondLabel.textContent = chemicalIds(vessels.second).join(' + ') || 'Empty';
}

function syncFirst(): void {
    const ids = chemicalIds(vessels.first);
    const amount = totalPortions(vessels.first);
    config.updateLabState({
        selectedChemicals: ids,
        targetLiquidVol: amount,
        currentLiquidVol: amount,
        streamActive: false
    });
    writeStorageValue(config.getLabStorageKey('savedChemicals'), JSON.stringify(ids));
    const mixture = document.getElementById('current-mixture');
    if (mixture) mixture.textContent = ids.join(' + ') || 'Empty Vessel';
    document.querySelectorAll<HTMLElement>('.chemical-card').forEach(card => {
        card.setAttribute('aria-pressed', ids.includes(card.dataset.name || '') ? 'true' : 'false');
    });
    window.dispatchEvent(new Event('omnilab:vessels-changed'));
}

export function isSecondDestination(): boolean { return vessels.secondVisible && destination === 'second'; }

export function addToSecond(name: string, color: string): void {
    if (vessels.second[name]) { announce(`${name} is already in vessel B.`); return; }
    const next = { ...vessels.second, [name]: PORTION };
    if (!canHold(next)) { announce('That pair is not supported in vessel B. Choose a compatible chemical.'); return; }
    vessels = { ...vessels, second: next, secondColor: color };
    save();
    updateDisplay();
    announce(`${name} added to vessel B. Amounts are visual portions, not milliliters.`);
}

export function recordFirstAddition(name: string): void {
    vessels.first = { ...vessels.first, [name]: PORTION };
    save();
    updateDisplay();
}

export function resetTwoVessels(): void {
    vessels = { first: {}, second: {}, secondVisible: false, secondColor: '#2b9ed8', firstType: 'flask' };
    destination = 'first';
    config.updateLabState({ secondVesselVisible: false });
    removeStorageValue(STORAGE_KEY);
    updateDisplay();
    announce('Select a vessel to begin.');
}

export function setupTwoVessels(): void {
    const existing = readStorageValue(STORAGE_KEY);
    if (existing) {
        try {
            const parsed = JSON.parse(existing) as VesselPortions;
            const valid = (part: unknown): part is Portions => part !== null && typeof part === 'object' && !Array.isArray(part)
                && Object.entries(part).every(([id, amount]) => /^[A-Za-z0-9()]+$/.test(id) && Number.isInteger(amount) && amount >= 0 && amount <= 210);
            if (!valid(parsed.first) || !valid(parsed.second) || typeof parsed.secondVisible !== 'boolean'
                || !['flask', 'beaker', 'tube', 'cylinder'].includes(parsed.firstType)
                || !/^#[0-9a-fA-F]{6}$/.test(parsed.secondColor) || totalPortions(parsed.first) > 210
                || totalPortions(parsed.second) > 210 || !canHold(parsed.second)) throw Error('Invalid saved vessels');
            vessels = parsed;
            config.updateLabState({ secondVesselVisible: parsed.secondVisible, currentVessel: parsed.firstType,
                apparatusSelected: parsed.secondVisible || config.getLabState().apparatusSelected });
            if (parsed.secondVisible) {
                const card = document.getElementById(`opt-${parsed.firstType}`);
                card?.classList.add('selected');
                card?.setAttribute('aria-pressed', 'true');
            }
            syncFirst();
        } catch { removeStorageValue(STORAGE_KEY); }
    } else {
        vessels.first = Object.fromEntries(config.getLabState().selectedChemicals.map(id => [id, PORTION]));
        vessels.firstType = config.getLabState().currentVessel;
    }

    document.getElementById('add-second-vessel')?.addEventListener('click', () => {
        if (!hasFirstVessel()) { announce('Choose the first vessel in Apparatus.'); return; }
        vessels.secondVisible = true;
        destination = 'second';
        config.updateLabState({ secondVesselVisible: true });
        save(); updateDisplay();
        announce('Vessel B added. Chemicals now go into vessel B.');
    });
    document.getElementById('select-first-vessel')?.addEventListener('click', () => {
        destination = 'first'; updateDisplay(); announce('Chemicals now go into vessel A.');
    });
    document.getElementById('select-second-vessel')?.addEventListener('click', () => {
        destination = 'second'; updateDisplay(); announce('Chemicals now go into vessel B.');
    });
    for (const from of ['first', 'second'] as const) {
        document.getElementById(`transfer-${from}-${from === 'first' ? 'second' : 'first'}`)?.addEventListener('click', () => {
            if (Math.round(config.getLabState().targetLiquidVol) !== totalPortions(vessels.first)) {
                announce('Transfer blocked after using tools in vessel A. Reset the lab to start a new transfer.');
                updateDisplay();
                return;
            }
            const next = transferHalf(vessels, from);
            if (!next) { announce('Transfer blocked. The source is empty or the combined chemicals are unsupported.'); return; }
            vessels = from === 'first'
                ? { ...next, secondColor: config.getLabState().liquidColor }
                : next;
            if (from === 'second' && chemicalIds(vessels.first).length > 0) {
                config.updateLabState({ liquidColor: vessels.secondColor });
                writeStorageValue(config.getLabStorageKey('savedLiquidColor'), vessels.secondColor);
            }
            syncFirst(); save(); updateDisplay();
            window.dispatchEvent(new Event('omnilab:vessel-transfer'));
            announce(`Half of vessel ${from === 'first' ? 'A' : 'B'} moved. Total portions are unchanged.`);
        });
    }
    window.addEventListener('omnilab:apparatus-changed', () => {
        vessels.firstType = config.getLabState().currentVessel;
        if (vessels.secondVisible) save();
        updateDisplay();
    });
    updateDisplay();
}
