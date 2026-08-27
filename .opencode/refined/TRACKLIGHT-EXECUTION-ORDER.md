# TRACKLIGHT Execution Order

**Purpose**: This is the running order for the TRACKLIGHT epic, written to be followed without reference to the refinement session that produced it. Each step names its gate, why it sits where it does, and what unblocks when it lands.

---

## Step 1: RIG-calibration-session — Do first. Gates the most.

See: [`RIG-calibration-session.md`](./RIG-calibration-session.md)

One physical session at the rig. Covers the 5 original calibration items (visualizer, bar sweep, LM70S pan/tilt, fixture-to-position mapping, rekordbox panel vocabulary) plus E2 and E3.

**E2 (The shadow test)** asks two critical questions:
1. Does repointing a track's `content.macro_pattern_id` to a different bank actually reach playback, or does the `phrase_data` layer shadow the change?
2. If it shadows, does running rekordbox's analysis on the track rebuild the `phrase_data` rows from the new bank's `macro_assign`?

**E3 (The direct phrase-write test)** asks whether an externally written `phrase_data.macro_id` fires at all. That is the entire technical premise of Stage 3.

**Build note on E2**: E2 needs a throwaway script that reconstructs `phrase_data` from a track's ANLZ analysis. Build it on the helpers in `src/rbxlight/experiments/e1e_phrase_phase_mapping.py` rather than waiting for S1.1 to land. This is precisely why the probe scripts were committed rather than deleted immediately.

**E2 has three possible verdicts**, each producing a different shape for S1.3:
- ☐ Bank repoint reaches playback directly (best case; Stage 1 writes ~7,500 `content` rows and is done)
- ☐ Shadowed, but re-analysis rebuilds `phrase_data` from the new bank (workable; Stage 1 writes the bank, then DJ re-analyses)
- ☐ Shadowed, and re-analysis does not rebuild (Stage 1 must write ~41,742 `phrase_data` rows directly; design changes substantially)

Because the verdict determines S1.3's apply path, **do not build S1.3's apply logic ahead of this result**.

**Logistics**: Requires rekordbox fully quit at two points in the session; budget one full quit/relaunch cycle mid-session.

---

## Step 2: S1.1 (Library reader) — Start in parallel with step 1. No gate.

See: [`TRACKLIGHT-S1.1-library-reader.md`](./TRACKLIGHT-S1.1-library-reader.md)

Read-only module. Depends on nothing from the rig — the right thing to build while a rig slot is being found.

On landing:
- Deletes the six E-series probe scripts from `src/rbxlight/experiments/` and the `experiments` extra from `pyproject.toml`
- Reports from `docs/experiments/` stay permanently (probes are disposable, findings are not)

**Do not delete the probes before step 1 is complete** — E2 depends on `e1e_phrase_phase_mapping.py`.

---

## Step 3, 4, 5: S1.2, S1.3, S1.4 — Strictly sequential.

See: [`TRACKLIGHT-S1.2-assignment-rules.md`](./TRACKLIGHT-S1.2-assignment-rules.md), [`TRACKLIGHT-S1.3-bank-cli.md`](./TRACKLIGHT-S1.3-bank-cli.md), [`TRACKLIGHT-S1.4-assignment-ledger.md`](./TRACKLIGHT-S1.4-assignment-ledger.md)

### Step 3: S1.2 (Assignment rules)
YAML rules mapper from track metadata (genre, My Tags, BPM) to bank and energy choices.

### Step 4: S1.3 (Bank CLI)
`bank plan` / `bank apply` / `bank revert` commands. **`bank plan` (dry-run) may be built and run before E2 returns.** Only `bank apply` waits on the E2 verdict.

### Step 5: S1.4 (Ledger)
Durable record of assignments for revert and audit.

---

### ⚠️ Reality Check — before this block

**E1f measured the addressable set at 2,081 of 7,615 tracks (27.3%)**. Stage 1 can never touch the remainder — those tracks are lit but permanently unidentifiable. 

**The COOL over-assignment is 38.2%** in the recovered population (fingerprint-identified + ID-resolved), not the 80.4% seen in the ID-resolvable slice that earlier figures were measured on. The work is still worth doing, but it is a smaller and less dramatic win than the epic's original framing implied.

---

## Step 6: S2.1 (Role-based YAML macro recipes) — Not yet refined. Can run alongside everything above.

See: Epic story index (not yet a refined story file)

Macro content authoring. Not gated by E2 in any way.

**If rig time is hard to schedule, this is the work to do instead of waiting.** Everything in Stage 2 and Stage 3 is starved without it — you cannot assign diverse macros that have not been authored.

**Strongest motivating example**: the perimeter sweep gesture (documented in `.opencode/skills/physical-rig-profile/SKILL.md`) — a path that hands off between fixture roles in order. It stresses the recipe vocabulary far harder than any static look.

---

## Step 7: S2.2 (Bank takeover) — Gated on E2 and S2.1.

See: [`TRACKLIGHT-S2.2-bank-takeover.md`](./TRACKLIGHT-S2.2-bank-takeover.md)

Repoints `macro_assign` rows from factory macros to user macros. **The target bank×energy slot must be re-picked at build time against the live distribution**, because Stage 1 deliberately drains COOL and today's highest-impact target will have moved.

---

## Step 8: S2.3 (FullArcAI venue) — Gated on RIG-calibration-session only.

See: [`TRACKLIGHT-S2.3-fullarcai-venue.md`](./TRACKLIGHT-S2.3-fullarcai-venue.md)

Venue creation with non-mirrored bar-cell assignment, enabling independent per-leg motion. Orthogonal to all bank and macro work; can be slotted whenever there is capacity.

---

## Step 9: S3.1 (Per-track shows) — Not refinable until E3 returns and S2.1 has produced real macro variety.

See: [`TRACKLIGHT-S3.1-per-track-shows.md`](./TRACKLIGHT-S3.1-per-track-shows.md)

This is a placeholder, not a story. It will be replaced once:
- E3 returns a positive verdict (external phrase writes fire at playback)
- S2.1 has delivered a macro library with enough diversity
- The `phrase_num` vocabulary has been mapped musically

---

## If you only read this far

1. **Book the rig session.** It is the gate for everything.
2. **Build S1.1 while waiting** for rig availability. It is read-only and fast.
3. **Refine S2.1 as the work that never blocks.** Macro authoring can happen anytime.

**Contingency worth stating plainly**: If E2 returns "shadowed, and re-analysis does not rebuild", Stage 1 becomes a ~41,000-row `phrase_data` write instead of a ~2,000-row `content` write, and Stage 3 arrives far earlier than planned. **Do not over-invest in S1.3's apply path before that verdict lands.**
