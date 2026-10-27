# User study protocol (draft 2)

Status: draft by LDN for DAT's and FAO's review (task W6-D3-LDN-1). Items marked **[TBC]** need a decision or a check before the first session. Drafted with AI assistance (Claude); LDN is responsible for the final text.

Decisions this draft follows: issue #134 (DAT, 2026-10-27: option A, moderated sessions; FAO confirmed his laptop as host) and DAT's answers on #111 (UI version, logged fields, no screen recording).

Planned sessions: D18 (Mon 2026-11-02) and D19 (Tue 2026-11-03), in the evening (Vietnam time). The first confirmed participants are scheduled back to back on Tue 2026-11-03 from 22:30 (section 12).

## 1. Purpose and scope

Find out how a small group of readers experiences the system: whether they can use it without help, and how useful they find the answers and the follow-up suggestions. The analysis is descriptive only (ADR 0010, cut-list item 5). With 5-6 participants the study cannot support statistical claims, and the report must say so.

This study measures user experience. It does not measure retrieval quality or faithfulness; those are measured on the golden set (see `evaluation/PLAN.md`).

## 2. Participants

- Target: 5-6 people, **classmates of our current course only**. More people are invited than needed. Replies by 2026-10-29; at least 5 confirmed by D16 (2026-10-30, Gate W6).
- Preferred: people who sometimes read research papers. A computer-science or NLP background is **not** required; record each participant's background (section 7) so the report can say who took part.
- Not eligible as study participants: team members (DAT, FAO, LDN). They may act as pilot participants (section 9); pilot data is not part of the results.
- Record only an anonymous code (P01, P02, ...). Names and contact details stay outside the repository; contact details are used only for scheduling and are deleted after the sessions.
- If fewer than 5 people take part, report the real number and say so in the limitations. Do not fill the gap with invented or simulated participants.

## 3. Consent text

Read aloud at the start of each session, and sent in the invitation (short form).

> Thank you for helping. You will try a question-answering tool for research papers (computer science, language processing) for about 30 minutes. You will tell us what you want to ask, we will type it, and then you answer a short questionnaire.
>
> What we record: the questions you ask, the answers and follow-up suggestions you see, your ratings, the questionnaire answers and the observer's notes. The system keeps these in two log files (`traces.jsonl` and `feedback.jsonl`) without your name or contact details; you are identified only by a code such as P03. **[TBC: exact field list of `traces.jsonl`, to be given by DAT when the W5-D4-DAT-1 PR is open.]** The session is **not** screen-recorded.
>
> The results are used only for the course report, as group summaries. We may quote short comments without your name. Contact details you gave us are used only to schedule the session and are deleted afterwards.
>
> This is a test of the tool, not of you. There are no right or wrong answers. Taking part is voluntary, you can skip any question, and you can stop at any time without giving a reason.

Ask: "Do you agree to take part under these conditions?" Note yes/no on the observer sheet. If no, thank the person and end the session. If the team ever wants to record the screen, that needs a separate consent and a change to this text first.

## 4. Setup (option A: moderated sessions)

