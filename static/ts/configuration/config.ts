export const canvas = document.getElementById('lab-canvas') as HTMLCanvasElement | null;
export const ctx = canvas ? canvas.getContext('2d') : null;

export interface Chemical {
    id: string;
    name: string;
    color: string;
}

export interface Particle {
    x: number;
    y: number;
    vx: number;
    vy: number;
    alpha: number;
    color: string;
}

export interface LabState {
    chemicalDatabase: Chemical[];
    selectedChemicals: string[];
    currentVessel: 'flask' | 'beaker' | 'tube';
    theme: 'light' | 'dark';
    targetLiquidVol: number;
    currentLiquidVol: number;
    liquidColor: string;
    waveTime: number;
    streamActive: boolean;
    streamX: number;
    streamColor: string;
    splashParticles: Particle[];
    ambientBubbles: Particle[];
    isDragging: boolean;
    dragStartX: number;
    dragStartY: number;
    vesselOffsetX: number;
    vesselOffsetY: number;
    smokeParticles: Particle[];
    explosionParticles: Particle[];
    isBubbling: boolean;
    precipitateColor: '#5ba7d1' | '#f2c94c' | '#f5f3ea' | null;
    burnerActive: boolean;
}

export interface ReactionDemoConfig {
    id: string;
    version: string;
    selectedChemicals: string[];
    vessel: LabState['currentVessel'];
    liquidColor: string;
}

type SupportedReactionPair = [string, string];

export interface ReactionGuide {
    href: string;
    title: string;
}

export type GuideVisitSource =
    | 'guide_reaction'
    | 'guide_formula'
    | 'guide_ionic_bond'
    | 'guide_virtual_lab'
    | 'guide_observation_a'
    | 'guide_observation_b'
    | 'guide_observation_c'
    | 'guide_observation_d'
    | 'guide_observation_e';

export type VisitSource = 'student_invite' | GuideVisitSource;

export type LabEntrySource = 'guide' | 'prepared_demo' | 'direct' | 'unknown';

export interface LabEntryAttribution {
    entry_source: LabEntrySource;
    visit_source?: VisitSource;
    prepared_reaction_id?: string;
}

const GUIDE_VISIT_SOURCES = new Set<GuideVisitSource>([
    'guide_reaction',
    'guide_formula',
    'guide_ionic_bond',
    'guide_virtual_lab',
    'guide_observation_a',
    'guide_observation_b',
    'guide_observation_c',
    'guide_observation_d',
    'guide_observation_e'
]);

const ALLOWED_VISIT_SOURCES = new Set<VisitSource>([
    'student_invite',
    ...GUIDE_VISIT_SOURCES
]);

declare global {
    interface Window {
        reactionDemo?: ReactionDemoConfig | null;
        firstExperiment?: boolean;
        supportedReactionPairs?: SupportedReactionPair[];
    }
}

