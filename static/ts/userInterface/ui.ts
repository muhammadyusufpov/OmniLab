import * as config from '../configuration/config.js';
import { captureLabSetupStarted } from '../analytics/analytics.js';

type ChemicalSelectionHandler = (name: string, color: string) => void;

export function buildChemicalMenu(onSelectChemical: ChemicalSelectionHandler): void {
    const container = document.getElementById('chem-matrix-target');
    if(!container) return;
    container.innerHTML = '';
    
    const state = config.getLabState();
    
    state.chemicalDatabase.forEach(chem => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'chemical-card';
        card.setAttribute('draggable', 'true');
        card.setAttribute('id', `chem-item-${chem.id}`);
        card.setAttribute('data-name', chem.id);
        card.setAttribute('data-color', chem.color);
        card.setAttribute('aria-label', `Add ${chem.name} (${chem.id}) to the lab`);
        card.setAttribute(
            'aria-pressed',
            state.selectedChemicals.includes(chem.id) ? 'true' : 'false'
        );
        card.style.borderColor = chem.color;
        card.addEventListener('dragstart', (ev: DragEvent) => {
            if (ev.dataTransfer && ev.currentTarget) {
                ev.dataTransfer.setData(
                    "text",
                    (ev.currentTarget as HTMLElement).id
                );
            }
        });
        card.addEventListener('click', (ev: MouseEvent) => {
            ev.stopPropagation();
            onSelectChemical(chem.id, chem.color);
        });
        
        const symbol = document.createElement('span');
        symbol.className = 'chemical-symbol';
        symbol.style.color = chem.color;
        symbol.textContent = chem.id;

        const chemicalName = document.createElement('span');
        chemicalName.className = 'chemical-name';
        chemicalName.textContent = chem.name;

        const status = document.createElement('span');
        status.className = 'chemical-card-status';
        status.setAttribute('aria-hidden', 'true');
        status.hidden = true;

        card.append(symbol, chemicalName, status);
        container.appendChild(card);
    });

    refreshChemicalMenuGuidance();
}

function chemicalDisplayName(chemicalId: string): string {
    const chemical = config.getLabState().chemicalDatabase.find(
        item => item.id === chemicalId
    );
    return chemical?.name || chemicalId;
}

function chemicalMenuMessage(selectedChemicals: string[]): string {
    if (selectedChemicals.length === 0) {
        return 'Select one chemical. OmniLab will mark every supported partner.';
    }

    if (selectedChemicals.length === 1) {
        const selectedName = chemicalDisplayName(selectedChemicals[0]);
        const partnerCount = config.getCompatibleReactionPartners(
            selectedChemicals[0]
        ).length;
        const optionLabel = partnerCount === 1 ? 'option is' : 'options are';
        return `Choose a partner for ${selectedName}. ${partnerCount} supported ${optionLabel} marked below.`;
    }

    if (selectedChemicals.length === 2) {
        if (config.isSupportedReactionSetup(selectedChemicals)) {
            return 'This pair is supported and ready to analyze.';
        }
        return "This pair isn't in OmniLab's supported set. Reset and choose a marked partner. That doesn't mean the combination is chemically impossible.";
    }

    return 'OmniLab analyzes two chemicals at a time. Reset and choose one marked pair.';
}

export function refreshChemicalMenuGuidance(): void {
    const state = config.getLabState();
    const selectedChemicals = state.selectedChemicals;
    const selectedChemical = selectedChemicals.length === 1
        ? selectedChemicals[0]
        : null;
    const compatiblePartners = new Set(
        selectedChemical
            ? config.getCompatibleReactionPartners(selectedChemical)
            : []
    );
    const selectedName = selectedChemical
        ? chemicalDisplayName(selectedChemical)
        : '';

    const guidance = document.getElementById('chemical-partner-guidance');
    if (guidance) {
        guidance.textContent = chemicalMenuMessage(selectedChemicals);
    }

    document.querySelectorAll<HTMLButtonElement>('.chemical-card').forEach(card => {
        const chemicalId = card.getAttribute('data-name') || '';
        const isSelected = selectedChemicals.includes(chemicalId);
        const isCompatible = compatiblePartners.has(chemicalId);
        const chemical = state.chemicalDatabase.find(item => item.id === chemicalId);
        const status = card.querySelector<HTMLElement>('.chemical-card-status');

        card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        card.classList.toggle('compatible-partner', isCompatible);
        card.setAttribute(
            'aria-label',
            isCompatible
                ? `Add ${chemical?.name || chemicalId} (${chemicalId}) to the lab. Compatible with ${selectedName}.`
                : isSelected
                    ? `${chemical?.name || chemicalId} (${chemicalId}) is selected.`
                    : `Add ${chemical?.name || chemicalId} (${chemicalId}) to the lab`
        );

        if (status) {
            status.hidden = !isSelected && !isCompatible;
            status.textContent = isSelected ? 'Selected' : isCompatible ? 'Compatible' : '';
        }
    });
}

