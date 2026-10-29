# OmniLab student-session protocol

Protocol version: 1.1

Use this protocol for each outside-student session. Its purpose is to learn what
the student is trying to accomplish and how OmniLab affects that progress. It
does not test the student's chemistry knowledge or teach them how to use the
product.

Keep the protocol version fixed across comparable sessions. If a safety issue
or product failure requires a change, stop the session, record what happened,
and version the protocol before using it again.

## Before the session

- Confirm in writing that the participant is a current chemistry student and
  has agreed to the session date, time, and timezone.
- Assign an anonymous participant label. Do not put the student's name, email,
  school, or other identifying details in the research note.
- Use a fresh browser state with no saved reaction result. Confirm that the
  prepared Sodium and Chlorine demo opens with both inputs selected and Analyze
  under the student's control.
- Confirm immediately before the session that the demo can return its supported
  result. Do not run the session against a broken or unavailable lab.
- Prepare a written note with the four evidence fields in this protocol.

Written notes are allowed only after the participant agrees. Do not make an
audio, video, or screen recording unless the founder has approved that specific
recording and the participant has given informed consent before it begins. The
default session is unrecorded.

## Opening script

Say:

> Thanks for trying OmniLab. I am testing the product, not your chemistry
> knowledge. Please use a real chemistry question you have had recently and say
> what you are thinking as you work. I will take written notes, but I will not
> record this session. OmniLab gives educational predictions that may be
> incomplete or wrong, so it does not replace trusted references, instructor
> guidance, or physical-lab safety rules. Please do not share personal or
> confidential information. You can stop at any time.

Ask whether the student agrees to continue. Stop immediately if they do not.

## Neutral questions

Keep OmniLab out of view for the first three questions. Ask each question as
written, then allow silence. A neutral follow-up such as "Can you say more about
that?" is allowed. Do not supply an answer, suggest a chemistry concept, or turn
the student's answer into a cleaner version.

1. Think of a recent reaction question you genuinely wanted answered. What was
   the question, and what was happening when it came up?
2. What were you trying to understand or get done? What would a useful answer
   have let you do next?
3. How did you try to answer it then, or how would you normally answer it?

Classify the original question as a supported match, unsupported, or unclear
using the reference below. Do this silently. The classification is researcher
coding, not participant language, and it must remain separate from the four
evidence fields.

Then say:

> I have recorded your original question. OmniLab currently supports 34 defined
> reaction pairs. We will use the same prepared Sodium and Chlorine setup used
> in every session. Please use it as you normally would, keep your original
> question in mind, and say what you are thinking. You can stop at any time.

Open the prepared demo:
`https://omnilab-bk8q.onrender.com/demo/sodium-chlorine/?source=student_invite`

Let the student decide what to do. If they become silent, ask only one of these
neutral prompts:

- What are you looking for right now?
- What, if anything, is unclear?
- What would you do next?

After the student completes or stops the journey, ask:

4. What, if anything, did this help you understand or do?
5. What would you check before acting on this result, and what would you do
   next?

## No-coaching boundary

The researcher may repeat a question, acknowledge an answer, or use one of the
neutral prompts above. The researcher must not:

- point out a control, select a chemical, choose apparatus, click Analyze, or
  complete another product action for the student;
- explain the reaction, correct the student's chemistry, interpret the result,
  or suggest what the student should conclude;
- steer the student toward completion, a favorable opinion, or one of the
  supported pairs;
- replace the student's words with a summary that adds intent, confidence, or
  understanding they did not express.

If the student is blocked, ask "What would you do next?" once. Record the
answer and the visible behavior. Do not rescue the journey.

## Completion and stopping rules

Mark the **product journey completed** only when the student independently
chooses Analyze and the visible result contains an equation, a non-empty
explanation, and exactly three safety rules. Record the analytics completion
event separately as `verified`, `not observed`, or `unknown`; do not infer it
from the visible result.

Mark the **session complete** when consent was obtained, all four evidence
fields were filled with observed information or `unknown`, and the product
journey was classified as completed or stopped. A stopped journey is still a
valid session outcome when the reason and last visible action are recorded.

Stop the journey when any of these occurs:

- the student declines or withdraws consent, asks to stop, or appears
  uncomfortable;
- the student starts to share personal, confidential, or unsafe information;
- the lab is unavailable, produces an unusable result, or cannot continue
  without researcher action;
- the student says they would stop or move to another resource after the single
  neutral blocked prompt.

Do not label a stopped journey as completed. Do not retry, substitute another
reaction, or continue the interview to manufacture a complete result.

## Evidence note

Preserve short participant phrases exactly where practical. Put quotation marks
only around words the student actually said. Record visible actions in plain
language and keep interpretation out of the note. If something was not observed
or verified, write `unknown`; never infer it from other answers or from the
researcher's chemistry knowledge.

### Learner situation

Record the student's recent chemistry question and what was happening when it
arose, in their words. If the situation was not described, write `unknown`.

### Desired progress

Record what the student wanted to understand, decide, complete, or prepare for,
and what they wanted to do next. If either part was not stated, write `unknown`.

### Observed behavior

Record only visible actions and spoken reactions during the standardized
journey. Include whether the student chose Analyze, pauses, confusion, recovery,
the last visible action, and any decision to stop. Do not diagnose why an action
happened unless the student said why.

### Completion outcome

Record `product journey completed` or `product journey stopped`, the visible
result or stopping reason, and the separately verified analytics-event status.
Write `unknown` for any part that was not observed or verified.

## Supported-reaction reference

A pair is supported in either input order. Match the student's original
question only when both substances are clear.

- Sodium + Chlorine
- Hydrogen + Oxygen
- Carbon + Oxygen
- Hydrochloric acid + Sodium hydroxide
- Iron + Hydrochloric acid
- Copper + Oxygen
- Iron + Oxygen
- Carbon dioxide + Sodium hydroxide
- Hydrogen + Chlorine
- Sodium + Water
- Carbon dioxide + Water
- Sodium chloride + Water
- Ammonia + Nitric acid
- Sulfuric acid + Potassium hydroxide
- Acetic acid + Sodium bicarbonate
- Calcium hydroxide + Carbon dioxide
- Copper(II) sulfate + Potassium hydroxide
- Silver nitrate + Sodium chloride
- Silver nitrate + Potassium iodide
- Potassium permanganate + Hydrogen peroxide
- Sodium carbonate + Hydrochloric acid
- Barium chloride + Sodium carbonate
- Zinc + Hydrochloric acid
- Hydrofluoric acid + Sodium hydroxide
- Hydrobromic acid + Sodium hydroxide
- Hydroiodic acid + Sodium hydroxide
- Silver chloride + Ammonia
- Aluminium chloride + Sodium hydroxide
- Magnesium sulfate + Sodium hydroxide
- Mercury(II) chloride + Sodium hydroxide
- Carbon monoxide + Oxygen
- Nitrogen dioxide + Water
- Hydrogen sulfide + Sodium hydroxide
- Ozone + Hydrogen peroxide

An original question with a different clear pair is `unsupported`. If one or
both substances cannot be identified from what the student said, mark it
`unclear`. Neither classification is a student-research finding by itself.

## Close and cleanup

Repeat the educational-prediction boundary, thank the student, and choose Reset.
Confirm that the result, selected inputs, liquid, and visible effect are gone.
Do not change product guide copy or claim a repeated learner job from one
session. A job is repeated only when at least three outside students
independently describe materially the same situation, desired progress, and
next action.
