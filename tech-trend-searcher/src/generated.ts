// Файл создан автоматически: python -m radar.export_ui
// Источник — сохранённые прогоны радара. Руками не править: перезапишется.
// Выгружено 2026-09-27T10:12:50+00:00
import type { Trend, Analysis } from "./data";

export const genTrends: Trend[] = [
 {
  "id": "t0",
  "name": "частное облако Azure Local с поддержкой отключенных режимов и локальных GPU",
  "definition": "развертывание валидированного стека Azure на локальной инфраструктуре клиента с поддержкой внешних SAN-хранилищ, локального управления кластерами и установки серверных GPU для инференса",
  "signal": 80,
  "firstYear": 2025,
  "series": [
   0,
   0,
   0,
   2,
   5
  ],
  "stage": "продукт",
  "kind": "ранний сигнал",
  "bank": "Требует экспертной проверки",
  "features": {
   "nT": 7,
   "logGrowth": 0.71,
   "share": 0.0,
   "shareGrowth": 0.0,
   "age": 20.4,
   "orgs": 2,
   "hhi": 0.0,
   "coverage": 1,
   "novelty": 10.0
  },
  "reasons": [
   "термин молодой: 2025-01-14",
   "5 из 7 упоминаний за последний год",
   "тихо: всего 7 упоминаний",
   "два игрока"
  ],
  "claims": [
   {
    "label": "Механизм",
    "text": "развертывание валидированного стека Azure на локальной инфраструктуре клиента с поддержкой внешних SAN-хранилищ, локального управления кластерами и установки серверных GPU для инференса",
    "status": "supported",
    "sourceId": "s0-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "термин молодой: 2025-01-14",
    "status": "supported",
    "sourceId": "s0-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "5 из 7 упоминаний за последний год",
    "status": "supported",
    "sourceId": "s0-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "тихо: всего 7 упоминаний",
    "status": "supported",
    "sourceId": "s0-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "два игрока",
    "status": "supported",
    "sourceId": "s0-0"
   }
  ],
  "sources": [
   {
    "id": "s0-0",
    "title": "windowsforum.com",
    "date": "2025-01-14",
    "type": "статья",
    "url": "https://windowsforum.com/news/microsoft-sovereign-cloud-in-region-ai-local-azure-and-partner-governance.388034/",
    "quote": "Azure Local’s move from 16‑server clusters to “hundreds of servers” is a game‑changer for organizations with substantial on‑prem workloads.",
    "language": "en",
    "trust": "низкий",
    "summaryRu": "развертывание валидированного стека Azure на локальной инфраструктуре клиента с поддержкой внешних SAN-хранилищ, локального управления кластерами и установки серверных GPU для инференса",
    "generated": false
   }
  ]
 },
 {
  "id": "t1",
  "name": "локальный запуск ИИ-моделей без облачной зависимости",
  "definition": "запуск ИИ-моделей на локальном оборудовании с полным контролем над данными, вычислениями и обновлениями",
  "signal": 76,
  "firstYear": 2025,
  "series": [
   0,
   0,
   0,
   3,
   2
  ],
  "stage": "продукт",
  "kind": "ранний сигнал",
  "bank": "Требует экспертной проверки",
  "features": {
   "nT": 5,
   "logGrowth": 0.4,
   "share": 0.0,
   "shareGrowth": 0.0,
   "age": 16.3,
   "orgs": 3,
   "hhi": 0.0,
   "coverage": 2,
   "novelty": 9.5
  },
  "reasons": [
   "термин молодой: 2025-05-19",
   "свежих упоминаний 40%",
   "тихо: всего 5 упоминаний",
   "3 независимых игроков"
  ],
  "claims": [
   {
    "label": "Механизм",
    "text": "запуск ИИ-моделей на локальном оборудовании с полным контролем над данными, вычислениями и обновлениями",
    "status": "supported",
    "sourceId": "s1-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "термин молодой: 2025-05-19",
    "status": "supported",
    "sourceId": "s1-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "свежих упоминаний 40%",
    "status": "supported",
    "sourceId": "s1-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "тихо: всего 5 упоминаний",
    "status": "supported",
    "sourceId": "s1-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "3 независимых игроков",
    "status": "supported",
    "sourceId": "s1-0"
   }
  ],
  "sources": [
   {
    "id": "s1-0",
    "title": "ertas.ai",
    "date": "2025-05-19",
    "type": "статья",
    "url": "https://www.ertas.ai/blog/sovereign-ai-enterprise-guide",
    "quote": "In February 2026, Microsoft launched Foundry Local at general availability — a framework for running AI models entirely on local hardware with no cloud dependency at runtime.",
    "language": "en",
    "trust": "низкий",
    "summaryRu": "запуск ИИ-моделей на локальном оборудовании с полным контролем над данными, вычислениями и обновлениями",
    "generated": false
   },
   {
    "id": "s1-1",
    "title": "ertas.ai",
    "date": "2025-05-19",
    "type": "статья",
    "url": "https://www.ertas.ai/blog/sovereign-ai-enterprise-guide",
    "quote": "Telenor, the Norwegian telecommunications company, partnered with Red Hat to build a sovereign AI factory in Norway running on NVIDIA infrastructure.",
    "language": "en",
    "trust": "низкий",
    "summaryRu": "запуск ИИ-моделей на локальном оборудовании с полным контролем над данными, вычислениями и обновлениями",
    "generated": false
   }
  ]
 },
 {
  "id": "t2",
  "name": "аппаратно-закрепленная идентификация агентов с верифицируемым происхождением",
  "definition": "привязка уникального идентификатора и кошелька агента к аппаратному обеспечению с регистрацией в блокчейне для обеспечения проверяемого происхождения",
  "signal": 68,
  "firstYear": 2025,
  "series": [
   0,
   0,
   0,
   5,
   56
  ],
  "stage": "прототип",
  "kind": "ранний сигнал",
  "bank": "Требует экспертной проверки",
  "features": {
   "nT": 61,
   "logGrowth": 0.92,
   "share": 0.0,
   "shareGrowth": 0.0,
   "age": 18.8,
   "orgs": 1,
   "hhi": 0.0,
   "coverage": 1,
   "novelty": 8.5
  },
  "reasons": [
   "термин молодой: 2025-03-03",
   "56 из 61 упоминаний за последний год",
   "стадия prototype"
  ],
  "claims": [
   {
    "label": "Механизм",
    "text": "привязка уникального идентификатора и кошелька агента к аппаратному обеспечению с регистрацией в блокчейне для обеспечения проверяемого происхождения",
    "status": "supported",
    "sourceId": "s2-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "термин молодой: 2025-03-03",
    "status": "supported",
    "sourceId": "s2-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "56 из 61 упоминаний за последний год",
    "status": "supported",
    "sourceId": "s2-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "стадия prototype",
    "status": "supported",
    "sourceId": "s2-0"
   }
  ],
  "sources": [
   {
    "id": "s2-0",
    "title": "ledger.com",
    "date": "2025-03-03",
    "type": "статья",
    "url": "https://www.ledger.com/blog-2026-ai-security-roadmap",
    "quote": "Agent Identity: Hardware-anchored identity for your agents. Instead of a spoofable software string, your agent gets a real identity and wallet anchored to Ledger hardware and registered on-chain. This provides verifiable provenance for every agent in your fleet.",
    "language": "en",
    "trust": "низкий",
    "summaryRu": "привязка уникального идентификатора и кошелька агента к аппаратному обеспечению с регистрацией в блокчейне для обеспечения проверяемого происхождения",
    "generated": false
   }
  ]
 },
 {
  "id": "t3",
  "name": "защита больших языковых моделей от вредоносных промптов и утечек данных",
  "definition": "фильтрация вредоносных промптов, модерация контента, шифрование запросов и ответов, валидация входных данных",
  "signal": 68,
  "firstYear": 2024,
  "series": [
   0,
   0,
   0,
   5,
   44
  ],
  "stage": "продукт",
  "kind": "ранний сигнал",
  "bank": "Требует экспертной проверки",
  "features": {
   "nT": 49,
   "logGrowth": 0.9,
   "share": 0.0,
   "shareGrowth": 0.0,
   "age": 30.8,
   "orgs": 3,
   "hhi": 0.0,
   "coverage": 1,
   "novelty": 8.5
  },
  "reasons": [
   "термину 30.8 мес.",
   "44 из 49 упоминаний за последний год",
   "3 независимых игроков"
  ],
  "claims": [
   {
    "label": "Механизм",
    "text": "фильтрация вредоносных промптов, модерация контента, шифрование запросов и ответов, валидация входных данных",
    "status": "supported",
    "sourceId": "s3-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "термину 30.8 мес.",
    "status": "supported",
    "sourceId": "s3-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "44 из 49 упоминаний за последний год",
    "status": "supported",
    "sourceId": "s3-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "3 независимых игроков",
    "status": "supported",
    "sourceId": "s3-0"
   }
  ],
  "sources": [
   {
    "id": "s3-0",
    "title": "forbes.ru",
    "date": "2024-03-04",
    "type": "статья",
    "url": "https://www.forbes.ru/svoi-biznes/552956-bezopasnyj-ii-regtech-i-cifrovoj-rubl-v-kakih-nisah-zapuskat-biznes-v-2026-godu",
    "quote": "Cloudflare в 2024 году запустила Firewall for AI — набор решений для фильтрации вредоносных промптов и модерации контента.",
    "language": "en",
    "trust": "средний",
    "summaryRu": "фильтрация вредоносных промптов, модерация контента, шифрование запросов и ответов, валидация входных данных",
    "generated": false
   }
  ]
 },
 {
  "id": "t4",
  "name": "фреймворк оценки рисков безопасности автономных ИИ-агентов",
  "definition": "идентификация критических уязвимостей и векторов атак",
  "signal": 64,
  "firstYear": 2025,
  "series": [
   0,
   0,
   0,
   0,
   4
  ],
  "stage": "исследование",
  "kind": "ранний сигнал",
  "bank": "Требует экспертной проверки",
  "features": {
   "nT": 4,
   "logGrowth": 1.0,
   "share": 0.0,
   "shareGrowth": 0.0,
   "age": 9.6,
   "orgs": 1,
   "hhi": 0.0,
   "coverage": 2,
   "novelty": 8.0
  },
  "reasons": [
   "термин молодой: 2025-12-10",
   "4 из 4 упоминаний за последний год",
   "тихо: всего 4 упоминаний"
  ],
  "claims": [
   {
    "label": "Механизм",
    "text": "идентификация критических уязвимостей и векторов атак",
    "status": "supported",
    "sourceId": "s4-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "термин молодой: 2025-12-10",
    "status": "supported",
    "sourceId": "s4-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "4 из 4 упоминаний за последний год",
    "status": "supported",
    "sourceId": "s4-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "тихо: всего 4 упоминаний",
    "status": "supported",
    "sourceId": "s4-0"
   }
  ],
  "sources": [
   {
    "id": "s4-0",
    "title": "github.com",
    "date": "2025-12-10",
    "type": "статья",
    "url": "https://github.com/requie/LLMSecurityGuide",
    "quote": "OWASP Top 10 for Agentic Applications 2026 (released December 10, 2025)",
    "language": "en",
    "trust": "высокий",
    "summaryRu": "идентификация критических уязвимостей и векторов атак",
    "generated": false
   },
   {
    "id": "s4-1",
    "title": "github.com",
    "date": "2025-12-10",
    "type": "статья",
    "url": "https://github.com/requie/LLMSecurityGuide",
    "quote": "Released at Black Hat Europe on December 10, 2025, this globally peer-reviewed framework identifies critical security risks facing autonomous AI systems",
    "language": "en",
    "trust": "высокий",
    "summaryRu": "идентификация критических уязвимостей и векторов атак",
    "generated": false
   }
  ]
 },
 {
  "id": "t5",
  "name": "автоматизированное тестирование на проникновение (red teaming) ИИ-систем",
  "definition": "симуляция реалистичных, граничных и враждебных взаимодействий для выявления отказов и рисков",
  "signal": 56,
  "firstYear": 2024,
  "series": [
   0,
   0,
   0,
   2,
   3
  ],
  "stage": "продукт",
  "kind": "ранний сигнал",
  "bank": "Требует экспертной проверки",
  "features": {
   "nT": 5,
   "logGrowth": 0.6,
   "share": 0.0,
   "shareGrowth": 0.0,
   "age": 27.5,
   "orgs": 2,
   "hhi": 0.0,
   "coverage": 2,
   "novelty": 7.0
  },
  "reasons": [
   "термину 27.5 мес.",
   "свежих упоминаний 60%",
   "тихо: всего 5 упоминаний",
   "два игрока"
  ],
  "claims": [
   {
    "label": "Механизм",
    "text": "симуляция реалистичных, граничных и враждебных взаимодействий для выявления отказов и рисков",
    "status": "supported",
    "sourceId": "s5-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "термину 27.5 мес.",
    "status": "supported",
    "sourceId": "s5-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "свежих упоминаний 60%",
    "status": "supported",
    "sourceId": "s5-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "тихо: всего 5 упоминаний",
    "status": "supported",
    "sourceId": "s5-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "два игрока",
    "status": "supported",
    "sourceId": "s5-0"
   }
  ],
  "sources": [
   {
    "id": "s5-0",
    "title": "newmarketpitch.com",
    "date": "2024-06-13",
    "type": "статья",
    "url": "https://newmarketpitch.com/blogs/news/ai-governance-funding-deals",
    "quote": "Provides AI assurance software that simulates realistic, edge-case and adversarial interactions to uncover failures and risks before and after deployment.",
    "language": "en",
    "trust": "низкий",
    "summaryRu": "симуляция реалистичных, граничных и враждебных взаимодействий для выявления отказов и рисков",
    "generated": false
   },
   {
    "id": "s5-1",
    "title": "newmarketpitch.com",
    "date": "2024-06-13",
    "type": "статья",
    "url": "https://newmarketpitch.com/blogs/news/ai-governance-funding-deals",
    "quote": "Provides adversarial AI evaluation, continuous automated red teaming and runtime protection for frontier models, agents and enterprise AI deployments.",
    "language": "en",
    "trust": "низкий",
    "summaryRu": "симуляция реалистичных, граничных и враждебных взаимодействий для выявления отказов и рисков",
    "generated": false
   }
  ]
 },
 {
  "id": "t6",
  "name": "услуга по картированию и тестированию ИИ-агентов и рабочих процессов",
  "definition": "картирование ИИ-приложений и агентов, тестирование промптов, инструментов и бизнес-процессов с превращением результатов в воспроизводимые доказательства",
  "signal": 48,
  "firstYear": 2025,
  "series": [
   0,
   0,
   0,
   4,
   0
  ],
  "stage": "продукт",
  "kind": "ранний сигнал",
  "bank": "Требует экспертной проверки",
  "features": {
   "nT": 4,
   "logGrowth": 0.0,
   "share": 0.0,
   "shareGrowth": 0.0,
   "age": 19.6,
   "orgs": 1,
   "hhi": 0.0,
   "coverage": 1,
   "novelty": 6.0
  },
  "reasons": [
   "термин молодой: 2025-02-08",
   "тихо: всего 4 упоминаний"
  ],
  "claims": [
   {
    "label": "Механизм",
    "text": "картирование ИИ-приложений и агентов, тестирование промптов, инструментов и бизнес-процессов с превращением результатов в воспроизводимые доказательства",
    "status": "supported",
    "sourceId": "s6-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "термин молодой: 2025-02-08",
    "status": "supported",
    "sourceId": "s6-0"
   },
   {
    "label": "Признак ранней стадии",
    "text": "тихо: всего 4 упоминаний",
    "status": "supported",
    "sourceId": "s6-0"
   }
  ],
  "sources": [
   {
    "id": "s6-0",
    "title": "generalanalysis.com",
    "date": "2025-02-08",
    "type": "статья",
    "url": "https://generalanalysis.com/guides/best-ai-red-teaming-tools",
    "quote": "General Analysis maps AI applications and agents, red teams prompts, retrieval, tools, MCP servers, browser actions, permissions, and business workflows, then turns findings into evidence your team can reproduce and retest.",
    "language": "en",
    "trust": "низкий",
    "summaryRu": "картирование ИИ-приложений и агентов, тестирование промптов, инструментов и бизнес-процессов с превращением результатов в воспроизводимые доказательства",
    "generated": false
   }
  ]
 }
];

