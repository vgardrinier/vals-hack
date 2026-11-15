# next iteration: a messy monday morning

## the goal

we want a benchmark where the best agents really struggle on the stuff nobody writes down at a company.
right now Fable is at 71% and the GPTs at 53 to 59%. that's too easy, because our world is too clean:
one habit, one column, 5 invoices, 90 rows. real finance work doesn't look like that.

target for this round: Fable and the top GPT models under 30% mean score, without cheating.
"without cheating" means a careful new hire who reads the recent history can still get every answer
right, and we never hide the answer or exploit a model quirk. the world just gets messier and more real.

## the world

same company (Redwood Inference), same finance team, but it should feel like a real monday:

- **a real history**: three quarterly tracker files (Q2, Q3, Q4 2026), around 300 invoices total,
  with the older quarters archived in `finance/archive/`. new rows go in the Q4 file
- **use the Redwood docs for real**: keep the ~2,100 emails, slack threads and tickets, and also mix in
  the Redwood docs that talk about invoices, billing and vendors (there are hundreds), as long as they
  don't contradict our habits. that's realistic noise a finance person would actually wade through
- **a stale handbook**: an official-looking AP policy in `company/drive/` from early 2026, saying things
  like "flag invoices over $5,000 for review". the team moved on since, and only the tracker shows it.
  every company has docs nobody updated. models tend to trust written text over what people actually
  do, and that's exactly what we want to test
- **15 new invoices** instead of 5, a realistic morning inbox

## the habits (several at once, each with its own quiet change)

1. **REVIEW cutoff**: moved from $5,000 to $10,000 in October
2. **who reviews**: since October, Infra invoices get "REVIEW: Tomasz", everything else "REVIEW: Mireille"
3. **contract supplier**: Halverson invoices stopped getting REVIEW after their contract in November
   (the contract email is in the inbox history, no rule written)
4. **cost center**: Wrenfield Creative got reclassified from Marketing to G&A in October
5. a bit of **human mess**: two big invoices before October where someone forgot REVIEW, and a couple of
   typos in vendor names, the way real trackers look

every new invoice touches at least one changed habit, so there's no coasting.

## the knobs

- **examples after the change**: 1, 2 or 3 rows showing each new habit (7 was mostly solved last time)
- **handbook**: with the stale handbook, or without it. if models do worse when we hand them the
  official policy, that's a headline

that's 3 x 2 = 6 versions.

## grading

per invoice: logged once, right REVIEW note (who / none), right cost center. past rows untouched.
- **Mean Score**: share of invoice decisions right, averaged over tries
- **Pass@1**: share of tries with everything right
deterministic, no model grades another. every task ships a grader test with the obvious wrong answers
(old habit, ignoring dates, following the handbook, flagging everything).

## fairness, the way we agreed

no separate fairness runs. a version is fair if at least one model solves it sometimes. if a version gets
0 from everyone, we read the runs before we trust it, like we did with "habit stopped".
solution scores 1 and an empty answer scores 0 for every task, checked with Valkyrie's own solution runs.

## how we run it

- same shared agent for every model (`agents/plain-agent`): same prompt, one terminal tool, effort high
- models: Fable 5.2, Opus 5.5, Sonnet 5.5, GPT-6.1 Sol, GPT-6 Astra
- **pilot first**: 2 tries per version, all 5 models. if Fable's mean score is still above 50%, we look at
  which habit it finds easy and tighten that one before the full run
- **full run**: 5 tries per version, one run per model holding every try, max 10 runs at once team-wide
- fetch results 20 at a time so collecting doesn't take forever
- don't trim the world to save upload time. if uploads are slow, live with it

## where it runs

all of it in the cloud, so it keeps going while my laptop is closed. everything gets pushed to GitHub as
it goes: the generator, the tasks' build script, the results, the page.

## what i want back

- the leaderboard page updated with the new main benchmark (old results under "earlier")
- the numbers per model, per habit, per number of examples, with and without the handbook
- how they failed, from reading the runs
- anything that looked broken and what got fixed
- `docs/STATUS.md` updated so Yacine can catch up
