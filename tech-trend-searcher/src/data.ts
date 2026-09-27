import { genTrends, genAnalyses, genExcluded, genPoolSize } from "./generated";

export type ClaimStatus = "supported" | "unsupported" | "hypothesis";

export type Stage = "исследование" | "прототип" | "патенты" | "продукт";

export type SignalKind = "ранний сигнал" | "хайп" | "на слуху";

export type Trust = "высокий" | "средний" | "низкий";

export interface Source {
  id: string;
  title: string;
  date: string;
  type: "статья" | "препринт" | "патент" | "отчёт" | "пресс-релиз";
  url: string;
  quote: string;
  language: "ru" | "en";
  trust: Trust;
  summaryRu: string;
  generated: boolean;
}

export interface Claim {
  label: string;
  text: string;
  status: ClaimStatus;
  sourceId?: string;
}

export interface Features {
  nT: number;
  logGrowth: number;
  share: number;
  shareGrowth: number;
  age: number | null;
  orgs: number;
  hhi: number;
  coverage: number;
  novelty: number;
}

export interface Trend {
  id: string;
  name: string;
  definition: string;
  signal: number;
  firstYear: number;
  series: number[];
  stage: Stage;
  kind: SignalKind;
  bank: string;
  features: Features;
  reasons: string[];
  claims: Claim[];
  sources: Source[];
}

export interface Analysis {
  id: string;
  query: string;
  year: number;
  status: "completed" | "running" | "partial";
  count: number;
  updated: string;
}

export interface TopicGroup {
  id: string;
  title: string;
  phrases: string[];
}

const mockAnalyses: Analysis[] = [
  {
    id: "ai",
    query: "Технологии в ИИ",
    year: 2025,
    status: "completed",
    count: 15,
    updated: "12.09.2026",
  },
  {
    id: "sec",
    query: "Кибербезопасность",
    year: 2025,
    status: "completed",
    count: 12,
    updated: "10.09.2026",
  },
  {
    id: "pay",
    query: "Платежи",
    year: 2025,
    status: "running",
    count: 0,
    updated: "13.09.2026",
  },
];

export const analyses: Analysis[] = genAnalyses.length ? genAnalyses : mockAnalyses;

export const topicGroups: TopicGroup[] = [
  {
    id: "emb",
    title: "Научные эмбеддинги и поиск",
    phrases: ["scientific embeddings", "paper retrieval", "citation graph"],
  },
  {
    id: "ground",
    title: "Проверка фактов и цитат",
    phrases: ["citation verification", "grounded RAG", "claim detection"],
  },
  {
    id: "priv",
    title: "Конфиденциальный инференс",
    phrases: ["TEE inference", "confidential computing", "CPU TEE"],
  },
  {
    id: "pat",
    title: "Патентная аналитика",
    phrases: ["patent family graph", "TRLmapping", "drawing embeddings"],
  },
  {
    id: "burst",
    title: "Детекция вспышек",
    phrases: ["Kleinberg burst", "preprint surge", "topic acceleration"],
  },
  {
    id: "lab",
    title: "Лабораторные агенты",
    phrases: ["lab protocol agents", "wet lab orchestration"],
  },
  {
    id: "edge",
    title: "Энергия и край",
    phrases: ["training energy budget", "neuromorphic embeddings"],
  },
  {
    id: "fed",
    title: "Федеративное обучение корпусов",
    phrases: ["federated patent corpus", "cross-silo embeddings"],
  },
];

const src = (
  id: string,
  title: string,
  date: string,
  type: Source["type"],
  url: string,
  quote: string,
  extra?: Partial<Pick<Source, "language" | "trust" | "summaryRu" | "generated">>
): Source => {
  const isRu = extra?.language === "ru" || /[а-яё]/i.test(`${title} ${quote}`);
  return {
    id,
    title,
    date,
    type,
    url,
    quote,
    language: extra?.language ?? (isRu ? "ru" : "en"),
    trust: extra?.trust ?? (type === "пресс-релиз" ? "низкий" : "высокий"),
    summaryRu:
      extra?.summaryRu ??
      (isRu
        ? quote
        : "Русское резюме: документ подтверждает ранний рост темы и отделяет её от обзорной зрелости."),
    generated: extra?.generated ?? !isRu,
  };
};

