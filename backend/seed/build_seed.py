"""Source for backend/seed/templates.json. Edit here, then run:

    python backend/seed/build_seed.py

Seeds are inserted only when their slug is missing, so office edits are never
overwritten. Every seed ships with needs_review=true: confirm the facts against the
source links, then save it in the Library to mark it reviewed.
"""
import json
from pathlib import Path

T = []


def add(slug, title, category, tags, summary, sms, body, sources):
    T.append({
        "slug": slug, "title": title, "category": category, "tags": tags,
        "summary": summary, "sms": sms, "body": body.strip(), "source_urls": sources,
        "needs_review": True, "last_reviewed": None,
    })


# ---------------------------------------------------------------- Privacy ----
add(
    "privacy-consent-pack", "Privacy & Consent Authorisation Pack", "other_casework",
    ["consent", "privacy", "authority", "authorisation", "signed", "form"],
    "Why we need written consent before contacting an agency, and how to return it.",
    "To help with your matter we need your signed privacy consent form - it lets the agency "
    "talk to our office. Please sign and return it by email or drop it into the office.",
    """
To help you with this, our office needs your written consent. Australian privacy law means
government agencies can't discuss your personal information with us — even to help you —
unless you've authorised it.

What to do:
1. Read the attached consent form. It lets our office contact the agency on your behalf about
   this matter only.
2. Sign and date it. If other adults are part of the same matter (for example, other applicants
   on a visa application), each of them needs to sign too.
3. Send it back by replying to this email with a photo or scan, or drop it into our office.

How we use your information: we only share it with the agency (or agencies) needed to help with
your matter, and only for that purpose. You can withdraw your consent at any time by letting us know.
""",
    ["https://www.oaic.gov.au/privacy/australian-privacy-principles"],
)

# ------------------------------------------------------ Services Australia ----
add(
    "mygov-link-centrelink", "Linking Centrelink to myGov", "services_australia",
    ["mygov", "my gov", "link", "linking", "linking code", "centrelink", "crn", "online account"],
    "Steps to link Centrelink to a myGov account, and who to call if it won't link.",
    "To link Centrelink to myGov: sign in at my.gov.au > Link a service > Centrelink, and have "
    "your CRN handy. Stuck? Call the myGov help desk on 13 23 07.",
    """
Here's how to link Centrelink to your myGov account:

1. Sign in at my.gov.au (or create an account if you don't have one yet).
2. Choose "Link a service", then "Centrelink".
3. Enter your Customer Reference Number (CRN) — it's on any Centrelink letter or card.
4. Either answer the identity questions, or enter a linking code if Centrelink has given you one.

If it won't link:
• For a linking code or help with your Centrelink record, call the Centrelink line for your
  payment (the number is on your letters).
• For problems with the myGov account itself (sign-in, codes, Digital ID), call the myGov help
  desk on 13 23 07.
""",
    ["https://my.gov.au/en/services/link-services", "https://www.servicesaustralia.gov.au/how-to-link-centrelink-to-mygov"],
)

add(
    "centrelink-review-of-decision", "Centrelink: asking for a review of a decision",
    "services_australia",
    ["review", "decision", "appeal", "authorised review officer", "aro", "tribunal", "art",
     "cancelled", "rejected", "debt", "overpayment"],
    "Explains internal review (Authorised Review Officer) then the Administrative Review Tribunal.",
    "If you disagree with a Centrelink decision you can ask for a review - first by an "
    "independent Authorised Review Officer, then the Administrative Review Tribunal. Ask soon: "
    "time limits can affect back pay.",
    """
If you disagree with a Centrelink decision, you have the right to ask for it to be looked at again.

1. Talk to Centrelink first — sometimes it's a simple fix, like missing information.
2. Ask for a formal review. This is done by an Authorised Review Officer (ARO) who wasn't involved
   in the original decision. You can request it online through your Centrelink online account,
   by phone, or in person.
3. If you still disagree, you can apply to the Administrative Review Tribunal (ART), which is
   independent of Services Australia.

Tips:
• Ask as soon as you can. If you ask within 13 weeks of the decision, any back pay can usually
  be paid from the date of the original decision.
• If you have a debt you disagree with, you can ask for a review of the debt too — and you can
  ask about pausing repayments while it's reviewed.
• Keep copies of letters and write down the date and name of anyone you speak to.
""",
    ["https://www.servicesaustralia.gov.au/reviews-and-appeals-centrelink-payments", "https://www.art.gov.au"],
)