const supportedReactionPairs = window.supportedReactionPairs || [['Na', 'Cl2']];
const supportedReactionPairKeys = new Set(
    supportedReactionPairs.map(pair => [...pair].sort().join('+'))
);
const reactionGuidesByPairKey = new Map<string, readonly ReactionGuide[]>([
    [
        'Cl2+Na',
        [
            {
                href: '/guides/sodium-and-chlorine-reaction/',
                title: 'What happens when sodium reacts with chlorine?'
            },
            {
                href: '/guides/sodium-and-chlorine-formula/',
                title: 'What formula forms from sodium and chlorine?'
            },
            {
                href: '/guides/sodium-and-chlorine-ionic-bond/',
                title: 'Why do sodium and chlorine form an ionic bond?'
            }
        ]
    ],
    [
        'CO2+Ca(OH)2',
        [
            {
                href: '/guides/why-limewater-turns-cloudy-with-carbon-dioxide/',
                title: 'Why does limewater turn cloudy when carbon dioxide is added?'
            }
        ]
    ],
    [
        'CO2+H2O',
        [
            {
                href: '/guides/carbon-dioxide-and-water-reaction/',
                title: 'What happens in the carbon dioxide and water reaction?'
            }
        ]
    ],
    [
        'H2O+NO2',
        [
            {
                href: '/guides/nitrogen-dioxide-and-water-reaction/',
                title: 'What happens when nitrogen dioxide reacts with water?'
            }
        ]
    ],
    [
        'CO2+NaOH',
        [
            {
                href: '/guides/carbon-dioxide-and-sodium-hydroxide-reaction/',
                title: 'What happens when carbon dioxide reacts with sodium hydroxide?'
            }
        ]
    ],
    [
        'Fe+HCl',
        [
            {
                href: '/guides/iron-and-hydrochloric-acid-reaction/',
                title: 'What happens when iron reacts with hydrochloric acid?'
            }
        ]
    ],
    [
        'HCl+Na2CO3',
        [
            {
                href: '/guides/why-sodium-carbonate-fizzes-with-hydrochloric-acid/',
                title: 'Why does sodium carbonate fizz with hydrochloric acid?'
            }
        ]
    ],
    [
        'HCl+NaOH',
        [
            {
                href: '/guides/hydrochloric-acid-and-sodium-hydroxide-reaction/',
                title: 'What happens when hydrochloric acid reacts with sodium hydroxide?'
            }
        ]
    ],
    [
        'AgNO3+KI',
        [
            {
                href: '/guides/silver-nitrate-potassium-iodide-precipitate/',
                title: 'What precipitate forms when silver nitrate reacts with potassium iodide?'
            }
        ]
    ],
    [
        'AgNO3+NaCl',
        [
            {
                href: '/guides/silver-nitrate-and-sodium-chloride-reaction/',
                title: 'What happens when silver nitrate reacts with sodium chloride?'
            }
        ]
    ],
    [
        'CuSO4+KOH',
        [
            {
                href: '/guides/copper-ii-sulfate-potassium-hydroxide-precipitate/',
                title: 'What precipitate forms from copper(II) sulfate and potassium hydroxide?'
            }
        ]
    ],
    [
        'C+O2',
        [
            {
                href: '/guides/carbon-and-oxygen-reaction/',
                title: 'What happens when carbon reacts with oxygen?'
            }
        ]
    ],
    [
        'Cu+O2',
        [
            {
                href: '/guides/reaction-of-copper-with-oxygen/',
                title: 'What happens in the reaction of copper with oxygen?'
            }
        ]
    ],
    [
        'H2O+Na',
        [
            {
                href: '/guides/reaction-of-sodium-in-water/',
                title: 'What happens when sodium reacts with water?'
            }
        ]
    ],
    [
        'H2O+NaCl',
        [
            {
                href: '/guides/sodium-chloride-and-water-reaction/',
                title: 'What happens when sodium chloride mixes with water?'
            }
        ]
    ],
    [
        'HCl+Zn',
        [
            {
                href: '/guides/zinc-and-hydrochloric-acid-reaction/',
                title: 'What happens when zinc reacts with hydrochloric acid?'
            }
        ]
    ],
    [
        'CH3COOH+NaHCO3',
        [
            {
                href: '/guides/acetic-acid-and-sodium-bicarbonate-reaction/',
                title: 'What happens when acetic acid reacts with sodium bicarbonate?'
            }
        ]
    ],
    [
        'H2+O2',
        [
            {
                href: '/guides/hydrogen-and-oxygen-reaction/',
                title: 'What happens when hydrogen reacts with oxygen?'
            }
        ]
    ],
    [
        'Cl2+H2',
        [
            {
                href: '/guides/hydrogen-and-chlorine-reaction/',
                title: 'What happens when hydrogen reacts with chlorine?'
            }
        ]
    ],
    [
        'H2O2+KMnO4',
        [
            {
                href: '/guides/potassium-permanganate-and-hydrogen-peroxide-reaction/',
                title: 'What happens when potassium permanganate reacts with hydrogen peroxide?'
            }
        ]
    ],
    [
        'CO+O2',
        [
            {
                href: '/guides/carbon-monoxide-and-oxygen-reaction/',
                title: 'What happens when carbon monoxide reacts with oxygen?'
            }
        ]
    ],
    [
        'Fe+O2',
        [
            {
                href: '/guides/reaction-of-iron-with-oxygen/',
                title: 'What happens in the reaction of iron with oxygen?'
            }
        ]
    ]
]);
const supportedChemicalIds = new Set(supportedReactionPairs.flat());
const supportedReactionPartners = new Map<string, Set<string>>();

for (const [firstChemical, secondChemical] of supportedReactionPairs) {
    const firstPartners = supportedReactionPartners.get(firstChemical) || new Set<string>();
    const secondPartners = supportedReactionPartners.get(secondChemical) || new Set<string>();
    firstPartners.add(secondChemical);
    secondPartners.add(firstChemical);
    supportedReactionPartners.set(firstChemical, firstPartners);
    supportedReactionPartners.set(secondChemical, secondPartners);
}