export const trends: Trend[] = [
  {
    id: "cite-ground",
    name: "Самопроверка цитат в поисковых контурах",
    definition:
      "Модель не отдаёт утверждение, пока цитата не совпала с сохранённым фрагментом документа.",
    signal: 91,
    firstYear: 2023,
    series: [4, 9, 18, 41, 67],
    stage: "прототип",
    kind: "ранний сигнал",
    bank: "Контроль галлюцинаций в аналитике банка",
    features: {
      nT: 67,
      logGrowth: 1.12,
      share: 0.0041,
      shareGrowth: 0.86,
      age: 2,
      orgs: 14,
      hhi: 0.18,
      coverage: 0.81,
      novelty: 0.8,
    },
    reasons: [
      "Доля в направлении выросла в 2,1 раза за три полных года",
      "14 независимых организаций, концентрация низкая",
      "Первое устойчивое упоминание — 2023, возраст 2 года",
    ],
    claims: [
      {
        label: "Проблема",
        text: "Поисковые контуры подставляют правдоподобные ссылки, которых нет в корпусе.",
        status: "supported",
        sourceId: "s1",
      },
      {
        label: "Преимущество",
        text: "Каждое утверждение привязано к фрагменту и отклоняется без совпадения.",
        status: "supported",
        sourceId: "s2",
      },
      {
        label: "Кейс",
        text: "Группа AllenAI проверяет ответы на совпадение с цитатой в OpenScholar.",
        status: "supported",
        sourceId: "s1",
      },
      {
        label: "Для банка",
        text: "Слой можно поставить перед карточкой тренда, чтобы скрывать поле без источника.",
        status: "hypothesis",
      },
    ],
    sources: [
      src(
        "s1",
        "OpenScholar: grounded scientific QA",
        "2024-05-12",
        "препринт",
        "https://arxiv.org/abs/2405.00001",
        "Answers without a verbatim supporting span are discarded before display.",
        {
          summaryRu:
            "Ответ без дословного совпадения с фрагментом документа отбрасывается до показа пользователю.",
          generated: true,
        }
      ),
      src(
        "s2",
        "Citation fidelity in retrieval-augmented generation",
        "2024-11-03",
        "статья",
        "https://arxiv.org/abs/2411.00002",
        "Exact span match reduces unsupported claims more than n-gram overlap.",
        {
          summaryRu:
            "Точное совпадение цитаты снижает долю неподтверждённых утверждений сильнее, чем пересечение n-грамм.",
          generated: true,
        }
      ),
      src(
        "s3",
        "Способ проверки цитат в выдаче поиска",
        "2025-02-18",
        "патент",
        "https://patents.google.com/patent/US20250011111",
        "Средство отклоняет предложение, если ни один сохранённый фрагмент не равен указанной цитате.",
        { language: "ru", generated: false }
      ),
    ],
  },
  {
    id: "tee-infer",
    name: "Конфиденциальный инференс на CPU-TEE",
    definition:
      "Запуск модели внутри анклава процессора, чтобы текст клиента не покидал защищённую область.",
    signal: 88,
    firstYear: 2022,
    series: [6, 11, 19, 33, 52],
    stage: "патенты",
    kind: "ранний сигнал",
    bank: "Разбор документов без выноса текста из контура",
    features: {
      nT: 52,
      logGrowth: 0.94,
      share: 0.0032,
      shareGrowth: 0.71,
      age: 3,
      orgs: 11,
      hhi: 0.22,
      coverage: 0.74,
      novelty: 0.7,
    },
    reasons: [
      "Рост доли устойчивый при низкой видимости",
      "Патентные семьи появились у трёх независимых заявителей",
      "Возраст 3 года, ещё не обзорная зрелость",
    ],
    claims: [
      {
        label: "Проблема",
        text: "Облачный инференс раскрывает сырой текст третьей стороне.",
        status: "supported",
        sourceId: "t1",
      },
      {
        label: "Преимущество",
        text: "Анклав держит промпт и веса в памяти, недоступной гипервизору.",
        status: "supported",
        sourceId: "t2",
      },
      {
        label: "Кейс",
        text: "Исследование ETH Zurich измеряет накладные расходы LLM в Intel TDX.",
        status: "supported",
        sourceId: "t1",
      },
      {
        label: "Для банка",
        text: "Подходит для разбора внутренних отчётов, если появится прямой источник внедрения.",
        status: "hypothesis",
      },
    ],
    sources: [
      src(
        "t1",
        "LLM inference inside CPU trusted execution",
        "2024-08-21",
        "препринт",
        "https://arxiv.org/abs/2408.00003",
        "TDX enclaves keep prompts out of host memory at 1.4× latency.",
        {
          summaryRu:
            "Анклавы TDX удерживают текст запроса вне памяти хоста при задержке около 1,4 раза.",
          generated: true,
        }
      ),
      src(
        "t2",
        "Confidential inference system",
        "2025-01-09",
        "патент",
        "https://patents.google.com/patent/US20250022222",
        "Model weights and user tokens reside only in enclave DRAM.",
        {
          summaryRu: "Веса модели и токены пользователя хранятся только в памяти анклава.",
          generated: true,
        }
      ),
    ],
  },
  {
    id: "kleinberg",
    name: "Детекция вспышек Клейнберга в препринтах",
    definition:
      "Статистический поиск резкого учащения темы в потоке arXiv до того, как она попадёт в обзоры.",
    signal: 86,
    firstYear: 2021,
    series: [8, 12, 21, 29, 48],
    stage: "исследование",
    kind: "ранний сигнал",
    bank: "Ранний контур мониторинга научных тем",
    features: {
      nT: 48,
      logGrowth: 0.88,
      share: 0.0029,
      shareGrowth: 0.64,
      age: 4,
      orgs: 9,
      hhi: 0.16,
      coverage: 0.9,
      novelty: 0.6,
    },
    reasons: [
      "Вспышка на потоке 2024–2025 подтверждена правилом Клейнберга",
      "Девять лабораторий, низкая концентрация",
      "Доля всё ещё ниже 75-го перцентиля видимости",
    ],
    claims: [
      {
        label: "Проблема",
        text: "Сглаженные средние опаздывают и ловят уже шумный рост.",
        status: "supported",
        sourceId: "k1",
      },
      {
        label: "Преимущество",
        text: "Двухсостояние модели потока отмечает смену интенсивности раньше скользящего окна.",
        status: "supported",
        sourceId: "k2",
      },
      {
        label: "Кейс",
        text: "Работа CWTS применяет burst detection к категориям cs.LG и cs.CR.",
        status: "supported",
        sourceId: "k1",
      },
    ],
    sources: [
      src(
        "k1",
        "Burst detection on preprint streams",
        "2024-03-02",
        "статья",
        "https://arxiv.org/abs/2403.00004",
        "Kleinberg bursts precede review-paper mentions by 11–18 months.",
        {
          summaryRu:
            "Вспышки по Клейнбергу опережают упоминания в обзорных статьях на 11–18 месяцев.",
          generated: true,
        }
      ),
      src(
        "k2",
        "Bursty and hierarchical structure in streams",
        "2002-07-01",
        "статья",
        "https://www.cs.cornell.edu/home/kleinber/bhs.pdf",
        "An infinite-state automaton models rate changes in document streams.",
        {
          summaryRu:
            "Автомат с бесконечным числом состояний моделирует смену интенсивности потока документов.",
          generated: true,
        }
      ),
    ],
  },
];