add(
    "statutory-declaration", "Commonwealth statutory declarations", "services_australia",
    ["statutory declaration", "stat dec", "witness", "jp", "justice of the peace", "declaration"],
    "How to make a Commonwealth stat dec: digitally via myGov or on paper with an authorised witness.",
    "You can make a Commonwealth stat dec online through myGov (with a Digital ID), or on paper "
    "signed in front of an authorised witness. List of witnesses: ag.gov.au/statdecs",
    """
There are two ways to make a Commonwealth statutory declaration:

1. Digitally, through myGov — you'll need a strong enough Digital ID (for example myID). No
   witness is needed. Sign in at my.gov.au and search for "statutory declaration".
2. On paper — download the form from the Attorney-General's Department website, fill it in, but
   don't sign it until you're in front of an authorised witness.

Who can witness a paper stat dec: the list is broad and includes Justices of the Peace, many
health practitioners, teachers, police officers, bank officers with 2+ years' service, and
others. Check the full list at ag.gov.au before you go.

Note: Queensland state matters use a different (Queensland) statutory declaration form — check
which one the organisation is asking for.
""",
    ["https://www.ag.gov.au/legal-system/statutory-declarations"],
)

add(
    "concession-cards", "Concession cards: who's eligible", "services_australia",
    ["concession", "concession card", "health care card", "pensioner concession card",
     "seniors health card", "cshc", "discount", "eligible", "eligibility"],
    "Overview of the Pensioner Concession Card, Health Care Card and Commonwealth Seniors Health Card.",
    "Concession cards: Pensioner Concession Card (most pension recipients), Health Care Card "
    "(some payments or low income), Commonwealth Seniors Health Card (Age Pension age, not on "
    "pension, income test). Check: servicesaustralia.gov.au/concession-and-health-care-cards",
    """
There are three main Australian Government concession cards:

• Pensioner Concession Card — generally issued automatically to people getting an Age Pension,
  Disability Support Pension, Carer Payment and some other payments.
• Health Care Card — for people getting certain payments, or on a low income (a separate
  Low Income Health Care Card). Some carers and foster carers can also get one.
• Commonwealth Seniors Health Card — for people who've reached Age Pension age but don't get
  a pension, subject to an income test.

The cards give cheaper PBS medicines, and can unlock state, council and business discounts
(for example on electricity, rates and transport) — those extra discounts vary.

You can check eligibility and apply through your Centrelink online account via myGov, or by
calling Centrelink on the line for your payment.
""",
    ["https://www.servicesaustralia.gov.au/concession-and-health-care-cards"],
)

add(
    "energy-rebates-qld", "Energy bill help & rebates (Qld)", "services_australia",
    ["energy", "electricity", "power bill", "rebate", "gas", "bill relief", "hardship",
     "disconnect", "disconnected"],
    "Where to point constituents for Queensland electricity rebates and hardship help.",
    "For electricity rebates in Qld (incl. concession card holders) see qld.gov.au/community "
    "or call 13 QGOV (13 74 68). Struggling to pay? Ask your retailer for their hardship program.",
    """
If you're finding power bills hard, here are the main places to start:

• Queensland Government electricity and gas rebates — concession card holders and some other
  households can get a rebate on their bill. Search "electricity rebates" at qld.gov.au or call
  13 QGOV (13 74 68). Apply through your energy retailer or the Queensland Government, as directed.
• Your energy retailer's hardship program — every retailer must have one. Call them, say you're
  having trouble paying, and ask for a payment plan or hardship assistance.
• Home Energy Emergency Assistance Scheme (Qld) — one-off help for households in an
  unexpected crisis that can't pay their bill.
• Energy & Water Ombudsman Queensland — if you can't sort a problem out with your retailer.

Any Australian Government energy bill relief credits are applied automatically by retailers —
you don't need to apply.
""",
    ["https://www.qld.gov.au/community/cost-of-living-support/concessions/energy-concessions", "https://www.ewoq.com.au"],
)