export function setupSearchFunction(): void {
    const searchInput = document.getElementById('chem-search-input') as HTMLInputElement | null;
    if (!searchInput) return;

    searchInput.addEventListener('input', function(this: HTMLInputElement) {
        const value = this.value.toLowerCase().trim();
        const cards = document.querySelectorAll('.chemical-card');

        cards.forEach(cardNode => {
            const card = cardNode as HTMLElement;
            const id = card.getAttribute('data-name') ? card.getAttribute('data-name')!.toLowerCase() : '';
            const fullName = card.textContent ? card.textContent.toLowerCase() : '';

            if (id.includes(value) || fullName.includes(value)) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    });

    searchInput.addEventListener('click', function(e: MouseEvent) {
        e.stopPropagation();
    });
}

export function toggleCustomPopover(event: MouseEvent, panelId: string): void {
    event.stopPropagation();
    const target = document.getElementById(`sub-panel-${panelId}`);
    if (!target) return;
    
    const isAlreadyOpen = target.style.display === 'block';

    if (isAlreadyOpen) {
        closeAllPopovers();
        return;
    }

    openCustomPopover(panelId);
}

export function openCustomPopover(
    panelId: string,
    focusDefault: boolean = true
): void {
    const target = document.getElementById(`sub-panel-${panelId}`);
    const trigger = document.getElementById(`trigger-${panelId}`);
    if (!target || !trigger) return;

    closeAllPopovers();
    target.style.display = 'block';
    trigger.classList.add('active');
    trigger.setAttribute('aria-expanded', 'true');

    if (focusDefault) {
        if (panelId === 'chemicals') {
            setTimeout(() => { 
                const input = document.getElementById('chem-search-input') as HTMLInputElement | null;
                if (input) input.focus(); 
            }, 50);
        } else if (panelId === 'apparatus') {
            setTimeout(() => {
                const option = target.querySelector<HTMLButtonElement>(
                    '.apparatus-option-card.selected, .apparatus-option-card'
                );
                option?.focus();
            }, 50);
        }
    }
}

export function closeAllPopovers(): void {
    document.querySelectorAll('.floating-popover-panel').forEach(p => {
        (p as HTMLElement).style.display = 'none';
    });
    document.querySelectorAll('.toolbar-trigger-btn').forEach(b => {
        (b as HTMLElement).classList.remove('active');
        b.setAttribute('aria-expanded', 'false');
    });
}

export function selectVessel(type: 'flask' | 'beaker' | 'tube' | 'burner'): void {
    const state = config.getLabState();
    
    if (type === 'burner') {
        const isActive = !state.burnerActive;
        config.updateLabState({ burnerActive: isActive });
        
        const burnerCard = document.getElementById('opt-burner');
        if (burnerCard) {
            burnerCard.classList.toggle('selected', isActive);
            burnerCard.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        }
    } else {
        config.updateLabState({ currentVessel: type });
        document.querySelectorAll('.apparatus-option-card').forEach(c => {
            if (c.id !== 'opt-burner') {
                (c as HTMLElement).classList.remove('selected');
                c.setAttribute('aria-pressed', 'false');
            }
        });
        const targetCard = document.getElementById(`opt-${type}`);
        if (targetCard) {
            targetCard.classList.add('selected');
            targetCard.setAttribute('aria-pressed', 'true');
        }
    }

    const updatedState = config.getLabState();
    captureLabSetupStarted({
        vessel: updatedState.currentVessel,
        burner_active: updatedState.burnerActive,
        ...config.getLabEntryAttribution()
    });
    closeAllPopovers();
}

export function toggleTheme(): void {
    const html = document.documentElement;
    const newTheme = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', newTheme);
    config.updateLabState({ theme: newTheme });
    closeAllPopovers();
}

export function resizeCanvas(): void {
    if(!config.canvas || !config.canvas.parentElement) return;
    config.canvas.width = config.canvas.parentElement.clientWidth;
    config.canvas.height = config.canvas.parentElement.clientHeight;
}