const extras: Array<Pick<Trend, "id" | "name" | "definition" | "signal" | "firstYear" | "stage" | "kind">> = [
  {
    id: "specter-dyn",
    name: "Динамические эмбеддинги корпуса SPECTER",
    definition: "Вектор статьи пересчитывается при появлении новых цитат, а не один раз при публикации.",
    signal: 84,
    firstYear: 2023,
    stage: "исследование",
    kind: "ранний сигнал",
  },
  {
    id: "neuro-sym",
    name: "Нейросимволическая проверка цепочек рассуждений",
    definition: "Логический слой отбраковывает шаг модели, если он нарушает заданные правила.",
    signal: 83,
    firstYear: 2022,
    stage: "прототип",
    kind: "ранний сигнал",
  },
  {
    id: "cite-diff",
    name: "Диффузия темы по графу цитирования",
    definition: "Скорость перехода темы между сообществами измеряется как сигнал выхода из лаборатории.",
    signal: 81,
    firstYear: 2023,
    stage: "исследование",
    kind: "ранний сигнал",
  },
  {
    id: "lab-agent",
    name: "Агентная оркестрация лабораторных протоколов",
    definition: "Агент собирает шаги эксперимента из протоколов и сверяет их с журналом установки.",
    signal: 79,
    firstYear: 2024,
    stage: "прототип",
    kind: "ранний сигнал",
  },
  {
    id: "pq-model",
    name: "Квантово-устойчивые подписи весов модели",
    definition: "Веса подписываются постквантовой схемой, чтобы подмена чекпоинта была видна.",
    signal: 77,
    firstYear: 2023,
    stage: "патенты",
    kind: "ранний сигнал",
  },
  {
    id: "energy",
    name: "Энергетические бюджеты обучения на грани",
    definition: "Обучение останавливается по джоулям, а не только по числу шагов.",
    signal: 75,
    firstYear: 2022,
    stage: "исследование",
    kind: "ранний сигнал",
  },
  {
    id: "causal-pat",
    name: "Каузальные графы патентных семей",
    definition: "Связь «публикация → семья → продукт» строится как лаг, а не как ключевые слова.",
    signal: 74,
    firstYear: 2023,
    stage: "прототип",
    kind: "ранний сигнал",
  },
  {
    id: "synth-trial",
    name: "Синтетические когортные испытания моделей",
    definition: "Модель гоняют по датированному срезу прошлого, как по клинической когорте.",
    signal: 72,
    firstYear: 2024,
    stage: "исследование",
    kind: "ранний сигнал",
  },
  {
    id: "neuro-emb",
    name: "Нейроморфные ускорители эмбеддингов",
    definition: "Спайковые чипы считают близость документов при ваттах, недоступных GPU.",
    signal: 70,
    firstYear: 2021,
    stage: "патенты",
    kind: "на слуху",
  },
  {
    id: "fed-pat",
    name: "Федеративное обучение на патентных корпусах",
    definition: "Ведомства считают общий вектор, не отдавая полные тексты заявок.",
    signal: 69,
    firstYear: 2022,
    stage: "прототип",
    kind: "ранний сигнал",
  },
  {
    id: "trl-map",
    name: "Автоматическое картирование готовности технологии",
    definition: "Стадия TRL оценивается по смеси грантов, патентов и репозиториев.",
    signal: 67,
    firstYear: 2023,
    stage: "прототип",
    kind: "ранний сигнал",
  },
  {
    id: "draw-emb",
    name: "Эмбеддинги патентных чертежей",
    definition: "Рисунок схемы становится вектором и ищется вместе с текстом формулы.",
    signal: 65,
    firstYear: 2024,
    stage: "исследование",
    kind: "ранний сигнал",
  },
];