add(
    "medicare-basics", "Medicare: enrolment, cards and claims", "services_australia",
    ["medicare", "medicare card", "enrol", "enrolment", "claim", "rebate", "safety net", "bulk billing"],
    "Medicare enrolment, replacement cards, claiming and the Medicare Safety Net.",
    "Medicare: manage your card, claims and details online via myGov or the Express Plus Medicare "
    "app, or call 132 011.",
    """
Most Medicare tasks can be done online through myGov or the Express Plus Medicare app:
• get a digital copy of your card or order a replacement,
• add a child or update your details,
• claim a rebate for a service you've paid for,
• check your Medicare Safety Net progress (families should register as a family so costs combine).

New to Medicare (for example a new migrant or newborn)? Enrolment eligibility depends on visa
or residency status — Services Australia can confirm.

Phone: 132 011.
""",
    ["https://www.servicesaustralia.gov.au/medicare"],
)

# ------------------------------------------------------------- Immigration ----
add(
    "ministerial-intervention-explainer", "Ministerial intervention: explainer & reality check",
    "immigration",
    ["ministerial intervention", "intervention", "minister", "refused", "tribunal", "art",
     "aat", "s351", "s417", "last resort", "deport", "removal"],
    "What ministerial intervention is, when it's possible, and why outcomes can't be promised.",
    "Ministerial intervention is a personal, discretionary power of the Minister, only available "
    "in limited circumstances (usually after a tribunal decision). There's no right to it and "
    "no guarantee. Please get registered migration advice before acting.",
    """
We understand how important this is, so we want to be upfront about how ministerial
intervention works.

• The Immigration Minister has personal powers to substitute a more favourable decision in
  some cases — most commonly after the Administrative Review Tribunal (ART) has made a decision.
• These powers are non-compellable: the Minister doesn't have to consider any request, and
  there's no right of appeal if they don't. Only a small proportion of requests succeed.
• Requests must meet the Minister's published guidelines (for example, unique or exceptional
  circumstances). The Department assesses requests against those guidelines before anything
  reaches the Minister.
• A request generally won't, by itself, give you permission to stay in Australia. Keep your
  visa status lawful and follow the Department's instructions.

What our office can do: we can make sure the Department has received your request and ask about
its status. We can't influence the Minister's decision.

What we recommend: get advice from a registered migration agent or an immigration lawyer
(check registration at mara.gov.au), or Legal Aid Queensland (1300 65 11 88), before lodging.
""",
    ["https://immi.homeaffairs.gov.au/what-we-do/status-resolution-service/ministerial-intervention", "https://www.mara.gov.au"],
)

add(
    "visa-processing-times", "Visa processing times & checking your application",
    "immigration",
    ["processing", "processing times", "waiting", "delay", "delayed", "immiaccount", "visa",
     "application status", "how long", "trn"],
    "Where to see current processing times and how to keep an application moving.",
    "You can check current visa processing times at immi.homeaffairs.gov.au (search 'processing "
    "times') and see your application in ImmiAccount. Keep your details up to date there.",
    """
Some things that help while you're waiting on a visa:

• Check current processing times on the Home Affairs website (search "global visa processing
  times"). Times are updated regularly and differ by visa and stream.
• Log in to ImmiAccount to check your application status and any requests for information.
  Respond to requests by the due date — missing one can delay or affect the decision.
• Keep your contact details, passport and circumstances up to date (for example a new address,
  baby, or relationship change).
• Avoid lodging duplicate applications or repeated enquiries — they don't speed things up.

If your application is well outside the published processing time, or there's a compelling
reason it's urgent (serious illness, family crisis), let us know — with your signed consent
and your TRN or Client ID we can raise it with the Department.

Home Affairs Global Service Centre: 131 881.
""",
    ["https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times"],
)

