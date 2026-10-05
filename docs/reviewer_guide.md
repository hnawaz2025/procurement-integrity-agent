# Reviewer guide (for non-technical users)

This tool helps you decide **where to look first**. It does not decide whether anyone did anything wrong. You do, following the normal integrity process.

## The three screens

**1. Portfolio screening.** Every contract is checked automatically for known warning signs. Contracts with the strongest signals and the highest value go to the top of the **lead queue**. Each row shows *why* it ranks, for example "bid rotation" or "hidden ownership link". Click **Investigate** to open the contract in the review screen.

**2. Agent review.** The AI assistant reads the document, checks the bidders against the company registry and past tenders, looks up relevant guidance, and lists **risk signals**. You can watch each step it takes in the middle column.

**3. Evals & scale.** This screen shows how well the system performed on test cases. Check it if you want to know how much to trust the results.

## Reading a risk signal
Each card shows:
- **Severity** (high, medium or low). This tells you how strongly the signal suggests a closer look is needed. It is not a verdict.
- **What was found**, in plain language.
- **Evidence**, which is one of:
  - the exact line from the document, highlighted in the "Evidence" view, or
  - a chain of links between companies, such as *Company A → shared director → shell company → shared address → Company B*.
- **Guidance**: click a KB chip to read the World Bank guidance the signal relates to.
- **Where it came from:**
  - a fixed rule
  - a pattern across past contracts
  - the assistant's own judgement
  - "baseline guarantee", meaning the system added the signal because the assistant did not address it

## What you should do
1. Read the evidence yourself. Does it say what the card claims?
2. Think about innocent explanations. Firms can share an address in a business centre. Thin local markets often have the same few bidders.
3. Use the **Reviewer questions** tab as a starting checklist.
4. Record a decision on each signal:
   - **Accept**: worth following up
   - **Reject**: not a concern, ideally with a note saying why
   - **Needs info**: you can't decide yet
5. Your decisions are saved permanently and help improve the system.

## Important limits
- A clean result does not mean a contract is clean. It means none of the known warning signs were found.
- "Confidence" describes how well-supported the analysis is: whether evidence and citations checked out. It is **not** the probability that fraud occurred.
- If the screen says **Offline · planner: scripted**, the AI assistant is off and only fixed rules ran. Qualitative issues, such as specifications written around one brand, will be missed.
- Never paste confidential documents into a system that hasn't been approved for that classification.