function fillTrend(base: (typeof extras)[number], index: number): Trend {
  const nT = 64 - index * 3;
  return {
    ...base,
    series: [3, 7, 12, 20, nT],
    bank: "Гипотеза для технологической разведки банка",
    features: {
      nT,
      logGrowth: 0.8 - index * 0.03,
      share: 0.0028 - index * 0.0001,
      shareGrowth: 0.6 - index * 0.02,
      age: 2025 - base.firstYear,
      orgs: 8,
      hhi: 0.2,
      coverage: 0.7,
      novelty: Math.max(0, 1 - (2025 - base.firstYear) / 10),
    },
    reasons: [
      "Рост доли за три полных года",
      "Не менее двух независимых организаций",
      `Первое найденное упоминание — ${base.firstYear}`,
    ],
    claims: [
      {
        label: "Проблема",
        text: "Тема закрывает разрыв, который плохо виден обычным поиском по ключевым словам.",
        status: "supported",
        sourceId: `${base.id}-a`,
      },
      {
        label: "Преимущество",
        text: "Появляется измеримый ранний сигнал до обзорных статей.",
        status: "supported",
        sourceId: `${base.id}-b`,
      },
      {
        label: "Кейс",
        text: "Исследовательская группа публикует открытый конвейер по теме.",
        status: "supported",
        sourceId: `${base.id}-a`,
      },
      {
        label: "Для банка",
        text: "Связь с продуктом банка пока гипотеза аналитика.",
        status: "hypothesis",
      },
    ],
    sources: [
      src(
        `${base.id}-a`,
        `${base.name}: обзор сигнала`,
        "2024-09-01",
        "препринт",
        "https://arxiv.org/abs/2409.00010",
        "The topic remains below review visibility while its share grows.",
        {
          summaryRu:
            "Тема остаётся ниже обзорной видимости, при этом её доля в направлении растёт.",
          generated: true,
        }
      ),
      src(
        `${base.id}-b`,
        `${base.name}: метод измерения`,
        "2025-01-15",
        "статья",
        "https://arxiv.org/abs/2501.00011",
        "Independent organizations adopt the method without a single lab monopoly.",
        {
          summaryRu:
            "Независимые организации перенимают метод, без монополии одной лаборатории.",
          generated: true,
        }
      ),
    ],
  };
}

const mockTrends: Trend[] = [
  ...trends,
  ...extras.map((item, index) => fillTrend(item, index)),
];

// Настоящие результаты прогонов радара; макет остаётся запасным вариантом.
export const allTrends: Trend[] = genTrends.length ? genTrends : mockTrends;
export const isRealData = genTrends.length > 0;

export const searchStats = {
  candidates: genPoolSize || 186,
  sources: allTrends.reduce((sum, item) => sum + item.sources.length, 0),
  highConfidence: allTrends.filter((item) => item.signal >= 75).length,
};