Participants never open the system themselves. The system runs on one host machine (FAO's laptop, as decided on #134). The participant watches the shared screen (online, or in person on the host machine where possible) and tells the operator what to ask.

Roles: **[TBC: who is operator (types what the participant says) and who is observer (fills the sheet); proposed: FAO operates the host laptop, LDN observes. Both are in the call.]**

Checklist, run 15 minutes before the first session of each day:

- FAO starts the Kaggle LLM session about 10 minutes before each block of sessions and stops it after the block (to save GPU quota). The tunnel URL stays only in FAO's local `.env`; it is never written in the repository, in issues or in chat.
- Qdrant, backend and frontend are running on the host laptop; run the snapshot check of `evaluation/SNAPSHOT.md` (same index id, 121,926 points) and one test question that returns an answer with sources.
- UI version: tag `v0.6-rc` (DAT, #111). **[TBC: the tag does not exist yet (only `v0.4-mvp` and `data-2026-10-17`); confirm that DAT creates it by the freeze on D16, and which UI it contains, old UI or #102.]**
- The laptop is plugged in with sleep turned off; free disk space before D18 (FAO).
- Note the git commit or tag, the index snapshot id and the model name (from `evaluation/SNAPSHOT.md`) on the observer sheet.
- Observer sheet and questionnaire are ready (sections 6 and 7). Close other windows on the shared screen and turn off notifications.

### If the LLM tunnel drops during a session

Rule from DAT (#134): start a new Kaggle session, finish or reschedule that participant, and log the incident with the time and the trace id (observer sheet, section 6). Tell the participant it is a technical problem and not their fault. If the session cannot be finished, it is rescheduled; partial data from it is kept but marked as incomplete.

## 5. Session script (about 30 minutes)

| Step | Time | What happens |
|---|---|---|
| 1. Welcome and consent | 2 min | Read the consent text (section 3). Record the answer. |
| 2. Warm-up | 2 min | The participant says one question; the operator types exactly those words. Nobody explains the interface. |
| 3. Task A | 12-15 min | Explore a topic (see below). |
| 4. Task B (optional) | 3 min | Ask one question the system should not be able to answer. |
| 5. Questionnaire | 5 min | Section 7, read aloud; the observer records the answers. |
| 6. Close | 1 min | Thank the participant; ask if anything was unclear. |

The operator types what the participant dictates, without correcting or improving it, and scrolls or clicks (for example a follow-up suggestion or a source) only when the participant asks. If the participant is on the host machine in person, they may type themselves.

### Task A: explore a topic

Say: "Choose one of these topics, or one of your own from computer science or language processing. Learn what you can about it using the tool. Ask at least 5 questions, and use the follow-up suggestions or ask a follow-up question at least twice."

Example topics (adjust to what the corpus covers): evaluation of machine translation; retrieval-augmented generation; hallucination in large language models.

The observer may say only: "Please say out loud what you are thinking" and "What did you expect to happen?" The observer does not suggest what to ask or click.

### Task B (optional): a question outside the system's scope

Say: "Now ask the tool something you think it cannot know, for example about a recent event or another field." Observe how the system refuses or fails and whether the message is understandable.

## 6. Observer sheet (one per participant)

Fill in during the session.

- Participant code, date, slot (start time), observer, operator, online or in person.
- Consent given (yes/no).
- Commit or tag, index snapshot, model, UI version.
- For each question: time asked, the question text, seconds until the answer appeared, did the participant ask to read the sources (yes/no), did they use a follow-up (clicked / asked), any error or confusion.
- Moments of hesitation, requests for help, requests the operator could not carry out.
- System failures and incidents: error text, time, trace id, what happened next (for a tunnel drop: time of the drop, time the new Kaggle session was ready, and whether the session was finished or rescheduled).
- Total task time.

## 7. Questionnaire

Ask after the tasks, read aloud. Scale 1-5 (1 = not at all useful, 3 = somewhat useful, 5 = very useful).

Background (once):

1. How often do you read research papers? (never / a few times a year / monthly / weekly or more)
2. Your field of study. (free text)

Ratings:

3. Overall, how useful were the answers for what you wanted to learn? (1-5)
4. How useful were the follow-up suggestions? (1-5)
5. How easy was the tool to use? (1-5) Note that the participant was guiding an operator, not using the interface alone (section 11).

Open questions:

6. What was confusing or frustrating?
7. What was missing, or what would you change first?
8. Did you trust the sources shown with the answers? Why or why not?

In-page rating buttons (W6-D2-LDN-1): with moderated sessions the participant asks the operator to click them. **[TBC: until `POST /feedback` works, use only the questionnaire.]**

## 8. Data handling

- Raw sheets, the contact list and the `traces.jsonl` and `feedback.jsonl` of the session days (they contain the question texts) are stored in a private location, not in the repository. **[TBC: where; proposed: a private folder of LDN, copied from FAO's laptop after each day.]**
- The repository gets only anonymised summaries (codes, counts, ratings, short quotes without names).
- Delete the contact list after the sessions.

## 9. Pilot run (W6-D4-LDN-1, D16)

- One teammate follows sections 4-7 exactly, as if in the study, including the Kaggle start routine and the screen sharing.
- Record the real duration of each step, the unclear instructions, how long the Kaggle session takes to be ready, and any system problems.
- Update this protocol after the pilot.
- Pilot data is never included in the results. The report names it only as a pilot of the procedure.

## 10. Analysis (descriptive)

- Number of participants and their backgrounds (counts, no names).
- For questions 3-5: the individual ratings and the median. No significance tests.
- Task time and number of questions per participant; number of follow-up uses; number of errors and incidents observed (including tunnel drops and incomplete sessions).
- Open comments: group by theme (for example "unclear sources", "slow", "wrong answer"); report counts per theme and a few short quotes.

## 11. Limitations to state in the report

- Very small sample (5-6), recruited from classmates of one course; not representative of all researchers, and the group has a similar background.
- Participants may not know the topic well enough to judge whether an answer is correct; the ratings measure perceived usefulness, not correctness.
- Sessions were moderated: the participant dictated and an operator typed, so ease of use (question 5) does not measure unaided use of the interface.
- The system ran on one host laptop with a Kaggle-hosted LLM behind a temporary tunnel; response time may differ from a production setup, and incidents (tunnel drops) may have affected some sessions.
- Sessions were held late in the evening, which may affect attention.
- The observer and operator were team members, which may bias comments.

## 12. Schedule and participants (no names)

- Invitations sent 2026-10-27; replies until 2026-10-29; Gate W6 on D16 (2026-10-30).
- Tue 2026-11-03: sessions back to back from 22:30 (22:30, 23:15, and 00:00 if there is a third participant). Further slots: Mon 2026-11-02 and Tue 2026-11-03 at 21:00, 21:45 and 22:30 (Vietnam time).
- Slots are confirmed by FAO on #134. Names and contact details are kept outside the repository (section 8).
