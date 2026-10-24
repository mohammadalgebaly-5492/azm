# Progress log

The project's memory between chats. Claude reads this at the start of **every** chat and updates it after every meaningful step (newest first). Keep each entry short. English, with Muhammad's own words quoted in Arabic when useful.

## Now

- **Current task:** writing the constitution with Muhammad. Articles 1–4 are all approved (3 and 4 on 2026-10-25). Article 4 = part 2, «إدارة المشروع وحوكمته», drafted from his 9 points; decisions applied 2026-10-25; all applied, including the 10,000 SAR limit per payment (`docs/constitution.md`). Discussion only: he said not to build anything until the discussion is finished. Open questions are listed under each article.
- **Published 2026-10-25 (commits `ba07534` and `17fe87f`, Vercel "Deployment has completed"):** the sign-in panel sentence «إدارة وأتمتة المشاريع وأكثر…», the constitution (articles 1–4), CLAUDE.md rules, and this log. Verified the GitHub copy of the constitution is byte-identical to the local one.
- **Published:** the new identity and the sign-in subtitle (commit `62ab8bb`). Vercel reported "Deployment has completed".
- **Live site address:** `https://azm-mohammad5493.vercel.app` (Vercel project `mohammad5493/azm`). It sits behind Vercel sign-in (Deployment Protection), so Claude cannot open it to verify; Muhammad can when signed in to Vercel. Do NOT use `azm.vercel.app` or `azm-app.vercel.app` (other people's apps) or `azm-iota-lime.vercel.app` (stale). Whether the protection should be off for the team is a programmer/Vercel setting.
- **Waiting on Muhammad:** his review of the demo (role names, chart bars, site-wide gradient) and his yes to publish. The migration renames role labels in the live database, so it needs that yes.
- **Next planned step:** the item pipeline (سلسلة تنفيذ البنود). Confirm the details with Muhammad, and with the programmer for the engine design, before building. See CLAUDE.md, "Roadmap".
- **Also open:** the decisions listed in CLAUDE.md, "Roadmap and open decisions".

## Log

- **2026-10-25.** Demo project built on the throwaway demo copy only (never the live database) at Muhammad's request («مشروع كامل ... قيمته 1 مليون ريال سعودي ... 5 مراحل تنفيذ»): P-2026-001 «مبنى إداري من ثلاثة طوابق», contract 1,000,000.00 SAR, 5 execution phases as the WBS top level (10 sections, 21 items), BOQ total equal to the contract, baseline approved, status in execution, team of 5. Built through the platform's own functions, so it passed the platform's baseline checks. Only what exists today can be shown: project, team, WBS, BOQ, baseline, analytics. Contract details, payments, schedule, allocation, procurement, daily reports and EVM are in the constitution but not built yet. Also fixed the BOQ-chart «both» category color (was purple-blue, now brand green).
- **2026-10-25.** Built locally, not published (demo on a throwaway SQLite copy, port 5056):
  - Migration `010_role_labels` (both folders) renames the default role labels to the constitution's titles, leaving customised names alone; test added (52 tests pass).
  - Chart bars use a neutral slate `--c-series`; green would have clashed with the «complete» status bars.
  - Muhammad asked for the sign-in panel's gradient across the whole site («الالوان بتاعت الموقع والخلفية كلها من نفس الشكل والتدرج دا»): page background now uses `--aurora-*`, cards are glass, and the sign-in page shares it. The fix needed `html` to own the background and `body` to be transparent, because the old opaque body hid the glow.
  - Muhammad confirmed contract creation is judged by its total and payments one by one («مظبوط كلامك»).
- **2026-10-25.** Muhammad approved articles 3 and 4 («اه اعتمد المواد») and said the new look is good («والشكل الجديد كويس»). He did not understand the question on contract creation vs payments; re-asked in simpler words with an example. The role-rename proposal (migration on the live database) is still awaiting his yes.
- **2026-10-25.** Titles approved («صح الاسم»; «الكوست كنترول انجنير هيكون مهندس تحكم تكلفة»): Director = «المدير التنفيذي», Cost Control Engineer = «مهندس تحكم تكلفة». Renamed across the constitution; «التحكم في التكاليف» stays only for the function. The app's role names still show the old transliterations and must be renamed when building.
- **2026-10-25.** The 10,000 SAR limit is judged per payment, not cumulatively per contract («كل دفعه لوحدها»). Reading applied: contract/PO award by its own total, each payment by its own amount, with the approved-commitment ceiling and the anti-splitting rule kept for new POs and contracts only. Director gets an automatic notice for every Cost Control approval within the limit.
- **2026-10-25.** Article 4 decisions:
  - Procurement account type added to article 1 («نعم ضيف المشتريات في المادة 1»).
  - Director approves the baselines, then the PM's kick-off gate («اقتراحك صحيح»).
  - Thresholds 5 / 10 / 30% («اكثر من 30 % حرج»).
  - At least 2 quotes («عرضين على الاقل»).
  - Up to 10,000 SAR the Cost Control engineer acts alone, and above that the Director approves too («لحد 10 الاف يمكن لمهندس الكوست كنترول اتخاذ اجراء»). Added an approval-limits table with an anti-splitting rule (same item and vendor within 30 days). Written as cumulative per PO/contract; awaiting his confirmation. CLAUDE.md open decisions updated.
- **2026-10-25.** Article 4 drafted from Muhammad's nine points («اربط كل الكلام دا ببالمادة العلمية العالمية»):
  - **References:** PMBOK, PMI EVM standard, ANSI/EIA-748, ISO 21502, PRINCE2, AACE TCM and RP 29R-03, FIDIC, COSO.
  - **Governance principles:** segregation of duties; no commitment without budget; no certificate above recorded progress; management by exception; fixed approve/return paths with a «مهامي» page.
  - **Ten processes**, from PM kick-off through closing, each with workflow and field tables.
  - **Automation table, RACI and new codes.**
  - **Five decisions in 4.14:** procurement account type; Director approves the baselines, then the PM's kick-off gate; RAG thresholds 5/10/20% (this also settles the CLAUDE.md "5–10% colour" question); a minimum of 3 quotes; the 10,000 SAR limit scope.
  - **Dependencies:** file storage, an email provider, and one shared approval engine (this is the item pipeline in CLAUDE.md's roadmap).
- **2026-10-25.** Make-or-buy per execution step: a company crew or a subcontractor can execute any step of the same item («ممكن يكون طاقم عمل للشركة او مقاول باطن»):
  - Each scope-of-work step has an execution party; the item's method is computed (self, subcontractor or mixed).
  - Subcontractors live in the Article 2 entities list as type «مقاول باطن» (`ENT-SUB-…`), with CR, VAT, specialties, approval status and documents.
  - Allocation supports subcontractors (quantity × estimated unit rate), with two new validation rules: the party matches the step, and the subcontractor is approved with a matching specialty.
  - Reference drawings in scope of work are now required. Asked whether reference specifications should be too.
- **2026-10-25.** Resource allocation (3.6) expanded at Muhammad's request («اديلو حقو في التفنيد وخلي معظم الجدول مربوط بشيء والزامي»):
  - 29 fields in six groups (identity, link to the plan, period, productivity, cost, governance), mostly linked and required.
  - 6 validation rules: no double-booking above 100% across projects, inside the activity window, valid status, enough days for the productivity rate, price check against the item analysis, governance after baseline.
  - Outputs: resource histogram, company-wide occupancy, planned resource cost.
  - New code `ALC`. Also: «المورد» became «الفرد أو الطاقم أو المعدة», «الوظيفة الأعلى» became «المدير المباشر», and the WBS «القسم الأعلى» became «القسم الرئيسي الذي يتبعه».
- **2026-10-25.** Equipment (3.6, 3.9):
  - The equipment name is picked from a database catalog, not typed («اسم المعدة يتم ربطه بحيث انه سيكون ضمن الداتا بيز»).
  - Types split into 5 (heavy, light, transport, power and services, tools) at his request («خليهم 4 انواع على الاقل»); type is picked first, then the name within it.
  - New governing rule 7: every repeated name comes from a database list (equipment, job titles, professions, specialties, units, entities). Added a job-title catalog.
  - Replaced the transliteration «لودر» with «محمّلة».
- **2026-10-25.** Contract (3.2): added a contractual payment schedule. Each payment is tied to one schedule activity («كل دفعه مربوطه ب اكتفيتي معين من جدول ادارة المشروع»); its due date follows the activity, and percentages total 100%. The schedule shows the linked payment and a cash-inflow view. Due/claim/collection tracking belongs to part 2.
- **2026-10-25.** Muhammad: every article 3 requirement must be fully recordable in detail, across many fields («يجب ان يكون كل بند من هذه البنود متاح تسجيله بالتفاصيل وفي اكثر من خانة»). Replaced the "current state" table with "from what exists now to what's required", added governing rule 6 (full detail in structured fields), and wrote field tables (field, type, required) for all seven requirements.
- **2026-10-25.** Article 3, Muhammad's answers:
  - Tendering means pricing the project with the contract; subcontractor and supplier quotes belong to part 2, cost control («اما المقاولين الباطن ولموردين دا هيكون في مرحلة الكوست كنترول»).
  - The detailed technical plan is made in Primavera P6, MS Project or Excel; the platform's own simple schedule is the tracking base.
  - Team and assets are for both planning and cost.
  - He left the scope-of-work chain and the coding system to me («انت الي تحدد»). Decided: the chain is the technical steps per item with weights (rules of credit), separate from the administrative item pipeline. Full coding system written, including people (`EMP-…`) and equipment (`EQP-…`), auto-generated and immutable.
  - Still to confirm: «المدير التنفيذي» as the Arabic title for Director.
- **2026-10-25.** Constitution:
  - **Language rule:** «العربي يكون بالعربي والانجليزي بالانجلزي»: no English words in Arabic letters, in chat, interface or docs. Added to CLAUDE.md and as a glossary in the constitution. Director is «المدير التنفيذي» (assumption, awaiting his confirmation).
  - **Later, when building:** the interface still shows transliterated role names («الكوست كنترول (المسؤول)», «الدايركتور»).
  - **Article 3 rewritten as a full PMO-based specification**, at his request («تناقش مع نفسك وتطور القصه»): five project phases, governing rules, each requirement detailed, RACI, codes.
  - **Governance principle made a general approved rule** («دا لازم تضيفه»).
  - **Schedule:** built on the platform as the base, simpler than Primavera, showing items, time and cost, planned and actual; import from Excel and Primavera is extra («الاساس يتم الاعداد على المنصة»).
- **2026-10-25.** Constitution article 3 drafted: Part 1 of the platform, project management. Muhammad's 7 components: documents, contract, BOQ + tendering, technical plan (Excel-like tables and charts), WBS linked to cost and schedule, team and assets, scope of work per item as a chain. Everything coded per section («كل قسم ليه SKU خاص بيه»), merged with PMO («عايزك تدمج نظريات PMO مع الشغل الي انا قلتو»). Proposals added for his approval: baseline freeze plus change requests, contract fields, document fields, coding system. Five open questions are in the file.
- **2026-10-24.** Constitution articles 1 and 2 approved («نعم ووخلينا نمشي باقتراحاتك ونخش عالبند الي بعدو»): the Director's past approvals keep the real approver's name after a transfer; consultants also go in the shared list; an entity can have several addresses; people belong to the entity, and each project picks at least 2 of them.
- **2026-10-24.** Constitution: Director stays one account, transferable to another person («يبقى حساب واحد يمكن نقله باسم شخص اخر»); owners repeat across projects and go in one shared list in the database; at least 2 representatives per entity («يسجل على الاقل عدد 2 اشخاص من كل جهة»).
- **2026-10-24.** Muhammad: «متبنيش الا لما نخلص نقاش»: no building until the discussion ends. Constitution updated: each licensee gets its own copy on a separate server in the future, and today is a trial platform; viewer accounts unlimited; new article 2, owner and consultant data per project (addresses, representatives, emails, an upload field for their company profile). The profile upload needs file storage, which isn't built yet (also needed for accounting invoices).
- **2026-10-24.** Constitution article 1 updated with Muhammad's answers: the main account belongs to whoever gets the usage rights («الحساب الرئيسي للي هيحصل على حقوق استخدام المنصة»); Cost Control and Accounting unlimited; no accounts for owner or consultant, but their data is recorded per project («لا يوجد دور للمالك والاستشاري في المنصة لكن يجب تسجيل بياناتهم في كل مشروع»). Today a project stores only `client` and `consultant` names as text.
- **2026-10-24.** Started `docs/constitution.md` (الدستور), Muhammad's numbered business rules. Article 1, accounts, is under discussion: one main account creates the others; one Cost Control, one Director, one Accounting, unlimited project engineers («دار قم واحد في الدستور خلينا نسميه الدستور»). The current platform already has these roles but no count limits, plus viewer / owner's rep / consultant roles. Nothing built yet.
- **2026-10-24.** Sign-in panel sentence changed to «إدارة وأتمتة المشاريع وأكثر…» (was «التحكم في تكلفة كل مشروع…») at Muhammad's request. Local only.
- **2026-10-24.** Published the new identity and the sign-in subtitle to the live site on Muhammad's yes («ماشي اعكس دا على المنصة»). No data-structure changes.
- **2026-10-24.** New AZM identity, built locally:
  - Muhammad's own logo (`docs/brand/azm-logo-source.png`), traced to a vector `mark()`; full logo on the sign-in panel; new favicon. Alenmaa logo files removed.
  - Green buttons and links; background lighter, without the violet tint (`#1d2a41`).
  - He first asked for a light theme («الخلفية هتكون ابيض متدرج الى الرصاصي…»), then chose the dark preview with green buttons and background ج, 25% lighter: «خليك مع دا وافتح الخلفية كمان بنسبة 25%». So the programmer's one-dark-theme rule stays.
  - The company shows by name only (no company logo).
- **2026-10-24.** Muhammad: AZM is his own product, independent of Alenmaa, usable inside or outside it («منصه عزم دي عاملها بشكل خاص ملهاش علاقه بشركه الانماء، يعني ممكن استخدمها في شركه الانماء او بره شركه الانماء»). He wants its own logo. Questions sent; see "Now".
- **2026-10-24.** Sign-in subtitle changed to «منصة إدارة المشروعات والحوكمة» at Muhammad's request («اكتب منصة ادارة المشروعات والحوكمة»). Not yet published to the live site.
- **2026-10-24.** Handover from the programmer. In place:
  - our own sign-in, roles and permissions;
  - sign-up links;
  - projects, BOQ, WBS and baseline;
  - analytics, audit log and avatars;
  - Arabic and English, one dark theme in the brand ink navy.