add(
    "citizenship-basics", "Australian citizenship: applying & ceremonies", "immigration",
    ["citizenship", "citizenship test", "ceremony", "conferral", "pledge"],
    "Citizenship by conferral basics, test, and ceremony timing.",
    "Citizenship info, eligibility and the online application are at immi.homeaffairs.gov.au/citizenship. "
    "Citizenship line: 131 880.",
    """
Becoming an Australian citizen (by conferral) generally involves:
1. Checking you meet the residence requirement — the online residence calculator helps.
2. Applying online through ImmiAccount.
3. Attending an appointment and, for most applicants, sitting the citizenship test.
4. Once approved, making the pledge at a citizenship ceremony — usually run by your local council.

Ceremony dates are set by councils, so there can be a wait after approval.

Citizenship information line: 131 880.
""",
    ["https://immi.homeaffairs.gov.au/citizenship"],
)

# -------------------------------------------------------------------- NDIS ----
add(
    "ndis-review-of-decision", "NDIS: asking for a review of a decision", "ndis",
    ["ndis", "review", "decision", "internal review", "plan", "reassessment", "variation",
     "access", "rejected", "tribunal"],
    "Internal review, plan changes, and the ART for NDIS decisions.",
    "Disagree with an NDIS decision? You can ask the NDIA for an internal review - generally "
    "within 3 months of getting the decision. Call 1800 800 110 or ask your LAC.",
    """
If you disagree with an NDIS decision, there are a few pathways:

• Internal review — ask the NDIA to review the decision. You generally need to ask within
  3 months of receiving the written decision. You can ask by phone (1800 800 110), email,
  in person, or through your Local Area Coordinator (LAC).
• Plan change — if your circumstances have changed, or your plan isn't working, you can ask
  for a plan variation or reassessment instead of a review.
• Administrative Review Tribunal (ART) — if you still disagree after an internal review.

Free support: an NDIS appeals advocate can help you through the review and tribunal process at
no cost — ask the NDIA or search "NDIS appeals" for a provider in Queensland.

Helpful to have ready: the decision letter, your NDIS number, and any reports or evidence
about your support needs.
""",
    ["https://www.ndis.gov.au/applying-access-ndis/how-apply/receiving-your-access-decision/internal-review-decision", "https://www.art.gov.au"],
)

# --------------------------------------------------------------- Aged care ----
add(
    "myagedcare-getting-started", "My Aged Care: getting started", "aged_care",
    ["aged care", "my aged care", "myagedcare", "assessment", "home care", "support at home",
     "residential", "nursing home", "respite", "register"],
    "How to register with My Aged Care, get assessed, and what happens next.",
    "To start aged care services, call My Aged Care on 1800 200 422 or apply online at "
    "myagedcare.gov.au. They'll arrange an assessment.",
    """
My Aged Care is the starting point for government-funded aged care, whether that's help at home
or moving into residential care.

1. Contact My Aged Care — call 1800 200 422 or apply online at myagedcare.gov.au. A family
   member or friend can call on your behalf with your permission.
2. Assessment — an assessor will visit to talk about your needs and what services suit you.
3. Approval and services — once approved, you'll be told what you're eligible for and how to
   find providers in your area. There can be a wait for some services.

Help at home is delivered through the Support at Home program (which replaced Home Care
Packages from 1 November 2025) and the Commonwealth Home Support Programme.

You can appoint a representative to deal with My Aged Care for you. Face-to-face help is also
available at some Services Australia service centres.
""",
    ["https://www.myagedcare.gov.au", "https://www.health.gov.au/our-work/support-at-home"],
)

# --------------------------------------------------------- ATO / NBN / DVA ----
add(
    "ato-basics", "ATO: getting help (and protecting your TFN)", "ato",
    ["ato", "tax", "tax return", "refund", "tfn", "tax file number", "debt", "payment plan",
     "super", "superannuation", "scam"],
    "ATO contact options, payment plans, complaints and TFN safety.",
    "ATO help: 13 28 61, or manage tax via myGov (link the ATO). Never share your TFN by text or "
    "email. Unresolved complaints can go to the Inspector-General of Taxation (1800 199 010).",
    """
A few ways to get your tax matter sorted:

• Online — link the ATO to your myGov account to check your return, refund status, debts and
  super.
• Phone — individuals can call the ATO on 13 28 61.
• Payment plans — if you owe tax and can't pay in full, you can usually set up a payment plan
  online or by phone.
• Complaints — if you can't resolve it with the ATO, you can lodge a complaint with the ATO and
  then the Inspector-General of Taxation and Taxation Ombudsman (1800 199 010).

Please keep your Tax File Number private — never send it by text or email (including to our
office). The ATO will never ask for it in an unsolicited text or email. If you think you've been
scammed, call the ATO straight away.
""",
    ["https://www.ato.gov.au/about-ato/contact-us", "https://www.igt.gov.au"],
)

