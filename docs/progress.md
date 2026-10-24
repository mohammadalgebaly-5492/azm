# Progress log

The project's memory between chats. Claude reads this at the start of **every** chat and updates it after every meaningful step (newest first). Keep each entry short. English, with Muhammad's own words quoted in Arabic when useful.

## Now

- **Current task:** none. The new identity and the sign-in subtitle are published (commit `62ab8bb`). Vercel reported "Deployment has completed".
- **Waiting on Muhammad:** confirmation that the live site shows the new look, and the live site's address. The GitHub repo's homepage (`azm-iota-lime.vercel.app`) is stale (`DEPLOYMENT_NOT_FOUND`); the team URLs `azm-mohammad5493.vercel.app` are behind Vercel sign-in.
- **Next planned step:** the item pipeline (سلسلة تنفيذ البنود). Confirm the details with Muhammad, and with the programmer for the engine design, before building. See CLAUDE.md, "Roadmap".
- **Also open:** the decisions listed in CLAUDE.md, "Roadmap and open decisions".

## Log

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