const mockExcluded: Array<{
  name: string;
  reason: string;
  kind: "зрелое" | "хайп" | "шум";
}> = [
  {
    name: "Генеративный ИИ как массовый продукт",
    reason: "Сформированный рынок и выраженные лидеры. Не ранняя стадия.",
    kind: "зрелое",
  },
  {
    name: "Облачные GPU-фермы",
    reason: "Массовое внедрение и отраслевой стандарт инфраструктуры.",
    kind: "зрелое",
  },
  {
    name: "Чат-боты клиентского сервиса",
    reason: "Устойчивое конкурентное разделение, рынок уже поделён.",
    kind: "зрелое",
  },
  {
    name: "Трансформеры для текста",
    reason: "Обзорная зрелость и тысячи работ в год. Штраф за зрелость.",
    kind: "зрелое",
  },
  {
    name: "ИИ-революция в банках 2026",
    reason: "Пресс-релиз без независимого научного или патентного источника.",
    kind: "хайп",
  },
  {
    name: "Квантовый интернет для всех",
    reason: "Медиа-шум высокий, патентная и научная база слабая.",
    kind: "хайп",
  },
  {
    name: "Автопилот в каждом приложении",
    reason: "Агрегаторы и блоги без первоисточника. Доверие низкое.",
    kind: "шум",
  },
  {
    name: "Нейросеть, которая заменит аналитика",
    reason: "Рекламная публикация. В топ не включается как единственное основание.",
    kind: "шум",
  },
];

export const excludedItems = genExcluded.length ? genExcluded : mockExcluded;

export const thresholdRejects = [
  "Мультиагентные обёртки без корпуса",
  "Универсальный корпоративный ассистент",
  "Голосовой ИИ в колл-центре",
  "Авторазметка любых документов",
  "Отраслевой стандарт OpenAPI для моделей",
];

export function trendTrust(trend: Trend): Trust {
  if (trend.sources.some((item) => item.trust === "низкий") && trend.sources.length < 2) {
    return "низкий";
  }
  if (trend.sources.every((item) => item.trust === "высокий")) return "высокий";
  return "средний";
}

export function trendById(id: string) {
  return allTrends.find((item) => item.id === id);
}

export function sourceById(trend: Trend, id?: string) {
  return trend.sources.find((item) => item.id === id);
}

/**
 * Что измерено на самом деле. Здесь раньше стоял бэктест с предсказаниями 2018–2020
 * годов, которых система не делала: цифры были оформительскими. Показывать жюри
 * выдуманное доказательство работоспособности нельзя, поэтому таблица заменена на
 * фактические замеры с указанием, чем именно они получены.
 */
export const measurements: Array<{
  metric: string;
  value: string;
  how: string;
  caveat: string;
}> = [
  {
    metric: "Покрытие эталона, «Защита ИИ»",
    value: "7 из 16",
    how: "Оценка модели-судьи по сохранённому прогону 27.09; показ пяти ближайших кандидатов на категорию.",
    caveat: "Это оценка сверху. Подтверждённых человеком пар — 2. Судья мягче эксперта.",
  },
  {
    metric: "Покрытие эталона, «Финтех»",
    value: "7 из 17",
    how: "Тот же судья, тот же конвейер, план по нерешённым проблемам области.",
    caveat: "План по сегментам отрасли на той же области давал 2 из 17.",
  },
  {
    metric: "Разброс между повторами",
    value: "7 и 5 из 16",
    how: "Два прогона одной конфигурации по «Защите ИИ» 26.09.",
    caveat: "Совпали 4 категории из 8. Одиночное число нельзя читать точнее, чем ±2.",
  },
  {
    metric: "Оценка достижимого по Чепмену",
    value: "8,6 ± 1,0",
    how: "Метод повторного отлова по двум повторам: (7+1)(5+1)/(4+1)−1.",
    caveat: "Метод предполагает независимость попыток; у нас одна конфигурация, поэтому оценка занижена и не является доказанным пределом.",
  },
  {
    metric: "Доля страниц с извлечённым текстом",
    value: "69–91 %",
    how: "Счётчики воронки по живым прогонам 26–27.09.",
    caveat: "Запросы по формулировкам проблем ведут на более тяжёлые страницы, доля падает.",
  },
  {
    metric: "Стоимость одного прогона области",
    value: "55–65 ₽",
    how: "Расчёт по тарифам поиска и модели, записанный в манифест прогона.",
    caveat: "Расчёт по тарифам, а не сверка со счётом провайдера.",
  },
];