export const genAnalyses: Analysis[] = [
 {
  "id": "20260926-18134",
  "query": "слабые сигналы в защите искусственного интеллекта",
  "year": 2026,
  "status": "completed",
  "count": 7,
  "updated": "2026-09-26"
 }
];

export const genExcluded = [
 {
  "name": "49 кандидатов",
  "reason": "отбраковано: недостаточно данных о термине",
  "kind": "шум"
 },
 {
  "name": "29 кандидатов",
  "reason": "отбраковано: масштабировано",
  "kind": "зрелое"
 },
 {
  "name": "9 кандидатов",
  "reason": "отбраковано: слишком громкое",
  "kind": "хайп"
 },
 {
  "name": "24 кандидатов",
  "reason": "отбраковано: термину больше четырёх лет",
  "kind": "зрелое"
 },
 {
  "name": "2 кандидатов",
  "reason": "слабый кандидат",
  "kind": "шум"
 }
] as Array<{
  name: string; reason: string; kind: "зрелое" | "хайп" | "шум";
}>;

export const genPoolSize = 180;

/** Воронка последнего прогона: настоящие счётчики, а не оформительские числа. */
export const genFunnel = {
 "queries": 36,
 "hits": 360,
 "urls": 64,
 "documents": 53,
 "candidates": 84,
 "measured": 120,
 "top": 7,
 "cost": 60.09
};

/** План поиска: то, на что конвейер разбил направление перед поиском. */
export const genPlan: string[] = [
 "grounded (40 сниппетов",
 "Agentic AI Security",
 "LLM Application Security",
 "AI Posture Management",
 "AI Supply Chain Security",
 "AI Compliance and Regulatory Governance",
 "AI Red Teaming and Adversarial Testing",
 "Sovereign AI Infrastructure",
 "Hardware-Anchored AI Security",
 "AI Model Risk Assessment",
 "Secure AI Lifecycle Management",
 "Prompt Injection Defense",
 "AI Developer Governance",
 "AI Agent Access Control"
];
