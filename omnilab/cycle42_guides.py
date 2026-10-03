"""Chemistry guide content and prepared examples.

Reuse the observation guide template and exact deterministic reaction content.
Discovery and reciprocal links use the shared registries in views.
"""

from .reactions import get_reaction

BOUNDARY = (
    "Results are educational predictions, not verified simulations, "
    "and never replace supervision."
)

_GUIDE_CONTENT = [{'key': 'sulfuric-acid-potassium-hydroxide',
  'slug': 'sulfuric-acid-and-potassium-hydroxide-reaction',
  'title': 'What happens when sulfuric acid reacts with potassium hydroxide?',
  'page_title': 'Sulfuric acid and potassium hydroxide reaction | OmniLab',
  'description': 'Study sulfuric acid and potassium hydroxide neutralization, the '
                 'balanced equation, its two-to-one ratio, and the limits of a prepared '
                 'browser example.',
  'pair': [('Sulfuric acid', 'H2SO4'), ('Potassium hydroxide', 'KOH')],
  'direct_answer': 'Complete neutralization forms potassium sulfate and water. One mole '
                   'of sulfuric acid needs two moles of potassium hydroxide.',
  'opening_boundary': 'This equation assumes complete neutralization. OmniLab does not '
                      'measure amounts, temperature, or the final pH.',
  'student_job': 'Explain the coefficient 2 before KOH, then distinguish a balanced '
                 'equation from a measured endpoint.',
  'study_intro': 'Count atoms first. Then compare complete neutralization with a mixture '
                 'that still contains acid or alkali.',
  'observation_title': 'A clear solution can still undergo a reaction',
  'observation': 'Dilute solutions can stay colorless while neutralization releases '
                 'heat. No gas or precipitate belongs in this equation. OmniLab gives a '
                 'text result and does not display a measured temperature change.',
  'observation_class': 'observation-clear',
  'observation_label': 'Text-only neutralization result',
  'study_steps': [{'title': 'Account for both acidic protons',
                   'body': 'Sulfuric acid can supply two acidic protons per molecule. '
                           'Complete neutralization therefore consumes two hydroxide '
                           'ions.'},
                  {'title': 'Check the complete equation',
                   'body': 'Each side contains two potassium atoms, one sulfur atom, '
                           'four hydrogen atoms, and six oxygen atoms. Coefficients '
                           'change amounts, not chemical formulas.'},
                  {'title': 'Keep amount and pH separate',
                   'body': 'Equal volumes need not contain the required mole ratio. The '
                           'final pH depends on amounts and solution equilibria; OmniLab '
                           'calculates neither.'}],
  'common_questions': [{'question': 'Why is there a 2 before KOH?',
                        'answer': 'Each KOH supplies one hydroxide ion. Two are needed '
                                  'for complete neutralization of one H2SO4.'},
                       {'question': 'Does equal volume mean complete neutralization?',
                        'answer': 'No. Moles depend on both concentration and volume. '
                                  'Equal volumes only satisfy the equation with the '
                                  'appropriate concentration ratio.'},
                       {'question': 'Can potassium hydrogen sulfate form instead?',
                        'answer': 'Partial neutralization can be represented using '
                                  'KHSO4. OmniLab returns only the '
                                  'complete-neutralization equation and does not track '
                                  'sulfate speciation.'},
                       {'question': 'Does the reaction produce bubbles or a solid?',
                        'answer': 'Neither is a product of this dilute aqueous equation. '
                                  'Dissolved potassium sulfate remains in solution, and '
                                  'heat release need not cause a visible change.'}],
  'boundary': 'OmniLab returns the complete-neutralization equation without calculating '
              'reagent amounts, excess acid, excess alkali, heat release, or pH.',
},
 {'key': 'aluminium-chloride-sodium-hydroxide',
  'slug': 'aluminium-chloride-and-sodium-hydroxide-reaction',
  'title': 'What happens when aluminium chloride reacts with sodium hydroxide?',
  'page_title': 'Aluminium chloride and sodium hydroxide reaction | OmniLab',
  'description': 'Study the white aluminium hydroxide precipitate, balance its ionic '
                 'equation, and learn why excess sodium hydroxide differs from the fixed '
                 'browser result.',
  'pair': [('Aluminum chloride', 'AlCl3'), ('Sodium hydroxide', 'NaOH')],
  'direct_answer': 'Aqueous aluminium chloride and sodium hydroxide can form a white '
                   'aluminium hydroxide precipitate. Excess hydroxide can dissolve that '
                   'solid.',
  'opening_boundary': 'OmniLab shows the precipitation stage only. Adding more sodium '
                      'hydroxide in the browser does not model redissolving the solid.',
  'student_job': 'Separate the first white precipitate from its later behavior in excess '
                 'alkali.',
  'observation_title': 'A white solid, with an important excess-alkali limit',
  'observation': 'The initial precipitate can look white and gelatinous. In a real '
                 'solution, sufficient excess hydroxide can dissolve it. OmniLab keeps a '
                 'simplified white precipitate cue and does not model that second stage.',
  'observation_class': 'observation-cloudy',
  'observation_label': 'White aluminium hydroxide',
  'net_ionic_equation': 'Al3+(aq) + 3OH-(aq) -> Al(OH)3(s)',
  'ionic_explanation': 'Aluminium ions combine with hydroxide ions to form the solid. '
                       'Hydration details are omitted from this classroom ionic '
                       'equation.',
  'spectator_ions': 'Na+(aq) and Cl-(aq) remain dissolved during the precipitation '
                    'stage.',
  'study_steps': [{'title': 'Balance the ion charges',
                   'body': 'One Al3+ ion has charge +3. Three OH- ions supply charge -3, '
                           'giving a neutral solid.'},
                  {'title': 'Keep spectators in solution',
                   'body': 'Sodium and chloride ions appear on both sides of the '
                           'complete ionic equation. Cancel them to show the change that '
                           'forms the solid.'},
                  {'title': 'Distinguish the second stage',
                   'body': 'Aluminium hydroxide can react with excess hydroxide to form '
                           'dissolved [Al(OH)4]- ions. That stage is outside this '
                           'prepared result.'}],
  'common_questions': [{'question': 'What is the white precipitate?',
                        'answer': 'It is aluminium hydroxide, Al(OH)3. The chloride and '
                                  'sodium ions stay dissolved during its formation.'},
                       {'question': 'What does amphoteric mean here?',
                        'answer': 'Aluminium hydroxide reacts with both acids and bases. '
                                  'Its dissolution in excess hydroxide demonstrates its '
                                  'reaction with a base.'},
                       {'question': 'What equation describes excess hydroxide?',
                        'answer': 'A common aqueous summary is Al(OH)3(s) + OH-(aq) -> '
                                  '[Al(OH)4]-(aq). This is a separate stage, not '
                                  "OmniLab's returned equation."},
                       {'question': 'Will the browser solid disappear in excess alkali?',
                        'answer': 'No. The model recognizes the selected pair, but it '
                                  'does not calculate amounts or complex-ion '
                                  'equilibria.'}],
  'boundary': 'OmniLab predicts the initial precipitate without calculating '
              'concentration, pH, precipitation yield, or dissolution in excess '
              'hydroxide. Aluminium is also spelled aluminum.',
},
 {'key': 'magnesium-sulfate-sodium-hydroxide',
  'slug': 'magnesium-sulfate-and-sodium-hydroxide-reaction',
  'title': 'What happens when magnesium sulfate reacts with sodium hydroxide?',
  'page_title': 'Magnesium sulfate and sodium hydroxide reaction | OmniLab',
  'description': 'Study magnesium sulfate and sodium hydroxide, identify the white '
                 'precipitate, balance the ionic equation, and open a prepared '
                 'educational example.',
  'pair': [('Magnesium sulfate', 'MgSO4'), ('Sodium hydroxide', 'NaOH')],
  'direct_answer': 'Aqueous magnesium sulfate and sodium hydroxide form a white '
                   'magnesium hydroxide precipitate. Sodium sulfate stays dissolved.',
  'opening_boundary': 'This is a simplified precipitation result. OmniLab does not '
                      'calculate concentration thresholds or how much solid forms.',
  'student_job': 'Identify the insoluble product and explain why two hydroxide ions are '
                 'needed per magnesium ion.',
  'observation_title': 'White magnesium hydroxide clouds the mixture',
  'observation': 'A suspended white solid can make the solution cloudy when '
                 'precipitation occurs. The virtual beaker shows a white precipitate '
                 'cue. It does not reproduce particle size, settling time, or the amount '
                 'of solid.',
  'observation_class': 'observation-cloudy',
  'observation_label': 'White magnesium hydroxide',
  'net_ionic_equation': 'Mg2+(aq) + 2OH-(aq) -> Mg(OH)2(s)',
  'ionic_explanation': 'Magnesium ions and hydroxide ions leave the dissolved state to '
                       'form a sparingly soluble solid. The net equation omits dissolved '
                       'spectator ions.',
  'spectator_ions': 'Na+(aq) and SO4^2-(aq) remain dissolved.',
  'study_steps': [{'title': 'Identify the solid',
                   'body': 'The (s) symbol marks Mg(OH)2 as the precipitate. The (aq) '
                           'symbol marks sodium sulfate as dissolved.'},
                  {'title': 'Balance charge and atoms',
                   'body': 'One Mg2+ ion needs two OH- ions. Their combined charge is '
                           'zero, matching neutral Mg(OH)2.'},
                  {'title': 'Remove the spectator ions',
                   'body': 'Sodium and sulfate remain aqueous on both sides of the '
                           'complete ionic equation. They are absent from the net ionic '
                           'equation.'}],
  'common_questions': [{'question': 'Which product is the precipitate?',
                        'answer': 'Magnesium hydroxide, Mg(OH)2, is the white solid. '
                                  'Sodium sulfate remains dissolved in this dilute '
                                  'aqueous model.'},
                       {'question': 'Why does Mg(OH)2 need brackets?',
                        'answer': 'The subscript 2 applies to the whole hydroxide group. '
                                  'Each formula unit contains one magnesium, two oxygen, '
                                  'and two hydrogen atoms.'},
                       {'question': 'Does it dissolve in excess sodium hydroxide?',
                        'answer': 'In standard qualitative tests, magnesium hydroxide '
                                  'remains insoluble in excess sodium hydroxide. '
                                  'Aluminium hydroxide behaves differently.'},
                       {'question': 'Does every mixture produce the same amount of '
                                    'solid?',
                        'answer': 'No. Concentrations and solubility equilibria affect '
                                  'whether precipitation occurs and how much forms. '
                                  'OmniLab does not calculate those quantities.'}],
  'boundary': 'OmniLab predicts a simplified white precipitate without calculating '
              'solubility equilibrium, pH, solid mass, particle size, or settling time.',
}]

