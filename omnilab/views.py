import hashlib
import ipaddress
import json
import logging
import re
import sqlite3
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie

from .email_delivery import (
    ContactEmailDeliveryCountError,
    get_contact_email_failure_category,
    validate_contact_email_configuration,
)
from .forms import ContactForm, REACTION_FEEDBACK_SOURCE
from .reactions import (
    PRECIPITATE_COLORS,
    get_reaction,
    supported_reaction_pairs,
)


contact_logger = logging.getLogger("omnilab.contact")


def health(request):
    """Return a dependency-free liveness response for hosting checks."""
    return HttpResponse("ok\n", content_type="text/plain")

PRODUCTION_BASE_URL = settings.OMNILAB_PUBLIC_ORIGIN
SOCIAL_PREVIEW_URL = (
    f"{PRODUCTION_BASE_URL}/static/images/omnilab-social-preview.png"
)
SOCIAL_PREVIEW_ALT = (
    "OmniLab virtual chemistry lab showing sodium and chlorine selected, "
    "a sodium chloride equation, reaction analysis, and safety guidance."
)
PUBLIC_CANONICAL_URLS = {
    "index": f"{PRODUCTION_BASE_URL}/",
    "pricing": f"{PRODUCTION_BASE_URL}/pricing/",
    "contact": f"{PRODUCTION_BASE_URL}/contact/",
    "faq": f"{PRODUCTION_BASE_URL}/faq/",
    "guides": f"{PRODUCTION_BASE_URL}/guides/",
    "privacy": f"{PRODUCTION_BASE_URL}/privacy/",
    "terms": f"{PRODUCTION_BASE_URL}/terms/",
    "sodium_chlorine_reaction": (
        f"{PRODUCTION_BASE_URL}/guides/sodium-and-chlorine-reaction/"
    ),
    "sodium_chlorine_formula": (
        f"{PRODUCTION_BASE_URL}/guides/sodium-and-chlorine-formula/"
    ),
    "sodium_chlorine_ionic_bond": (
        f"{PRODUCTION_BASE_URL}/guides/sodium-and-chlorine-ionic-bond/"
    ),
    "chemical_reaction_virtual_lab": (
        f"{PRODUCTION_BASE_URL}/guides/chemical-reaction-virtual-lab/"
    ),
    "limewater_carbon_dioxide": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "why-limewater-turns-cloudy-with-carbon-dioxide/"
    ),
    "sodium_carbonate_hydrochloric_acid": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "why-sodium-carbonate-fizzes-with-hydrochloric-acid/"
    ),
    "silver_nitrate_potassium_iodide": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "silver-nitrate-potassium-iodide-precipitate/"
    ),
    "copper_sulfate_potassium_hydroxide": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "copper-ii-sulfate-potassium-hydroxide-precipitate/"
    ),
    "sodium_water": (
        f"{PRODUCTION_BASE_URL}/guides/reaction-of-sodium-in-water/"
    ),
    "zinc_hydrochloric_acid": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "zinc-and-hydrochloric-acid-reaction/"
    ),
    "acetic_acid_sodium_bicarbonate": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "acetic-acid-and-sodium-bicarbonate-reaction/"
    ),
    "hydrogen_oxygen": (
        f"{PRODUCTION_BASE_URL}/guides/hydrogen-and-oxygen-reaction/"
    ),
    "iron_oxygen": (
        f"{PRODUCTION_BASE_URL}/guides/reaction-of-iron-with-oxygen/"
    ),
    "hydrochloric_acid_sodium_hydroxide": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "hydrochloric-acid-and-sodium-hydroxide-reaction/"
    ),
    "silver_nitrate_sodium_chloride": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "silver-nitrate-and-sodium-chloride-reaction/"
    ),
    "carbon_monoxide_oxygen": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "carbon-monoxide-and-oxygen-reaction/"
    ),
    "carbon_dioxide_water": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "carbon-dioxide-and-water-reaction/"
    ),
    "iron_hydrochloric_acid": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "iron-and-hydrochloric-acid-reaction/"
    ),
    "copper_oxygen": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "reaction-of-copper-with-oxygen/"
    ),
    "potassium_permanganate_hydrogen_peroxide": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "potassium-permanganate-and-hydrogen-peroxide-reaction/"
    ),
    "sodium_chloride_water": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "sodium-chloride-and-water-reaction/"
    ),
    "carbon_dioxide_sodium_hydroxide": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "carbon-dioxide-and-sodium-hydroxide-reaction/"
    ),
    "nitrogen_dioxide_water": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "nitrogen-dioxide-and-water-reaction/"
    ),
    "hydrogen_chlorine": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "hydrogen-and-chlorine-reaction/"
    ),
    "carbon_oxygen": (
        f"{PRODUCTION_BASE_URL}/guides/"
        "carbon-and-oxygen-reaction/"
    ),
}
SODIUM_CHLORINE_DEMO_URL = f"{PRODUCTION_BASE_URL}/demo/sodium-chlorine/"
FIRST_EXPERIMENT_URL = f"{PRODUCTION_BASE_URL}/first-experiment/"
REACTION_FEEDBACK_VIEWED_EVENT = "reaction_feedback_viewed"
REACTION_FEEDBACK_ACCEPTED_EVENT = "reaction_feedback_accepted"
REACTION_FEEDBACK_VALIDATION_FAILED_EVENT = (
    "reaction_feedback_validation_failed"
)
REACTION_FEEDBACK_RATE_LIMITED_EVENT = "reaction_feedback_rate_limited"
REACTION_FEEDBACK_DELIVERY_FAILED_EVENT = (
    "reaction_feedback_delivery_failed"
)
SODIUM_CHLORINE_DEMO = {
    "id": "first-supported-reaction",
    "version": "v1",
    "selectedChemicals": ["Na", "Cl2"],
    "vessel": "beaker",
    "liquidColor": "#89a83b",
    "mixture_label": "Na + Cl2",
    "title": "Sodium and chlorine, ready to analyze",
    "page_title": "OmniLab - Sodium and chlorine reaction demo",
    "page_description": (
        "Open a prepared Sodium and Chlorine setup, then choose whether to "
        "request an educational reaction prediction."
    ),
    "url": SODIUM_CHLORINE_DEMO_URL,
}
FIRST_EXPERIMENT = {
    "id": "sodium-chlorine-first-experiment",
    "version": "v1",
    "page_title": "Your first virtual chemistry experiment | OmniLab",
    "page_description": (
        "Learn the OmniLab controls by building a Sodium and Chlorine "
        "prediction one guided step at a time."
    ),
    "url": FIRST_EXPERIMENT_URL,
}
REACTION_DEMOS = {
    "sodium-chlorine": SODIUM_CHLORINE_DEMO,
    "carbon-dioxide-calcium-hydroxide": {
        "id": "limewater-carbon-dioxide",
        "version": "v1",
        "selectedChemicals": ["Ca(OH)2", "CO2"],
        "vessel": "beaker",
        "liquidColor": "#6d7782",
        "mixture_label": "Ca(OH)2 + CO2",
        "title": "Limewater and carbon dioxide, ready to analyze",
        "page_title": "OmniLab - Limewater and carbon dioxide demo",
        "page_description": (
            "Open a prepared Calcium hydroxide and Carbon dioxide setup, then "
            "choose whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "carbon-dioxide-calcium-hydroxide/"
        ),
    },
    "sodium-carbonate-hydrochloric-acid": {
        "id": "sodium-carbonate-hydrochloric-acid",
        "version": "v1",
        "selectedChemicals": ["Na2CO3", "HCl"],
        "vessel": "beaker",
        "liquidColor": "#d0a22f",
        "mixture_label": "Na2CO3 + HCl",
        "title": "Sodium carbonate and hydrochloric acid, ready to analyze",
        "page_title": "OmniLab - Sodium carbonate and hydrochloric acid demo",
        "page_description": (
            "Open a prepared Sodium carbonate and Hydrochloric acid setup, "
            "then choose whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "sodium-carbonate-hydrochloric-acid/"
        ),
    },
    "silver-nitrate-potassium-iodide": {
        "id": "silver-nitrate-potassium-iodide",
        "version": "v1",
        "selectedChemicals": ["AgNO3", "KI"],
        "vessel": "beaker",
        "liquidColor": "#a77742",
        "mixture_label": "AgNO3 + KI",
        "title": "Silver nitrate and potassium iodide, ready to analyze",
        "page_title": "OmniLab - Silver nitrate and potassium iodide demo",
        "page_description": (
            "Open a prepared Silver nitrate and Potassium iodide setup, then "
            "choose whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "silver-nitrate-potassium-iodide/"
        ),
    },
    "copper-sulfate-potassium-hydroxide": {
        "id": "copper-sulfate-potassium-hydroxide",
        "version": "v1",
        "selectedChemicals": ["CuSO4", "KOH"],
        "vessel": "beaker",
        "liquidColor": "#5ba7d1",
        "mixture_label": "CuSO4 + KOH",
        "title": (
            "Copper(II) sulfate and potassium hydroxide, ready to analyze"
        ),
        "page_title": (
            "OmniLab - Copper(II) sulfate and potassium hydroxide demo"
        ),
        "page_description": (
            "Open a prepared Copper(II) sulfate and Potassium hydroxide "
            "setup, then choose whether to request an educational reaction "
            "prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "copper-sulfate-potassium-hydroxide/"
        ),
    },
    "sodium-water": {
        "id": "sodium-water",
        "version": "v1",
        "selectedChemicals": ["Na", "H2O"],
        "vessel": "beaker",
        "liquidColor": "#2b9ed8",
        "mixture_label": "Na + H2O",
        "title": "Sodium and water, ready to analyze",
        "page_title": "OmniLab - Sodium and water reaction demo",
        "page_description": (
            "Open a prepared Sodium and Water setup, then choose whether to "
            "request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/sodium-water/",
    },
    "zinc-hydrochloric-acid": {
        "id": "zinc-hydrochloric-acid",
        "version": "v1",
        "selectedChemicals": ["Zn", "HCl"],
        "vessel": "beaker",
        "liquidColor": "#8d98a3",
        "mixture_label": "Zn + HCl",
        "title": "Zinc and hydrochloric acid, ready to analyze",
        "page_title": "OmniLab - Zinc and hydrochloric acid demo",
        "page_description": (
            "Open a prepared Zinc and Hydrochloric acid setup, then choose "
            "whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/zinc-hydrochloric-acid/"
        ),
    },
    "acetic-acid-sodium-bicarbonate": {
        "id": "acetic-acid-sodium-bicarbonate",
        "version": "v1",
        "selectedChemicals": ["CH3COOH", "NaHCO3"],
        "vessel": "beaker",
        "liquidColor": "#b9c4cc",
        "mixture_label": "CH3COOH + NaHCO3",
        "title": "Acetic acid and sodium bicarbonate, ready to analyze",
        "page_title": (
            "OmniLab - Acetic acid and sodium bicarbonate demo"
        ),
        "page_description": (
            "Open a prepared Acetic acid and Sodium bicarbonate setup, then "
            "choose whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "acetic-acid-sodium-bicarbonate/"
        ),
    },
    "hydrogen-oxygen": {
        "id": "hydrogen-oxygen",
        "version": "v1",
        "selectedChemicals": ["H2", "O2"],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": "H2 + O2",
        "title": "Hydrogen and oxygen, ready to analyze",
        "page_title": "OmniLab - Hydrogen and oxygen reaction demo",
        "page_description": (
            "Open a prepared Hydrogen and Oxygen setup, then choose whether "
            "to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/hydrogen-oxygen/",
    },
    "iron-oxygen": {
        "id": "iron-oxygen",
        "version": "v1",
        "selectedChemicals": ["Fe", "O2"],
        "vessel": "beaker",
        "liquidColor": "#9b6958",
        "mixture_label": "Fe + O2",
        "title": "Iron and oxygen, ready to analyze",
        "page_title": "OmniLab - Iron and oxygen reaction demo",
        "page_description": (
            "Open a prepared Iron and Oxygen setup, then choose whether to "
            "request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/iron-oxygen/",
    },
    "hydrochloric-acid-sodium-hydroxide": {
        "id": "hydrochloric-acid-sodium-hydroxide",
        "version": "v1",
        "selectedChemicals": ["HCl", "NaOH"],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": "HCl + NaOH",
        "title": (
            "Hydrochloric acid and sodium hydroxide, ready to analyze"
        ),
        "page_title": (
            "OmniLab - Hydrochloric acid and sodium hydroxide demo"
        ),
        "page_description": (
            "Open a prepared Hydrochloric acid and Sodium hydroxide setup, "
            "then choose whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "hydrochloric-acid-sodium-hydroxide/"
        ),
    },
    "silver-nitrate-sodium-chloride": {
        "id": "silver-nitrate-sodium-chloride",
        "version": "v1",
        "selectedChemicals": ["AgNO3", "NaCl"],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": "AgNO3 + NaCl",
        "title": "Silver nitrate and sodium chloride, ready to analyze",
        "page_title": "OmniLab - Silver nitrate and sodium chloride demo",
        "page_description": (
            "Open a prepared Silver nitrate and Sodium chloride setup, then "
            "choose whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "silver-nitrate-sodium-chloride/"
        ),
    },
    "carbon-monoxide-oxygen": {
        "id": "carbon-monoxide-oxygen",
        "version": "v1",
        "selectedChemicals": ["CO", "O2"],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": "CO + O2",
        "title": "Carbon monoxide and oxygen, ready to analyze",
        "page_title": "OmniLab - Carbon monoxide and oxygen reaction demo",
        "page_description": (
            "Open a prepared Carbon monoxide and Oxygen setup, then choose "
            "whether to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/carbon-monoxide-oxygen/",
    },
    "carbon-dioxide-water": {
        "id": "carbon-dioxide-water",
        "version": "v1",
        "selectedChemicals": ["CO2", "H2O"],
        "vessel": "beaker",
        "liquidColor": "#2b9ed8",
        "mixture_label": "CO2 + H2O",
        "title": "Carbon dioxide and water, ready to analyze",
        "page_title": "OmniLab - Carbon dioxide and water reaction demo",
        "page_description": (
            "Open a prepared Carbon dioxide and Water setup, then choose "
            "whether to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/carbon-dioxide-water/",
    },
    "nitrogen-dioxide-water": {
        "id": "nitrogen-dioxide-water",
        "version": "v1",
        "selectedChemicals": ["NO2", "H2O"],
        "vessel": "beaker",
        "liquidColor": "#a85f32",
        "mixture_label": "NO2 + H2O",
        "title": "Nitrogen dioxide and water, ready to analyze",
        "page_title": "OmniLab - Nitrogen dioxide and water demo",
        "page_description": (
            "Open a prepared Nitrogen dioxide and Water setup, then choose "
            "whether to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/nitrogen-dioxide-water/",
    },
    "hydrogen-chlorine": {
        "id": "hydrogen-chlorine",
        "version": "v1",
        "selectedChemicals": ["H2", "Cl2"],
        "vessel": "beaker",
        "liquidColor": "#9cab4f",
        "mixture_label": "H2 + Cl2",
        "title": "Hydrogen and chlorine, ready to analyze",
        "page_title": "OmniLab - Hydrogen and chlorine demo",
        "page_description": (
            "Open a prepared Hydrogen and Chlorine setup, then choose "
            "whether to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/hydrogen-chlorine/",
    },
    "carbon-oxygen": {
        "id": "carbon-oxygen",
        "version": "v1",
        "selectedChemicals": ["C", "O2"],
        "vessel": "beaker",
        "liquidColor": "#465b66",
        "mixture_label": "C + O2",
        "title": "Carbon and oxygen, ready to analyze",
        "page_title": "OmniLab - Carbon and oxygen demo",
        "page_description": (
            "Open a prepared Carbon and Oxygen setup, then choose whether "
            "to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/carbon-oxygen/",
    },
    "iron-hydrochloric-acid": {
        "id": "iron-hydrochloric-acid",
        "version": "v1",
        "selectedChemicals": ["Fe", "HCl"],
        "vessel": "beaker",
        "liquidColor": "#d0a22f",
        "mixture_label": "Fe + HCl",
        "title": "Iron and hydrochloric acid, ready to analyze",
        "page_title": "OmniLab - Iron and hydrochloric acid reaction demo",
        "page_description": (
            "Open a prepared Iron and Hydrochloric acid setup, then choose "
            "whether to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/iron-hydrochloric-acid/",
    },
    "copper-oxygen": {
        "id": "copper-oxygen",
        "version": "v1",
        "selectedChemicals": ["Cu", "O2"],
        "vessel": "beaker",
        "liquidColor": "#b86938",
        "mixture_label": "Cu + O2",
        "title": "Copper and oxygen, ready to analyze",
        "page_title": "OmniLab - Copper and oxygen reaction demo",
        "page_description": (
            "Open a prepared Copper and Oxygen setup, then choose whether "
            "to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/copper-oxygen/",
    },
    "potassium-permanganate-hydrogen-peroxide": {
        "id": "potassium-permanganate-hydrogen-peroxide",
        "version": "v1",
        "selectedChemicals": ["KMnO4", "H2O2"],
        "vessel": "beaker",
        "liquidColor": "#7f3f98",
        "mixture_label": "KMnO4 + H2O2",
        "title": (
            "Potassium permanganate and hydrogen peroxide, ready to analyze"
        ),
        "page_title": (
            "OmniLab - Potassium permanganate and hydrogen peroxide demo"
        ),
        "page_description": (
            "Open a prepared Potassium permanganate and Hydrogen peroxide "
            "setup, then choose whether to request an educational reaction "
            "prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "potassium-permanganate-hydrogen-peroxide/"
        ),
    },
    "sodium-chloride-water": {
        "id": "sodium-chloride-water",
        "version": "v1",
        "selectedChemicals": ["NaCl", "H2O"],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": "NaCl + H2O",
        "title": "Sodium chloride and water, ready to analyze",
        "page_title": "OmniLab - Sodium chloride and water demo",
        "page_description": (
            "Open a prepared Sodium chloride and Water setup, then choose "
            "whether to request an educational reaction prediction."
        ),
        "url": f"{PRODUCTION_BASE_URL}/demo/sodium-chloride-water/",
    },
    "carbon-dioxide-sodium-hydroxide": {
        "id": "carbon-dioxide-sodium-hydroxide",
        "version": "v1",
        "selectedChemicals": ["CO2", "NaOH"],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": "CO2 + NaOH",
        "title": "Carbon dioxide and sodium hydroxide, ready to analyze",
        "page_title": "OmniLab - Carbon dioxide and sodium hydroxide demo",
        "page_description": (
            "Open a prepared Carbon dioxide and Sodium hydroxide setup, then "
            "choose whether to request an educational reaction prediction."
        ),
        "url": (
            f"{PRODUCTION_BASE_URL}/demo/"
            "carbon-dioxide-sodium-hydroxide/"
        ),
    },
}
CHEMICAL_REACTION_VIRTUAL_LAB_VISIT_SOURCE = "guide_virtual_lab"
SUPPORTED_REACTION_EFFECTS = frozenset(
    {"explosion", "bubble", "precipitate", "none"}
)

GUIDED_EXPERIMENT_PAGES = {
    "reaction": {
        "route_name": "guide_sodium_chlorine_reaction",
        "canonical_key": "sodium_chlorine_reaction",
        "visit_source": "guide_reaction",
        "title": "What happens when sodium reacts with chlorine?",
        "page_title": "Sodium and chlorine reaction | OmniLab student guide",
        "description": (
            "See what sodium and chlorine form, read the balanced equation, "
            "and open the supported reaction in OmniLab's virtual lab."
        ),
        "context": "Reaction guide",
        "reading_time": "4 minute read",
        "direct_answer": (
            "Sodium and chlorine form sodium chloride, an ionic solid. "
            "The balanced equation is 2Na(s) + Cl₂(g) → 2NaCl(s)."
        ),
        "equation_label": "Balanced reaction",
        "equation": "2Na(s) + Cl₂(g) → 2NaCl(s)",
        "equation_note": (
            "Two sodium atoms are needed for one chlorine molecule because "
            "elemental chlorine is written as Cl₂."
        ),
        "section_title": "Read the reaction in three moves",
        "steps": [
            {
                "number": "01",
                "title": "Start with the reactants",
                "body": (
                    "The reactant side contains sodium metal, Na, and "
                    "diatomic chlorine gas, Cl₂."
                ),
            },
            {
                "number": "02",
                "title": "Track the electron transfer",
                "body": (
                    "Each sodium atom loses one electron and each chlorine "
                    "atom gains one, producing Na⁺ and Cl⁻ ions."
                ),
            },
            {
                "number": "03",
                "title": "Name the product",
                "body": (
                    "Oppositely charged ions attract in a crystal lattice, "
                    "so the product is solid sodium chloride, NaCl."
                ),
            },
        ],
        "notice_title": "What to notice in OmniLab",
        "notice_points": [
            "The prepared setup selects Sodium and Chlorine.",
            "The prediction uses those selected chemicals only.",
            "The beaker is a visual aid and does not change the prediction.",
        ],
    },
    "formula": {
        "route_name": "guide_sodium_chlorine_formula",
        "canonical_key": "sodium_chlorine_formula",
        "visit_source": "guide_formula",
        "title": "What formula forms from sodium and chlorine?",
        "page_title": "Sodium and chlorine formula | OmniLab student guide",
        "description": (
            "Learn why sodium and chlorine form NaCl, connect the ion charges "
            "to the 1:1 formula, and try the supported setup in OmniLab."
        ),
        "context": "Formula guide",
        "reading_time": "3 minute read",
        "direct_answer": (
            "The formula is NaCl. Sodium forms Na⁺ and chlorine forms Cl⁻, "
            "so one ion of each gives an electrically neutral formula unit."
        ),
        "equation_label": "Formula and reaction",
        "equation": "Na⁺ + Cl⁻ → NaCl",
        "equation_note": (
            "For the elemental reaction, balance chlorine as Cl₂: "
            "2Na(s) + Cl₂(g) → 2NaCl(s)."
        ),
        "section_title": "Build the formula from the charges",
        "steps": [
            {
                "number": "01",
                "title": "Write the ions",
                "body": (
                    "Sodium is a group 1 metal and forms Na⁺. Chlorine "
                    "accepts an electron and forms the chloride ion, Cl⁻."
                ),
            },
            {
                "number": "02",
                "title": "Make the charge total zero",
                "body": (
                    "A +1 sodium ion and a −1 chloride ion balance in a 1:1 "
                    "ratio. No subscripts are needed in NaCl."
                ),
            },
            {
                "number": "03",
                "title": "Use formula-unit language",
                "body": (
                    "Solid sodium chloride is a repeating ionic lattice, so "
                    "NaCl describes its simplest ion ratio rather than one "
                    "discrete molecule."
                ),
            },
        ],
        "notice_title": "Use the lab to connect formula and equation",
        "notice_points": [
            "The compounds matrix starts with Na + Cl₂.",
            "The returned equation should use only the selected reactants.",
            "Check the generated explanation against your course materials.",
        ],
    },
    "ionic-bond": {
        "route_name": "guide_sodium_chlorine_ionic_bond",
        "canonical_key": "sodium_chlorine_ionic_bond",
        "visit_source": "guide_ionic_bond",
        "title": "Why do sodium and chlorine form an ionic bond?",
        "page_title": "Sodium and chlorine ionic bond | OmniLab student guide",
        "description": (
            "Follow the electron transfer from sodium to chlorine, see how "
            "Na⁺ and Cl⁻ form an ionic solid, and explore it in OmniLab."
        ),
        "context": "Bonding guide",
        "reading_time": "4 minute read",
        "direct_answer": (
            "Sodium transfers an electron to chlorine, creating Na⁺ and Cl⁻. "
            "Their opposite charges attract, forming an ionic lattice."
        ),
        "equation_label": "Electron transfer model",
        "equation": "Na → Na⁺ + e⁻   |   Cl + e⁻ → Cl⁻",
        "equation_note": (
            "In the full elemental reaction, one Cl₂ molecule accepts two "
            "electrons from two sodium atoms."
        ),
        "section_title": "From neutral atoms to an ionic lattice",
        "steps": [
            {
                "number": "01",
                "title": "Sodium loses one electron",
                "body": (
                    "A neutral sodium atom becomes Na⁺ when it gives up its "
                    "outer electron."
                ),
            },
            {
                "number": "02",
                "title": "Chlorine gains that electron",
                "body": (
                    "A chlorine atom becomes Cl⁻ after accepting one electron, "
                    "giving the two ions opposite charges."
                ),
            },
            {
                "number": "03",
                "title": "Attraction builds the solid",
                "body": (
                    "Electrostatic attraction holds many Na⁺ and Cl⁻ ions in "
                    "a repeating three-dimensional sodium chloride lattice."
                ),
            },
        ],
        "notice_title": "What the virtual prediction can show",
        "notice_points": [
            "The lab can return an equation and short explanation.",
            "Its result is generated and may be incomplete or wrong.",
            "Use a textbook or instructor to verify the bonding model.",
        ],
    },
}

OBSERVATION_GUIDE_PAGES = {
    "limewater-carbon-dioxide": {
        "route_name": "guide_limewater_carbon_dioxide",
        "canonical_key": "limewater_carbon_dioxide",
        "visit_source": "guide_observation_a",
        "demo_route_name": "demo_carbon_dioxide_calcium_hydroxide",
        "title": "Why does limewater turn cloudy when carbon dioxide is added?",
        "page_title": (
            "Why limewater turns cloudy with carbon dioxide | OmniLab"
        ),
        "description": (
            "See why carbon dioxide turns limewater cloudy, read the balanced "
            "equation, and open the exact supported setup in OmniLab."
        ),
        "reading_time": "4 minute read",
        "direct_answer": (
            "Carbon dioxide reacts with calcium hydroxide in limewater to form "
            "solid calcium carbonate. That suspended white precipitate makes "
            "the mixture look cloudy."
        ),
        "reactants": [
            {"name": "Calcium hydroxide", "formula": "Ca(OH)2"},
            {"name": "Carbon dioxide", "formula": "CO2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Calcium hydroxide and Carbon dioxide. "
            "The burner stays off, and you decide when to analyze."
        ),
        "cta_label": "Try the limewater setup",
        "equation": "Ca(OH)2(aq) + CO2(g) -> CaCO3(s) + H2O(l)",
        "explanation": (
            "Carbon dioxide reacts with calcium hydroxide to form a calcium "
            "carbonate precipitate and water. In the common limewater test, "
            "the suspended calcium carbonate makes the solution appear "
            "cloudy. Excess carbon dioxide can cause further changes that "
            "are outside this simplified equation."
        ),
        "observation_title": "A cloudy white precipitate",
        "observation": (
            "OmniLab shows a bounded white precipitate cue inside the beaker "
            "to represent the expected calcium carbonate solid."
        ),
        "observation_class": "observation-cloudy",
        "observation_label": "Cloudy white",
        "safety": [
            (
                "Avoid breathing calcium hydroxide dust or carbon dioxide-rich "
                "air."
            ),
            "Wear splash goggles and gloves when handling limewater.",
            "Work with carbon dioxide in a well-ventilated area.",
        ],
        "boundary": (
            "OmniLab predicts this simplified limewater test. It does not "
            "simulate gas delivery, concentration, rate, yield, or the further "
            "chemistry that excess carbon dioxide can cause."
        ),
    },
    "sodium-carbonate-hydrochloric-acid": {
        "route_name": "guide_sodium_carbonate_hydrochloric_acid",
        "canonical_key": "sodium_carbonate_hydrochloric_acid",
        "visit_source": "guide_observation_b",
        "demo_route_name": "demo_sodium_carbonate_hydrochloric_acid",
        "title": "Why does sodium carbonate fizz with hydrochloric acid?",
        "page_title": (
            "Why sodium carbonate fizzes with hydrochloric acid | OmniLab"
        ),
        "description": (
            "See why sodium carbonate fizzes with hydrochloric acid, read the "
            "balanced equation, and try the exact supported setup in OmniLab."
        ),
        "reading_time": "4 minute read",
        "direct_answer": (
            "Sodium carbonate reacts with hydrochloric acid to form sodium "
            "chloride, water, and carbon dioxide gas. The escaping carbon "
            "dioxide is what makes the mixture fizz."
        ),
        "reactants": [
            {"name": "Sodium carbonate", "formula": "Na2CO3"},
            {"name": "Hydrochloric acid", "formula": "HCl"},
        ],
        "setup_summary": (
            "An open beaker is prepared with Sodium carbonate and Hydrochloric "
            "acid. The burner stays off, and you decide when to analyze."
        ),
        "cta_label": "Try the fizzing setup",
        "equation": (
            "Na2CO3(aq) + 2HCl(aq) -> "
            "2NaCl(aq) + CO2(g) + H2O(l)"
        ),
        "explanation": (
            "Sodium carbonate reacts with hydrochloric acid to form sodium "
            "chloride, carbon dioxide, and water. Carbon dioxide escaping "
            "from the solution causes bubbling. Two hydrogen ions are needed "
            "for each carbonate ion in the balanced equation."
        ),
        "observation_title": "Carbon dioxide bubbles",
        "observation": (
            "OmniLab shows a bounded bubble cue inside the beaker to represent "
            "the expected gas evolution."
        ),
        "observation_class": "observation-bubbles",
        "observation_label": "Visible fizzing",
        "safety": [
            "Wear splash goggles and acid-resistant gloves.",
            "Add hydrochloric acid slowly to control foaming and heat.",
            "Keep the vessel open and work in a ventilated area.",
        ],
        "boundary": (
            "The bubble cue represents expected gas evolution, not its rate, "
            "volume, temperature change, or real-procedure safety. Vessel and "
            "burner choices do not affect the prediction."
        ),
    },
    "silver-nitrate-potassium-iodide": {
        "route_name": "guide_silver_nitrate_potassium_iodide",
        "canonical_key": "silver_nitrate_potassium_iodide",
        "visit_source": "guide_observation_c",
        "demo_route_name": "demo_silver_nitrate_potassium_iodide",
        "title": (
            "What precipitate forms when silver nitrate reacts with "
            "potassium iodide?"
        ),
        "page_title": (
            "Silver nitrate and potassium iodide precipitate | OmniLab"
        ),
        "description": (
            "Identify the precipitate from silver nitrate and potassium "
            "iodide, read the equation, and try the supported setup in OmniLab."
        ),
        "reading_time": "4 minute read",
        "direct_answer": (
            "Silver nitrate and potassium iodide form silver iodide, an "
            "insoluble yellow precipitate. Potassium and nitrate ions remain "
            "dissolved in the solution."
        ),
        "reactants": [
            {"name": "Silver nitrate", "formula": "AgNO3"},
            {"name": "Potassium iodide", "formula": "KI"},
        ],
        "setup_summary": (
            "A beaker is prepared with Silver nitrate and Potassium iodide. "
            "The burner stays off, and you decide when to analyze."
        ),
        "cta_label": "Try the yellow precipitate setup",
        "equation": "AgNO3(aq) + KI(aq) -> AgI(s) + KNO3(aq)",
        "explanation": (
            "Silver nitrate and potassium iodide undergo a precipitation "
            "reaction. Insoluble silver iodide forms as a yellow solid while "
            "potassium and nitrate ions remain in solution. The molecular "
            "equation has a one-to-one reactant ratio."
        ),
        "observation_title": "A yellow silver iodide precipitate",
        "observation": (
            "OmniLab shows a bounded yellow precipitate cue inside the beaker "
            "to represent the expected silver iodide solid."
        ),
        "observation_class": "observation-yellow",
        "observation_label": "Yellow solid",
        "safety": [
            "Wear gloves and splash goggles when handling silver nitrate.",
            "Protect the silver iodide precipitate from strong light.",
            "Collect silver-containing waste for approved disposal.",
        ],
        "boundary": (
            "The yellow cue is a simplified expected observation. OmniLab does "
            "not model concentration, yield, particle size, light-driven "
            "decomposition, or waste handling."
        ),
    },
    "copper-sulfate-potassium-hydroxide": {
        "route_name": "guide_copper_sulfate_potassium_hydroxide",
        "canonical_key": "copper_sulfate_potassium_hydroxide",
        "visit_source": "guide_observation_d",
        "demo_route_name": "demo_copper_sulfate_potassium_hydroxide",
        "title": (
            "What precipitate forms from copper(II) sulfate and potassium "
            "hydroxide?"
        ),
        "page_title": (
            "Copper(II) sulfate and potassium hydroxide precipitate | OmniLab"
        ),
        "description": (
            "Identify the blue precipitate from copper(II) sulfate and "
            "potassium hydroxide, read the ionic equation, and try it in "
            "OmniLab."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Copper(II) sulfate and potassium hydroxide form copper(II) "
            "hydroxide, an insoluble blue precipitate. Potassium and sulfate "
            "ions remain dissolved in the solution."
        ),
        "reactants": [
            {"name": "Copper(II) sulfate", "formula": "CuSO4"},
            {"name": "Potassium hydroxide", "formula": "KOH"},
        ],
        "setup_summary": (
            "A beaker is prepared with Copper(II) sulfate and Potassium "
            "hydroxide. The burner stays off, and you decide when to analyze."
        ),
        "cta_label": "Try the blue precipitate setup",
        "equation": (
            "CuSO4(aq) + 2KOH(aq) -> Cu(OH)2(s) + K2SO4(aq)"
        ),
        "explanation": (
            "Copper(II) sulfate and potassium hydroxide undergo a double "
            "displacement reaction. Insoluble copper(II) hydroxide forms as "
            "a blue precipitate while potassium sulfate remains in solution. "
            "Two hydroxide ions are required for each copper(II) ion."
        ),
        "observation_title": "A blue copper(II) hydroxide precipitate",
        "observation": (
            "OmniLab shows a bounded blue precipitate cue inside the beaker "
            "to represent the expected copper(II) hydroxide solid."
        ),
        "observation_class": "observation-blue",
        "observation_label": "Blue solid",
        "net_ionic_equation": (
            "Cu2+(aq) + 2OH-(aq) -> Cu(OH)2(s)"
        ),
        "spectator_ions": "K+(aq) and SO4^2-(aq)",
        "ionic_explanation": (
            "Copper(II) ions combine with hydroxide ions because copper(II) "
            "hydroxide is insoluble in water. Potassium and sulfate ions do "
            "not form the solid, so they cancel from the complete ionic "
            "equation."
        ),
        "study_steps": [
            {
                "title": "Split the soluble reactants into ions",
                "body": (
                    "CuSO4 provides Cu2+ and SO4^2-. Each KOH provides K+ "
                    "and OH-."
                ),
            },
            {
                "title": "Identify the insoluble product",
                "body": (
                    "Cu2+ combines with two OH- ions to form solid Cu(OH)2, "
                    "the blue precipitate."
                ),
            },
            {
                "title": "Cancel the spectator ions",
                "body": (
                    "K+ and SO4^2- remain aqueous on both sides, leaving the "
                    "net ionic equation for precipitation."
                ),
            },
        ],
        "safety": [
            "Wear splash goggles and chemical-resistant gloves.",
            (
                "Avoid skin contact with copper sulfate and potassium "
                "hydroxide."
            ),
            "Collect copper-containing waste for proper disposal.",
        ],
        "boundary": (
            "The blue cue is a simplified expected observation. OmniLab does "
            "not model concentration, yield, particle size, temperature, "
            "addition order, or waste handling. Vessel and burner choices do "
            "not affect the prediction."
        ),
    },
    "sodium-water": {
        "route_name": "guide_sodium_water",
        "canonical_key": "sodium_water",
        "visit_source": "guide_observation_e",
        "demo_route_name": "demo_sodium_water",
        "title": "What happens when sodium reacts with water?",
        "page_title": (
            "Sodium reacts with water: equation and result | OmniLab"
        ),
        "description": (
            "See what happens when sodium reacts with water, including the "
            "balanced equation, hydrogen bubbles, sodium hydroxide, and "
            "safety limits."
        ),
        "reading_time": "6 minute read",
        "direct_answer": (
            "Sodium reacts with water to form sodium hydroxide and hydrogen "
            "gas. The reaction releases substantial heat, and the escaping "
            "hydrogen appears as bubbles."
        ),
        "reactants": [
            {"name": "Sodium", "formula": "Na"},
            {"name": "Water", "formula": "H2O"},
        ],
        "setup_summary": (
            "A beaker is prepared with Sodium and Water. The burner stays off, "
            "and you decide when to request the supported prediction."
        ),
        "cta_label": "Try the sodium and water setup",
        "equation": "2Na(s) + 2H2O(l) -> 2NaOH(aq) + H2(g)",
        "explanation": (
            "Sodium reacts with water to form sodium hydroxide and hydrogen "
            "gas. Hydrogen evolution produces bubbles while the strongly "
            "exothermic reaction heats the mixture. Two sodium atoms react "
            "with two water molecules in the balanced equation."
        ),
        "observation_title": "Hydrogen bubbles and released heat",
        "observation": (
            "OmniLab shows a bounded bubble cue inside the beaker to represent "
            "hydrogen gas forming. It does not reproduce the speed, surface "
            "motion, flame, or heat of a physical demonstration."
        ),
        "observation_class": "observation-bubbles",
        "observation_label": "Hydrogen bubbles",
        "study_steps": [
            {
                "title": "Balance sodium and water",
                "body": (
                    "The coefficient 2 appears before Na and H2O. It also "
                    "appears before NaOH, leaving two hydrogen atoms to form "
                    "one H2 molecule."
                ),
            },
            {
                "title": "Identify the gas",
                "body": (
                    "H2 is hydrogen gas. The bubbles are evidence of gas "
                    "evolution, not simply water boiling."
                ),
            },
            {
                "title": "Identify the solution",
                "body": (
                    "NaOH is sodium hydroxide. It remains dissolved, making "
                    "the resulting solution alkaline and corrosive."
                ),
            },
        ],
        "detail_sections": [
            {
                "title": "Why sodium floats and moves",
                "body": (
                    "Sodium is less dense than water, so a small piece floats. "
                    "The reaction heats the metal, which may melt into a ball, "
                    "while uneven hydrogen release can push it across the "
                    "surface. Those physical effects are not part of "
                    "OmniLab's simplified bubble cue."
                ),
            },
            {
                "title": "Why the reaction may show a flame",
                "body": (
                    "The reaction is strongly exothermic and creates flammable "
                    "hydrogen. In some demonstrations, enough heat can ignite "
                    "the hydrogen. A yellow-orange color may also appear from "
                    "excited sodium atoms. OmniLab does not predict ignition."
                ),
            },
            {
                "title": "What remains in the beaker",
                "body": (
                    "The gas leaves the mixture, but sodium hydroxide stays in "
                    "solution. That means the liquid is not merely unchanged "
                    "water: it becomes alkaline and can cause chemical burns."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What type of reaction is sodium with water?",
                "answer": (
                    "It is a redox reaction and a metal displacement reaction. "
                    "Sodium is oxidized to Na+ while hydrogen in water is "
                    "reduced to H2 gas."
                ),
            },
            {
                "question": "Why does sodium move on the surface of water?",
                "answer": (
                    "Sodium floats because it is less dense than water. Gas "
                    "formation and uneven heat release can make it move."
                ),
            },
            {
                "question": "Why is sodium and water dangerous?",
                "answer": (
                    "The reaction releases substantial heat, produces "
                    "flammable hydrogen, and leaves corrosive sodium hydroxide. "
                    "It belongs only in a controlled laboratory."
                ),
            },
            {
                "question": "Is the liquid product still water?",
                "answer": (
                    "Water remains, but the reaction also creates dissolved "
                    "sodium hydroxide. The resulting solution is alkaline."
                ),
            },
        ],
        "safety": [
            "Do not attempt this reaction outside a controlled laboratory.",
            "Keep flames and sparks away from the hydrogen produced.",
            "Use face protection and trained supervision.",
        ],
        "boundary": (
            "OmniLab predicts the balanced products and shows a simplified "
            "bubble cue. It does not model sodium mass, water volume, reaction "
            "rate, temperature, motion, ignition, or a physical procedure."
        ),
    },
    "zinc-hydrochloric-acid": {
        "route_name": "guide_zinc_hydrochloric_acid",
        "canonical_key": "zinc_hydrochloric_acid",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_zinc_hydrochloric_acid",
        "title": "What happens when zinc reacts with hydrochloric acid?",
        "page_title": (
            "Zinc and hydrochloric acid reaction | OmniLab"
        ),
        "description": (
            "See the zinc and hydrochloric acid reaction, balanced equation, "
            "hydrogen bubbles, zinc chloride product, and safety limits."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Zinc reacts with hydrochloric acid to form zinc chloride and "
            "hydrogen gas. The hydrogen leaves the solution as bubbles."
        ),
        "opening_boundary": (
            "The model leaves out acid concentration, zinc surface area, and "
            "reaction rate. Hydrochloric acid is corrosive, and the hydrogen "
            "product is flammable."
        ),
        "student_job": (
            "Use this guide to balance the equation, identify the gas, and "
            "connect the bubbles to a metal-acid displacement reaction."
        ),
        "reactants": [
            {"name": "Zinc", "formula": "Zn"},
            {"name": "Hydrochloric acid", "formula": "HCl"},
        ],
        "setup_summary": (
            "A beaker is prepared with Zinc and Hydrochloric acid. The burner "
            "stays off, and you decide when to request the supported prediction."
        ),
        "cta_label": "Try the zinc and acid setup",
        "equation": "Zn(s) + 2HCl(aq) -> ZnCl2(aq) + H2(g)",
        "explanation": (
            "Zinc displaces hydrogen from hydrochloric acid to form zinc "
            "chloride and hydrogen gas. The bubbles are hydrogen leaving the "
            "solution. Zinc is oxidized while hydrogen ions are reduced in "
            "this single-displacement reaction."
        ),
        "observation_title": "Hydrogen bubbles as zinc is consumed",
        "observation": (
            "OmniLab shows a bounded bubble cue inside the beaker to represent "
            "hydrogen gas forming. It does not reproduce the reaction rate, "
            "temperature change, or gradual loss of the zinc surface."
        ),
        "observation_class": "observation-bubbles",
        "observation_label": "Hydrogen bubbles",
        "study_steps": [
            {
                "title": "Balance the acid",
                "body": (
                    "The coefficient 2 before HCl supplies two chloride ions "
                    "for ZnCl2 and two hydrogen atoms for one H2 molecule."
                ),
            },
            {
                "title": "Track the electrons",
                "body": (
                    "Zinc loses two electrons to become Zn2+. Two hydrogen "
                    "ions gain those electrons and combine as H2 gas."
                ),
            },
            {
                "title": "Identify the evidence",
                "body": (
                    "The bubbles are hydrogen leaving the solution. Zinc is "
                    "consumed while aqueous zinc chloride remains."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What gas forms when zinc reacts with hydrochloric acid?",
                "answer": (
                    "Hydrogen gas forms. In the balanced equation, two H+ "
                    "ions gain electrons and combine to make H2."
                ),
            },
            {
                "question": "What type of reaction is zinc with hydrochloric acid?",
                "answer": (
                    "It is a single-displacement and redox reaction. Zinc "
                    "displaces hydrogen from the acid."
                ),
            },
            {
                "question": "What is oxidized and what is reduced?",
                "answer": (
                    "Zinc is oxidized from Zn to Zn2+. Hydrogen ions are "
                    "reduced to H2 gas."
                ),
            },
            {
                "question": "What remains in the solution?",
                "answer": (
                    "Zinc chloride remains dissolved in water while hydrogen "
                    "gas leaves the mixture."
                ),
            },
        ],
        "safety": [
            "Keep flames and sparks away from the hydrogen produced.",
            "Work in a ventilated area under trained supervision.",
            "Wear acid-resistant gloves and splash goggles.",
        ],
        "boundary": (
            "OmniLab predicts the products and shows a simplified bubble cue. "
            "It does not model reagent concentration, zinc surface area, gas "
            "volume, temperature, reaction rate, or a physical procedure."
        ),
    },
    "acetic-acid-sodium-bicarbonate": {
        "route_name": "guide_acetic_acid_sodium_bicarbonate",
        "canonical_key": "acetic_acid_sodium_bicarbonate",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_acetic_acid_sodium_bicarbonate",
        "title": (
            "What happens when acetic acid reacts with sodium bicarbonate?"
        ),
        "page_title": (
            "Acetic acid and sodium bicarbonate reaction | OmniLab"
        ),
        "description": (
            "See the acetic acid and sodium bicarbonate reaction, balanced "
            "equation, carbon dioxide bubbles, products, and safety limits."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Acetic acid reacts with sodium bicarbonate to form sodium "
            "acetate, carbon dioxide, and water. Escaping carbon dioxide "
            "causes the fizzing."
        ),
        "opening_boundary": (
            "The model leaves out foam height, gas volume, cooling, and "
            "spillover. Carbon dioxide can build pressure in a closed "
            "container, and splashes can irritate eyes."
        ),
        "student_job": (
            "Use this guide to balance the equation, identify the gas, and "
            "connect the fizzing to an acid-bicarbonate reaction."
        ),
        "reactants": [
            {"name": "Acetic acid", "formula": "CH3COOH"},
            {"name": "Sodium bicarbonate", "formula": "NaHCO3"},
        ],
        "setup_summary": (
            "A beaker is prepared with Acetic acid and Sodium bicarbonate. "
            "The burner stays off, and you decide when to request the "
            "supported prediction."
        ),
        "cta_label": "Try the fizzing setup",
        "equation": (
            "CH3COOH(aq) + NaHCO3(s) -> "
            "CH3COONa(aq) + CO2(g) + H2O(l)"
        ),
        "explanation": (
            "Acetic acid reacts with sodium bicarbonate to form sodium "
            "acetate, carbon dioxide, and water. The visible bubbling comes "
            "from carbon dioxide leaving the mixture. The equation has a "
            "one-to-one ratio of acid and bicarbonate."
        ),
        "observation_title": "Carbon dioxide bubbles and visible fizzing",
        "observation": (
            "OmniLab shows a bounded bubble cue inside the beaker to represent "
            "carbon dioxide leaving the mixture. It does not reproduce foam "
            "height, reaction rate, cooling, or spillover."
        ),
        "observation_class": "observation-bubbles",
        "observation_label": "Carbon dioxide bubbles",
        "study_steps": [
            {
                "title": "Balance the one-to-one reaction",
                "body": (
                    "One acetic acid molecule reacts with one bicarbonate "
                    "unit, so every coefficient in the balanced equation is 1."
                ),
            },
            {
                "title": "Identify the gas",
                "body": (
                    "Bicarbonate accepts a proton from the acid. The resulting "
                    "carbonic acid breaks down into CO2 and H2O."
                ),
            },
            {
                "title": "Identify what stays dissolved",
                "body": (
                    "Sodium and acetate ions remain in solution as sodium "
                    "acetate while carbon dioxide leaves as gas."
                ),
            },
        ],
        "common_questions": [
            {
                "question": (
                    "What gas forms when acetic acid reacts with sodium "
                    "bicarbonate?"
                ),
                "answer": (
                    "Carbon dioxide gas forms. Its escape from the liquid "
                    "produces the visible fizzing and bubbles."
                ),
            },
            {
                "question": "What are the products of the reaction?",
                "answer": (
                    "The products are aqueous sodium acetate, carbon dioxide "
                    "gas, and liquid water."
                ),
            },
            {
                "question": "Why does the mixture foam?",
                "answer": (
                    "Rapidly forming carbon dioxide creates many bubbles. "
                    "Their behavior at the liquid surface can produce foam."
                ),
            },
            {
                "question": "What type of reaction is this?",
                "answer": (
                    "It is an acid-base reaction followed by carbonic acid "
                    "decomposition, which releases carbon dioxide gas."
                ),
            },
        ],
        "safety": [
            (
                "Keep the reaction vessel open so carbon dioxide cannot "
                "build pressure."
            ),
            "Wear eye protection to guard against splashes.",
            "Add the bicarbonate in small portions to control foaming.",
        ],
        "boundary": (
            "OmniLab predicts the products and shows a simplified bubble cue. "
            "It does not model reagent concentration, foam height, gas volume, "
            "temperature change, reaction rate, or a physical procedure."
        ),
    },
    "hydrogen-oxygen": {
        "route_name": "guide_hydrogen_oxygen",
        "canonical_key": "hydrogen_oxygen",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_hydrogen_oxygen",
        "title": "What happens when hydrogen reacts with oxygen?",
        "page_title": "Hydrogen and oxygen reaction: equation and result | OmniLab",
        "description": (
            "See the hydrogen and oxygen reaction, balanced equation, water "
            "product, energy release, initiation requirement, and safety limits."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Hydrogen reacts with oxygen to form water when the mixture is "
            "initiated. The reaction releases substantial energy, and "
            "OmniLab predicts the product without simulating ignition."
        ),
        "opening_boundary": (
            "The equation shows the two-to-one molecular ratio and water "
            "product; ignition, flame, pressure, and reaction rate are not "
            "simulated. Hydrogen-oxygen mixtures can ignite explosively."
        ),
        "student_job": (
            "Use this guide to balance the equation, identify the product, and "
            "separate the reaction conditions from the chemical result."
        ),
        "reactants": [
            {"name": "Hydrogen", "formula": "H2"},
            {"name": "Oxygen", "formula": "O2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Hydrogen and Oxygen. The burner stays "
            "off, and you decide when to request the supported prediction."
        ),
        "cta_label": "Try the hydrogen and oxygen setup",
        "equation": "2H2(g) + O2(g) -> 2H2O(l)",
        "explanation": (
            "Hydrogen and oxygen form water when the mixture is initiated. "
            "The reaction is strongly exothermic as O-H bonds form. "
            "Two hydrogen molecules react with one oxygen molecule to "
            "produce two water molecules."
        ),
        "observation_title": "Water forms in a strongly exothermic reaction",
        "observation": (
            "The supported prediction identifies water as the product. OmniLab "
            "does not add a flame, blast, or motion cue for this pair because "
            "its visual effects are simplified, not a physical simulation."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Water product",
        "study_steps": [
            {
                "title": "Balance the two-to-one ratio",
                "body": (
                    "Two H2 molecules supply four hydrogen atoms. One O2 "
                    "molecule supplies two oxygen atoms, producing two H2O "
                    "molecules."
                ),
            },
            {
                "title": "Separate initiation from the products",
                "body": (
                    "Hydrogen and oxygen need an initiation source before the "
                    "reaction proceeds rapidly. That condition is not written "
                    "as another reactant in the balanced equation."
                ),
            },
            {
                "title": "Account for the energy release",
                "body": (
                    "Forming strong O-H bonds releases substantial energy, so "
                    "the reaction is exothermic even though energy does not "
                    "appear as a product formula."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What is the product of hydrogen and oxygen?",
                "answer": (
                    "The product is water. The balanced equation forms two "
                    "water molecules from two hydrogen molecules and one "
                    "oxygen molecule."
                ),
            },
            {
                "question": "Why is the equation 2H2 + O2 -> 2H2O?",
                "answer": (
                    "Those coefficients balance four hydrogen atoms and two "
                    "oxygen atoms on each side of the equation."
                ),
            },
            {
                "question": "Does hydrogen react with oxygen on its own?",
                "answer": (
                    "A hydrogen-oxygen mixture generally needs initiation, "
                    "such as a spark, before it reacts rapidly. That same fact "
                    "also makes the mixture hazardous."
                ),
            },
            {
                "question": "What type of reaction is hydrogen with oxygen?",
                "answer": (
                    "It is a combustion and redox reaction. Hydrogen is "
                    "oxidized, oxygen is reduced, and water forms."
                ),
            },
        ],
        "safety": [
            "Keep the gas mixture away from ignition sources.",
            "Use blast shielding in a supervised laboratory.",
            "Wear splash goggles and protective clothing.",
        ],
        "boundary": (
            "OmniLab predicts water as the product without simulating ignition, "
            "flame, pressure, temperature, gas ratio, reaction rate, or a "
            "physical procedure."
        ),
    },
    "iron-oxygen": {
        "route_name": "guide_iron_oxygen",
        "canonical_key": "iron_oxygen",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_iron_oxygen",
        "title": "What happens in the reaction of iron with oxygen?",
        "page_title": (
            "Reaction of iron with oxygen: equation and result | OmniLab"
        ),
        "description": (
            "See the reaction of iron with oxygen, balanced equation, "
            "iron(III) oxide product, redox changes, observations, and limits."
        ),
        "reading_time": "6 minute read",
        "direct_answer": (
            "Iron reacts with oxygen to form iron oxide. In the simplified "
            "model used by OmniLab, the product is iron(III) oxide, Fe2O3. "
            "The balanced equation uses coefficients 4, 3, and 2. Different "
            "conditions can produce other iron oxides."
        ),
        "student_job": (
            "Use this guide to balance the equation, explain the redox change, "
            "and separate rapid oxidation from slow rusting."
        ),
        "study_intro": (
            "Connect the coefficients and formulas to the products, electron "
            "transfer, and expected observation."
        ),
        "reactants": [
            {"name": "Iron", "formula": "Fe"},
            {"name": "Oxygen", "formula": "O2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Iron and Oxygen. The burner stays off, "
            "and you decide when to request the supported prediction."
        ),
        "cta_label": "Try the iron and oxygen setup",
        "equation": "4Fe(s) + 3O2(g) -> 2Fe2O3(s)",
        "explanation": (
            "Iron can oxidize in oxygen to form iron(III) oxide. The process "
            "is exothermic, although bulk iron may react slowly unless it is "
            "finely divided or heated. Four iron atoms combine with three "
            "oxygen molecules in the simplified balanced equation."
        ),
        "observation_title": "A solid iron oxide product",
        "observation": (
            "This guide uses a simple solid-product diagram for Fe2O3. A real "
            "heated iron sample may glow or spark and leave a dark oxide, while "
            "slow corrosion can produce reddish-brown rust. OmniLab returns "
            "text for this pair and does not render those physical effects."
        ),
        "observation_class": "observation-oxide",
        "observation_label": "Iron(III) oxide",
        "study_steps": [
            {
                "title": "Balance iron and oxygen",
                "body": (
                    "Two Fe2O3 units contain four iron atoms and six oxygen "
                    "atoms. Those six oxygen atoms come from three O2 molecules, "
                    "so the coefficients are 4, 3, and 2."
                ),
            },
            {
                "title": "Track the electron transfer",
                "body": (
                    "Iron moves from oxidation state 0 to +3 and is oxidized. "
                    "Oxygen moves from 0 to -2 and is reduced, so the overall "
                    "change is a redox reaction."
                ),
            },
            {
                "title": "Keep the conditions attached",
                "body": (
                    "Fine or heated iron can oxidize rapidly. Bulk iron usually "
                    "reacts much more slowly, and moisture helps the corrosion "
                    "process commonly called rusting."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What is the word equation for iron and oxygen?",
                "answer": (
                    "The word equation is iron + oxygen -> iron oxide. A formula "
                    "equation must name the oxide being modeled because iron "
                    "can form more than one oxide."
                ),
            },
            {
                "question": "How do you balance Fe + O2 -> Fe2O3?",
                "answer": (
                    "Write 4Fe + 3O2 -> 2Fe2O3. Both sides then contain four "
                    "iron atoms and six oxygen atoms. Coefficients change the "
                    "number of particles, not the formulas of the substances."
                ),
            },
            {
                "question": "Why do some equations show Fe3O4 instead?",
                "answer": (
                    "Iron can form FeO, Fe2O3, Fe3O4, or mixtures of oxides. "
                    "Temperature, oxygen availability, particle size, and other "
                    "conditions affect the product. OmniLab deliberately uses "
                    "the simplified Fe2O3 equation for its supported pair."
                ),
            },
            {
                "question": "Is the reaction of iron with oxygen the same as rusting?",
                "answer": (
                    "Rusting is the slow corrosion of iron in the presence of "
                    "oxygen and moisture. Rapid oxidation of fine or heated iron "
                    "is related chemistry, but the rate, appearance, and mixture "
                    "of oxide products can differ."
                ),
            },
            {
                "question": "What type of reaction is iron with oxygen?",
                "answer": (
                    "It is an oxidation and redox reaction. When iron burns "
                    "rapidly it is also a combustion reaction: iron loses "
                    "electrons as oxygen gains them."
                ),
            },
            {
                "question": "Why can the iron sample gain mass?",
                "answer": (
                    "Oxygen atoms become part of the solid product. If the oxide "
                    "stays with the sample, its mass includes the original iron "
                    "plus oxygen taken from the surrounding gas."
                ),
            },
        ],
        "safety": [
            "Keep fine iron powder away from ignition sources.",
            "Use heat-resistant tools for heated samples.",
            "Wear eye protection and avoid oxide dust.",
        ],
        "boundary": (
            "OmniLab uses one simplified Fe2O3 product model. It does not "
            "simulate temperature, oxygen supply, moisture, particle size, "
            "reaction rate, sparks, oxide mixtures, or a physical procedure."
        ),
    },
    "hydrochloric-acid-sodium-hydroxide": {
        "route_name": "guide_hydrochloric_acid_sodium_hydroxide",
        "canonical_key": "hydrochloric_acid_sodium_hydroxide",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_hydrochloric_acid_sodium_hydroxide",
        "title": (
            "What happens when hydrochloric acid reacts with sodium hydroxide?"
        ),
        "page_title": (
            "Hydrochloric acid and sodium hydroxide reaction | OmniLab"
        ),
        "description": (
            "See the hydrochloric acid and sodium hydroxide reaction, balanced "
            "equation, neutralization products, net ionic change, and limits."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Hydrochloric acid and sodium hydroxide neutralize to form sodium "
            "chloride and water. The solution can warm because neutralization "
            "is exothermic, but there may be no dramatic visible change."
        ),
        "opening_boundary": (
            "The model leaves out concentration, volume, temperature, pH, and "
            "a titration endpoint. Both hydrochloric acid and sodium hydroxide "
            "can cause serious chemical burns."
        ),
        "student_job": (
            "Use this guide to identify the products, balance the equation, "
            "and reduce it to the net ionic change that forms water."
        ),
        "study_intro": (
            "Connect the one-to-one molecular equation to the ions that react, "
            "the spectator ions, and the expected temperature change."
        ),
        "reactants": [
            {"name": "Hydrochloric acid", "formula": "HCl"},
            {"name": "Sodium hydroxide", "formula": "NaOH"},
        ],
        "setup_summary": (
            "A beaker is prepared with Hydrochloric acid and Sodium hydroxide. "
            "The burner stays off, and you decide when to request the "
            "supported prediction."
        ),
        "cta_label": "Try the neutralization setup",
        "equation": "HCl(aq) + NaOH(aq) -> NaCl(aq) + H2O(l)",
        "explanation": (
            "Hydrochloric acid and sodium hydroxide neutralize to form "
            "sodium chloride and water. The net ionic change is the "
            "combination of hydrogen and hydroxide ions into water. "
            "Neutralization is exothermic, so the solution can warm."
        ),
        "observation_title": "A clear solution that can warm",
        "observation": (
            "OmniLab returns the equation and explanation without a dramatic "
            "visual effect for this pair. In a physical reaction, both "
            "solutions can remain clear while the temperature rises."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Clear solution",
        "study_steps": [
            {
                "title": "Balance the one-to-one equation",
                "body": (
                    "One HCl unit reacts with one NaOH unit. The coefficients "
                    "are all 1, producing one NaCl unit and one H2O molecule."
                ),
            },
            {
                "title": "Cancel the spectator ions",
                "body": (
                    "Na+ and Cl- remain dissolved on both sides. Removing "
                    "them leaves H+(aq) + OH-(aq) -> H2O(l)."
                ),
            },
            {
                "title": "Separate heat from visible change",
                "body": (
                    "Neutralization releases heat, so the mixture can warm "
                    "even when no gas, precipitate, or color change appears."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What type of reaction is HCl with NaOH?",
                "answer": (
                    "It is an acid-base neutralization reaction. It can also "
                    "be classified as a double-displacement reaction in the "
                    "molecular equation."
                ),
            },
            {
                "question": "What is the net ionic equation?",
                "answer": (
                    "The net ionic equation is H+(aq) + OH-(aq) -> H2O(l). "
                    "Sodium and chloride ions are spectators."
                ),
            },
            {
                "question": "Do HCl and NaOH make salt water?",
                "answer": (
                    "The simplified products are aqueous sodium chloride and "
                    "water. The final pH still depends on the starting amounts "
                    "and concentrations, which OmniLab does not model."
                ),
            },
            {
                "question": "What can you observe during neutralization?",
                "answer": (
                    "The solutions can remain clear, so there may be no obvious "
                    "visual cue. A temperature rise can provide evidence that "
                    "the exothermic reaction occurred."
                ),
            },
        ],
        "safety": [
            "Wear chemical splash goggles and gloves.",
            "Add concentrated solutions slowly to control heating.",
            "Rinse acid or alkali splashes with plenty of water.",
        ],
        "boundary": (
            "OmniLab predicts one simplified neutralization path. It does not "
            "model concentration, volume, pH, temperature rise, addition "
            "order, titration endpoints, or a physical procedure."
        ),
    },
    "silver-nitrate-sodium-chloride": {
        "route_name": "guide_silver_nitrate_sodium_chloride",
        "canonical_key": "silver_nitrate_sodium_chloride",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_silver_nitrate_sodium_chloride",
        "title": (
            "What happens when silver nitrate reacts with sodium chloride?"
        ),
        "page_title": (
            "Silver nitrate and sodium chloride reaction | OmniLab"
        ),
        "description": (
            "See the silver nitrate and sodium chloride reaction, white "
            "precipitate, balanced and net ionic equations, and model limits."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Silver nitrate and sodium chloride form silver chloride, an "
            "insoluble white precipitate. Sodium and nitrate ions remain "
            "dissolved in the solution."
        ),
        "opening_boundary": (
            "The white cue is a simplified prediction. The model leaves out "
            "concentration, yield, particle size, light exposure, and a "
            "physical procedure."
        ),
        "student_job": (
            "Use this guide to identify the white solid, balance the molecular "
            "equation, and reduce it to the ions that form silver chloride."
        ),
        "reactants": [
            {"name": "Silver nitrate", "formula": "AgNO3"},
            {"name": "Sodium chloride", "formula": "NaCl"},
        ],
        "setup_summary": (
            "A beaker is prepared with Silver nitrate and Sodium chloride. "
            "The burner stays off, and you decide when to request the "
            "supported prediction."
        ),
        "cta_label": "Try the white precipitate setup",
        "equation": "AgNO3(aq) + NaCl(aq) -> AgCl(s) + NaNO3(aq)",
        "explanation": (
            "Silver nitrate and sodium chloride exchange ions to form "
            "insoluble silver chloride. The white silver chloride precipitate "
            "is the usual evidence for chloride ions in this simplified test. "
            "Sodium and nitrate ions remain in solution."
        ),
        "observation_title": "A white silver chloride precipitate",
        "observation": (
            "OmniLab shows a bounded cloudy-white precipitate cue inside the "
            "beaker to represent the expected silver chloride solid. The cue "
            "does not model how quickly particles appear or settle."
        ),
        "observation_class": "observation-cloudy",
        "observation_label": "White solid",
        "net_ionic_equation": "Ag+(aq) + Cl-(aq) -> AgCl(s)",
        "spectator_ions": "Na+(aq) and NO3-(aq)",
        "ionic_explanation": (
            "Silver ions combine with chloride ions because silver chloride "
            "is insoluble in water. Sodium and nitrate ions stay aqueous, so "
            "they cancel from the complete ionic equation."
        ),
        "study_steps": [
            {
                "title": "Split the soluble reactants into ions",
                "body": (
                    "AgNO3 provides Ag+ and NO3-. NaCl provides Na+ and Cl-. "
                    "All four ions begin in the aqueous reactants."
                ),
            },
            {
                "title": "Identify the insoluble product",
                "body": (
                    "Ag+ and Cl- combine in a one-to-one ratio to form solid "
                    "AgCl, the white precipitate."
                ),
            },
            {
                "title": "Cancel the spectator ions",
                "body": (
                    "Na+ and NO3- remain aqueous on both sides, leaving only "
                    "the ions that form silver chloride."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What type of reaction is AgNO3 with NaCl?",
                "answer": (
                    "It is a precipitation reaction and can also be described "
                    "as double displacement. The insoluble product is AgCl."
                ),
            },
            {
                "question": "What color is the silver chloride precipitate?",
                "answer": (
                    "Fresh silver chloride is represented as white or cloudy "
                    "in this simplified result. Strong light can change its "
                    "appearance over time."
                ),
            },
            {
                "question": "What is the net ionic equation?",
                "answer": (
                    "The net ionic equation is Ag+(aq) + Cl-(aq) -> AgCl(s). "
                    "Sodium and nitrate ions are spectators."
                ),
            },
            {
                "question": "Why does a precipitate form?",
                "answer": (
                    "Silver chloride has low solubility in water, so Ag+ and "
                    "Cl- leave the aqueous mixture together as a solid."
                ),
            },
        ],
        "safety": [
            "Wear gloves and splash goggles when handling silver nitrate.",
            "Protect the mixture from strong light after the precipitate forms.",
            (
                "Collect silver-containing waste instead of pouring it down "
                "a drain."
            ),
        ],
        "boundary": (
            "The white cue is a simplified expected observation. OmniLab does "
            "not model concentration, yield, particle size, light-driven "
            "changes, temperature, addition order, or waste handling. Vessel "
            "and burner choices do not affect the prediction."
        ),
    },
    "carbon-monoxide-oxygen": {
        "route_name": "guide_carbon_monoxide_oxygen",
        "canonical_key": "carbon_monoxide_oxygen",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_carbon_monoxide_oxygen",
        "title": "What happens when carbon monoxide reacts with oxygen?",
        "page_title": "Carbon monoxide and oxygen reaction | OmniLab",
        "description": (
            "See how carbon monoxide reacts with oxygen, balance the "
            "combustion equation, and keep the required activation and "
            "safety limits attached."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Carbon monoxide reacts with oxygen to form carbon dioxide after "
            "ignition or catalytic activation. The balanced equation is "
            "2CO(g) + O2(g) -> 2CO2(g)."
        ),
        "opening_boundary": (
            "The model predicts the products but not the ignition or catalyst "
            "needed to start the reaction. Carbon monoxide is highly toxic, "
            "and its mixture with oxygen can be flammable or explosive."
        ),
        "student_job": (
            "Use this guide to balance the combustion equation, identify the "
            "oxidation product, and explain why activation conditions matter."
        ),
        "study_intro": (
            "Connect the two-to-one gas ratio to the carbon dioxide product, "
            "electron transfer, and activation requirement."
        ),
        "reactants": [
            {"name": "Carbon monoxide", "formula": "CO"},
            {"name": "Oxygen", "formula": "O2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Carbon monoxide and Oxygen. The burner "
            "stays off, and you decide when to request the supported "
            "prediction."
        ),
        "cta_label": "Try the carbon monoxide setup",
        "equation": "2CO(g) + O2(g) -> 2CO2(g)",
        "explanation": (
            "Carbon monoxide oxidizes to carbon dioxide after ignition or "
            "catalytic activation. The combustion is exothermic, and two "
            "carbon monoxide molecules consume one oxygen molecule. The "
            "current model does not predict the activation conditions."
        ),
        "observation_title": "No simulated flame or ignition cue",
        "observation": (
            "OmniLab returns the equation and explanation without a visual "
            "effect for this pair. A physical reaction needs activation and "
            "can release substantial heat, but the virtual beaker does not "
            "represent ignition, flame, temperature, or gas pressure."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Text-only result",
        "study_steps": [
            {
                "title": "Balance carbon first",
                "body": (
                    "Two CO molecules contain two carbon atoms, so the "
                    "products need two CO2 molecules."
                ),
            },
            {
                "title": "Balance the oxygen atoms",
                "body": (
                    "The two CO molecules provide two oxygen atoms. One O2 "
                    "molecule supplies the other two needed in 2CO2."
                ),
            },
            {
                "title": "Keep activation in the answer",
                "body": (
                    "The balanced equation names reactants and products, but "
                    "the gas mixture does not react safely on demand. Ignition "
                    "or catalytic activation is still required."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What is the balanced equation for CO and O2?",
                "answer": (
                    "The balanced equation is 2CO(g) + O2(g) -> 2CO2(g). It "
                    "contains two carbon atoms and four oxygen atoms on each "
                    "side."
                ),
            },
            {
                "question": "What type of reaction is carbon monoxide with oxygen?",
                "answer": (
                    "It is a combustion and redox reaction. Carbon monoxide "
                    "is oxidized to carbon dioxide while oxygen is reduced."
                ),
            },
            {
                "question": "Does carbon monoxide react with oxygen by itself?",
                "answer": (
                    "The reaction needs ignition or catalytic activation. "
                    "OmniLab identifies the supported net change but does not "
                    "predict when or how activation occurs."
                ),
            },
            {
                "question": "Why is this reaction dangerous?",
                "answer": (
                    "Carbon monoxide is highly toxic, and a carbon monoxide-"
                    "oxygen mixture can burn rapidly or explode after "
                    "activation. This is specialist-laboratory chemistry."
                ),
            },
        ],
        "safety": [
            "Run this only in a specialist gas laboratory.",
            (
                "Use continuous carbon monoxide monitoring and effective "
                "ventilation."
            ),
            (
                "Treat carbon monoxide and oxygen as a flammable, potentially "
                "explosive mixture."
            ),
        ],
        "boundary": (
            "OmniLab predicts the simplified carbon dioxide product. It does "
            "not simulate ignition, catalysts, concentration, gas ratio, "
            "pressure, temperature, reaction rate, flame, or a physical "
            "procedure."
        ),
    },
    "carbon-dioxide-water": {
        "route_name": "guide_carbon_dioxide_water",
        "canonical_key": "carbon_dioxide_water",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_carbon_dioxide_water",
        "title": "What happens in the carbon dioxide and water reaction?",
        "page_title": "Carbon dioxide and water reaction | OmniLab",
        "description": (
            "See the carbon dioxide and water reaction, its simplified "
            "equation, carbonic acid equilibrium, expected result, and "
            "safety limits."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "When carbon dioxide contacts water, it dissolves and a small "
            "fraction reacts reversibly to form carbonic acid. OmniLab "
            "represents the simplified change as CO2(g) + H2O(l) -> H2CO3(aq)."
        ),
        "opening_boundary": (
            "The equation is a simplified model of an equilibrium, not a "
            "complete conversion to carbonic acid. The dissolved amount and "
            "pH depend on conditions such as carbon dioxide pressure and "
            "temperature."
        ),
        "student_job": (
            "Use this guide to separate dissolution from hydration, read the "
            "one-to-one equation, and explain why the water becomes mildly "
            "acidic."
        ),
        "study_intro": (
            "Connect dissolved carbon dioxide, reversible hydration, and "
            "partial acid dissociation to the simplified equation."
        ),
        "reactants": [
            {"name": "Carbon dioxide", "formula": "CO2"},
            {"name": "Water", "formula": "H2O"},
        ],
        "setup_summary": (
            "A beaker is prepared with Carbon dioxide and Water. The burner "
            "stays off, and you decide when to request the supported "
            "prediction."
        ),
        "cta_label": "Try the carbon dioxide and water setup",
        "equation": "CO2(g) + H2O(l) -> H2CO3(aq)",
        "explanation": (
            "Dissolved carbon dioxide establishes an equilibrium with "
            "carbonic acid in water. Only a fraction of the dissolved carbon "
            "dioxide is hydrated at equilibrium. Carbonic acid can then "
            "partially dissociate and lower the solution pH."
        ),
        "observation_title": "A clear solution with no dramatic color change",
        "observation": (
            "OmniLab returns a text-only result for this pair. In a physical "
            "setup, bubbles can show carbon dioxide entering the water, but "
            "they are not a carbonic acid product. The dissolved solution "
            "usually remains clear while its pH can decrease."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Clear solution",
        "study_steps": [
            {
                "title": "Start with dissolution",
                "body": (
                    "Carbon dioxide first enters the liquid as dissolved CO2. "
                    "That physical step is distinct from forming H2CO3."
                ),
            },
            {
                "title": "Read the reversible hydration",
                "body": (
                    "One CO2 molecule and one H2O molecule can form one H2CO3 "
                    "molecule, but only a fraction is hydrated at equilibrium."
                ),
            },
            {
                "title": "Connect carbonic acid to pH",
                "body": (
                    "Carbonic acid can partially dissociate, increasing the "
                    "hydrogen-ion concentration and lowering the solution pH."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What is the equation for carbon dioxide and water?",
                "answer": (
                    "OmniLab uses CO2(g) + H2O(l) -> H2CO3(aq). In real water, "
                    "the process is reversible and most dissolved carbon "
                    "dioxide is not present as H2CO3."
                ),
            },
            {
                "question": "Does carbon dioxide make water acidic?",
                "answer": (
                    "Dissolved carbon dioxide can lower the pH because a small "
                    "fraction forms carbonic acid, which partially dissociates."
                ),
            },
            {
                "question": "Is dissolving carbon dioxide the same as reacting?",
                "answer": (
                    "No. Dissolution puts CO2 molecules into the liquid. A "
                    "smaller fraction then hydrates reversibly to form H2CO3."
                ),
            },
            {
                "question": "What would you observe in the reaction?",
                "answer": (
                    "The solution usually stays clear. Bubbles can show gas "
                    "delivery, while a pH indicator or meter is needed to show "
                    "the acidity change."
                ),
            },
        ],
        "safety": [
            "Use ventilation when handling concentrated carbon dioxide.",
            "Avoid pressurizing a closed vessel with the gas.",
            "Wear eye protection when handling the solution.",
        ],
        "boundary": (
            "OmniLab shows one simplified hydration equation. It does not "
            "model gas pressure, dissolved concentration, equilibrium "
            "composition, pH, temperature, gas-flow rate, bubbles, or a "
            "physical procedure."
        ),
    },
    "iron-hydrochloric-acid": {
        "route_name": "guide_iron_hydrochloric_acid",
        "canonical_key": "iron_hydrochloric_acid",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_iron_hydrochloric_acid",
        "title": "What happens when iron reacts with hydrochloric acid?",
        "page_title": "Iron and hydrochloric acid reaction | OmniLab",
        "description": (
            "See how iron reacts with hydrochloric acid, balance the "
            "equation, identify the hydrogen bubbles, and keep the model "
            "and safety limits attached."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Iron reacts with hydrochloric acid to form iron(II) chloride "
            "and hydrogen gas. The balanced equation is "
            "Fe(s) + 2HCl(aq) -> FeCl2(aq) + H2(g)."
        ),
        "opening_boundary": (
            "The model predicts one simplified metal-acid reaction. It does "
            "not predict how quickly it starts or how concentration, "
            "temperature, surface condition, and oxide coatings change the "
            "rate."
        ),
        "student_job": (
            "Use this guide to balance the equation, connect the bubbles to "
            "hydrogen gas, and track the electron transfer from iron to "
            "hydrogen ions."
        ),
        "study_intro": (
            "Connect the two-to-one acid ratio to iron(II) chloride, hydrogen "
            "gas, and the redox change."
        ),
        "reactants": [
            {"name": "Iron", "formula": "Fe"},
            {"name": "Hydrochloric acid", "formula": "HCl"},
        ],
        "setup_summary": (
            "A beaker is prepared with Iron and Hydrochloric acid. The burner "
            "stays off, and you decide when to request the supported "
            "prediction."
        ),
        "cta_label": "Try the iron and acid setup",
        "equation": "Fe(s) + 2HCl(aq) -> FeCl2(aq) + H2(g)",
        "explanation": (
            "Iron displaces hydrogen from hydrochloric acid to form iron(II) "
            "chloride and hydrogen gas. The bubbles correspond to hydrogen "
            "leaving the solution. The reaction is a redox process in which "
            "iron is oxidized and hydrogen ions are reduced."
        ),
        "observation_title": "Hydrogen bubbles at the iron surface",
        "observation": (
            "OmniLab shows a bounded bubble cue inside the beaker to "
            "represent hydrogen gas leaving the mixture. The cue does not "
            "model bubble rate, acid concentration, heat, or the condition "
            "of the iron surface."
        ),
        "observation_class": "observation-bubbles",
        "observation_label": "Hydrogen bubbles",
        "study_steps": [
            {
                "title": "Balance hydrochloric acid",
                "body": (
                    "One iron atom forms one FeCl2 unit, which needs two "
                    "chloride ions. That sets the coefficient of HCl to two."
                ),
            },
            {
                "title": "Follow the electron transfer",
                "body": (
                    "Iron loses two electrons to become Fe2+. Two hydrogen "
                    "ions gain those electrons and pair to form H2 gas."
                ),
            },
            {
                "title": "Connect the bubbles to the product",
                "body": (
                    "The visible bubbles are hydrogen gas, not chlorine. "
                    "Iron(II) chloride remains in the aqueous mixture."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What is the balanced equation for iron and hydrochloric acid?",
                "answer": (
                    "The balanced equation is "
                    "Fe(s) + 2HCl(aq) -> FeCl2(aq) + H2(g)."
                ),
            },
            {
                "question": "What gas forms when iron reacts with hydrochloric acid?",
                "answer": (
                    "Hydrogen gas forms. The bubbles represent H2 leaving "
                    "the solution."
                ),
            },
            {
                "question": "Why does iron form iron(II) chloride here?",
                "answer": (
                    "In this simplified reaction, iron is oxidized to Fe2+. "
                    "Two chloride ions remain with each iron(II) ion, giving "
                    "FeCl2 in solution."
                ),
            },
            {
                "question": "Why might the physical reaction start slowly?",
                "answer": (
                    "An oxide coating, a smooth iron surface, dilute acid, or "
                    "a lower temperature can reduce the observed rate. "
                    "OmniLab does not model those factors."
                ),
            },
        ],
        "safety": [
            "Keep the reaction away from flames and sparks.",
            "Vent hydrogen gas in a supervised laboratory.",
            "Wear acid-resistant gloves and splash goggles.",
        ],
        "boundary": (
            "OmniLab predicts one simplified iron and hydrochloric acid "
            "reaction. It does not model acid concentration, iron purity, "
            "surface area, oxide layers, temperature, rate, gas volume, heat, "
            "or a physical procedure."
        ),
    },
    "copper-oxygen": {
        "route_name": "guide_copper_oxygen",
        "canonical_key": "copper_oxygen",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_copper_oxygen",
        "title": "What happens in the reaction of copper with oxygen?",
        "page_title": (
            "Reaction of copper with oxygen: equation and result | OmniLab"
        ),
        "description": (
            "See the reaction of copper with oxygen, its balanced equation, "
            "black copper(II) oxide product, heating condition, and safety "
            "limits."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "When copper is heated in oxygen, it forms black copper(II) "
            "oxide. The simplified balanced equation is "
            "2Cu(s) + O2(g) -> 2CuO(s)."
        ),
        "opening_boundary": (
            "Heating is an important condition for the classroom reaction. "
            "OmniLab models CuO as the product, but temperature, oxygen "
            "availability, and surface conditions can affect the rate and "
            "oxide that forms."
        ),
        "student_job": (
            "Use this guide to balance the equation, identify the black "
            "product, and explain the electron transfer between copper and "
            "oxygen."
        ),
        "study_intro": (
            "Connect the two-to-one ratio to copper(II) oxide, the black "
            "coating, and the oxidation-state changes."
        ),
        "reactants": [
            {"name": "Copper", "formula": "Cu"},
            {"name": "Oxygen", "formula": "O2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Copper and Oxygen. The burner stays "
            "off, and you decide when to request the supported prediction."
        ),
        "cta_label": "Try the copper and oxygen setup",
        "equation": "2Cu(s) + O2(g) -> 2CuO(s)",
        "explanation": (
            "Heated copper reacts with oxygen to form black copper(II) "
            "oxide. Copper is oxidized from oxidation state zero to plus "
            "two while oxygen is reduced. The balanced equation uses two "
            "copper atoms for each oxygen molecule."
        ),
        "observation_title": "A black copper(II) oxide coating",
        "observation": (
            "A clean copper surface can develop a black copper(II) oxide "
            "coating when heated in oxygen. OmniLab returns a text-only "
            "result for this pair and does not render heating, glow, or the "
            "physical color change."
        ),
        "observation_class": "observation-oxide",
        "observation_label": "Black copper(II) oxide",
        "study_steps": [
            {
                "title": "Balance the oxygen molecule",
                "body": (
                    "One O2 molecule supplies two oxygen atoms, so two copper "
                    "atoms form two CuO formula units. The coefficients are "
                    "2, 1, and 2."
                ),
            },
            {
                "title": "Track the electron transfer",
                "body": (
                    "Each copper atom moves from oxidation state 0 to +2. "
                    "Oxygen moves from 0 in O2 to -2 in CuO, making this a "
                    "redox reaction."
                ),
            },
            {
                "title": "Keep heating with the result",
                "body": (
                    "Copper usually needs heating for the classroom reaction "
                    "to proceed at an observable rate. A burner setting in "
                    "OmniLab does not change its fixed prediction."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What is the balanced equation for copper and oxygen?",
                "answer": (
                    "The simplified equation is "
                    "2Cu(s) + O2(g) -> 2CuO(s). It has two copper and two "
                    "oxygen atoms on each side."
                ),
            },
            {
                "question": "What color is copper oxide after heating?",
                "answer": (
                    "Copper(II) oxide, CuO, is black. A heated copper surface "
                    "can therefore develop a black coating in this model."
                ),
            },
            {
                "question": "Why must copper be heated to react with oxygen?",
                "answer": (
                    "Heating helps the reactants overcome the activation "
                    "barrier so oxidation proceeds at an observable rate."
                ),
            },
            {
                "question": "Can copper form a different oxide?",
                "answer": (
                    "Copper can also form copper(I) oxide, Cu2O, under some "
                    "conditions. OmniLab deliberately uses the simplified "
                    "CuO result for its supported pair."
                ),
            },
            {
                "question": "Why can the copper sample gain mass?",
                "answer": (
                    "Oxygen atoms become part of the solid oxide. If the "
                    "coating stays on the sample, the final mass includes "
                    "the original copper plus oxygen from the gas."
                ),
            },
        ],
        "safety": [
            "Handle heated copper with suitable tongs.",
            "Avoid breathing copper oxide dust.",
            "Wear eye protection during heating.",
        ],
        "boundary": (
            "OmniLab predicts one simplified CuO product. It does not model "
            "temperature, heating time, oxygen supply, copper shape, surface "
            "condition, reaction rate, oxide mixtures, color change, mass "
            "change, or a physical procedure."
        ),
    },
    "potassium-permanganate-hydrogen-peroxide": {
        "route_name": "guide_potassium_permanganate_hydrogen_peroxide",
        "canonical_key": "potassium_permanganate_hydrogen_peroxide",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_potassium_permanganate_hydrogen_peroxide",
        "title": (
            "What happens when potassium permanganate reacts with hydrogen peroxide?"
        ),
        "page_title": (
            "Potassium permanganate and hydrogen peroxide reaction | OmniLab"
        ),
        "description": (
            "See the potassium permanganate and hydrogen peroxide reaction, "
            "balanced equation, oxygen bubbles, manganese dioxide product, "
            "redox roles, and safety."
        ),
        "reading_time": "6 minute read",
        "direct_answer": (
            "In neutral or alkaline conditions, potassium permanganate "
            "oxidizes hydrogen peroxide to oxygen gas while brown manganese "
            "dioxide forms. The permanganate color fades, bubbles appear, and "
            "the simplified balanced equation is 2KMnO4(aq) + 3H2O2(aq) -> "
            "2MnO2(s) + 3O2(g) + 2KOH(aq) + 2H2O(l)."
        ),
        "opening_boundary": (
            "The products depend on acidity. This guide and OmniLab use the "
            "neutral-or-alkaline pathway; acidic conditions can produce "
            "manganese(II) ions instead of manganese dioxide."
        ),
        "student_job": (
            "Use this guide to balance the equation, identify the oxidizing "
            "and reducing agents, and connect oxygen bubbles and brown "
            "manganese dioxide to the products."
        ),
        "study_intro": (
            "Connect the coefficients to oxygen formation, manganese "
            "reduction, hydrogen peroxide oxidation, and the visible result."
        ),
        "reactants": [
            {"name": "Potassium permanganate", "formula": "KMnO4"},
            {"name": "Hydrogen peroxide", "formula": "H2O2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Potassium permanganate and Hydrogen "
            "peroxide. Nothing runs until you select Analyze."
        ),
        "cta_label": "Try the potassium permanganate and peroxide setup",
        "equation": (
            "2KMnO4(aq) + 3H2O2(aq) -> 2MnO2(s) + 3O2(g) + "
            "2KOH(aq) + 2H2O(l)"
        ),
        "explanation": (
            "In neutral or alkaline conditions, permanganate oxidizes "
            "hydrogen peroxide to oxygen while manganese dioxide forms. "
            "Oxygen evolution produces bubbles and the permanganate color "
            "fades as brown manganese dioxide appears. Different acidity "
            "can change the products."
        ),
        "observation_title": "Oxygen bubbles and brown manganese dioxide",
        "observation": (
            "Oxygen evolution produces bubbles while the purple permanganate "
            "color fades and brown manganese dioxide appears. OmniLab renders "
            "the bubbling cue for this supported pair, but it does not render "
            "the brown solid or reproduce the rate or intensity of a physical "
            "reaction."
        ),
        "observation_class": "observation-bubbles",
        "observation_label": "Oxygen bubbles",
        "study_steps": [
            {
                "title": "Keep the condition with the equation",
                "body": (
                    "The displayed products fit neutral or alkaline conditions. "
                    "Changing the acidity changes the manganese product, so the "
                    "condition is part of the answer."
                ),
            },
            {
                "title": "Track manganese reduction",
                "body": (
                    "Manganese moves from +7 in MnO4- to +4 in MnO2. Because "
                    "permanganate is reduced, it accepts electrons and acts as "
                    "the oxidizing agent."
                ),
            },
            {
                "title": "Track oxygen formation",
                "body": (
                    "Some oxygen atoms in H2O2 move from oxidation state -1 to "
                    "0 in O2. The oxygen gas accounts for the visible bubbles."
                ),
            },
        ],
        "common_questions": [
            {
                "question": (
                    "What happens if you mix hydrogen peroxide with potassium permanganate?"
                ),
                "answer": (
                    "In the neutral-or-alkaline pathway used here, oxygen gas "
                    "and brown manganese dioxide form, the purple permanganate "
                    "color fades, and bubbling occurs. The exact products and "
                    "rate depend on conditions."
                ),
            },
            {
                "question": (
                    "What is the balanced equation for KMnO4 and H2O2?"
                ),
                "answer": (
                    "For the simplified neutral-or-alkaline pathway, it is "
                    "2KMnO4(aq) + 3H2O2(aq) -> 2MnO2(s) + 3O2(g) + "
                    "2KOH(aq) + 2H2O(l)."
                ),
            },
            {
                "question": "Is KMnO4 or H2O2 the oxidizing agent?",
                "answer": (
                    "Permanganate is the oxidizing agent because manganese is "
                    "reduced from +7 to +4. Hydrogen peroxide is the reducing "
                    "agent because some of its oxygen is oxidized from -1 to 0."
                ),
            },
            {
                "question": "Why does the reaction bubble?",
                "answer": (
                    "Hydrogen peroxide is converted partly into oxygen gas. "
                    "That escaping O2 produces the bubbles."
                ),
            },
            {
                "question": "Why do acidic conditions give a different equation?",
                "answer": (
                    "Permanganate can be reduced to manganese(II) ions in acidic "
                    "solution rather than to MnO2. Acidity changes the reduction "
                    "half-reaction and therefore changes the overall products and "
                    "coefficients."
                ),
            },
        ],
        "safety": [
            "Use dilute solutions and add hydrogen peroxide slowly.",
            "Keep both reagents away from combustible or reducing materials.",
            "Do not seal the vessel because oxygen gas is produced.",
        ],
        "boundary": (
            "OmniLab predicts one simplified neutral-or-alkaline result. It "
            "does not model acidity, concentration, quantity, order of addition, "
            "temperature, reaction rate, heat release, pressure, the brown "
            "precipitate, or a physical procedure. It is an educational "
            "prediction, not a verified simulation or a substitute for trained "
            "laboratory supervision."
        ),
    },
    "sodium-chloride-water": {
        "route_name": "guide_sodium_chloride_water",
        "canonical_key": "sodium_chloride_water",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_sodium_chloride_water",
        "title": "What happens when sodium chloride mixes with water?",
        "page_title": "Sodium chloride and water reaction | OmniLab",
        "description": (
            "See what happens when sodium chloride mixes with water, including "
            "the dissolution equation, hydrated ions, conductivity, and limits."
        ),
        "reading_time": "6 minute read",
        "direct_answer": (
            "Sodium chloride does not form a new compound when it mixes with "
            "water. The solid dissolves and dissociates into hydrated sodium "
            "and chloride ions, while water remains the solvent."
        ),
        "opening_boundary": (
            "This is dissolution and ionic dissociation, not a chemical "
            "reaction that forms sodium hydroxide or hydrochloric acid. "
            "Electrolysis requires an external electric current and is outside "
            "this supported setup."
        ),
        "student_job": (
            "Use this guide to distinguish dissolving, dissociation, and "
            "hydration. Then connect the aqueous state symbols to the mobile "
            "ions in the solution."
        ),
        "study_intro": (
            "Read the process equation from the ionic lattice to the hydrated "
            "ions, while tracking water as the unchanged solvent."
        ),
        "reactants": [
            {"name": "Sodium chloride", "formula": "NaCl"},
            {"name": "Water", "formula": "H2O"},
        ],
        "setup_summary": (
            "A beaker is prepared with Sodium chloride and Water. Nothing runs "
            "until you select Analyze."
        ),
        "cta_label": "Try the sodium chloride and water setup",
        "equation": (
            "NaCl(s) + H2O(l) -> Na+(aq) + Cl-(aq) + H2O(l)"
        ),
        "explanation": (
            "Sodium chloride dissolves in water and dissociates into hydrated "
            "sodium and chloride ions. Water is the solvent and is not consumed, "
            "so it appears on both sides of this process equation. This is "
            "dissolution rather than formation of a new compound."
        ),
        "observation_title": "A clear solution with dissolved ions",
        "observation": (
            "The salt can disappear from view as it dissolves, while the "
            "solution stays clear. OmniLab uses a clear liquid cue and does not "
            "render individual hydrated ions or measure conductivity."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Clear sodium chloride solution",
        "study_steps": [
            {
                "title": "Separate the ions from the lattice",
                "body": (
                    "Solid NaCl contains a repeating ionic lattice. Polar water "
                    "molecules stabilize Na+ and Cl- as the ions leave that "
                    "lattice."
                ),
            },
            {
                "title": "Read the aqueous state",
                "body": (
                    "The symbol (aq) means each ion is hydrated in water. It "
                    "does not mean isolated, dry ions are floating alone."
                ),
            },
            {
                "title": "Keep water on both sides",
                "body": (
                    "Water acts as the solvent and is not consumed. It appears "
                    "on both sides to show the supported dissolution process."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "Is sodium chloride and water a chemical reaction?",
                "answer": (
                    "No new compound forms in this supported process. Sodium "
                    "chloride dissolves and dissociates, which is a physical "
                    "change at this level."
                ),
            },
            {
                "question": "Why does salt water conduct electricity?",
                "answer": (
                    "Dissolved Na+ and Cl- ions can move through the solution. "
                    "Those mobile charged particles carry electric current."
                ),
            },
            {
                "question": "Do sodium hydroxide and hydrochloric acid form?",
                "answer": (
                    "No. Mixing sodium chloride with water alone gives hydrated "
                    "sodium and chloride ions, not NaOH and HCl."
                ),
            },
            {
                "question": "Can salt water make new products during electrolysis?",
                "answer": (
                    "Yes, an imposed electric current can drive electrode "
                    "reactions. That is a different process and is not modeled "
                    "by this prepared setup."
                ),
            },
            {
                "question": "Can the sodium chloride be recovered?",
                "answer": (
                    "Yes. Removing the water can let sodium chloride crystallize "
                    "again, subject to concentration and temperature conditions."
                ),
            },
        ],
        "safety": [
            "Wear eye protection when handling laboratory solutions.",
            "Do not ingest laboratory-grade sodium chloride.",
            "Clean spills promptly to prevent slippery surfaces.",
        ],
        "boundary": (
            "OmniLab predicts one simplified dissolution process. It does not "
            "model mass, volume, concentration, saturation, temperature, "
            "dissolution rate, conductivity, crystallization, electrolysis, or "
            "a physical procedure. It is an educational prediction, not a "
            "verified simulation or a substitute for trained laboratory "
            "supervision."
        ),
    },
    "carbon-dioxide-sodium-hydroxide": {
        "route_name": "guide_carbon_dioxide_sodium_hydroxide",
        "canonical_key": "carbon_dioxide_sodium_hydroxide",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_carbon_dioxide_sodium_hydroxide",
        "title": "What happens when carbon dioxide reacts with sodium hydroxide?",
        "page_title": "Carbon dioxide and sodium hydroxide reaction | OmniLab",
        "description": (
            "See how carbon dioxide reacts with sodium hydroxide, balance the "
            "equation, compare carbonate and bicarbonate, and try the setup."
        ),
        "reading_time": "6 minute read",
        "direct_answer": (
            "Carbon dioxide reacts with excess sodium hydroxide to form sodium "
            "carbonate and water. The balanced equation uses two moles of NaOH "
            "for each mole of CO2."
        ),
        "opening_boundary": (
            "The product depends on the reactant ratio. Excess NaOH supports "
            "the carbonate equation shown here. A 1:1 ratio can instead favor "
            "sodium bicarbonate."
        ),
        "student_job": (
            "Track the 1:2 ratio in the balanced equation. Then explain why "
            "carbon dioxide acts as an acidic oxide."
        ),
        "study_intro": (
            "Follow the carbon atom into carbonate and check that sodium, "
            "oxygen, and hydrogen atoms balance on both sides."
        ),
        "reactants": [
            {"name": "Carbon dioxide", "formula": "CO2"},
            {"name": "Sodium hydroxide", "formula": "NaOH"},
        ],
        "setup_summary": (
            "A beaker is prepared with Carbon dioxide and Sodium hydroxide. "
            "Nothing runs until you select Analyze."
        ),
        "cta_label": "Try the carbon dioxide and sodium hydroxide setup",
        "equation": "CO2(g) + 2NaOH(aq) -> Na2CO3(aq) + H2O(l)",
        "explanation": (
            "Carbon dioxide reacts with excess sodium hydroxide to form "
            "sodium carbonate and water. Carbon dioxide behaves as an acidic "
            "oxide in this acid-base reaction. Two hydroxide equivalents are "
            "required for each carbon dioxide molecule in the stated equation."
        ),
        "observation_title": "No dramatic visible change",
        "observation": (
            "A dilute sodium hydroxide solution can remain clear as it absorbs "
            "carbon dioxide. The reaction changes the dissolved ions, but it "
            "does not produce a gas or precipitate in this stated pathway."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Clear carbonate solution",
        "study_steps": [
            {
                "title": "Recognize the acidic oxide",
                "body": (
                    "Carbon dioxide is a non-metal oxide. It reacts with the "
                    "alkaline hydroxide solution in an acid-base process."
                ),
            },
            {
                "title": "Use two hydroxide equivalents",
                "body": (
                    "Two NaOH units supply two sodium ions and two hydroxide "
                    "groups for each CO2 molecule in the carbonate pathway."
                ),
            },
            {
                "title": "Check the product ratio",
                "body": (
                    "Excess NaOH favors Na2CO3. With less hydroxide, carbon "
                    "dioxide can form NaHCO3 instead."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What forms when CO2 reacts with NaOH?",
                "answer": (
                    "Excess sodium hydroxide forms sodium carbonate and water. "
                    "The supported equation is CO2 + 2NaOH -> Na2CO3 + H2O."
                ),
            },
            {
                "question": "Why are two moles of NaOH required?",
                "answer": (
                    "The carbonate ion has a 2- charge. Two sodium ions are "
                    "needed to form neutral Na2CO3."
                ),
            },
            {
                "question": "Can sodium bicarbonate form instead?",
                "answer": (
                    "Yes. A 1:1 amount of CO2 and NaOH can favor NaHCO3. The "
                    "supported result assumes excess NaOH and the 1:2 ratio."
                ),
            },
            {
                "question": "Is carbon dioxide an acid?",
                "answer": (
                    "Carbon dioxide is an acidic oxide, not an acid by itself. "
                    "It reacts with bases and can form carbonic acid in water."
                ),
            },
            {
                "question": "What can you observe during the reaction?",
                "answer": (
                    "A dilute solution may stay clear. Indicators, pH data, or "
                    "mass measurements can show absorption more clearly."
                ),
            },
        ],
        "safety": [
            "Wear gloves and splash goggles when handling sodium hydroxide.",
            "Add sodium hydroxide slowly to limit splashing.",
            "Use ventilation when working with concentrated carbon dioxide.",
        ],
        "boundary": (
            "OmniLab predicts the excess-NaOH carbonate pathway. It does not "
            "model reactant amounts, concentration, pH, gas flow, absorption "
            "rate, temperature, bicarbonate formation, or a physical procedure. "
            "It is an educational prediction, not a verified simulation or a "
            "substitute for trained laboratory supervision."
        ),
    },
    "nitrogen-dioxide-water": {
        "route_name": "guide_nitrogen_dioxide_water",
        "canonical_key": "nitrogen_dioxide_water",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_nitrogen_dioxide_water",
        "title": "What happens when nitrogen dioxide reacts with water?",
        "page_title": "Nitrogen dioxide and water reaction | OmniLab",
        "description": (
            "See how nitrogen dioxide reacts with water, balance the simplified "
            "equation, compare nitrous and nitric acid, and keep its limits clear."
        ),
        "reading_time": "6 minute read",
        "direct_answer": (
            "Nitrogen dioxide reacts with cool, dilute water in OmniLab's "
            "simplified model. The products are nitrous acid and nitric acid."
        ),
        "opening_boundary": (
            "Real absorption involves equilibria and further chemistry. Nitrous "
            "acid can decompose, so some summaries show nitric acid and nitric "
            "oxide instead."
        ),
        "student_job": (
            "Balance the equation and track nitrogen from oxidation state +4. "
            "Then separate the classroom model from real gas absorption."
        ),
        "study_intro": (
            "Follow nitrogen into two acid products and check the atom count. "
            "Keep the cool, dilute-water condition attached to the result."
        ),
        "reactants": [
            {"name": "Nitrogen dioxide", "formula": "NO2"},
            {"name": "Water", "formula": "H2O"},
        ],
        "setup_summary": (
            "A beaker is prepared with Nitrogen dioxide and Water. Nothing runs "
            "until you select Analyze."
        ),
        "cta_label": "Try the nitrogen dioxide and water setup",
        "equation": "2NO2(g) + H2O(l) -> HNO2(aq) + HNO3(aq)",
        "explanation": (
            "Nitrogen dioxide absorbed into cool, dilute water forms a mixture "
            "of nitrous acid and nitric acid in this simplified equation. The "
            "real gas absorption can involve additional equilibria, so this "
            "result describes the classroom-scale net change."
        ),
        "observation_title": "Less brown gas above a clear acidic solution",
        "observation": (
            "Nitrogen dioxide is a reddish-brown gas. Absorption can reduce its "
            "color while the liquid stays clear and becomes acidic. OmniLab "
            "returns text only and does not simulate color or pH."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Clear acidic solution",
        "study_steps": [
            {
                "title": "Balance nitrogen first",
                "body": (
                    "Place 2 before NO2. One nitrogen enters HNO2, and the "
                    "other enters HNO3."
                ),
            },
            {
                "title": "Track the oxidation states",
                "body": (
                    "Nitrogen starts at +4. It changes to +3 in HNO2 and +5 "
                    "in HNO3, so disproportionation occurs."
                ),
            },
            {
                "title": "Keep the model boundary",
                "body": (
                    "The equation represents one cool, dilute-water pathway. "
                    "Equilibria and later nitrous acid chemistry can change the "
                    "mixture."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What forms when nitrogen dioxide reacts with water?",
                "answer": (
                    "The simplified cool, dilute-water equation forms nitrous "
                    "acid and nitric acid. Both products remain aqueous."
                ),
            },
            {
                "question": "What is the balanced equation for NO2 and water?",
                "answer": (
                    "OmniLab uses 2NO2(g) + H2O(l) -> HNO2(aq) + HNO3(aq). "
                    "It balances two nitrogen, five oxygen, and two hydrogen atoms."
                ),
            },
            {
                "question": "Why do two different acids form?",
                "answer": (
                    "Nitrogen in NO2 has oxidation state +4. Some changes to +3, "
                    "while some changes to +5."
                ),
            },
            {
                "question": "Why do some equations show nitric oxide?",
                "answer": (
                    "Nitrous acid can undergo further chemistry. A later net "
                    "summary can therefore include nitric acid and nitric oxide."
                ),
            },
            {
                "question": "What would you observe?",
                "answer": (
                    "The reddish-brown gas can fade as it is absorbed. The liquid "
                    "can stay clear, so acidity needs a suitable measurement."
                ),
            },
        ],
        "safety": [
            "Use nitrogen dioxide only in a specialist fume-handling system.",
            "Avoid inhalation and wear corrosion-resistant gloves and goggles.",
            "Keep this oxidizer and the acidic products away from combustibles.",
        ],
        "boundary": (
            "OmniLab predicts one simplified cool, dilute-water pathway. It does "
            "not model gas concentration, NO2-N2O4 equilibrium, absorption rate, "
            "temperature, pH, nitric oxide formation, acid decomposition, color "
            "change, or a physical procedure. It is an educational prediction, "
            "not a verified simulation or a substitute for trained laboratory "
            "supervision."
        ),
    },
    "hydrogen-chlorine": {
        "route_name": "guide_hydrogen_chlorine",
        "canonical_key": "hydrogen_chlorine",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_hydrogen_chlorine",
        "title": "What happens when hydrogen reacts with chlorine?",
        "page_title": "Hydrogen and chlorine reaction | OmniLab",
        "description": (
            "See how hydrogen reacts with chlorine, balance the hydrogen "
            "chloride equation, and keep light, heat, and safety limits clear."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "Hydrogen reacts with chlorine after initiation to form hydrogen "
            "chloride gas. The balanced equation is H2(g) + Cl2(g) -> 2HCl(g)."
        ),
        "opening_boundary": (
            "Light or heat can initiate a rapid chain reaction. OmniLab "
            "predicts the product without simulating initiation, flame, "
            "pressure, or reaction rate."
        ),
        "student_job": (
            "Balance the equation, distinguish hydrogen chloride gas from "
            "hydrochloric acid, and keep initiation attached to the result."
        ),
        "study_intro": (
            "Follow the one-to-one reactant ratio into two hydrogen chloride "
            "molecules. Then separate the gas product from its aqueous form."
        ),
        "reactants": [
            {"name": "Hydrogen", "formula": "H2"},
            {"name": "Chlorine", "formula": "Cl2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Hydrogen and Chlorine. Nothing runs "
            "until you select Analyze."
        ),
        "cta_label": "Try the hydrogen and chlorine setup",
        "equation": "H2(g) + Cl2(g) -> 2HCl(g)",
        "explanation": (
            "Hydrogen and chlorine form hydrogen chloride after initiation, "
            "often by light or heat. The chain reaction is highly exothermic "
            "and can proceed violently. One molecule of each reactant forms "
            "two hydrogen chloride molecules."
        ),
        "observation_title": "No simulated flash, flame, or pressure change",
        "observation": (
            "OmniLab returns a text-only prediction for this pair. A physical "
            "mixture can react rapidly after initiation, but the virtual "
            "beaker does not represent light, heat, flame, or pressure."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Text-only result",
        "study_steps": [
            {
                "title": "Balance both diatomic reactants",
                "body": (
                    "H2 and Cl2 each supply two atoms. Place 2 before HCl so "
                    "both hydrogen and chlorine balance."
                ),
            },
            {
                "title": "Keep initiation in the explanation",
                "body": (
                    "The equation gives the net change. Light or heat starts "
                    "the chain reaction but is not another reactant."
                ),
            },
            {
                "title": "Name the product state correctly",
                "body": (
                    "The stated product is hydrogen chloride gas, HCl(g). It "
                    "is called hydrochloric acid after it dissolves in water."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What forms when hydrogen reacts with chlorine?",
                "answer": (
                    "Hydrogen chloride gas forms. The balanced equation makes "
                    "two HCl molecules from one H2 molecule and one Cl2 molecule."
                ),
            },
            {
                "question": "What is the balanced equation for H2 and Cl2?",
                "answer": (
                    "The balanced equation is H2(g) + Cl2(g) -> 2HCl(g). It "
                    "has two hydrogen and two chlorine atoms on each side."
                ),
            },
            {
                "question": "Why does the reaction need light or heat?",
                "answer": (
                    "Initiation breaks a bond and creates reactive species. "
                    "They continue the chain reaction that forms HCl."
                ),
            },
            {
                "question": "Is hydrogen chloride the same as hydrochloric acid?",
                "answer": (
                    "Hydrogen chloride is the molecular gas. Its aqueous "
                    "solution is called hydrochloric acid."
                ),
            },
        ],
        "safety": [
            "Keep the gas mixture away from bright light and ignition sources.",
            "Use blast shielding and trained supervision.",
            "Avoid inhaling chlorine or hydrogen chloride gas.",
        ],
        "boundary": (
            "OmniLab predicts hydrogen chloride without modeling light level, "
            "temperature, gas ratio, pressure, reaction rate, flame, or a "
            "physical procedure. Its results are educational predictions, not "
            "verified simulations, and never a replacement for trained "
            "laboratory supervision."
        ),
    },
    "carbon-oxygen": {
        "route_name": "guide_carbon_oxygen",
        "canonical_key": "carbon_oxygen",
        "visit_source": "guide_virtual_lab",
        "demo_route_name": "demo_carbon_oxygen",
        "title": "What happens when carbon reacts with oxygen?",
        "page_title": "Carbon and oxygen reaction | OmniLab",
        "description": (
            "See how carbon reacts with sufficient oxygen, balance the carbon "
            "dioxide equation, and compare complete with incomplete combustion."
        ),
        "reading_time": "5 minute read",
        "direct_answer": (
            "In sufficient oxygen, carbon burns to form carbon dioxide. The "
            "balanced equation is C(s) + O2(g) -> CO2(g)."
        ),
        "opening_boundary": (
            "Carbon needs ignition or strong heating before it burns. Oxygen "
            "supply changes the products, but OmniLab predicts only complete "
            "combustion in sufficient oxygen."
        ),
        "student_job": (
            "Balance the equation, name the complete-combustion product, and "
            "keep oxygen supply attached to the result."
        ),
        "study_intro": (
            "Follow one carbon atom and one oxygen molecule into carbon "
            "dioxide. Then compare sufficient and limited oxygen."
        ),
        "reactants": [
            {"name": "Carbon", "formula": "C"},
            {"name": "Oxygen", "formula": "O2"},
        ],
        "setup_summary": (
            "A beaker is prepared with Carbon and Oxygen. The burner stays "
            "off, and nothing runs until you select Analyze."
        ),
        "cta_label": "Try the carbon and oxygen setup",
        "equation": "C(s) + O2(g) -> CO2(g)",
        "explanation": (
            "Carbon undergoes complete combustion in sufficient oxygen to "
            "form carbon dioxide. The oxidation is exothermic and releases "
            "energy as strong carbon-oxygen bonds form. One carbon atom and "
            "one oxygen molecule produce one carbon dioxide molecule."
        ),
        "observation_title": "No simulated glow, flame, or gas buildup",
        "observation": (
            "OmniLab returns a text-only prediction for this pair. A physical "
            "sample can glow or burn after ignition, but carbon dioxide is "
            "colorless and the virtual beaker does not model combustion."
        ),
        "observation_class": "observation-clear",
        "observation_label": "Text-only result",
        "study_steps": [
            {
                "title": "Balance the atoms",
                "body": (
                    "One carbon atom and two oxygen atoms appear on each side, "
                    "so every coefficient is 1."
                ),
            },
            {
                "title": "Keep sufficient oxygen in the answer",
                "body": (
                    "The equation describes complete combustion. Limited "
                    "oxygen can produce carbon monoxide instead."
                ),
            },
            {
                "title": "Separate ignition from the net equation",
                "body": (
                    "Heating starts the physical reaction. It is a condition, "
                    "not another reactant in the balanced equation."
                ),
            },
        ],
        "common_questions": [
            {
                "question": "What forms when carbon reacts with oxygen?",
                "answer": (
                    "Carbon dioxide forms during complete combustion in "
                    "sufficient oxygen."
                ),
            },
            {
                "question": "What is the balanced equation for C and O2?",
                "answer": (
                    "The balanced equation is C(s) + O2(g) -> CO2(g). It has "
                    "one carbon and two oxygen atoms on each side."
                ),
            },
            {
                "question": "What happens when oxygen is limited?",
                "answer": (
                    "Incomplete combustion can form carbon monoxide. The "
                    "OmniLab result does not model that alternate pathway."
                ),
            },
            {
                "question": "What type of reaction is carbon and oxygen?",
                "answer": (
                    "It is a combustion reaction and a redox reaction. Carbon "
                    "is oxidized as carbon dioxide forms."
                ),
            },
        ],
        "safety": [
            "Use heat-resistant tools for hot carbon.",
            "Vent carbon dioxide from the work area.",
            "Keep combustible materials away from the reaction.",
        ],
        "boundary": (
            "OmniLab predicts complete combustion without modeling ignition, "
            "temperature, oxygen supply, reaction rate, glow, flame, carbon "
            "monoxide formation, or a physical procedure. Its results are "
            "educational predictions, not verified simulations, and never a "
            "replacement for trained laboratory supervision."
        ),
    },
}

CHEMICAL_REACTION_VIRTUAL_LAB_PAGE = {
    "route_name": "chemical_reaction_virtual_lab",
    "canonical_key": "chemical_reaction_virtual_lab",
    "title": "How does the chemical reaction virtual lab work?",
    "page_title": "Chemical reaction virtual lab for students | OmniLab",
    "description": (
        "Try 34 supported reaction pairs in OmniLab's free chemical reaction "
        "virtual lab. See equations, explanations, safety guidance, and "
        "visible reaction cues."
    ),
    "heading": "Try a chemical reaction in a virtual lab",
    "direct_answer": (
        "Choose two chemicals from a supported pair. OmniLab returns a "
        "balanced equation, a plain-language explanation, three safety "
        "notes, and a visible reaction cue when the result includes bubbling "
        "or a precipitate."
    ),
    "reaction_examples": [
        {
            "type": "Synthesis",
            "title": "Hydrogen + Oxygen",
            "equation": "2H₂ + O₂ → 2H₂O",
            "explanation": "Follow how two elements combine into one compound.",
        },
        {
            "type": "Neutralization",
            "title": "Hydrochloric acid + Sodium hydroxide",
            "equation": "HCl + NaOH → NaCl + H₂O",
            "explanation": (
                "Connect an acid-base reaction to salt and water formation."
            ),
        },
        {
            "type": "Gas evolution",
            "title": "Acetic acid + Sodium bicarbonate",
            "equation": "CH₃COOH + NaHCO₃ → CO₂ + H₂O + CH₃COONa",
            "explanation": (
                "See carbon dioxide represented as a bubbling result."
            ),
        },
        {
            "type": "Blue precipitate",
            "title": "Copper(II) sulfate + Potassium hydroxide",
            "equation": "CuSO₄ + 2KOH → Cu(OH)₂ + K₂SO₄",
            "explanation": (
                "Relate the equation to a blue copper(II) hydroxide solid."
            ),
        },
        {
            "type": "Yellow precipitate",
            "title": "Silver nitrate + Potassium iodide",
            "equation": "AgNO₃ + KI → AgI + KNO₃",
            "explanation": (
                "Identify a yellow silver iodide precipitate in a double "
                "displacement reaction."
            ),
        },
        {
            "type": "Single displacement",
            "title": "Zinc + Hydrochloric acid",
            "equation": "Zn + 2HCl → ZnCl₂ + H₂",
            "explanation": "Track zinc oxidation and hydrogen gas formation.",
        },
    ],
    "boundary": (
        "OmniLab matches supported chemical pairs to a fixed educational "
        "result. It does not infer a real outcome from concentration, "
        "quantity, pressure, temperature, order of addition, vessel choice, "
        "burner state, contamination, or laboratory technique."
    ),
    "safety_boundary": (
        "That makes it useful for studying a simplified reaction path, not "
        "for deciding that a real procedure is safe. Results can be "
        "incomplete or wrong. Check important information against trusted "
        "chemistry references and follow trained supervision and your "
        "laboratory's safety rules."
    ),
    "safety_warning": (
        "Never attempt a reaction solely because it appears in a virtual lab."
    ),
}

GUIDED_EXPERIMENT_BOUNDARY = (
    "OmniLab generates an educational prediction from the selected chemicals. "
    "It can be incomplete or wrong and does not replace instructor "
    "supervision, trusted references, or physical-lab safety procedures."
)
GUIDED_EXPERIMENT_SAFETY_WARNING = (
    "Do not attempt the sodium and chlorine reaction outside a properly "
    "equipped, supervised laboratory."
)
OBSERVATION_GUIDE_SAFETY_WARNING = (
    "The result can be incomplete or wrong. Verify it with trusted course "
    "materials and follow trained laboratory supervision."
)

GUIDE_PAGE_REFERENCES = {
    CHEMICAL_REACTION_VIRTUAL_LAB_PAGE["canonical_key"]: (
        CHEMICAL_REACTION_VIRTUAL_LAB_PAGE
    ),
    **{
        guide["canonical_key"]: guide
        for guide in GUIDED_EXPERIMENT_PAGES.values()
    },
    **{
        guide["canonical_key"]: guide
        for guide in OBSERVATION_GUIDE_PAGES.values()
    },
}

SODIUM_CHLORINE_REACTION_FAMILY = "Cl2+Na"
GUIDE_REACTION_FAMILY_BY_PAGE = {
    **{
        guide["canonical_key"]: SODIUM_CHLORINE_REACTION_FAMILY
        for guide in GUIDED_EXPERIMENT_PAGES.values()
    },
    **{
        guide["canonical_key"]: "+".join(
            sorted(reactant["formula"] for reactant in guide["reactants"])
        )
        for guide in OBSERVATION_GUIDE_PAGES.values()
    },
}
GUIDE_SUPPORTED_REACTION_FAMILIES = {
    CHEMICAL_REACTION_VIRTUAL_LAB_PAGE["canonical_key"]: frozenset(
        GUIDE_REACTION_FAMILY_BY_PAGE.values()
    ),
    **{
        guide_key: frozenset({reaction_family})
        for guide_key, reaction_family in GUIDE_REACTION_FAMILY_BY_PAGE.items()
    },
}

# Substance sets include reactants and products named in each rendered equation.
# Reaction patterns are used only when two supported pairs teach the same
# specific chemistry relationship and do not share an exact substance.
GUIDE_CHEMISTRY_PROFILES = {
    "chemical_reaction_virtual_lab": {
        "substances": frozenset(),
        "reaction_patterns": frozenset(),
    },
    "sodium_chlorine_reaction": {
        "substances": frozenset({"Na", "Cl2", "NaCl"}),
        "reaction_patterns": frozenset({"ionic-synthesis", "redox"}),
    },
    "sodium_chlorine_formula": {
        "substances": frozenset({"Na", "Cl2", "NaCl"}),
        "reaction_patterns": frozenset({"ionic-synthesis", "redox"}),
    },
    "sodium_chlorine_ionic_bond": {
        "substances": frozenset({"Na", "Cl2", "NaCl"}),
        "reaction_patterns": frozenset({"ionic-synthesis", "redox"}),
    },
    "limewater_carbon_dioxide": {
        "substances": frozenset({"Ca(OH)2", "CO2", "CaCO3", "H2O"}),
        "reaction_patterns": frozenset({"precipitation"}),
    },
    "sodium_carbonate_hydrochloric_acid": {
        "substances": frozenset({"Na2CO3", "HCl", "NaCl", "CO2", "H2O"}),
        "reaction_patterns": frozenset(
            {"acid-base", "acid-carbonate", "gas-evolution"}
        ),
    },
    "silver_nitrate_potassium_iodide": {
        "substances": frozenset({"AgNO3", "KI", "AgI", "KNO3"}),
        "reaction_patterns": frozenset({"precipitation"}),
    },
    "copper_sulfate_potassium_hydroxide": {
        "substances": frozenset({"CuSO4", "KOH", "Cu(OH)2", "K2SO4"}),
        "reaction_patterns": frozenset({"copper-ii", "precipitation"}),
    },
    "sodium_water": {
        "substances": frozenset({"Na", "H2O", "NaOH", "H2"}),
        "reaction_patterns": frozenset({"gas-forming-redox"}),
    },
    "zinc_hydrochloric_acid": {
        "substances": frozenset({"Zn", "HCl", "ZnCl2", "H2"}),
        "reaction_patterns": frozenset({"metal-acid"}),
    },
    "acetic_acid_sodium_bicarbonate": {
        "substances": frozenset(
            {"CH3COOH", "NaHCO3", "CH3COONa", "CO2", "H2O"}
        ),
        "reaction_patterns": frozenset(
            {"acid-base", "acid-carbonate", "gas-evolution"}
        ),
    },
    "hydrogen_oxygen": {
        "substances": frozenset({"H2", "O2", "H2O"}),
        "reaction_patterns": frozenset({"combustion", "redox"}),
    },
    "iron_oxygen": {
        "substances": frozenset({"Fe", "O2", "Fe2O3"}),
        "reaction_patterns": frozenset({"metal-oxidation", "redox"}),
    },
    "hydrochloric_acid_sodium_hydroxide": {
        "substances": frozenset({"HCl", "NaOH", "NaCl", "H2O"}),
        "reaction_patterns": frozenset({"acid-base", "neutralization"}),
    },
    "silver_nitrate_sodium_chloride": {
        "substances": frozenset({"AgNO3", "NaCl", "AgCl", "NaNO3"}),
        "reaction_patterns": frozenset({"precipitation"}),
    },
    "carbon_monoxide_oxygen": {
        "substances": frozenset({"CO", "O2", "CO2"}),
        "reaction_patterns": frozenset({"combustion", "redox"}),
    },
    "carbon_dioxide_water": {
        "substances": frozenset({"CO2", "H2O", "H2CO3"}),
        "reaction_patterns": frozenset({"acid-formation"}),
    },
    "iron_hydrochloric_acid": {
        "substances": frozenset({"Fe", "HCl", "FeCl2", "H2"}),
        "reaction_patterns": frozenset({"metal-acid"}),
    },
    "copper_oxygen": {
        "substances": frozenset({"Cu", "O2", "CuO"}),
        "reaction_patterns": frozenset({"copper-ii", "metal-oxidation"}),
    },
    "potassium_permanganate_hydrogen_peroxide": {
        "substances": frozenset(
            {"KMnO4", "H2O2", "MnO2", "O2", "KOH", "H2O"}
        ),
        "reaction_patterns": frozenset({"gas-forming-redox", "redox"}),
    },
    "sodium_chloride_water": {
        "substances": frozenset({"NaCl", "H2O", "Na+", "Cl-"}),
        "reaction_patterns": frozenset(),
    },
    "carbon_dioxide_sodium_hydroxide": {
        "substances": frozenset({"CO2", "NaOH", "Na2CO3", "H2O"}),
        "reaction_patterns": frozenset({"acid-base"}),
    },
    "nitrogen_dioxide_water": {
        "substances": frozenset({"NO2", "H2O", "HNO2", "HNO3"}),
        "reaction_patterns": frozenset(
            {"acid-formation", "disproportionation", "redox"}
        ),
    },
    "hydrogen_chlorine": {
        "substances": frozenset({"H2", "Cl2", "HCl"}),
        "reaction_patterns": frozenset({"combination", "redox"}),
    },
    "carbon_oxygen": {
        "substances": frozenset({"C", "O2", "CO2"}),
        "reaction_patterns": frozenset({"combustion", "redox"}),
    },
}

# Each edge carries machine-checkable chemistry evidence. The UI deliberately
# renders only the student-facing reason.
GUIDE_RELATIONSHIP_DEFINITIONS = {
    "chemical_reaction_virtual_lab": [
        (
            "hydrochloric_acid_sodium_hydroxide",
            "Study a supported neutralization reaction",
            "supported_reaction_family",
            "HCl+NaOH",
        ),
        (
            "limewater_carbon_dioxide",
            "See a cloudy precipitate result",
            "supported_reaction_family",
            "CO2+Ca(OH)2",
        ),
        (
            "potassium_permanganate_hydrogen_peroxide",
            "Study oxygen bubbles in a supported redox reaction",
            "supported_reaction_family",
            "H2O2+KMnO4",
        ),
    ],
    "sodium_chlorine_reaction": [
        (
            "sodium_chlorine_formula",
            "Use the same substances to build NaCl",
            "supported_reaction_family",
            SODIUM_CHLORINE_REACTION_FAMILY,
        ),
        (
            "sodium_chlorine_ionic_bond",
            "Follow the same electron transfer",
            "supported_reaction_family",
            SODIUM_CHLORINE_REACTION_FAMILY,
        ),
        (
            "hydrogen_chlorine",
            "Compare chlorine reacting with another element",
            "shared_substance",
            "Cl2",
        ),
    ],
    "sodium_chlorine_formula": [
        (
            "sodium_chlorine_reaction",
            "Put NaCl into the balanced reaction",
            "supported_reaction_family",
            SODIUM_CHLORINE_REACTION_FAMILY,
        ),
        (
            "sodium_chlorine_ionic_bond",
            "Connect the formula to ion charges",
            "supported_reaction_family",
            SODIUM_CHLORINE_REACTION_FAMILY,
        ),
        (
            "sodium_chloride_water",
            "Follow NaCl from its formula to dissolved ions",
            "shared_substance",
            "NaCl",
        ),
    ],
    "sodium_chlorine_ionic_bond": [
        (
            "sodium_chlorine_formula",
            "Use the ion charges to build NaCl",
            "supported_reaction_family",
            SODIUM_CHLORINE_REACTION_FAMILY,
        ),
        (
            "sodium_chlorine_reaction",
            "See the same ions in the full reaction",
            "supported_reaction_family",
            SODIUM_CHLORINE_REACTION_FAMILY,
        ),
        ("sodium_water", "Compare another reaction of sodium", "shared_substance", "Na"),
    ],
    "limewater_carbon_dioxide": [
        (
            "carbon_dioxide_water",
            "Compare another reaction of carbon dioxide",
            "shared_substance",
            "CO2",
        ),
        (
            "sodium_carbonate_hydrochloric_acid",
            "Follow carbon dioxide from gas to precipitate",
            "shared_substance",
            "CO2",
        ),
        (
            "carbon_dioxide_sodium_hydroxide",
            "Compare carbon dioxide reacting with sodium hydroxide",
            "shared_substance",
            "CO2",
        ),
    ],
    "sodium_carbonate_hydrochloric_acid": [
        (
            "zinc_hydrochloric_acid",
            "Compare another hydrochloric acid reaction",
            "shared_substance",
            "HCl",
        ),
        (
            "limewater_carbon_dioxide",
            "Use the carbon dioxide in limewater",
            "shared_substance",
            "CO2",
        ),
        (
            "acetic_acid_sodium_bicarbonate",
            "Compare another carbon dioxide-producing reaction",
            "shared_reaction_pattern",
            "acid-carbonate",
        ),
    ],
    "silver_nitrate_potassium_iodide": [
        (
            "silver_nitrate_sodium_chloride",
            "Compare yellow and white silver precipitates",
            "shared_substance",
            "AgNO3",
        ),
        (
            "copper_sulfate_potassium_hydroxide",
            "Compare a blue precipitate result",
            "shared_reaction_pattern",
            "precipitation",
        ),
    ],
    "copper_sulfate_potassium_hydroxide": [
        (
            "silver_nitrate_potassium_iodide",
            "Compare a yellow precipitate result",
            "shared_reaction_pattern",
            "precipitation",
        ),
        (
            "limewater_carbon_dioxide",
            "Compare a cloudy precipitate result",
            "shared_reaction_pattern",
            "precipitation",
        ),
    ],
    "sodium_water": [
        ("sodium_chlorine_reaction", "Compare another reaction of sodium", "shared_substance", "Na"),
        (
            "zinc_hydrochloric_acid",
            "Compare another hydrogen-producing reaction",
            "shared_substance",
            "H2",
        ),
        (
            "hydrogen_oxygen",
            "Follow hydrogen into a water-forming reaction",
            "shared_substance",
            "H2",
        ),
    ],
    "zinc_hydrochloric_acid": [
        (
            "sodium_carbonate_hydrochloric_acid",
            "Compare another hydrochloric acid reaction",
            "shared_substance",
            "HCl",
        ),
        (
            "iron_hydrochloric_acid",
            "Compare another metal-acid reaction",
            "shared_substance",
            "HCl",
        ),
        (
            "hydrogen_oxygen",
            "Follow hydrogen into a water-forming reaction",
            "shared_substance",
            "H2",
        ),
    ],
    "acetic_acid_sodium_bicarbonate": [
        (
            "sodium_carbonate_hydrochloric_acid",
            "Compare another carbon dioxide-producing reaction",
            "shared_reaction_pattern",
            "acid-carbonate",
        ),
        (
            "limewater_carbon_dioxide",
            "Use the carbon dioxide in limewater",
            "shared_substance",
            "CO2",
        ),
        (
            "carbon_dioxide_water",
            "Follow carbon dioxide into water",
            "shared_substance",
            "CO2",
        ),
    ],
    "hydrogen_oxygen": [
        ("sodium_water", "Trace hydrogen from a water reaction", "shared_substance", "H2"),
        (
            "hydrogen_chlorine",
            "Compare hydrogen reacting with another diatomic gas",
            "shared_substance",
            "H2",
        ),
        ("iron_oxygen", "Compare another reaction with oxygen", "shared_substance", "O2"),
    ],
    "iron_oxygen": [
        ("hydrogen_oxygen", "Compare another reaction with oxygen", "shared_substance", "O2"),
        (
            "copper_oxygen",
            "Compare another heated metal oxidation",
            "shared_substance",
            "O2",
        ),
        (
            "carbon_oxygen",
            "Compare oxygen reacting with a nonmetal",
            "shared_substance",
            "O2",
        ),
    ],
    "hydrochloric_acid_sodium_hydroxide": [
        (
            "zinc_hydrochloric_acid",
            "Compare an acid reacting with a metal",
            "shared_substance",
            "HCl",
        ),
        (
            "sodium_chloride_water",
            "Follow the sodium chloride product into water",
            "shared_substance",
            "NaCl",
        ),
        (
            "carbon_dioxide_sodium_hydroxide",
            "Compare sodium hydroxide reacting with carbon dioxide",
            "shared_substance",
            "NaOH",
        ),
    ],
    "silver_nitrate_sodium_chloride": [
        (
            "silver_nitrate_potassium_iodide",
            "Compare yellow and white silver precipitates",
            "shared_substance",
            "AgNO3",
        ),
        (
            "copper_sulfate_potassium_hydroxide",
            "Compare a blue precipitate result",
            "shared_reaction_pattern",
            "precipitation",
        ),
        (
            "sodium_chloride_water",
            "Compare dissolved chloride before silver chloride forms",
            "shared_substance",
            "NaCl",
        ),
    ],
    "carbon_monoxide_oxygen": [
        (
            "hydrogen_oxygen",
            "Compare another oxygen combustion reaction",
            "shared_substance",
            "O2",
        ),
        (
            "iron_oxygen",
            "Compare oxidation with a solid product",
            "shared_substance",
            "O2",
        ),
        (
            "carbon_oxygen",
            "Compare complete combustion pathways",
            "shared_substance",
            "CO2",
        ),
    ],
    "carbon_dioxide_water": [
        (
            "limewater_carbon_dioxide",
            "Compare carbon dioxide reacting with limewater",
            "shared_substance",
            "CO2",
        ),
        (
            "nitrogen_dioxide_water",
            "Compare another gas oxide reacting with water",
            "shared_substance",
            "H2O",
        ),
        (
            "carbon_dioxide_sodium_hydroxide",
            "Compare carbon dioxide reacting with sodium hydroxide",
            "shared_substance",
            "CO2",
        ),
    ],
    "iron_hydrochloric_acid": [
        (
            "zinc_hydrochloric_acid",
            "Compare another metal-acid reaction",
            "shared_substance",
            "HCl",
        ),
        (
            "hydrochloric_acid_sodium_hydroxide",
            "Compare hydrochloric acid in neutralization",
            "shared_substance",
            "HCl",
        ),
    ],
    "copper_oxygen": [
        (
            "iron_oxygen",
            "Compare another metal reacting with oxygen",
            "shared_substance",
            "O2",
        ),
        (
            "carbon_monoxide_oxygen",
            "Compare oxidation that forms a gaseous product",
            "shared_substance",
            "O2",
        ),
        (
            "copper_sulfate_potassium_hydroxide",
            "Compare another copper(II) compound",
            "shared_reaction_pattern",
            "copper-ii",
        ),
    ],
    "potassium_permanganate_hydrogen_peroxide": [
        (
            "hydrogen_oxygen",
            "Compare another reaction involving oxygen",
            "shared_substance",
            "O2",
        ),
        (
            "sodium_water",
            "Compare another gas-forming redox reaction",
            "shared_reaction_pattern",
            "gas-forming-redox",
        ),
        (
            "nitrogen_dioxide_water",
            "Compare another condition-specific redox equation",
            "shared_reaction_pattern",
            "redox",
        ),
    ],
    "sodium_chloride_water": [
        (
            "sodium_chlorine_formula",
            "Connect dissolved ions to the NaCl formula",
            "shared_substance",
            "NaCl",
        ),
        (
            "hydrochloric_acid_sodium_hydroxide",
            "See neutralization form sodium chloride and water",
            "shared_substance",
            "NaCl",
        ),
        (
            "silver_nitrate_sodium_chloride",
            "Use dissolved chloride to form silver chloride",
            "shared_substance",
            "NaCl",
        ),
    ],
    "carbon_dioxide_sodium_hydroxide": [
        (
            "carbon_dioxide_water",
            "Compare carbon dioxide reacting with water",
            "shared_substance",
            "CO2",
        ),
        (
            "limewater_carbon_dioxide",
            "Compare another reaction of carbon dioxide",
            "shared_substance",
            "CO2",
        ),
        (
            "hydrochloric_acid_sodium_hydroxide",
            "Compare sodium hydroxide in neutralization",
            "shared_substance",
            "NaOH",
        ),
    ],
    "nitrogen_dioxide_water": [
        (
            "carbon_dioxide_water",
            "Compare another gas oxide reacting with water",
            "shared_substance",
            "H2O",
        ),
        (
            "potassium_permanganate_hydrogen_peroxide",
            "Compare another condition-specific redox equation",
            "shared_reaction_pattern",
            "redox",
        ),
    ],
    "hydrogen_chlorine": [
        (
            "hydrogen_oxygen",
            "Compare hydrogen reacting with another diatomic gas",
            "shared_substance",
            "H2",
        ),
        (
            "sodium_chlorine_reaction",
            "Compare chlorine reacting with another element",
            "shared_substance",
            "Cl2",
        ),
    ],
    "carbon_oxygen": [
        (
            "carbon_monoxide_oxygen",
            "Compare complete combustion pathways",
            "shared_substance",
            "CO2",
        ),
        (
            "iron_oxygen",
            "Compare oxygen reacting with a metal",
            "shared_substance",
            "O2",
        ),
    ],
}

GUIDE_RELATIONSHIPS = {
    guide_key: [
        (related_key, reason)
        for related_key, reason, _evidence_kind, _evidence_value in relationships
    ]
    for guide_key, relationships in GUIDE_RELATIONSHIP_DEFINITIONS.items()
}


def related_guides_for(canonical_key):
    return [
        {
            "route_name": GUIDE_PAGE_REFERENCES[related_key]["route_name"],
            "title": GUIDE_PAGE_REFERENCES[related_key]["title"],
            "reason": reason,
        }
        for related_key, reason in GUIDE_RELATIONSHIPS[canonical_key]
    ]


def guide_learning_schema(
    guide,
    canonical_url,
    learning_resource_type,
    *,
    equations=(),
    safety_notes=(),
    boundary_notes=(),
    include_question_answer=True,
):
    """Build guide JSON-LD only from content rendered on the same page."""
    schema = {
        "@context": "https://schema.org",
        "@type": "LearningResource",
        "@id": f"{canonical_url}#guide",
        "name": guide.get("heading", guide["title"]),
        "description": guide.get("direct_answer", guide["description"]),
        "url": canonical_url,
        "inLanguage": "en",
        "educationalLevel": "Introductory chemistry",
        "learningResourceType": learning_resource_type,
        "isPartOf": {
            "@type": "WebSite",
            "name": "OmniLab",
            "url": PUBLIC_CANONICAL_URLS["index"],
        },
    }

    if include_question_answer and guide.get("direct_answer"):
        schema["mainEntity"] = {
            "@type": "Question",
            "name": guide["title"],
            "acceptedAnswer": {
                "@type": "Answer",
                "text": guide["direct_answer"],
            },
        }

    content_parts = [
        {
            "@type": "CreativeWork",
            "name": "Reaction equation",
            "text": equation,
        }
        for equation in equations
    ]
    safety_text = " ".join((*safety_notes, *boundary_notes))
    if safety_text:
        content_parts.append(
            {
                "@type": "CreativeWork",
                "name": "Safety and educational boundary",
                "text": safety_text,
            }
        )
    if content_parts:
        schema["hasPart"] = content_parts

    return schema

GUIDE_LIBRARY_GROUPS = [
    {
        "label": "Start with the virtual lab",
        "description": (
            "See what OmniLab supports, how to choose a reaction pair, and "
            "how to read the result."
        ),
        "guides": [
            {
                "number": "01",
                "title": CHEMICAL_REACTION_VIRTUAL_LAB_PAGE["title"],
                "summary": (
                    "Choose a supported pair, request a prediction, and read "
                    "the equation, explanation, safety notes, and visible cue."
                ),
                "route_name": CHEMICAL_REACTION_VIRTUAL_LAB_PAGE[
                    "route_name"
                ],
                "canonical_key": CHEMICAL_REACTION_VIRTUAL_LAB_PAGE[
                    "canonical_key"
                ],
            },
        ],
    },
    {
        "label": "Study sodium and chlorine",
        "description": (
            "Follow one reaction from reactants and electron transfer to its "
            "formula and ionic bond."
        ),
        "guides": [
            {
                "number": "02",
                "title": GUIDED_EXPERIMENT_PAGES["reaction"]["title"],
                "summary": (
                    "Follow the reactants, electron transfer, and sodium "
                    "chloride product."
                ),
                "route_name": GUIDED_EXPERIMENT_PAGES["reaction"]["route_name"],
                "canonical_key": GUIDED_EXPERIMENT_PAGES["reaction"][
                    "canonical_key"
                ],
            },
            {
                "number": "03",
                "title": GUIDED_EXPERIMENT_PAGES["formula"]["title"],
                "summary": (
                    "Connect the ion charges to NaCl and the balanced "
                    "equation."
                ),
                "route_name": GUIDED_EXPERIMENT_PAGES["formula"]["route_name"],
                "canonical_key": GUIDED_EXPERIMENT_PAGES["formula"][
                    "canonical_key"
                ],
            },
            {
                "number": "04",
                "title": GUIDED_EXPERIMENT_PAGES["ionic-bond"]["title"],
                "summary": (
                    "Trace the electron transfer from atoms to an ionic "
                    "lattice."
                ),
                "route_name": GUIDED_EXPERIMENT_PAGES["ionic-bond"][
                    "route_name"
                ],
                "canonical_key": GUIDED_EXPERIMENT_PAGES["ionic-bond"][
                    "canonical_key"
                ],
            },
        ],
    },
    {
        "label": "Follow a visible result",
        "description": (
            "Use cloudiness, fizzing, gas bubbles, or a colored precipitate "
            "to connect an observation to its equation."
        ),
        "guides": [
            {
                "number": "05",
                "title": OBSERVATION_GUIDE_PAGES[
                    "limewater-carbon-dioxide"
                ]["title"],
                "summary": (
                    "Connect the equation to the cloudy white calcium "
                    "carbonate precipitate."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "limewater-carbon-dioxide"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "limewater-carbon-dioxide"
                ]["canonical_key"],
            },
            {
                "number": "06",
                "title": OBSERVATION_GUIDE_PAGES[
                    "sodium-carbonate-hydrochloric-acid"
                ]["title"],
                "summary": (
                    "Identify the carbon dioxide behind the visible bubbles."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "sodium-carbonate-hydrochloric-acid"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "sodium-carbonate-hydrochloric-acid"
                ]["canonical_key"],
            },
            {
                "number": "07",
                "title": OBSERVATION_GUIDE_PAGES[
                    "silver-nitrate-potassium-iodide"
                ]["title"],
                "summary": (
                    "Trace the ions that produce the yellow silver iodide "
                    "solid."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "silver-nitrate-potassium-iodide"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "silver-nitrate-potassium-iodide"
                ]["canonical_key"],
            },
            {
                "number": "08",
                "title": OBSERVATION_GUIDE_PAGES[
                    "copper-sulfate-potassium-hydroxide"
                ]["title"],
                "summary": (
                    "Connect the double displacement equation to a blue "
                    "copper(II) hydroxide precipitate."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "copper-sulfate-potassium-hydroxide"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "copper-sulfate-potassium-hydroxide"
                ]["canonical_key"],
            },
            {
                "number": "09",
                "title": OBSERVATION_GUIDE_PAGES["sodium-water"]["title"],
                "summary": (
                    "Connect hydrogen bubbles, heat release, and sodium "
                    "hydroxide to the balanced equation."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "sodium-water"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "sodium-water"
                ]["canonical_key"],
            },
            {
                "number": "10",
                "title": OBSERVATION_GUIDE_PAGES[
                    "zinc-hydrochloric-acid"
                ]["title"],
                "summary": (
                    "Connect hydrogen bubbles and electron transfer to the "
                    "balanced metal-acid reaction."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "zinc-hydrochloric-acid"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "zinc-hydrochloric-acid"
                ]["canonical_key"],
            },
            {
                "number": "11",
                "title": OBSERVATION_GUIDE_PAGES[
                    "acetic-acid-sodium-bicarbonate"
                ]["title"],
                "summary": (
                    "Connect carbon dioxide bubbles to the balanced "
                    "acid-bicarbonate reaction."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "acetic-acid-sodium-bicarbonate"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "acetic-acid-sodium-bicarbonate"
                ]["canonical_key"],
            },
            {
                "number": "12",
                "title": OBSERVATION_GUIDE_PAGES[
                    "hydrogen-oxygen"
                ]["title"],
                "summary": (
                    "Balance the two-to-one gas ratio and connect the "
                    "exothermic reaction to its water product."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "hydrogen-oxygen"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "hydrogen-oxygen"
                ]["canonical_key"],
            },
            {
                "number": "13",
                "title": OBSERVATION_GUIDE_PAGES["iron-oxygen"]["title"],
                "summary": (
                    "Balance the iron(III) oxide equation and distinguish "
                    "rapid oxidation from slow rusting."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "iron-oxygen"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "iron-oxygen"
                ]["canonical_key"],
            },
            {
                "number": "14",
                "title": OBSERVATION_GUIDE_PAGES[
                    "hydrochloric-acid-sodium-hydroxide"
                ]["title"],
                "summary": (
                    "Connect neutralization, the net ionic equation, and "
                    "exothermic warming without a dramatic visible change."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "hydrochloric-acid-sodium-hydroxide"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "hydrochloric-acid-sodium-hydroxide"
                ]["canonical_key"],
            },
            {
                "number": "15",
                "title": OBSERVATION_GUIDE_PAGES[
                    "silver-nitrate-sodium-chloride"
                ]["title"],
                "summary": (
                    "Connect a white silver chloride precipitate to the "
                    "balanced and net ionic equations."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "silver-nitrate-sodium-chloride"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "silver-nitrate-sodium-chloride"
                ]["canonical_key"],
            },
            {
                "number": "16",
                "title": OBSERVATION_GUIDE_PAGES[
                    "carbon-monoxide-oxygen"
                ]["title"],
                "summary": (
                    "Balance carbon monoxide combustion and keep ignition or "
                    "catalytic activation attached to the result."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "carbon-monoxide-oxygen"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "carbon-monoxide-oxygen"
                ]["canonical_key"],
            },
            {
                "number": "17",
                "title": OBSERVATION_GUIDE_PAGES[
                    "carbon-dioxide-water"
                ]["title"],
                "summary": (
                    "Separate carbon dioxide dissolution from reversible "
                    "carbonic acid formation and its effect on pH."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "carbon-dioxide-water"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "carbon-dioxide-water"
                ]["canonical_key"],
            },
            {
                "number": "18",
                "title": OBSERVATION_GUIDE_PAGES[
                    "iron-hydrochloric-acid"
                ]["title"],
                "summary": (
                    "Connect hydrogen bubbles and electron transfer to the "
                    "balanced iron and hydrochloric acid reaction."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "iron-hydrochloric-acid"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "iron-hydrochloric-acid"
                ]["canonical_key"],
            },
            {
                "number": "19",
                "title": OBSERVATION_GUIDE_PAGES[
                    "copper-oxygen"
                ]["title"],
                "summary": (
                    "Connect heating, a black copper(II) oxide coating, and "
                    "electron transfer to the balanced equation."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "copper-oxygen"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "copper-oxygen"
                ]["canonical_key"],
            },
            {
                "number": "20",
                "title": OBSERVATION_GUIDE_PAGES[
                    "potassium-permanganate-hydrogen-peroxide"
                ]["title"],
                "summary": (
                    "Connect oxygen bubbles, brown manganese dioxide, and "
                    "redox roles to the condition-specific balanced equation."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "potassium-permanganate-hydrogen-peroxide"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "potassium-permanganate-hydrogen-peroxide"
                ]["canonical_key"],
            },
            {
                "number": "21",
                "title": OBSERVATION_GUIDE_PAGES[
                    "sodium-chloride-water"
                ]["title"],
                "summary": (
                    "Separate dissolution from chemical change, then connect "
                    "the aqueous state symbols to hydrated ions."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "sodium-chloride-water"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "sodium-chloride-water"
                ]["canonical_key"],
            },
            {
                "number": "22",
                "title": OBSERVATION_GUIDE_PAGES[
                    "carbon-dioxide-sodium-hydroxide"
                ]["title"],
                "summary": (
                    "Balance the 1:2 reactant ratio and compare carbonate "
                    "formation with the bicarbonate pathway."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "carbon-dioxide-sodium-hydroxide"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "carbon-dioxide-sodium-hydroxide"
                ]["canonical_key"],
            },
            {
                "number": "23",
                "title": OBSERVATION_GUIDE_PAGES[
                    "nitrogen-dioxide-water"
                ]["title"],
                "summary": (
                    "Balance the two acid products and separate the simplified "
                    "equation from later nitrogen oxide chemistry."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "nitrogen-dioxide-water"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "nitrogen-dioxide-water"
                ]["canonical_key"],
            },
            {
                "number": "24",
                "title": OBSERVATION_GUIDE_PAGES[
                    "hydrogen-chlorine"
                ]["title"],
                "summary": (
                    "Balance the two diatomic gases and separate hydrogen "
                    "chloride gas from hydrochloric acid."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "hydrogen-chlorine"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "hydrogen-chlorine"
                ]["canonical_key"],
            },
            {
                "number": "25",
                "title": OBSERVATION_GUIDE_PAGES[
                    "carbon-oxygen"
                ]["title"],
                "summary": (
                    "Balance complete carbon combustion and keep oxygen "
                    "supply attached to the carbon dioxide result."
                ),
                "route_name": OBSERVATION_GUIDE_PAGES[
                    "carbon-oxygen"
                ]["route_name"],
                "canonical_key": OBSERVATION_GUIDE_PAGES[
                    "carbon-oxygen"
                ]["canonical_key"],
            },
        ],
    },
]

CHEMICAL_REACTION_LAB_FAQS = [
    {
        "question": "Is OmniLab's chemical reaction virtual lab free?",
        "answer": (
            "Yes. The current public release is free to use without an "
            "account or payment. Future access or pricing may change as the "
            "product develops."
        ),
    },
    {
        "question": "How many chemical reactions can I try?",
        "answer": (
            "OmniLab currently supports 34 specific reaction pairs across "
            "38 available substances. After you choose the first chemical, "
            "the lab marks every supported partner."
        ),
    },
    {
        "question": "Does the beaker or burner change the prediction?",
        "answer": (
            "No. The selected chemicals are the only inputs to the current "
            "prediction. Vessel and burner choices are visual setup aids."
        ),
    },
    {
        "question": "Can a virtual reaction replace a physical lab?",
        "answer": (
            "No. OmniLab is an educational prediction tool, not a physical "
            "simulation or a substitute for instructor supervision, trusted "
            "references, or real-laboratory safety procedures."
        ),
    },
]

PRODUCT_FAQS = [
    {
        "question": "How do I set up an experiment in OmniLab?",
        "answer": (
            "Choose an Erlenmeyer flask, graduated test tube, or laboratory "
            "beaker from Apparatus. Open Chemicals, search the available "
            "inputs, and drag one or more into the vessel. Add the virtual "
            "Bunsen burner if you want to model heating, then select Analyze "
            "Chemical Reaction."
        ),
    },
    {
        "question": "Which chemicals and equipment can I use?",
        "answer": (
            "The current release supports 34 reaction pairs using the chemicals "
            "listed in its searchable Chemicals menu. Equipment includes an "
            "Erlenmeyer flask, graduated test tube, laboratory beaker, and "
            "virtual Bunsen burner. The menus in the lab are the current source "
            "of truth for supported inputs."
        ),
    },
    {
        "question": "How accurate are the reaction results?",
        "answer": (
            "OmniLab returns educational equations, explanations, visual "
            "effects, and safety guidance for supported chemical pairs. "
            "Results can be incomplete or wrong, so check important "
            "information against trusted chemistry sources and follow your "
            "instructor's guidance."
        ),
    },
    {
        "question": "Can OmniLab replace a physical chemistry lab?",
        "answer": (
            "No. OmniLab is an educational prediction tool for exploring "
            "setups before working with real materials. It doesn't reproduce "
            "every real-world condition or replace trained supervision, "
            "professional judgment, or the safety procedures of a physical "
            "laboratory."
        ),
    },
    {
        "question": "Do I need an account to start?",
        "answer": (
            "No. The current public release opens directly in the lab and "
            "doesn't require an account or payment. Future access or pricing "
            "may change as the product develops."
        ),
    },
    {
        "question": "How can I contact and get help?",
        "answer": (
            "Use the Contact page to ask a question, report something that "
            "isn't working, or suggest an improvement. Submit only the details "
            "needed to understand your request, and OmniLab will show whether "
            "your message was sent."
        ),
        "answer_before_link": "Use the ",
        "answer_link_text": "Contact page",
        "answer_after_link": (
            " to ask a question, report something that isn't working, or "
            "suggest an improvement. Submit only the details needed to "
            "understand your request, and OmniLab will show whether your "
            "message was sent."
        ),
        "link_url": "/contact/",
    },
]

REACTION_RETRY_MESSAGE = (
    "OmniLab couldn't complete this prediction. Please try again."
)
REACTION_FEEDBACK_LABEL = "Reaction feedback"
REACTION_FEEDBACK_PROMPTS = "\n\n".join(
    [
        "What were you trying to predict?",
        "What do you plan to do next?",
    ]
)


def get_client_network_address(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    # Render puts the real client address first and appends proxy hops after it.
    # The application socket address is the safe fallback for malformed input.
    candidates = [
        forwarded_for.split(",", 1)[0].strip(),
        request.META.get("REMOTE_ADDR", "").strip(),
    ]

    for candidate in candidates:
        try:
            return ipaddress.ip_address(candidate).compressed
        except ValueError:
            continue

    return "unknown"


def increment_reaction_request_count(
    client_digest,
    window_number,
    database_path=None,
):
    rate_limit_database = Path(
        database_path
        or settings.OMNILAB_REACTION_RATE_LIMIT_DATABASE_PATH
    )
    rate_limit_database.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(rate_limit_database, timeout=5) as connection:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_rate_limits (
                client_digest TEXT NOT NULL,
                window_number INTEGER NOT NULL,
                request_count INTEGER NOT NULL,
                PRIMARY KEY (client_digest, window_number)
            ) WITHOUT ROWID
            """
        )
        updated = connection.execute(
            """
            UPDATE reaction_rate_limits
            SET request_count = request_count + 1
            WHERE client_digest = ? AND window_number = ?
            """,
            (client_digest, window_number),
        )
        if updated.rowcount == 0:
            connection.execute(
                """
                INSERT INTO reaction_rate_limits (
                    client_digest,
                    window_number,
                    request_count
                ) VALUES (?, ?, 1)
                """,
                (client_digest, window_number),
            )

        request_count = connection.execute(
            """
            SELECT request_count
            FROM reaction_rate_limits
            WHERE client_digest = ? AND window_number = ?
            """,
            (client_digest, window_number),
        ).fetchone()[0]
        connection.execute(
            "DELETE FROM reaction_rate_limits WHERE window_number < ?",
            (window_number - 1,),
        )

    return request_count


def reaction_rate_limit(request):
    limit = max(1, settings.OMNILAB_REACTION_RATE_LIMIT_REQUESTS)
    window_seconds = max(
        1, settings.OMNILAB_REACTION_RATE_LIMIT_WINDOW_SECONDS
    )
    now = int(time.time())
    window_number = now // window_seconds
    retry_after = window_seconds - (now % window_seconds)
    client_address = get_client_network_address(request)
    client_digest = hashlib.sha256(client_address.encode()).hexdigest()
    request_count = increment_reaction_request_count(
        client_digest,
        window_number,
    )

    if request_count <= limit:
        return None

    response = JsonResponse(
        {
            "status": "rate_limited",
            "message": (
                "Too many reaction analyses were requested from this "
                f"network. Try again in {retry_after} seconds."
            ),
        },
        status=429,
    )
    response["Retry-After"] = str(retry_after)
    return response


def contact_rate_limit(request):
    limit = max(1, settings.OMNILAB_CONTACT_RATE_LIMIT_REQUESTS)
    window_seconds = max(
        1, settings.OMNILAB_CONTACT_RATE_LIMIT_WINDOW_SECONDS
    )
    now = int(time.time())
    window_number = now // window_seconds
    retry_after = window_seconds - (now % window_seconds)
    client_address = get_client_network_address(request)
    client_digest = hashlib.sha256(client_address.encode()).hexdigest()
    cache_key = f"omnilab:contact:{client_digest}:{window_number}"

    if cache.add(cache_key, 1, timeout=retry_after):
        request_count = 1
    else:
        try:
            request_count = cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=retry_after)
            request_count = 1

    if request_count <= limit:
        return None

    return retry_after


def parse_selected_chemicals(user_query):
    return [
        chemical.strip()
        for chemical in user_query.split("+")
        if chemical.strip()
    ]


def is_supported_reaction_setup(selected_chemicals):
    return get_reaction(selected_chemicals) is not None


def normalize_reactant(reactant):
    normalized = reactant.strip()
    normalized = re.sub(r"^\d+(?:\.\d+)?\s*", "", normalized)
    normalized = re.sub(r"\((?:s|l|g|aq)\)\s*$", "", normalized, flags=re.I)
    return re.sub(r"\s+", "", normalized).casefold()


def equation_uses_only_selected_reactants(equation, selected_chemicals):
    selected = {
        normalize_reactant(chemical) for chemical in selected_chemicals
    }
    equation_steps = [
        step.strip() for step in equation.split("|") if step.strip()
    ]

    if not equation_steps:
        return False

    for step in equation_steps:
        if "->" not in step:
            return False
        reactant_side, _ = step.split("->", 1)
        reactants = {
            normalize_reactant(reactant)
            for reactant in reactant_side.split("+")
            if reactant.strip()
        }
        if not reactants or not reactants.issubset(selected):
            return False

    return True


def normalize_reaction_effect(effect):
    if not isinstance(effect, str):
        return None

    normalized_effect = effect.strip().casefold()
    return (
        normalized_effect
        if normalized_effect in SUPPORTED_REACTION_EFFECTS
        else None
    )


def validate_complete_reaction_response(data, selected_chemicals):
    if not isinstance(data, dict):
        return None

    equation = data.get("equation")
    explanation = data.get("explanation")
    safety = data.get("safety")
    effect = normalize_reaction_effect(data.get("effect"))
    precipitate_color = data.get("precipitate_color")

    if not all(
        isinstance(value, str)
        for value in (equation, explanation, safety)
    ):
        return None

    equation = equation.strip()
    explanation = explanation.strip()
    safety_rules = [rule.strip() for rule in safety.split("|")]

    if (
        not equation
        or not explanation
        or len(safety_rules) != 3
        or not all(safety_rules)
        or effect is None
        or not equation_uses_only_selected_reactants(
            equation, selected_chemicals
        )
    ):
        return None

    if effect == "precipitate":
        if (
            not isinstance(precipitate_color, str)
            or precipitate_color not in PRECIPITATE_COLORS
        ):
            return None
    elif precipitate_color is not None:
        return None

    reaction = {
        "effect": effect,
        "equation": equation,
        "explanation": explanation,
        "safety": " | ".join(safety_rules),
    }
    if effect == "precipitate":
        reaction["precipitate_color"] = precipitate_color
    return reaction


def insufficient_input_response(message):
    return JsonResponse(
        {
            "status": "insufficient_input",
            "message": message,
        }
    )


def reaction_retry_response():
    return JsonResponse(
        {
            "status": "error",
            "message": REACTION_RETRY_MESSAGE,
        },
        status=502,
    )


def homepage_context(reaction_demo=None, first_experiment=None):
    software_schema = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "OmniLab",
        "url": PUBLIC_CANONICAL_URLS["index"],
        "description": (
            "An interactive virtual chemistry laboratory for chemistry "
            "students to mix compounds, choose lab equipment, and review "
            "predicted reactions."
        ),
        "applicationCategory": "EducationalApplication",
        "operatingSystem": "Any",
        "featureList": [
            "Search and mix supported chemicals",
            "Choose a flask, test tube, beaker, or virtual Bunsen burner",
            (
                "Review predicted equations, explanations, visual effects, "
                "and safety guidance"
            ),
        ],
        "license": (
            "https://github.com/Yusupov-Muhammadyusuf/OmniLab/blob/main/LICENSE"
        ),
        "codeRepository": "https://github.com/Yusupov-Muhammadyusuf/OmniLab",
    }
    context = {
        "canonical_url": PUBLIC_CANONICAL_URLS["index"],
        "social_url": PUBLIC_CANONICAL_URLS["index"],
        "page_title": "Virtual chemistry lab for students | OmniLab",
        "social_title": "OmniLab - Test chemical reactions in a virtual lab",
        "page_description": (
            "Explore predicted reactions in a virtual lab built for chemistry "
            "students. OmniLab is educational and doesn't replace physical "
            "lab procedures."
        ),
        "social_preview_url": SOCIAL_PREVIEW_URL,
        "social_preview_alt": SOCIAL_PREVIEW_ALT,
        "software_schema_json": json.dumps(software_schema),
        "reaction_demo": reaction_demo,
        "reaction_demo_json": json.dumps(reaction_demo),
        "first_experiment": first_experiment,
        "first_experiment_json": json.dumps(bool(first_experiment)),
        "supported_reaction_pairs_json": json.dumps(
            supported_reaction_pairs()
        ),
    }
    if reaction_demo:
        context.update(
            {
                "social_url": reaction_demo["url"],
                "page_title": reaction_demo["page_title"],
                "social_title": reaction_demo["page_title"],
                "page_description": reaction_demo["page_description"],
            }
        )
    elif first_experiment:
        context.update(
            {
                "social_url": first_experiment["url"],
                "page_title": first_experiment["page_title"],
                "social_title": first_experiment["page_title"],
                "page_description": first_experiment["page_description"],
            }
        )
    return context


@ensure_csrf_cookie
def index(request):
    return render(request, "index.html", homepage_context())


@ensure_csrf_cookie
def first_experiment(request):
    return render(
        request,
        "index.html",
        homepage_context(first_experiment=FIRST_EXPERIMENT),
    )


@ensure_csrf_cookie
def sodium_chlorine_demo(request):
    return render(
        request,
        "index.html",
        homepage_context(SODIUM_CHLORINE_DEMO),
    )


@ensure_csrf_cookie
def prepared_reaction_demo(request, demo_key):
    return render(
        request,
        "index.html",
        homepage_context(REACTION_DEMOS[demo_key]),
    )


def guided_experiment(request, guide_key):
    guide = GUIDED_EXPERIMENT_PAGES[guide_key]
    related_guides = related_guides_for(guide["canonical_key"])
    canonical_url = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]
    page_schema = guide_learning_schema(
        guide,
        canonical_url,
        "Study guide",
        equations=(guide["equation"],),
        boundary_notes=(
            GUIDED_EXPERIMENT_BOUNDARY,
            GUIDED_EXPERIMENT_SAFETY_WARNING,
        ),
    )
    return render(
        request,
        "guided_experiment.html",
        {
            "guide": guide,
            "related_guides": related_guides,
            "canonical_url": canonical_url,
            "social_preview_url": SOCIAL_PREVIEW_URL,
            "social_preview_alt": SOCIAL_PREVIEW_ALT,
            "page_schema_json": json.dumps(page_schema),
            "guide_boundary": GUIDED_EXPERIMENT_BOUNDARY,
            "guide_safety_warning": GUIDED_EXPERIMENT_SAFETY_WARNING,
        },
    )


def observation_guide(request, guide_key):
    guide = OBSERVATION_GUIDE_PAGES[guide_key]
    related_guides = related_guides_for(guide["canonical_key"])
    canonical_url = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]
    page_schema = guide_learning_schema(
        guide,
        canonical_url,
        "Experiment observation guide",
        equations=(guide["equation"],),
        safety_notes=tuple(guide["safety"]),
        boundary_notes=(
            guide["boundary"],
            OBSERVATION_GUIDE_SAFETY_WARNING,
        ),
    )
    return render(
        request,
        "observation_guide.html",
        {
            "guide": guide,
            "related_guides": related_guides,
            "canonical_url": canonical_url,
            "social_preview_url": SOCIAL_PREVIEW_URL,
            "social_preview_alt": SOCIAL_PREVIEW_ALT,
            "page_schema_json": json.dumps(page_schema),
            "guide_safety_warning": OBSERVATION_GUIDE_SAFETY_WARNING,
        },
    )


def chemical_reaction_virtual_lab(request):
    guide = CHEMICAL_REACTION_VIRTUAL_LAB_PAGE
    canonical_url = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]
    description = guide["description"]
    learning_schema = guide_learning_schema(
        guide,
        canonical_url,
        "Virtual laboratory guide",
        equations=tuple(
            example["equation"] for example in guide["reaction_examples"]
        ),
        boundary_notes=(
            guide["boundary"],
            guide["safety_boundary"],
            guide["safety_warning"],
        ),
        include_question_answer=False,
    )
    page_schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                key: value
                for key, value in learning_schema.items()
                if key != "@context"
            },
            {
                "@type": "FAQPage",
                "@id": f"{canonical_url}#faq",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": faq["question"],
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": faq["answer"],
                        },
                    }
                    for faq in CHEMICAL_REACTION_LAB_FAQS
                ],
            },
        ],
    }
    return render(
        request,
        "chemical_reaction_virtual_lab.html",
        {
            "page_title": guide["page_title"],
            "page_description": description,
            "canonical_url": canonical_url,
            "social_preview_url": SOCIAL_PREVIEW_URL,
            "social_preview_alt": SOCIAL_PREVIEW_ALT,
            "page_schema_json": json.dumps(page_schema),
            "faqs": CHEMICAL_REACTION_LAB_FAQS,
            "visit_source": CHEMICAL_REACTION_VIRTUAL_LAB_VISIT_SOURCE,
            "related_guides": related_guides_for(guide["canonical_key"]),
            "guide": guide,
        },
    )


def guide_library(request):
    canonical_url = PUBLIC_CANONICAL_URLS["guides"]
    description = (
        "Browse 25 free, no-account chemistry guides about virtual reaction "
        "labs, equations, bonding, combustion, oxidation, acids, gases, and "
        "precipitates."
    )
    guides = [
        guide
        for group in GUIDE_LIBRARY_GROUPS
        for guide in group["guides"]
    ]
    page_schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "OmniLab chemistry guides",
        "description": description,
        "url": canonical_url,
        "isPartOf": {
            "@type": "WebSite",
            "name": "OmniLab",
            "url": PUBLIC_CANONICAL_URLS["index"],
        },
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(guides),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": position,
                    "item": {
                        "@type": "LearningResource",
                        "name": guide["title"],
                        "url": PUBLIC_CANONICAL_URLS[
                            guide["canonical_key"]
                        ],
                    },
                }
                for position, guide in enumerate(guides, start=1)
            ],
        },
    }
    return render(
        request,
        "guide_library.html",
        {
            "page_title": (
                "Free chemistry reaction guides for students | OmniLab"
            ),
            "page_description": description,
            "canonical_url": canonical_url,
            "social_preview_url": SOCIAL_PREVIEW_URL,
            "social_preview_alt": SOCIAL_PREVIEW_ALT,
            "page_schema_json": json.dumps(page_schema),
            "guide_groups": GUIDE_LIBRARY_GROUPS,
        },
    )


def pricing(request):
    return render(
        request,
        "pricing.html",
        {"canonical_url": PUBLIC_CANONICAL_URLS["pricing"]},
    )


def faq(request):
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item["answer"],
                },
            }
            for item in PRODUCT_FAQS
        ],
    }
    return render(
        request,
        "faq.html",
        {
            "canonical_url": PUBLIC_CANONICAL_URLS["faq"],
            "faqs": PRODUCT_FAQS,
            "faq_schema_json": json.dumps(faq_schema),
        },
    )


def contact(request):
    sent = request.GET.get("sent") == "1"
    is_feedback = request.GET.get("source") == REACTION_FEEDBACK_SOURCE
    feedback_event = None
    if is_feedback:
        feedback_event = (
            REACTION_FEEDBACK_ACCEPTED_EVENT
            if sent
            else REACTION_FEEDBACK_VIEWED_EVENT
        )
    feedback_initial = (
        {
            "message": REACTION_FEEDBACK_PROMPTS,
            "source": REACTION_FEEDBACK_SOURCE,
        }
        if is_feedback
        else None
    )

    if request.method != "POST":
        return render(
            request,
            "contact.html",
            {
                "canonical_url": PUBLIC_CANONICAL_URLS["contact"],
                "form": ContactForm(initial=feedback_initial),
                "sent": sent,
                "is_feedback": is_feedback,
                "feedback_event": feedback_event,
            },
        )

    form = ContactForm(request.POST)
    is_feedback = request.POST.get("source") == REACTION_FEEDBACK_SOURCE
    if not form.is_valid():
        return render(
            request,
            "contact.html",
            {
                "canonical_url": PUBLIC_CANONICAL_URLS["contact"],
                "form": form,
                "sent": False,
                "is_feedback": is_feedback,
                "feedback_event": (
                    REACTION_FEEDBACK_VALIDATION_FAILED_EVENT
                    if is_feedback
                    else None
                ),
            },
        )

    # Quietly accept bot-filled honeypot submissions without forwarding them.
    if form.cleaned_data["website"]:
        return redirect("/contact/?sent=1")

    retry_after = contact_rate_limit(request)
    if retry_after is not None:
        form.add_error(
            None,
            "Too many messages were sent from this network. "
            "Please try again later.",
        )
        response = render(
            request,
            "contact.html",
            {
                "canonical_url": PUBLIC_CANONICAL_URLS["contact"],
                "form": form,
                "sent": False,
                "is_feedback": is_feedback,
                "feedback_event": (
                    REACTION_FEEDBACK_RATE_LIMITED_EVENT
                    if is_feedback
                    else None
                ),
            },
            status=429,
        )
        response["Retry-After"] = str(retry_after)
        return response

    source = form.cleaned_data["source"]
    is_feedback = source == REACTION_FEEDBACK_SOURCE
    if is_feedback:
        subject = (
            "Student session interest"
            if form.cleaned_data["session_interest"]
            else "Learner feedback"
        )
    else:
        subject = form.cleaned_data["subject"] or "New website message"
    submitted_subject = (
        "" if is_feedback else form.cleaned_data["subject"]
    )
    body = "\n".join(
        [
            f"Name: {form.cleaned_data['name']}",
            f"Email: {form.cleaned_data['email']}",
            f"Subject: {submitted_subject or '(not provided)'}",
            *(
                [f"Source: {REACTION_FEEDBACK_LABEL}"]
                if is_feedback
                else []
            ),
            *(
                [
                    "Student session interest: "
                    + (
                        "Yes"
                        if form.cleaned_data["session_interest"]
                        else "No"
                    )
                ]
                if is_feedback
                else []
            ),
            "",
            "Message:",
            form.cleaned_data["message"],
        ]
    )
    message = EmailMessage(
        subject=f"OmniLab contact: {subject}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.OMNILAB_CONTACT_TO_EMAIL],
        reply_to=[form.cleaned_data["email"]],
    )

    try:
        validate_contact_email_configuration()
        delivered_messages = message.send(fail_silently=False)
        if delivered_messages != 1:
            raise ContactEmailDeliveryCountError
    except Exception as error:
        contact_logger.error(
            "contact_email_delivery_failed category=%s",
            get_contact_email_failure_category(error),
        )
        form.add_error(
            None,
            "Your message couldn't be sent right now. "
            "Please try again later.",
        )
        return render(
            request,
            "contact.html",
            {
                "canonical_url": PUBLIC_CANONICAL_URLS["contact"],
                "form": form,
                "sent": False,
                "is_feedback": is_feedback,
                "feedback_event": (
                    REACTION_FEEDBACK_DELIVERY_FAILED_EVENT
                    if is_feedback
                    else None
                ),
            },
        )

    if is_feedback:
        return redirect(
            f"/contact/?sent=1&source={REACTION_FEEDBACK_SOURCE}"
        )
    return redirect("/contact/?sent=1")


def privacy(request):
    return render(
        request,
        "privacy.html",
        {"canonical_url": PUBLIC_CANONICAL_URLS["privacy"]},
    )

def terms(request):
    return render(
        request,
        "terms.html",
        {"canonical_url": PUBLIC_CANONICAL_URLS["terms"]},
    )


def robots_txt(request):
    content = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /ai_insights/",
            f"Sitemap: {PRODUCTION_BASE_URL}/sitemap.xml",
            "",
        ]
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    urls = "".join(
        f"  <url><loc>{url}</loc></url>\n"
        for url in PUBLIC_CANONICAL_URLS.values()
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}"
        "</urlset>\n"
    )
    return HttpResponse(content, content_type="application/xml; charset=utf-8")

def ai_insights(request):
    if request.method == "POST":
        user_query = request.POST.get("query", "")
        selected_chemicals = parse_selected_chemicals(user_query)
        reaction = get_reaction(selected_chemicals)

        if reaction is None:
            return insufficient_input_response(
                "Choose two chemicals from a supported reaction pair, "
                "then try again."
            )

        rate_limit_response = reaction_rate_limit(request)
        if rate_limit_response is not None:
            return rate_limit_response

        data = validate_complete_reaction_response(
            reaction, selected_chemicals
        )
        if data is None:
            return reaction_retry_response()

        return JsonResponse({"status": "success", "data": data})

    return JsonResponse({"status": "error", "message": "Only POST requests are accepted."})
