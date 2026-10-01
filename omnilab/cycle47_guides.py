"""Student guides for the seven supported pairs without result links."""

from .reactions import get_reaction


BOUNDARY = (
    "OmniLab gives educational predictions, not verified simulations. "
    "It never replaces trained laboratory supervision."
)

CONTENT = [
    {
        "key": "hydrofluoric-acid-sodium-hydroxide",
        "pair": (("Hydrofluoric acid", "HF"), ("Sodium hydroxide", "NaOH")),
        "answer": "Hydrofluoric acid and sodium hydroxide form sodium fluoride and water in the supported one-to-one equation.",
        "description": "Explore the HF and NaOH neutralization equation, sodium fluoride product, weak-acid distinction, and strict safety limits in a prepared virtual example.",
        "goal": "Explain why a weak acid can still neutralize a strong base.",
        "limit": "The equation assumes controlled amounts. It does not calculate pH, heat, or exposure risk.",
        "observation": "Both dilute solutions may look clear. OmniLab shows no measured temperature or color change for this pair.",
        "steps": (
            ("Find the proton transfer", "Hydroxide removes the acidic proton from HF. The remaining fluoride ion pairs with sodium in the molecular equation."),
            ("Balance the formulas", "One HF and one NaOH supply the atoms for one NaF and one H2O. Coefficients are all one."),
            ("Keep the safety limit", "Hydrofluoric acid can cause severe injury despite its weak-acid classification. This virtual result is no handling guide."),
        ),
        "questions": (
            ("Is HF safe because it is a weak acid?", "No. Weak describes its partial ionization in water, not its hazard. Physical work needs a specialist laboratory."),
            ("Does OmniLab find the final pH?", "No. The model recognizes the pair and returns a fixed equation. It does not use concentration or volume."),
        ),
        "pattern": "acid-base",
        "products": ("NaF", "H2O"),
        "related": ("hydrochloric_acid_sodium_hydroxide", "hydrobromic_acid_sodium_hydroxide"),
    },
    {
        "key": "hydrobromic-acid-sodium-hydroxide",
        "pair": (("Hydrobromic acid", "HBr"), ("Sodium hydroxide", "NaOH")),
        "answer": "Hydrobromic acid and sodium hydroxide neutralize to form sodium bromide and water.",
        "description": "Balance the HBr and NaOH neutralization equation, identify sodium bromide, and explain why a clear solution can warm in this virtual example.",
        "goal": "Cancel the spectator ions and explain why the clear solution can warm.",
        "limit": "The one-to-one equation does not tell you the final pH or measured temperature.",
        "observation": "No gas or solid appears in the supported equation. The solution can warm even while it stays clear.",
        "steps": (
            ("Count one acid and one base", "One HBr supplies one acidic proton. One NaOH supplies one hydroxide ion, so the molecular ratio is one to one."),
            ("Cancel dissolved ions", "Sodium and bromide remain dissolved. The net ionic change is H+(aq) + OH-(aq) -> H2O(l)."),
            ("Separate heat from appearance", "Neutralization can release heat without a visible precipitate or gas. OmniLab does not measure that heat."),
        ),
        "questions": (
            ("What salt forms?", "The product salt is sodium bromide, NaBr, dissolved in water."),
            ("Does clear mean no reaction?", "No. Acid-base neutralization can change the solution while both starting and final mixtures look clear."),
        ),
        "pattern": "acid-base",
        "products": ("NaBr", "H2O"),
        "related": ("hydrochloric_acid_sodium_hydroxide", "hydroiodic_acid_sodium_hydroxide"),
    },
    {
        "key": "hydroiodic-acid-sodium-hydroxide",
        "pair": (("Hydroiodic acid", "HI"), ("Sodium hydroxide", "NaOH")),
        "answer": "Hydroiodic acid and sodium hydroxide neutralize to form sodium iodide and water.",
        "description": "Study the HI and NaOH neutralization equation, sodium iodide product, net ionic change, and limits of a prepared browser prediction.",
        "goal": "Use the one-to-one equation to identify the salt and the net ionic change.",
        "limit": "The model does not track solution concentration, pH, heat, or iodide oxidation.",
        "observation": "This result has no gas or precipitate cue. A real dilute solution can stay clear and warm during neutralization.",
        "steps": (
            ("Find the ions", "HI supplies an acidic proton and iodide. NaOH supplies sodium and hydroxide in water."),
            ("Make water", "The acidic proton and hydroxide form H2O. Sodium and iodide remain dissolved as NaI."),
            ("Check the limit", "The fixed result describes neutralization only. It does not predict side reactions or the final solution pH."),
        ),
        "questions": (
            ("What is the net ionic equation?", "For this simplified aqueous neutralization, H+(aq) + OH-(aq) -> H2O(l)."),
            ("Does a clear result mean no heat?", "No. Neutralization can release heat without making a visible gas or solid."),
        ),
        "pattern": "acid-base",
        "products": ("NaI", "H2O"),
        "related": ("hydrobromic_acid_sodium_hydroxide", "hydrochloric_acid_sodium_hydroxide"),
    },
    {
        "key": "silver-chloride-ammonia",
        "pair": (("Silver chloride", "AgCl"), ("Ammonia", "NH3")),
        "answer": "Silver chloride can dissolve in excess dilute ammonia as a soluble diamminesilver(I) complex forms.",
        "description": "See how silver chloride dissolves in excess dilute ammonia, form the silver complex, and read the equilibrium limits in a prepared virtual example.",
        "goal": "Explain why forming a complex can dissolve a solid without changing silver's oxidation state.",
        "limit": "The result assumes excess dilute ammonia and fresh silver chloride. It calculates no equilibrium or concentration.",
        "observation": "A white silver chloride solid can disappear as the complex forms. OmniLab gives the equation, not a timed dissolution animation.",
        "steps": (
            ("Start with the solid", "AgCl(s) is a silver chloride precipitate. It is not a source of free chloride alone."),
            ("Add two ammonia ligands", "Two NH3 molecules bind one silver(I) ion in [Ag(NH3)2]+. Chloride remains in solution."),
            ("Read the equilibrium", "Complex formation lowers free silver-ion concentration and can pull more AgCl into solution. The model does not calculate how much."),
        ),
        "questions": (
            ("Is this a redox reaction?", "No. Silver remains in the +1 oxidation state in the complex."),
            ("Does every silver compound dissolve in ammonia?", "No. This guide covers only the supported AgCl and NH3 pair under the stated conditions."),
        ),
        "pattern": "complex-formation",
        "products": ("[Ag(NH3)2]+", "Cl-"),
        "related": ("silver_nitrate_sodium_chloride", "ammonia_nitric_acid"),
    },
    {
        "key": "mercury-chloride-sodium-hydroxide",
        "pair": (("Mercury(II) chloride", "HgCl2"), ("Sodium hydroxide", "NaOH")),
        "answer": "Mercury(II) chloride and sodium hydroxide form yellow mercury(II) oxide in the supported overall equation.",
        "description": "Balance the mercury(II) chloride and NaOH equation, identify yellow mercury(II) oxide, and read the specialist safety limits of this virtual result.",
        "goal": "Balance the overall equation and explain why the represented solid is HgO.",
        "limit": "This is virtual-only outside a specialist mercury laboratory. The model does not estimate exposure or waste risk.",
        "observation": "The supported result represents a yellow HgO precipitate. Color and amount are simplified cues, not measurements.",
        "steps": (
            ("Count the hydroxide", "Two NaOH units provide enough oxygen and hydrogen for HgO and H2O in the overall equation."),
            ("Balance the chloride", "Two chloride ions from HgCl2 remain with two sodium ions as 2NaCl(aq)."),
            ("Name the solid", "Mercury hydroxide is unstable here. The fixed overall equation represents the solid as HgO(s)."),
        ),
        "questions": (
            ("Why is the product HgO rather than Hg(OH)2?", "The supported overall equation represents unstable mercury hydroxide through its oxide and water products."),
            ("Can this be tried as a home experiment?", "No. Mercury compounds are highly hazardous and require specialist controls and hazardous-waste handling."),
        ),
        "pattern": "precipitation",
        "products": ("HgO", "NaCl", "H2O"),
        "related": ("aluminium_chloride_sodium_hydroxide", "magnesium_sulfate_sodium_hydroxide"),
    },
    {
        "key": "hydrogen-sulfide-sodium-hydroxide",
        "pair": (("Hydrogen sulfide", "H2S"), ("Sodium hydroxide", "NaOH")),
        "answer": "With two equivalents of sodium hydroxide, hydrogen sulfide forms sodium sulfide and water in the supported equation.",
        "description": "Learn why hydrogen sulfide needs two NaOH units for the modeled sodium sulfide product, with gas safety limits and a prepared virtual example.",
        "goal": "Explain the two-to-one base ratio and distinguish sulfide from hydrosulfide.",
        "limit": "The fixed result assumes excess base and contained gas handling. It cannot predict gas escape or exposure.",
        "observation": "No gas-production cue belongs to this equation: hydrogen sulfide starts as a reactant. OmniLab does not display gas capture or pH.",
        "steps": (
            ("Count two acidic protons", "H2S can transfer two protons. Complete neutralization needs two OH- ions from two NaOH units."),
            ("Name the salt", "Two sodium ions balance one sulfide ion in Na2S. Two water molecules account for the transferred protons."),
            ("Keep the alternate outcome separate", "With one base equivalent, sodium hydrosulfide can form instead. OmniLab returns only the excess-base equation."),
        ),
        "questions": (
            ("Why is there a 2 before NaOH?", "Two hydroxide ions are needed to remove both acidic protons in the stated complete-neutralization equation."),
            ("Is smell a safe test for hydrogen sulfide?", "No. Odor cannot establish safety. This virtual guide is no substitute for specialist gas controls."),
        ),
        "pattern": "acid-base",
        "products": ("Na2S", "H2O"),
        "related": ("sulfuric_acid_potassium_hydroxide", "hydrochloric_acid_sodium_hydroxide"),
    },
    {
        "key": "ozone-hydrogen-peroxide",
        "pair": (("Ozone", "O3"), ("Hydrogen peroxide", "H2O2")),
        "answer": "The simplified aqueous peroxone equation combines ozone and hydrogen peroxide to form oxygen and water.",
        "description": "Balance the simplified ozone and hydrogen peroxide equation, identify oxygen gas, and separate its bubble cue from the real peroxone pathway.",
        "goal": "Balance the net equation and separate its oxygen gas cue from the real reaction pathway.",
        "limit": "The real pathway includes short-lived intermediates. OmniLab does not model them, reaction rate, or ozone exposure.",
        "observation": "Oxygen evolution can produce bubbles. The virtual bubble cue does not measure gas volume or show the intermediate reactions.",
        "steps": (
            ("Count oxygen atoms", "O3 and H2O2 supply five oxygen atoms. Two O2 molecules and one H2O contain the same total."),
            ("Count hydrogen atoms", "H2O2 supplies two hydrogen atoms. They appear together in the single water molecule."),
            ("Read the model boundary", "The balanced net equation summarizes products. It does not describe the short-lived reactive species in real peroxone chemistry."),
        ),
        "questions": (
            ("What gas does the model predict?", "It predicts oxygen gas, O2, in the simplified net equation."),
            ("Does the equation show every reaction step?", "No. The real aqueous pathway includes short-lived intermediates outside this deterministic model."),
        ),
        "pattern": "oxidation",
        "products": ("O2", "H2O"),
        "related": ("potassium_permanganate_hydrogen_peroxide", "hydrogen_oxygen"),
    },
]