add(
    "nbn-connection-faults", "NBN / internet faults: who to contact", "nbn",
    ["nbn", "internet", "broadband", "connection", "fault", "outage", "telstra", "optus",
     "tpg", "ombudsman", "tio"],
    "Retail provider first, then the Telecommunications Industry Ombudsman.",
    "For NBN/internet faults, contact your internet provider first and get a ticket number. If "
    "it's not fixed, the Telecommunications Industry Ombudsman can help: 1800 062 058.",
    """
For NBN and internet problems, your internet provider (for example Telstra, Optus, TPG, Aussie
Broadband) is the first point of contact — NBN Co deals with providers rather than customers.

1. Report the fault to your provider and ask for a reference / ticket number.
2. Write down dates, who you spoke to and what you were told.
3. If it isn't fixed in a reasonable time, make a formal complaint to your provider.
4. Still stuck? The Telecommunications Industry Ombudsman (TIO) is free and independent:
   1800 062 058 or tio.com.au.

If you have a serious medical condition and rely on your phone service, ask your provider about
priority assistance.
""",
    ["https://www.tio.com.au"],
)

add(
    "dva-basics", "DVA: contacts and support for veterans", "dva",
    ["dva", "veteran", "veterans", "gold card", "white card", "claim", "open arms", "defence",
     "adf", "myservice"],
    "DVA contact, MyService claims, Open Arms counselling, and free advocates.",
    "DVA: 1800 VETERAN (1800 838 372). Claims via MyService on myGov. Open Arms counselling 24/7: "
    "1800 011 046.",
    """
Support for veterans and their families:

• DVA — call 1800 VETERAN (1800 838 372).
• MyService — lodge and track claims online through myGov.
• Open Arms – Veterans & Families Counselling — free, confidential, 24/7: 1800 011 046.
• Free advocates — trained ex-service organisation advocates can help prepare and lodge claims at
  no cost. Search "Advocacy Training and Development Program" or ask your local RSL sub-branch.

If a claim is taking a long time or you disagree with a decision, let us know — with your
consent and DVA file number we can follow it up.
""",
    ["https://www.dva.gov.au/contact", "https://www.openarms.gov.au"],
)

# --------------------------------------------------------- Flags & messages --
add(
    "flags-portraits-eligibility", "Flags & portraits: eligibility guidelines", "flag",
    ["flag", "flags", "australian flag", "aboriginal flag", "torres strait islander flag",
     "portrait", "king", "school", "community group", "constituents request program"],
    "What the office can provide under the Constituents' Request Program and who's eligible.",
    "Our office can provide Australian, Aboriginal and Torres Strait Islander flags and official "
    "portraits to eligible schools, community groups and organisations in Moreton. Reply with your "
    "organisation's name and delivery address and we'll check eligibility.",
    """
Thanks for your interest! Through the Australian Government's Constituents' Request Program,
our office can provide items such as:
• the Australian National Flag,
• the Aboriginal Flag and the Torres Strait Islander Flag,
• official portraits (for example of His Majesty The King).

Who's eligible: items are generally available to schools, community organisations, not-for-
profit groups and other eligible organisations, and some individuals. Availability, sizes and
quantities are set by the program guidelines and stock levels.

What we need from you:
• the name of your organisation (or yourself),
• a contact name, phone and email,
• the delivery or pick-up address in Moreton,
• what you're requesting and how it will be used or displayed.

We'll confirm eligibility and let you know when it's ready.

[STAFF: confirm current item list and eligibility against the Department of the Prime Minister
and Cabinet's Constituents' Request Program guidelines before sending.]
""",
    ["https://www.pmc.gov.au/honours-and-symbols/australian-national-symbols"],
)