CYCLE42_GUIDES = {}
CYCLE42_DEMOS = {}
for content in _GUIDE_CONTENT:
    key = content["key"]
    canonical_key = key.replace("-", "_")
    reaction = get_reaction([formula for _name, formula in content["pair"]])
    CYCLE42_GUIDES[key] = {
        **content,
        "route_name": f"guide_{canonical_key}",
        "canonical_key": canonical_key,
        "visit_source": "guide_virtual_lab",
        "demo_route_name": f"demo_{canonical_key}",
        "reading_time": "4 minute read",
        "reactants": [{"name": name, "formula": formula} for name, formula in content["pair"]],
        "setup_summary": "The supported pair is prepared in a beaker. Analysis waits for you.",
        "cta_label": "Open the prepared example",
        "equation": reaction["equation"],
        "explanation": reaction["explanation"],
        "safety": reaction["safety"].split(" | "),
        "boundary": content["boundary"] + " " + BOUNDARY,
    }
    CYCLE42_DEMOS[key] = {
        "id": key,
        "version": "v1",
        "selectedChemicals": [formula for _name, formula in content["pair"]],
        "vessel": "beaker",
        "liquidColor": "#d7edf7",
        "mixture_label": " + ".join(formula for _name, formula in content["pair"]),
        "title": "Prepared chemistry example, ready to analyze",
        "page_title": content["page_title"],
        "page_description": "Open the supported pair, then select Analyze for an educational prediction.",
    }
