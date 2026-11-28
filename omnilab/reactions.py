"""Deterministic educational reactions supported by OmniLab."""

from copy import deepcopy


PRECIPITATE_COLORS = frozenset({"#5ba7d1", "#f2c94c", "#f5f3ea"})


def _reaction(
    effect,
    equation,
    explanation,
    safety,
    precipitate_color=None,
):
    reaction = {
        "effect": effect,
        "equation": equation,
        "explanation": explanation,
        "safety": " | ".join(safety),
    }
    if precipitate_color is not None:
        reaction["precipitate_color"] = precipitate_color
    return reaction


REACTION_MATRIX = {
    frozenset({"Na", "Cl2"}): _reaction(
        "none",
        "2Na(s) + Cl2(g) -> 2NaCl(s)",
        (
            "Sodium and chlorine form the ionic solid sodium chloride. "
            "The reaction is strongly exothermic because the product lattice "
            "is substantially more stable than the separated elements. "
            "The equation uses two sodium atoms for each chlorine molecule."
        ),
        (
            "Use trained laboratory supervision.",
            "Keep sodium away from moisture before use.",
            "Avoid inhaling chlorine gas.",
        ),
    ),
    frozenset({"H2", "O2"}): _reaction(
        "none",
        "2H2(g) + O2(g) -> 2H2O(l)",
        (
            "Hydrogen and oxygen form water when the mixture is initiated. "
            "The reaction is strongly exothermic as O-H bonds form. "
            "Two hydrogen molecules react with one oxygen molecule to "
            "produce two water molecules."
        ),
        (
            "Keep the gas mixture away from ignition sources.",
            "Use blast shielding in a supervised laboratory.",
            "Wear splash goggles and protective clothing.",
        ),
    ),
    frozenset({"C", "O2"}): _reaction(
        "none",
        "C(s) + O2(g) -> CO2(g)",
        (
            "Carbon undergoes complete combustion in sufficient oxygen to "
            "form carbon dioxide. The oxidation is exothermic and releases "
            "energy as strong carbon-oxygen bonds form. One carbon atom and "
            "one oxygen molecule produce one carbon dioxide molecule."
        ),
        (
            "Use heat-resistant tools for hot carbon.",
            "Vent carbon dioxide from the work area.",
            "Keep combustible materials away from the reaction.",
        ),
    ),
    frozenset({"HCl", "NaOH"}): _reaction(
        "none",
        "HCl(aq) + NaOH(aq) -> NaCl(aq) + H2O(l)",
        (
            "Hydrochloric acid and sodium hydroxide neutralize to form "
            "sodium chloride and water. The net ionic change is the "
            "combination of hydrogen and hydroxide ions into water. "
            "Neutralization is exothermic, so the solution can warm."
        ),
        (
            "Wear chemical splash goggles and gloves.",
            "Add concentrated solutions slowly to control heating.",
            "Rinse acid or alkali splashes with plenty of water.",
        ),
    ),
    frozenset({"Fe", "HCl"}): _reaction(
        "bubble",
        "Fe(s) + 2HCl(aq) -> FeCl2(aq) + H2(g)",
        (
            "Iron displaces hydrogen from hydrochloric acid to form iron(II) "
            "chloride and hydrogen gas. The bubbles correspond to hydrogen "
            "leaving the solution. The reaction is a redox process in which "
            "iron is oxidized and hydrogen ions are reduced."
        ),
        (
            "Keep the reaction away from flames and sparks.",
            "Vent hydrogen gas in a supervised laboratory.",
            "Wear acid-resistant gloves and splash goggles.",
        ),
    ),
    frozenset({"Cu", "O2"}): _reaction(
        "none",
        "2Cu(s) + O2(g) -> 2CuO(s)",
        (
            "Heated copper reacts with oxygen to form black copper(II) "
            "oxide. Copper is oxidized from oxidation state zero to plus "
            "two while oxygen is reduced. The balanced equation uses two "
            "copper atoms for each oxygen molecule."
        ),
        (
            "Handle heated copper with suitable tongs.",
            "Avoid breathing copper oxide dust.",
            "Wear eye protection during heating.",
        ),
    ),
    frozenset({"Fe", "O2"}): _reaction(
        "none",
        "4Fe(s) + 3O2(g) -> 2Fe2O3(s)",
        (
            "Iron can oxidize in oxygen to form iron(III) oxide. The process "
            "is exothermic, although bulk iron may react slowly unless it is "
            "finely divided or heated. Four iron atoms combine with three "
            "oxygen molecules in the simplified balanced equation."
        ),
        (
            "Keep fine iron powder away from ignition sources.",
            "Use heat-resistant tools for heated samples.",
            "Wear eye protection and avoid oxide dust.",
        ),
    ),
    frozenset({"CO2", "NaOH"}): _reaction(
        "none",
        "CO2(g) + 2NaOH(aq) -> Na2CO3(aq) + H2O(l)",
        (
            "Carbon dioxide reacts with excess sodium hydroxide to form "
            "sodium carbonate and water. Carbon dioxide behaves as an acidic "
            "oxide in this acid-base reaction. Two hydroxide equivalents are "
            "required for each carbon dioxide molecule in the stated equation."
        ),
        (
            "Wear gloves and splash goggles when handling sodium hydroxide.",
            "Add sodium hydroxide slowly to limit splashing.",
            "Use ventilation when working with concentrated carbon dioxide.",
        ),
    ),
    frozenset({"H2", "Cl2"}): _reaction(
        "none",
        "H2(g) + Cl2(g) -> 2HCl(g)",
        (
            "Hydrogen and chlorine form hydrogen chloride after initiation, "
            "often by light or heat. The chain reaction is highly exothermic "
            "and can proceed violently. One molecule of each reactant forms "
            "two hydrogen chloride molecules."
        ),
        (
            "Keep the gas mixture away from bright light and ignition sources.",
            "Use blast shielding and trained supervision.",
            "Avoid inhaling chlorine or hydrogen chloride gas.",
        ),
    ),
    frozenset({"Na", "H2O"}): _reaction(
        "bubble",
        "2Na(s) + 2H2O(l) -> 2NaOH(aq) + H2(g)",
        (
            "Sodium reacts with water to form sodium hydroxide and hydrogen "
            "gas. Hydrogen evolution produces bubbles while the strongly "
            "exothermic reaction heats the mixture. Two sodium atoms react "
            "with two water molecules in the balanced equation."
        ),
        (
            "Do not attempt this reaction outside a controlled laboratory.",
            "Keep flames and sparks away from the hydrogen produced.",
            "Use face protection and trained supervision.",
        ),
    ),
    frozenset({"CO2", "H2O"}): _reaction(
        "none",
        "CO2(g) + H2O(l) -> H2CO3(aq)",
        (
            "Dissolved carbon dioxide establishes an equilibrium with "
            "carbonic acid in water. Only a fraction of the dissolved carbon "
            "dioxide is hydrated at equilibrium. Carbonic acid can then "
            "partially dissociate and lower the solution pH."
        ),
        (
            "Use ventilation when handling concentrated carbon dioxide.",
            "Avoid pressurizing a closed vessel with the gas.",
            "Wear eye protection when handling the solution.",
        ),
    ),
    frozenset({"NaCl", "H2O"}): _reaction(
        "none",
        "NaCl(s) + H2O(l) -> Na+(aq) + Cl-(aq) + H2O(l)",
        (
            "Sodium chloride dissolves in water and dissociates into hydrated "
            "sodium and chloride ions. Water is the solvent and is not "
            "consumed, so it appears on both sides of this process equation. "
            "This is dissolution rather than formation of a new compound."
        ),
        (
            "Wear eye protection when handling laboratory solutions.",
            "Do not ingest laboratory-grade sodium chloride.",
            "Clean spills promptly to prevent slippery surfaces.",
        ),
    ),
    frozenset({"NH3", "HNO3"}): _reaction(
        "none",
        "NH3(aq) + HNO3(aq) -> NH4NO3(aq)",
        (
            "Ammonia accepts a proton from nitric acid to form ammonium "
            "nitrate in solution. This is an acid-base reaction and can "
            "release heat, especially when concentrated solutions are used. "
            "The balanced equation uses one molecule of each reactant."
        ),
        (
            "Use dilute solutions under trained laboratory supervision.",
            "Avoid inhaling ammonia or nitric acid vapors.",
            "Do not isolate or heat the ammonium nitrate product.",
        ),
    ),
    frozenset({"H2SO4", "KOH"}): _reaction(
        "none",
        "H2SO4(aq) + 2KOH(aq) -> K2SO4(aq) + 2H2O(l)",
        (
            "Sulfuric acid and potassium hydroxide neutralize to form "
            "potassium sulfate and water. Two hydroxide ions are needed to "
            "neutralize the two acidic protons represented in the balanced "
            "equation. The solution can warm because neutralization is "
            "exothermic."
        ),
        (
            "Wear chemical splash goggles and alkali-resistant gloves.",
            "Add one dilute solution slowly to the other to control heating.",
            "Rinse acid or alkali splashes immediately with plenty of water.",
        ),
    ),
    frozenset({"CH3COOH", "NaHCO3"}): _reaction(
        "bubble",
        (
            "CH3COOH(aq) + NaHCO3(s) -> "
            "CH3COONa(aq) + CO2(g) + H2O(l)"
        ),
        (
            "Acetic acid reacts with sodium bicarbonate to form sodium "
            "acetate, carbon dioxide, and water. The visible bubbling comes "
            "from carbon dioxide leaving the mixture. The equation has a "
            "one-to-one ratio of acid and bicarbonate."
        ),
        (
            "Keep the reaction vessel open so carbon dioxide cannot build "
            "pressure.",
            "Wear eye protection to guard against splashes.",
            "Add the bicarbonate in small portions to control foaming.",
        ),
    ),
    frozenset({"Ca(OH)2", "CO2"}): _reaction(
        "precipitate",
        "Ca(OH)2(aq) + CO2(g) -> CaCO3(s) + H2O(l)",
        (
            "Carbon dioxide reacts with calcium hydroxide to form a calcium "
            "carbonate precipitate and water. In the common limewater test, "
            "the suspended calcium carbonate makes the solution appear "
            "cloudy. Excess carbon dioxide can cause further changes that "
            "are outside this simplified equation."
        ),
        (
            "Avoid breathing calcium hydroxide dust or carbon dioxide-rich "
            "air.",
            "Wear splash goggles and gloves when handling limewater.",
            "Work with carbon dioxide in a well-ventilated area.",
        ),
        precipitate_color="#f5f3ea",
    ),
    frozenset({"CuSO4", "KOH"}): _reaction(
        "precipitate",
        "CuSO4(aq) + 2KOH(aq) -> Cu(OH)2(s) + K2SO4(aq)",
        (
            "Copper(II) sulfate and potassium hydroxide undergo a double "
            "displacement reaction. Insoluble copper(II) hydroxide forms as "
            "a blue precipitate while potassium sulfate remains in solution. "
            "Two hydroxide ions are required for each copper(II) ion."
        ),
        (
            "Wear splash goggles and chemical-resistant gloves.",
            "Avoid skin contact with copper sulfate and potassium hydroxide.",
            "Collect copper-containing waste for proper disposal.",
        ),
        precipitate_color="#5ba7d1",
    ),
    frozenset({"AgNO3", "NaCl"}): _reaction(
        "precipitate",
        "AgNO3(aq) + NaCl(aq) -> AgCl(s) + NaNO3(aq)",
        (
            "Silver nitrate and sodium chloride exchange ions to form "
            "insoluble silver chloride. The white silver chloride precipitate "
            "is the usual evidence for chloride ions in this simplified test. "
            "Sodium and nitrate ions remain in solution."
        ),
        (
            "Wear gloves and splash goggles when handling silver nitrate.",
            "Protect the mixture from strong light after the precipitate "
            "forms.",
            "Collect silver-containing waste instead of pouring it down a "
            "drain.",
        ),
        precipitate_color="#f5f3ea",
    ),
    frozenset({"AgNO3", "KI"}): _reaction(
        "precipitate",
        "AgNO3(aq) + KI(aq) -> AgI(s) + KNO3(aq)",
        (
            "Silver nitrate and potassium iodide undergo a precipitation "
            "reaction. Insoluble silver iodide forms as a yellow solid while "
            "potassium and nitrate ions remain in solution. The molecular "
            "equation has a one-to-one reactant ratio."
        ),
        (
            "Wear gloves and splash goggles when handling silver nitrate.",
            "Protect the silver iodide precipitate from strong light.",
            "Collect silver-containing waste for approved disposal.",
        ),
        precipitate_color="#f2c94c",
    ),
    frozenset({"KMnO4", "H2O2"}): _reaction(
        "bubble",
        (
            "2KMnO4(aq) + 3H2O2(aq) -> "
            "2MnO2(s) + 3O2(g) + 2KOH(aq) + 2H2O(l)"
        ),
        (
            "In neutral or alkaline conditions, permanganate oxidizes "
            "hydrogen peroxide to oxygen while manganese dioxide forms. "
            "Oxygen evolution produces bubbles and the permanganate color "
            "fades as brown manganese dioxide appears. Different acidity "
            "can change the products."
        ),
        (
            "Use dilute solutions and add hydrogen peroxide slowly.",
            "Keep both reagents away from combustible or reducing materials.",
            "Do not seal the vessel because oxygen gas is produced.",
        ),
    ),
    frozenset({"Na2CO3", "HCl"}): _reaction(
        "bubble",
        "Na2CO3(aq) + 2HCl(aq) -> 2NaCl(aq) + CO2(g) + H2O(l)",
        (
            "Sodium carbonate reacts with hydrochloric acid to form sodium "
            "chloride, carbon dioxide, and water. Carbon dioxide escaping "
            "from the solution causes bubbling. Two hydrogen ions are needed "
            "for each carbonate ion in the balanced equation."
        ),
        (
            "Wear splash goggles and acid-resistant gloves.",
            "Add hydrochloric acid slowly to control foaming and heat.",
            "Keep the vessel open and work in a ventilated area.",
        ),
    ),
    frozenset({"BaCl2", "Na2CO3"}): _reaction(
        "precipitate",
        "BaCl2(aq) + Na2CO3(aq) -> BaCO3(s) + 2NaCl(aq)",
        (
            "Barium chloride and sodium carbonate exchange ions to form "
            "insoluble barium carbonate. The white precipitate removes "
            "barium ions from the solution while sodium and chloride ions "
            "remain dissolved. The reactants combine in a one-to-one ratio."
        ),
        (
            "Treat soluble barium compounds as toxic and avoid all ingestion.",
            "Wear gloves and splash goggles throughout the procedure.",
            "Collect all barium-containing material as hazardous waste.",
        ),
        precipitate_color="#f5f3ea",
    ),
    frozenset({"Zn", "HCl"}): _reaction(
        "bubble",
        "Zn(s) + 2HCl(aq) -> ZnCl2(aq) + H2(g)",
        (
            "Zinc displaces hydrogen from hydrochloric acid to form zinc "
            "chloride and hydrogen gas. The bubbles are hydrogen leaving the "
            "solution. Zinc is oxidized while hydrogen ions are reduced in "
            "this single-displacement reaction."
        ),
        (
            "Keep flames and sparks away from the hydrogen produced.",
            "Work in a ventilated area under trained supervision.",
            "Wear acid-resistant gloves and splash goggles.",
        ),
    ),
    frozenset({"HF", "NaOH"}): _reaction(
        "none",
        "HF(aq) + NaOH(aq) -> NaF(aq) + H2O(l)",
        (
            "Dilute aqueous hydrofluoric acid and sodium hydroxide neutralize "
            "under controlled addition to form sodium fluoride and water. "
            "Although hydrofluoric acid is a weak acid in water, hydroxide "
            "removes its acidic proton and drives this simplified one-to-one "
            "reaction toward products."
        ),
        (
            "Do not handle hydrofluoric acid outside a specially equipped "
            "laboratory.",
            "Use hydrofluoric-acid-rated protective equipment and a compatible "
            "non-glass vessel.",
            "Follow the institution's hydrofluoric-acid exposure protocol "
            "immediately after any suspected contact.",
        ),
    ),
    frozenset({"HBr", "NaOH"}): _reaction(
        "none",
        "HBr(aq) + NaOH(aq) -> NaBr(aq) + H2O(l)",
        (
            "Hydrobromic acid and sodium hydroxide neutralize to form sodium "
            "bromide and water. Hydrogen ions from the acid combine with "
            "hydroxide ions from the base. The one-to-one neutralization is "
            "exothermic, so the solution can warm."
        ),
        (
            "Work in a fume hood with dilute solutions.",
            "Wear acid-resistant gloves and chemical splash goggles.",
            "Add the sodium hydroxide slowly to control heating and splashing.",
        ),
    ),
    frozenset({"HI", "NaOH"}): _reaction(
        "none",
        "HI(aq) + NaOH(aq) -> NaI(aq) + H2O(l)",
        (
            "Hydroiodic acid and sodium hydroxide neutralize to form sodium "
            "iodide and water. Hydrogen ions combine with hydroxide ions in "
            "the net ionic change. The one-to-one neutralization can release "
            "enough heat to warm the solution."
        ),
        (
            "Work in a fume hood with fresh, dilute solutions.",
            "Wear acid-resistant gloves and chemical splash goggles.",
            "Keep hydroiodic acid away from oxidizers and add the base slowly.",
        ),
    ),
    frozenset({"AgCl", "NH3"}): _reaction(
        "none",
        "AgCl(s) + 2NH3(aq) -> [Ag(NH3)2]+(aq) + Cl-(aq)",
        (
            "Freshly prepared silver chloride can dissolve in sufficient "
            "aqueous ammonia as the diamminesilver(I) complex forms. Complex "
            "formation lowers the free silver-ion concentration and shifts "
            "the silver chloride dissolution equilibrium."
        ),
        (
            "Use ammonia only in a fume hood and avoid breathing its vapors.",
            "Wear chemical splash goggles and avoid contact with the mixture.",
            "Collect every silver-containing solution for approved hazardous "
            "waste disposal.",
        ),
    ),
    frozenset({"AlCl3", "NaOH"}): _reaction(
        "precipitate",
        "AlCl3(aq) + 3NaOH(aq) -> Al(OH)3(s) + 3NaCl(aq)",
        (
            "Aluminum chloride and sodium hydroxide form a white aluminum "
            "hydroxide precipitate while sodium chloride remains in solution. "
            "Three hydroxide ions are required for each aluminum ion. Excess "
            "hydroxide can redissolve the amphoteric precipitate."
        ),
        (
            "Wear chemical splash goggles and alkali-resistant gloves.",
            "Add dilute sodium hydroxide dropwise to avoid excess base.",
            "Rinse chemical splashes immediately with plenty of water.",
        ),
        precipitate_color="#f5f3ea",
    ),
    frozenset({"MgSO4", "NaOH"}): _reaction(
        "precipitate",
        "MgSO4(aq) + 2NaOH(aq) -> Mg(OH)2(s) + Na2SO4(aq)",
        (
            "Dilute aqueous magnesium sulfate and sodium hydroxide exchange "
            "ions to form sparingly soluble magnesium hydroxide. The white "
            "precipitate removes magnesium ions from solution while sodium "
            "sulfate remains dissolved. Two hydroxide ions are needed per "
            "magnesium ion."
        ),
        (
            "Wear splash goggles and chemical-resistant gloves.",
            "Add sodium hydroxide slowly to limit heating and splashing.",
            "Do not ingest the mixture, and clean spills promptly.",
        ),
        precipitate_color="#f5f3ea",
    ),
    frozenset({"HgCl2", "NaOH"}): _reaction(
        "precipitate",
        "HgCl2(aq) + 2NaOH(aq) -> HgO(s) + 2NaCl(aq) + H2O(l)",
        (
            "Under specialist mercury controls, dilute mercury(II) chloride "
            "and sodium hydroxide form yellow mercury(II) oxide, sodium "
            "chloride, and water. An initially formed mercury hydroxide is "
            "unstable and is represented by mercury(II) oxide in the balanced "
            "overall equation."
        ),
        (
            "Treat this as virtual-only outside a specialist mercury laboratory.",
            "Avoid all skin contact, ingestion, and inhalation of mercury "
            "materials.",
            "Collect the entire mixture as mercury-containing hazardous waste.",
        ),
        precipitate_color="#f2c94c",
    ),
    frozenset({"CO", "O2"}): _reaction(
        "none",
        "2CO(g) + O2(g) -> 2CO2(g)",
        (
            "Carbon monoxide oxidizes to carbon dioxide after ignition or "
            "catalytic activation. The combustion is exothermic, and two "
            "carbon monoxide molecules consume one oxygen molecule. The "
            "current model does not predict the activation conditions."
        ),
        (
            "Run this only in a specialist gas laboratory.",
            "Use continuous carbon monoxide monitoring and effective ventilation.",
            "Treat carbon monoxide and oxygen as a flammable, potentially "
            "explosive mixture.",
        ),
    ),
    frozenset({"NO2", "H2O"}): _reaction(
        "none",
        "2NO2(g) + H2O(l) -> HNO2(aq) + HNO3(aq)",
        (
            "Nitrogen dioxide absorbed into cool, dilute water forms a mixture "
            "of nitrous acid and nitric acid in this simplified equation. The "
            "real gas absorption can involve additional equilibria, so this "
            "result describes the classroom-scale net change."
        ),
        (
            "Use nitrogen dioxide only in a specialist fume-handling system.",
            "Avoid inhalation and wear corrosion-resistant gloves and goggles.",
            "Keep this oxidizer and the acidic products away from combustibles.",
        ),
    ),
    frozenset({"H2S", "NaOH"}): _reaction(
        "none",
        "H2S(g) + 2NaOH(aq) -> Na2S(aq) + 2H2O(l)",
        (
            "Hydrogen sulfide transfers both acidic protons to excess sodium "
            "hydroxide to form sodium sulfide and water. This equation assumes "
            "two equivalents of base and a contained gas-handling system. With "
            "one equivalent, sodium hydrosulfide would form instead."
        ),
        (
            "Run this only in a specialist gas laboratory.",
            "Use gas detection and ventilation, and never rely on odor.",
            "Control ignition sources and collect sulfide-containing hazardous "
            "waste without adding acid.",
        ),
    ),
    frozenset({"O3", "H2O2"}): _reaction(
        "none",
        "O3(g) + H2O2(aq) -> 2O2(g) + H2O(l)",
        (
            "Ozone and hydrogen peroxide produce water and oxygen in the "
            "simplified net equation for the aqueous peroxone process. The "
            "real pathway includes short-lived reactive intermediates that "
            "the current model does not represent. The model lacks gas flow, "
            "concentration, and reaction-rate inputs, so it cannot predict "
            "whether visible bubbles form."
        ),
        (
            "Use contained, ventilated ozone equipment in a specialist setup.",
            "Prevent ozone inhalation and keep both oxidizers away from combustibles.",
            "Do not seal the vessel because oxygen gas is produced.",
        ),
    ),
}


SUPPORTED_CHEMICAL_IDS = frozenset(
    chemical
    for pair in REACTION_MATRIX
    for chemical in pair
)


def reaction_key(selected_chemicals):
    canonical_by_casefold = {
        chemical.casefold(): chemical for chemical in SUPPORTED_CHEMICAL_IDS
    }
    canonical = []
    for chemical in selected_chemicals:
        normalized = chemical.strip().casefold()
        if normalized not in canonical_by_casefold:
            return None
        canonical.append(canonical_by_casefold[normalized])

    if len(canonical) != 2 or len(set(canonical)) != 2:
        return None
    return frozenset(canonical)


def get_reaction(selected_chemicals):
    key = reaction_key(selected_chemicals)
    reaction = REACTION_MATRIX.get(key)
    return deepcopy(reaction) if reaction is not None else None


def supported_reaction_pairs():
    return sorted(
        (sorted(pair) for pair in REACTION_MATRIX),
        key=lambda pair: tuple(chemical.casefold() for chemical in pair),
    )