add(
    "milestone-messages-protocol", "Birthday & anniversary congratulatory messages",
    "congratulations",
    ["birthday", "anniversary", "wedding anniversary", "100th", "90th", "60th", "50th", "65th",
     "70th", "congratulations", "message", "king", "governor-general", "centenarian", "milestone"],
    "Which milestones can get messages from the MP, Governor-General, PM and The King — and lead times.",
    "Congratulations to the family! We'd love to arrange a message. Please send the person's "
    "name, the milestone date, and (for The King or the Governor-General) proof of age or "
    "marriage, ideally 6-8 weeks ahead.",
    """
What a wonderful milestone! Here's how congratulatory messages generally work:

From Julie-Ann (your local Member): we're happy to send a message for significant birthdays and
wedding anniversaries — just let us know.

From the Governor-General, the Prime Minister and His Majesty The King: messages are available
for some milestones, generally:
• Birthdays — 100th and later birthdays (some offices also mark 90th and 95th).
• Wedding anniversaries — 50th, 60th, 65th, 70th and later.
Messages from The King are arranged through Government House (the Governor-General's office).

What we need:
• the name(s) of the person or couple, and the date of the milestone,
• the address to send the message to,
• for The King / Governor-General: proof of age (birthdays) or of marriage (anniversaries) may
  be required.

Please give us as much notice as possible — ideally 6 to 8 weeks before the date.

[STAFF: confirm current milestone eligibility and lead times at gg.gov.au before sending.]
""",
    ["https://www.gg.gov.au/request-message", "https://www.pmc.gov.au"],
)

# ------------------------------------------------------------ Referrals ------
add(
    "local-referrals-relief-housing-legal", "Food relief, housing & legal referrals (Brisbane)",
    "admin",
    ["food", "food relief", "hungry", "homeless", "housing", "rent", "eviction", "legal",
     "lawyer", "legal aid", "emergency relief", "crisis", "financial counselling", "debt"],
    "Starting points for emergency relief, housing and free legal help on Brisbane's southside.",
    "Help is available: Ask Izzy (askizzy.org.au) finds food, housing & support near you. Qld "
    "Homeless Hotline 1800 474 753. Salvos 13 72 58. Legal Aid Qld 1300 65 11 88. Free financial "
    "counselling 1800 007 007.",
    """
Here are some places that can help straight away:

Food and emergency relief
• Ask Izzy — askizzy.org.au — search for food, emergency relief and other services near you.
• The Salvation Army — 13 72 58.
• St Vincent de Paul Society Queensland — 1800 846 643.

Housing
• Queensland Homeless Hotline (24/7) — 1800 474 753.
• Housing Service Centres (Queensland Government) — 13 QGOV (13 74 68) for social housing,
  bond loans and rental grants.
• Tenants Queensland — tenancy advice: 1300 744 263.

Legal help
• Legal Aid Queensland — 1300 65 11 88.
• Community legal centres — find your nearest at communitylegalqld.org.au.

Money
• National Debt Helpline (free financial counselling) — 1800 007 007.

[STAFF: add the office's preferred local southside services (pantries, community centres) here.]
""",
    ["https://askizzy.org.au", "https://www.legalaid.qld.gov.au", "https://ndh.org.au"],
)

add(
    "commonwealth-ombudsman", "Complaints: the Commonwealth Ombudsman", "other_casework",
    ["complaint", "complain", "ombudsman", "unfair", "no response", "maladministration"],
    "When and how to escalate a complaint about an Australian Government agency.",
    "If you've complained to an Australian Government agency and it's not resolved, the "
    "Commonwealth Ombudsman can help for free: 1300 362 072 or ombudsman.gov.au.",
    """
If you've had a problem with an Australian Government agency (for example Services Australia,
Home Affairs or the NDIA) and you've already tried to resolve it with them, the Commonwealth
Ombudsman may be able to help.

• It's free and independent.
• Complain to the agency first and keep your reference number — the Ombudsman will usually ask.
• Contact: 1300 362 072 or ombudsman.gov.au.

The Ombudsman looks at how a decision was made and whether you were treated fairly; it generally
can't change a decision that has its own review or appeal process.
""",
    ["https://www.ombudsman.gov.au"],
)

out = Path(__file__).with_name("templates.json")
out.write_text(json.dumps(T, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {len(T)} templates to {out}")