let state: LabState = {
    chemicalDatabase: [],
    selectedChemicals: [],
    currentVessel: 'flask',
    theme: 'light',
    targetLiquidVol: 0,
    currentLiquidVol: 0,
    liquidColor: '#3399ff',
    waveTime: 0,
    streamActive: false,
    streamX: 0,
    streamColor: '#ffffff',
    splashParticles: [],
    ambientBubbles: [],
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    vesselOffsetX: 0,
    vesselOffsetY: 0,
    smokeParticles: [],
    explosionParticles: [],
    isBubbling: false,
    precipitateColor: null,
    burnerActive: false
};

export function getLabState(): LabState {
    return state;
}

export function updateLabState(newState: Partial<LabState>): void {
    state = { ...state, ...newState };
}

export function getReactionDemoConfig(): ReactionDemoConfig | null {
    return window.reactionDemo || null;
}

export function getGuideVisitSource(source: string | null): GuideVisitSource | null {
    return source && GUIDE_VISIT_SOURCES.has(source as GuideVisitSource)
        ? source as GuideVisitSource
        : null;
}

export function getVisitSource(): VisitSource | null {
    if (!getReactionDemoConfig()) return null;

    const source = new URLSearchParams(window.location.search).get('source');
    return source && ALLOWED_VISIT_SOURCES.has(source as VisitSource)
        ? source as VisitSource
        : null;
}

export function getLabEntryAttribution(): LabEntryAttribution {
    const reactionDemo = getReactionDemoConfig();
    const rawSource = new URLSearchParams(window.location.search).get('source');
    const visitSource = getVisitSource();
    const preparedReaction = reactionDemo?.id
        ? { prepared_reaction_id: reactionDemo.id }
        : {};

    if (reactionDemo && visitSource && getGuideVisitSource(visitSource)) {
        return {
            entry_source: 'guide',
            visit_source: visitSource,
            ...preparedReaction
        };
    }
    if (reactionDemo && !rawSource) {
        return {
            entry_source: 'prepared_demo',
            ...preparedReaction
        };
    }
    if (reactionDemo && visitSource) {
        return {
            entry_source: 'prepared_demo',
            visit_source: visitSource,
            ...preparedReaction
        };
    }
    if (!reactionDemo && !rawSource) {
        return { entry_source: 'direct' };
    }
    return {
        entry_source: 'unknown',
        ...preparedReaction
    };
}

export function isSupportedReactionSetup(selectedChemicals: string[]): boolean {
    if (selectedChemicals.length !== 2) return false;
    return supportedReactionPairKeys.has([...selectedChemicals].sort().join('+'));
}

export function getMatchingReactionGuides(
    selectedChemicals: string[]
): readonly ReactionGuide[] {
    if (selectedChemicals.length !== 2) return [];
    return reactionGuidesByPairKey.get(
        [...selectedChemicals].sort().join('+')
    ) || [];
}

export function getCompatibleReactionPartners(chemicalId: string): string[] {
    return [...(supportedReactionPartners.get(chemicalId) || [])];
}

export function parseSavedChemicals(serializedChemicals: string | null): string[] | null {
    if (serializedChemicals === null) return null;

    try {
        const parsedChemicals: unknown = JSON.parse(serializedChemicals);
        if (!Array.isArray(parsedChemicals)) return null;
        if (!parsedChemicals.every(
            (chemical: unknown): chemical is string => typeof chemical === 'string'
                && supportedChemicalIds.has(chemical)
        )) return null;
        if (new Set(parsedChemicals).size !== parsedChemicals.length) return null;

        return parsedChemicals;
    } catch {
        return null;
    }
}

export function getLabStorageKey(baseKey: string): string {
    const reactionDemo = getReactionDemoConfig();
    if (reactionDemo) {
        return `reactionDemo:${reactionDemo.id}:${baseKey}`;
    }
    return window.firstExperiment
        ? `firstExperiment:v1:${baseKey}`
        : baseKey;
}

export function hexToRgbA(hex: string, alpha: number = 1): string {
    let c: string[] | null;
    if (/^#([A-Fa-f0-9]{3}){1,2}$/.test(hex)) {
        c = hex.substring(1).split('');
        if (c.length === 3) {
            c = [c[0], c[0], c[1], c[1], c[2], c[2]];
        }
        const num = parseInt(c.join(''), 16);
        return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
    }
    return `rgba(0, 0, 0, ${alpha})`;
}