CYCLE47_GUIDES = {}
CYCLE47_DEMOS = {}
for item in CONTENT:
    key = item["key"]
    canonical_key = key.replace("-", "_")
    reactants = [{"name": name, "formula": formula} for name, formula in item["pair"]]
    reaction = get_reaction([part["formula"] for part in reactants])
    name = f"{reactants[0]['name']} and {reactants[1]['name'].lower()}"
    CYCLE47_GUIDES[key] = {
        "slug": f"{key}-reaction",
        "route_name": f"guide_{canonical_key}",
        "canonical_key": canonical_key,
        "visit_source": "guide_virtual_lab",
        "demo_route_name": f"demo_{canonical_key}",
        "title": f"What happens when {name[0].lower() + name[1:]} react?",
        "page_title": f"{name} reaction | OmniLab",
        "description": item["description"],
        "reading_time": "4 minute read",
        "direct_answer": item["answer"],
        "opening_boundary": item["limit"],
        "student_job": item["goal"],
        "reactants": reactants,
        "setup_summary": "The supported pair is prepared in the virtual beaker. Analyze waits for you.",
        "cta_label": "Open the prepared example",
        "equation": reaction["equation"],
        "explanation": reaction["explanation"],
        "observation_title": item["observation"].split(". ")[0],
        "observation": item["observation"],
        "observation_class": (
            "observation-bubbles" if reaction["effect"] == "bubble"
            else "observation-yellow" if reaction["effect"] == "precipitate"
            else "observation-clear"
        ),
        "observation_label": (
            "Oxygen bubbles" if reaction["effect"] == "bubble"
            else "Yellow precipitate" if reaction["effect"] == "precipitate"
            else "Simplified result"
        ),
        "study_steps": [{"title": title, "body": body} for title, body in item["steps"]],
        "common_questions": [{"question": question, "answer": answer} for question, answer in item["questions"]],
        "safety": reaction["safety"].split(" | "),
        "boundary": item["limit"] + " " + BOUNDARY,
    }
    CYCLE47_DEMOS[key] = {
        "id": key,
        "version": "v1",
        "selectedChemicals": [part["formula"] for part in reactants],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": " + ".join(part["formula"] for part in reactants),
        "title": f"{name}, ready to analyze",
        "page_title": f"OmniLab - {name} prepared example",
        "page_description": "Open the supported pair, then select Analyze for an educational prediction.",
    }
