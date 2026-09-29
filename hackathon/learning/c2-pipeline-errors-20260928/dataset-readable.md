# Набор C2: читаемый экспорт

Записей 44, срез 2026-09-27. Метки не назначены; тип дефекта — гипотеза.

## 1. приобретение платежной инфраструктуры традиционными банками

- **ID**: `d125ca50f91498ab13f0f663`  ·  область: Финтех
- **Механизм**: приобретение
- **Применение**: платежная инфраструктура
- **Источник**: [Fintech M&A Market Report 2026 | Windsor Drake](https://windsordrake.com/fintech-ma-market-report/)  ·  дата публикации: не установлена  ·  дата события из извлечения: 2025-12-31
- **Цитата дословно**: «Traditional players like J. Safra Sarasin and FIS are also staying active, hunting for digital transformation capabilities.»
- **Предложенный тип дефекта**: `broad_topic_no_mechanism` — механизм длиной 12 знаков не описывает способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 2. инструменты поиска стартапов через живой веб-скрейпинг

- **ID**: `e920b944b3fbe1befbd8b4d5`  ·  область: Защита ИИ
- **Механизм**: поиск и агрегация данных из живых веб-источников (Crunchbase, TechCrunch, Twitter, страницы найма) с использованием ИИ-агентов для обхода ограничений статических баз данных
- **Применение**: данные о стартапах и их финансировании
- **Источник**: [Find AI Agent Startups Raising Seed Funding (2026 Guide)](https://origami.chat/blog/ai-agent-startups-seed-funding)  ·  дата публикации: 2026-05-03
- **Цитата дословно**: «Origami searches the live web for every query. Instead of filtering a static database, it crawls recent funding announcements on Crunchbase, TechCrunch, and founder Twitter accounts.»
- **Предложенный тип дефекта**: `review_not_new_result` — источник — обзор или подборка, а не сообщение о новом результате
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 3. федеративное обучение для обнаружения мошенничества в платежах

- **ID**: `cadfec2fab12d1bb7206c03f`  ·  область: Финтех
- **Механизм**: обучение общей модели на данных нескольких институтов без раскрытия сырых транзакционных данных
- **Применение**: данные о транзакциях
- **Источник**: [Payment Security in 2026: How to Use AI for Fraud Detection](https://colibrix.one/post/how-ai-is-securing-b2b-payments-in-2026)  ·  дата публикации: не установлена
- **Цитата дословно**: «Trains a shared model across institutions without exposing raw transaction data. Boosts detection accuracy — one study showed 99% accuracy with federated learning vs. 95% with local models alone.»
- **Предложенный тип дефекта**: `wrong_date_or_scale` — машинная причина отказа: «отбраковано: термину 189 лет при 64041 упоминаниях — это не зарождающееся понятие» — возраст термина не соответствует заявленной новизне механизма
- **Вердикт сервиса**: отбраковано: термину 189 лет при 64041 упоминаниях — это не зарождающееся понятие
- **Решение человека**: _не принято_

## 4. Атаки вывода членства

- **ID**: `888bd013fc722caa7654aa5d`  ·  область: Защита ИИ
- **Механизм**: Анализ ответов модели (потери, уверенности, предсказаний) для определения того, был ли конкретный образец включен в обучающую выборку
- **Применение**: Модели машинного обучения
- **Источник**: [Membership Inference Attacks: AI Privacy Risks Explained](https://www.ultralytics.com/glossary/membership-inference-attacks)  ·  дата публикации: 2026-09-22
- **Цитата дословно**: «Membership inference attacks are privacy attacks that determine whether a particular record was included in a model’s training dataset.»
- **Предложенный тип дефекта**: `attack_instead_of_defense` — в названии описан способ атаки, а запрос был о защите
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 5. архитектура изоляции контента для разделения обработки и генерации

- **ID**: `f93e1f2e83c28c9a4c84d615`  ·  область: Защита ИИ
- **Механизм**: разделение модели, извлекающей информацию, и модели, генерирующей ответы, чтобы скрыть сырые данные от генератора
- **Применение**: LLM-инфраструктура
- **Источник**: [Indirect Prompt Injection: The Hidden Attack Vector in RAG & Agents (2026) | AI Safety Directory](https://aisecurityandsafety.org/en/guides/indirect-prompt-injection/)  ·  дата публикации: не установлена
- **Цитата дословно**: «Content isolation architectures separate the model instance that processes retrieved data from the model instance that generates user-facing responses.»
- **Предложенный тип дефекта**: `measurement_failure_not_card_defect` — фильтр отказал по причине «упоминаний не найдено по этой формулировке»: это состояние замера, а не установленный дефект карточки
- **Вердикт сервиса**: упоминаний не найдено по этой формулировке
- **Решение человека**: _не принято_

## 6. практика красного тестирования систем ИИ

- **ID**: `4391f71f9cdd4afc4181e36c`  ·  область: Защита ИИ
- **Механизм**: структурированное проактивное тестирование безопасности с симуляцией враждебных атак экспертными группами
- **Применение**: системы искусственного интеллекта
- **Источник**: [GitHub - requie/AI-Red-Teaming-Guide: A comprehensive guide to adversarial testing and security evaluation of AI systems, helping organizations identify vulnerabilities before attackers exploit them. ](https://github.com/requie/AI-Red-Teaming-Guide)  ·  дата публикации: не установлена
- **Цитата дословно**: «A comprehensive guide to adversarial testing and security evaluation of AI systems, helping organizations identify vulnerabilities before attackers exploit them.»
- **Предложенный тип дефекта**: `general_advice_not_technology` — в названии слово «практика»: описан подход или рамка, а не способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 7. обнаружение инсайдерских угроз через объединение поведенческих, идентификационных и технических сигналов

- **ID**: `189f001aaffae1c961dae084`  ·  область: Защита ИИ
- **Механизм**: корреляция и анализ поведенческих индикаторов (язык, контекст), идентификационных данных (статус, доступ) и технической телеметрии (доступы, попытки эксфильтрации) для формирования единого сигнала риска
- **Применение**: инсайдерские угрозы и поведение сотрудников
- **Источник**: [How AI is Becoming the Next Insider Threat in 2026 | Proofpoint US](https://www.proofpoint.com/us/blog/information-protection/ai-next-insider-threat-turning-point-for-insider-risk)  ·  дата публикации: 2026-01-14
- **Цитата дословно**: «In 2026, organizations will stop treating human signals, identity data, and technical events as separate streams. The next evolution of insider risk management depends on connecting these areas»
- **Предложенный тип дефекта**: `promise_not_event` — цитата говорит о планах или ожиданиях, а не о состоявшемся событии
- **Вердикт сервиса**: термину 14 лет: проверьте, не старое ли это понятие под новым применением
- **Решение человека**: _не принято_

## 8. интеграция NGFW с платформой СКДПУ НТ

- **ID**: `f04cb371417b4c72b3df3d1c`  ·  область: Защита ИИ
- **Механизм**: совместимость
- **Применение**: платформа СКДПУ НТ
- **Источник**: [Ideco NGFW](https://www.tadviser.ru/index.php/%D0%9F%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82:Ideco_NGFW)  ·  дата публикации: не установлена
- **Цитата дословно**: «Совместимость с платформой СКДПУ НТ»
- **Предложенный тип дефекта**: `broad_topic_no_mechanism` — механизм длиной 13 знаков не описывает способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 9. применение ИИ для автоматизации процессов финансового управления, рисков и соответствия

- **ID**: `56cbb9324655171f6e4fe78f`  ·  область: Финтех
- **Механизм**: применение ИИ для ускорения рутинных задач GRC, включая картирование нормативных изменений, оценку рисков и генерацию аудиторских отчетов
- **Применение**: процессы финансового управления, рисков и соответствия (GRC)
- **Источник**: [IBM named a Leader in the 2026 IDC MarketScape for Worldwide AI-Enabled Financial Governance, Risk, and Compliance](https://www.ibm.com/new/announcements/ibm-named-a-leader-in-the-2026-idc-marketscape-for-worldwide-ai-enabled-financial-governance-risk-and-compliance)  ·  дата публикации: 2026-07-29  ·  дата события из извлечения: 2026-07-29
- **Цитата дословно**: «IBM watsonx.governance and IBM OpenPages help finance, risk and audit teams connect controls, compliance and enterprise risk while applying AI to time-intensive GRC workflows.»
- **Предложенный тип дефекта**: `review_not_new_result` — источник — обзор или подборка, а не сообщение о новом результате
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 10. обеспечение соответствия требованиям регуляторов и устранение предвзятости моделей

- **ID**: `cd2094575a75870fbb11cc54`  ·  область: Защита ИИ
- **Механизм**: проведение регулярных аудитов справедливости, генерация отчетов об объяснимости и ведение неизменяемых журналов аудита
- **Применение**: выводы моделей и процессы принятия решений
- **Источник**: [AI Risk Mitigation: Tools and Strategies for 2026](https://www.sentinelone.com/cybersecurity-101/data-and-ai/ai-risk-mitigation/)  ·  дата публикации: 2025-10-27
- **Цитата дословно**: «Mitigation: Regular fairness audits, explainability reports, and immutable audit trails help demonstrate due diligence.»
- **Предложенный тип дефекта**: `wrong_date_or_scale` — машинная причина отказа: «отбраковано: термину 26 лет при 1002 упоминаниях — это не зарождающееся понятие» — возраст термина не соответствует заявленной новизне механизма
- **Вердикт сервиса**: отбраковано: термину 26 лет при 1002 упоминаниях — это не зарождающееся понятие
- **Решение человека**: _не принято_

## 11. Атаки инверсии модели

- **ID**: `8ea9263fbaf3e1ca197b1c04`  ·  область: Защита ИИ
- **Механизм**: Использование доступа к обученной модели для реконструкции примеров обучающей выборки или вывода конфиденциальных характеристик
- **Применение**: Нейронные сети
- **Источник**: [[2411.10023] Model Inversion Attacks: A Survey of Approaches and Countermeasures](https://arxiv.org/abs/2411.10023)  ·  дата публикации: не установлена
- **Цитата дословно**: «Model inversion attacks (MIAs) exploit access to a trained model to reconstruct training examples or infer privacy-sensitive characteristics represented by the model.»
- **Предложенный тип дефекта**: `attack_instead_of_defense` — в названии описан способ атаки, а запрос был о защите
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 12. ограниченная десериализация в PaddlePaddle через RestrictedUnpickler

- **ID**: `002de05e23e7473c9a459d69`  ·  область: Защита ИИ
- **Механизм**: использование RestrictedUnpickler, разрешающего десериализацию только определенных классов
- **Применение**: модели PaddlePaddle
- **Источник**: [Securing the AI Model Supply Chain: A Practical Defense Guide for 2026 - DEV Community](https://dev.to/young_gao/securing-the-ai-model-supply-chain-a-practical-defense-guide-for-2026-49oo)  ·  дата публикации: 2026-03-22
- **Цитата дословно**: «PaddlePaddle implements a RestrictedUnpickler that only allows specific classes to be deserialized»
- **Предложенный тип дефекта**: `measurement_failure_not_card_defect` — фильтр отказал по причине «упоминаний не найдено по этой формулировке»: это состояние замера, а не установленный дефект карточки
- **Вердикт сервиса**: упоминаний не найдено по этой формулировке
- **Решение человека**: _не принято_

## 13. практики безопасного проектирования (secure-by-design) в разработке ПО для логистики

- **ID**: `538b3272a8a0a66045d18527`  ·  область: Защита ИИ
- **Механизм**: внедрение практик безопасного проектирования на всех этапах разработки
- **Применение**: программное обеспечение для логистики и управления цепочками поставок
- **Источник**: [AI in Supply Chain Security: Why Prevention Beats Detection in 2026](https://www.traxtech.com/ai-in-supply-chain/ai-in-supply-chain-security-why-prevention-beats-detection-in-2026)  ·  дата публикации: 2026-01-07
- **Цитата дословно**: «Organizations should implement secure-by-design practices that build security into every development stage rather than retrofitting it later. This approach prevents vulnerabilities from entering systems in the first place, reducing the attack surface before deployment.»
- **Предложенный тип дефекта**: `general_advice_not_technology` — в названии слово «практики»: описан подход или рамка, а не способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 14. управление идентификацией и делегированными полномочиями автономных ИИ-агентов в финансовом секторе

- **ID**: `f82e34ab762c921f6132d34f`  ·  область: Финтех
- **Механизм**: установление идентичности программного агента, проверка делегированных полномочий, контекстно-зависимый контроль рисков и аудит действий для обеспечения доверия к автономным решениям
- **Применение**: автономные ИИ-агенты
- **Источник**: [AI Agents in Financial Services: A Bank’s Guide | YouVerify](https://youverify.co/en/blogs/ai-agents-financial-services)  ·  дата публикации: 2026-08-18
- **Цитата дословно**: «banks will need a layered trust model combining agent identity, authentication, delegated authorization, context-aware risk controls, continuous monitoring, and audit trails.»
- **Предложенный тип дефекта**: `promise_not_event` — цитата говорит о планах или ожиданиях, а не о состоявшемся событии
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 15. детализированный контроль ИИ-приложений в NGFW

- **ID**: `0159aae7b1b2765b31479613`  ·  область: Защита ИИ
- **Механизм**: детализированный контроль
- **Применение**: ИИ-приложения
- **Источник**: [Ideco NGFW](https://www.tadviser.ru/index.php/%D0%9F%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82:Ideco_NGFW)  ·  дата публикации: не установлена  ·  дата события из извлечения: 2026
- **Цитата дословно**: «Ideco NGFW Novum v23 с детализированным контролем ИИ-приложений»
- **Предложенный тип дефекта**: `broad_topic_no_mechanism` — механизм длиной 25 знаков не описывает способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 16. интеллектуальный анализ данных поставщиков для обеспечения прозрачности

- **ID**: `6f7982e43c190a9511d953a2`  ·  область: Защита ИИ
- **Механизм**: предоставление услуг интеллектуального анализа данных поставщиков
- **Применение**: данные о поставщиках
- **Источник**: [Supply Chain AI Fundraising Guide (2026)](https://startupfundraising.com/supply-chain-ai-fundraising)  ·  дата публикации: не установлена
- **Цитата дословно**: «UFLPA enforcement (Uyghur Forced Labor Prevention Act) forced supplier-transparency investment. Altana ($200M+ raised at $1B+) validated the supplier-intelligence category.»
- **Предложенный тип дефекта**: `review_not_new_result` — источник — обзор или подборка, а не сообщение о новом результате
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 17. защита от инъекций промптов в агентах на базе протокола MCP

- **ID**: `111c6dda2805115916171153`  ·  область: Защита ИИ
- **Механизм**: анализ уязвимостей и применение стратегий смягчения рисков для предотвращения несанкционированного выполнения инструментов и утечки данных
- **Применение**: агенты искусственного интеллекта, использующие Model Context Protocol
- **Источник**: [MCP Security Risks: Key Threats and How to Mitigate Them](https://www.akto.io/blog/mcp-security-risks)  ·  дата публикации: 2026-06-02
- **Цитата дословно**: «Learn the top MCP security risks, including prompt injection, tool poisoning, unauthorized access, and data leakage, plus mitigation strategies.»
- **Предложенный тип дефекта**: `wrong_date_or_scale` — машинная причина отказа: «отбраковано: термину 62 лет при 4147 упоминаниях — это не зарождающееся понятие» — возраст термина не соответствует заявленной новизне механизма
- **Вердикт сервиса**: отбраковано: термину 62 лет при 4147 упоминаниях — это не зарождающееся понятие
- **Решение человека**: _не принято_

## 18. атака типа «отказ в обслуживании» (DoS/DDoS)

- **ID**: `5ff91e86ed1226c236849613`  ·  область: Защита ИИ
- **Механизм**: перегрузка ресурсов или каналов связи для нарушения доступности сервиса
- **Применение**: сервисы и сети
- **Источник**: [What Is a Denial of Service (DoS) Attack? - Palo Alto Networks](https://www.paloaltonetworks.com/cyberpedia/what-is-a-denial-of-service-attack-dos)  ·  дата публикации: не установлена
- **Цитата дословно**: «How Distributed Denial-of-Service Attacks Work»
- **Предложенный тип дефекта**: `attack_instead_of_defense` — в названии описан способ атаки, а запрос был о защите
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 19. обеспечение прослеживаемости (lineage) и сертификации данных для ИИ-агентов в мультиоблачной среде

- **ID**: `67ed1ae1d39da88a07d1385b`  ·  область: Защита ИИ
- **Механизм**: применение сквозной прослеживаемости происхождения данных и единой сертификации бизнес-определений, не зависящей от облачной платформы
- **Применение**: источники данных и бизнес-определения
- **Источник**: [Multicloud AI Agent Governance: A Practical Framework [2026]](https://atlan.com/know/ai-agent/how-to-govern-ai-agents-across-multiple-clouds/)  ·  дата публикации: 2026-09-01
- **Цитата дословно**: «Cross-cloud governance needs shared inventory, shared definitions, portable certification, cross-cloud lineage, and retrieval-time policy enforcement»
- **Предложенный тип дефекта**: `measurement_failure_not_card_defect` — фильтр отказал по причине «упоминаний не найдено по этой формулировке»: это состояние замера, а не установленный дефект карточки
- **Вердикт сервиса**: упоминаний не найдено по этой формулировке
- **Решение человека**: _не принято_

## 20. Методологии тестирования на кибербезопасность ИИ

- **ID**: `f394c409236185ffa76da0db`  ·  область: Защита ИИ
- **Механизм**: Защита целостности модели и безопасности конвейера вывода
- **Применение**: ИИ-системы
- **Источник**: [Technical Safeguards - AI System Accuracy, Robustness & Cybersecurity Compliance](https://technicalsafeguards.com/)  ·  дата публикации: не установлена
- **Цитата дословно**: «Cybersecurity: Model integrity protection, inference pipeline security, data poisoning defenses, access controls»
- **Предложенный тип дефекта**: `general_advice_not_technology` — в названии слово «Методолог»: описан подход или рамка, а не способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 21. ускорение проектирования и тестирования синтетических организмов с помощью ИИ и роботизированных платформ

- **ID**: `2bb1f901b71a04f524ffa19d`  ·  область: Биотехнологии и генетика (открытый запрос, вне таблицы)
- **Механизм**: использование ИИ-систем для анализа геномных и химических данных в сочетании с автоматизированными микрофлюидными и роботизированными системами для проведения экспериментов
- **Применение**: синтетические биологические системы и организмы
- **Источник**: [Engineering Tomorrow: DARPAâs Push into the Frontier of Synthetic Biology](https://www.synbiobeta.com/read/engineering-tomorrow-darpas-push-into-the-frontier-of-synthetic-biology)  ·  дата публикации: 2025-02-04
- **Цитата дословно**: «He believes the field will benefit from synergy with advanced machine learning. Where biology used to be stymied by small sets of data from a single lab, now AI systems can interpret data across thousands of labs and millions of genomes.»
- **Предложенный тип дефекта**: `promise_not_event` — цитата говорит о планах или ожиданиях, а не о состоявшемся событии
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 22. космические технологии обороны

- **ID**: `d92caa27664f2314f709fcda`  ·  область: Защита ИИ
- **Механизм**: использование космических активов
- **Применение**: оборонная инфраструктура
- **Источник**: [33+ Funded Defense Startups (2026)](https://leadmagic.io/funded-startups/defense?trk=article-ssr-frontend-pulse_little-text-block)  ·  дата публикации: не установлена
- **Цитата дословно**: «space-based defense technologies are attracting unprecedented venture capital.»
- **Предложенный тип дефекта**: `broad_topic_no_mechanism` — механизм длиной 33 знаков не описывает способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 23. изоляция системного промпта

- **ID**: `af3f5fe0b3f656e185c5ad5e`  ·  область: Защита ИИ
- **Механизм**: структурное разделение системных инструкций и пользовательских данных
- **Применение**: LLM-приложения
- **Источник**: [What Is Prompt Injection? 2026 Defense Field Guide](https://futureagi.com/blog/what-is-prompt-injection-defense-2026/)  ·  дата публикации: 2026-01-01
- **Цитата дословно**: «The 2026 consensus is five defences in depth: input sanitisation, system prompt isolation, output filtering, model level training, gateway layer inline guardrails.»
- **Предложенный тип дефекта**: `review_not_new_result` — источник — обзор или подборка, а не сообщение о новом результате
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 24. токенизация реальных активов

- **ID**: `17bfda921cd17817f0506e9d`  ·  область: Финтех
- **Механизм**: создание блокчейн-токенов, представляющих доли владения или права на требования к физическим или традиционным финансовым активам, с использованием смарт-контрактов для управления правами и распределением дохода
- **Применение**: физические и традиционные финансовые активы
- **Источник**: [Tokenized real-world assets (RWAs) explained](https://metamask.io/news/understanding-tokenized-real-world-assets-rwa)  ·  дата публикации: 2026-02-06
- **Цитата дословно**: «Tokenized real-world assets (also known as RWAs) are blockchain-based tokens that represent ownership stakes in physical or traditional financial assets—such as stocks, ETFs, Treasuries, or commodities—recorded and transferred on a blockchain.»
- **Предложенный тип дефекта**: `wrong_date_or_scale` — машинная причина отказа: «отбраковано: термину 6 лет при 115 упоминаниях — это не зарождающееся понятие» — возраст термина не соответствует заявленной новизне механизма
- **Вердикт сервиса**: отбраковано: термину 6 лет при 115 упоминаниях — это не зарождающееся понятие
- **Решение человека**: _не принято_

## 25. атака на экосистему ИИ-агентов через вредоносные манифесты навыков (supply chain attack)

- **ID**: `72738ea5371d7bf3551a5c1e`  ·  область: Защита ИИ
- **Механизм**: внедрение инструкций социальной инженерии и инъекций промптов в файлы манифестов навыков (SKILL.md), заставляющих LLM выполнять вредоносные команды или инъекции в контекст агента
- **Применение**: навыки (skills) и манифесты ИИ-агентов
- **Источник**: [RSAC 2026 Confirmed It: Agentic AI Security Is the Industry's Next Unsolved Problem | Amine Raji, PhD](https://aminrj.com/posts/rsac26-agentic-security/)  ·  дата публикации: 2026-04-02  ·  дата события из извлечения: 2026-02
- **Цитата дословно**: «Some ClawHavoc skills embedded prompt injection directly in the descriptor files. When the agent loaded the skill, the malicious instructions entered the context window and executed silently on the next natural language query.»
- **Предложенный тип дефекта**: `attack_instead_of_defense` — в названии описан способ атаки, а запрос был о защите
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 26. безопасная десериализация тензоров в формате SafeTensors

- **ID**: `49dfadd8703cc7138b24501c`  ·  область: Защита ИИ
- **Механизм**: использование формата с JSON-заголовком и сырыми байтами тензоров, парсинг в Rust с строгой валидацией для исключения выполнения кода
- **Применение**: файлы моделей машинного обучения
- **Источник**: [Securing the AI Model Supply Chain: A Practical Defense Guide for 2026 - DEV Community](https://dev.to/young_gao/securing-the-ai-model-supply-chain-a-practical-defense-guide-for-2026-49oo)  ·  дата публикации: 2026-03-22
- **Цитата дословно**: «SafeTensors completely eliminates pickle. The format is a JSON header followed by raw tensor bytes, parsed in Rust with strict validation»
- **Предложенный тип дефекта**: `measurement_failure_not_card_defect` — фильтр отказал по причине «громкость не измерена: нет канонического термина»: это состояние замера, а не установленный дефект карточки
- **Вердикт сервиса**: громкость не измерена: нет канонического термина
- **Решение человека**: _не принято_

## 27. методология красного тестирования для приложений LLM

- **ID**: `6f6f4869b9849c7f2afc73df`  ·  область: Защита ИИ
- **Механизм**: систематическое тестирование приложения с использованием 6-шаговой методологии и 7 категорий атак
- **Применение**: приложения на основе генеративного ИИ (GenAI)
- **Источник**: [Prompt Injection & Red Teaming — Attack and Defense (2026) | MyEngineeringPath](https://myengineeringpath.dev/genai-engineer/prompt-injection/)  ·  дата публикации: не установлена
- **Цитата дословно**: «A 6-step red teaming methodology for systematically testing your application»
- **Предложенный тип дефекта**: `general_advice_not_technology` — в названии слово «методолог»: описан подход или рамка, а не способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 28. локальная обработка данных и ИИ-инференса в границах юрисдикции

- **ID**: `d5438a4f6218ff60dbbadef8`  ·  область: Защита ИИ
- **Механизм**: политическое и техническое ограничение маршрутизации телеметрии, инференса и хранения данных внутри географических границ (страны или региона) с использованием локальных дата-центров и валидированных стеков
- **Применение**: данные пользователей, промпты, эмбеддинги, телеметрия ИИ-моделей
- **Источник**: [Microsoft Sovereign Cloud: In-Region AI, Local Azure & Governance](https://windowsforum.com/news/microsoft-sovereign-cloud-in-region-ai-local-azure-and-partner-governance.388034/)  ·  дата публикации: 2025-11-05  ·  дата события из извлечения: 2025-11-05
- **Цитата дословно**: «Microsoft says the EU Data Boundary will ensure AI data processing for EU customers remains inside the EU/EFTA geography unless the customer directs otherwise.»
- **Предложенный тип дефекта**: `promise_not_event` — цитата говорит о планах или ожиданиях, а не о состоявшемся событии
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 29. адресное тестирование на уязвимости агентов ИИ

- **ID**: `6f40ecb1a46fe2c33e6a51b1`  ·  область: Защита ИИ
- **Механизм**: адресное тестирование на уязвимости
- **Применение**: агенты ИИ
- **Источник**: [General Analysis Raises $10M Seed to Secure Agentic AI | Let's Data Science](https://letsdatascience.com/news/general-analysis-raises-10m-seed-to-secure-agentic-ai-33e27740)  ·  дата публикации: 2026-04-29  ·  дата события из извлечения: 2026-03
- **Цитата дословно**: «Business Wire describes adversarial testing by General Analysis that, in March, tricked roughly 50 live customer-service agents»
- **Предложенный тип дефекта**: `broad_topic_no_mechanism` — механизм длиной 35 знаков не описывает способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 30. защита моделей машинного обучения от инверсии через состязательное обучение

- **ID**: `68a24579deb388c3e342d940`  ·  область: Защита ИИ
- **Механизм**: обучение модели на состязательных примерах для повышения устойчивости
- **Применение**: модели машинного обучения
- **Источник**: [Model Inversion: The Essential Guide | Nightfall AI Security 101](https://www.nightfall.ai/ai-security-101/model-inversion)  ·  дата публикации: не установлена
- **Цитата дословно**: «Proactive defenses involve designing machine learning models that are robust to model inversion attacks. These defenses can include techniques such as adversarial training, where the model is trained on adversarial examples to improve its robustness.»
- **Предложенный тип дефекта**: `review_not_new_result` — источник — обзор или подборка, а не сообщение о новом результате
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 31. изоляция ИИ-агентов в виртуальной машине с проверкой действий по политике безопасности

- **ID**: `3925c4bda9e0045e4804e5fd`  ·  область: Защита ИИ
- **Механизм**: выполнение ИИ-агента в изолированной виртуальной машине с применением формализованной политики безопасности, преобразуемой из естественного языка с помощью ИИ, для контроля доступа к внешним сервисам
- **Применение**: ИИ-агенты
- **Источник**: [«Железный занавес» для ИИ: как повысить безопасность работы автономных ИИ-агентов | Блог Касперского](https://www.kaspersky.ru/blog/ironcurtain-ai-agent-security/41602/)  ·  дата публикации: 2026-03-30
- **Цитата дословно**: «Исследователь Нильс Провос предложил архитектуру IronCurtain («железный занавес») — систему, которая должна ограничивать действия ИИ-агентов с помощью изоляции и политики безопасности.»
- **Предложенный тип дефекта**: `wrong_date_or_scale` — машинная причина отказа: «отбраковано: термину 69 лет при 183 упоминаниях — это не зарождающееся понятие» — возраст термина не соответствует заявленной новизне механизма
- **Вердикт сервиса**: отбраковано: термину 69 лет при 183 упоминаниях — это не зарождающееся понятие
- **Решение человека**: _не принято_

## 32. атака отравления памяти агента

- **ID**: `b32eb894586341c783fe45e7`  ·  область: Защита ИИ
- **Механизм**: коррупция долговременной памяти или хранилищ контекста агента вредоносными инструкциями
- **Применение**: ИИ-агенты с долговременной памятью
- **Источник**: [How Prompt Injection Attacks Compromise AI Agents in 2026](https://atlan.com/know/prompt-injection-attacks-ai-agents/)  ·  дата публикации: 2026-05-04
- **Цитата дословно**: «Memory poisoning — corrupting agent long-term memory or context stores»
- **Предложенный тип дефекта**: `attack_instead_of_defense` — в названии описан способ атаки, а запрос был о защите
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 33. мониторинг экологических заявлений с помощью технологий

- **ID**: `be41ff67965440aa2b5be072`  ·  область: Финтех
- **Механизм**: раннее выявление потенциальных нарушений и рисков зеленого промывания
- **Применение**: экологические заявления и данные ESG
- **Источник**: [Mitigating greenwashing risk in the age of AI](https://kpmg.com/in/en/insights/2026/06/mitigating-greenwashing-risk-in-the-age-of-ai.html)  ·  дата публикации: не установлена
- **Цитата дословно**: «Implement tech-based monitoring mechanisms to identify and address potential greenwashing violations at an early stage»
- **Предложенный тип дефекта**: `measurement_failure_not_card_defect` — фильтр отказал по причине «упоминаний не найдено по этой формулировке»: это состояние замера, а не установленный дефект карточки
- **Вердикт сервиса**: упоминаний не найдено по этой формулировке
- **Решение человека**: _не принято_

## 34. методология оценки безопасности агентов для предрейсового обеспечения

- **ID**: `5b057b93d3a41cbad811051d`  ·  область: Биотехнологии и генетика (открытый запрос, вне таблицы)
- **Механизм**: оценка систем через банки сценариев, охватывающие безопасность, конфиденциальность, справедливость и системную безопасность
- **Применение**: агентные системы на основе больших языковых моделей
- **Источник**: [AGENTSAFE: A Unified Framework for Ethical Assurance and Governance in Agentic AI](http://arxiv.org/abs/2512.03180)  ·  дата публикации: 2025-12-02
- **Цитата дословно**: «an Agent Safety Evaluation methodology that provides measurable pre-deployment assurance»
- **Предложенный тип дефекта**: `general_advice_not_technology` — в названии слово «методолог»: описан подход или рамка, а не способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 35. платформа агентского управления для финансовых учреждений

- **ID**: `0fa0103127e9250685cbb663`  ·  область: Биотехнологии и генетика (открытый запрос, вне таблицы)
- **Механизм**: запуск бета-версии платформы для управления агентскими операциями
- **Применение**: финансовые учреждения
- **Источник**: [Agentic Banking: An Authorisation Problem, Not AI](https://digitalbankexpert.com/2026/07/agentic-banking-authorisation-not-automation)  ·  дата публикации: не установлена
- **Цитата дословно**: «Fiserv's agentOS is already running in beta at two financial institutions ahead of a planned August 2026 general release.»
- **Предложенный тип дефекта**: `promise_not_event` — цитата говорит о планах или ожиданиях, а не о состоявшемся событии
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 36. сканирование безопасности контейнеров и реестров

- **ID**: `57236290ba3ef60248b61793`  ·  область: Защита ИИ
- **Механизм**: сканирование безопасности
- **Применение**: контейнеров и реестров
- **Источник**: [Best Supply Chain Security Solutions in 2026](https://www.waldosecurity.com/post/best-supply-chain-security-solutions-in-2026)  ·  дата публикации: 2026-05-13
- **Цитата дословно**: «Container and registry security scanning»
- **Предложенный тип дефекта**: `broad_topic_no_mechanism` — механизм длиной 25 знаков не описывает способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 37. координация консенсуса состояний нескольких блокчейнов через ретейл-чейн

- **ID**: `a623603190a17a6db7b4f43f`  ·  область: Финтех
- **Механизм**: использование центрального ретейл-чейна для синхронизации и верификации состояний пара-чейнов
- **Применение**: состояния транзакций в мультичейн-экосистеме
- **Источник**: [Blockchain Interoperability: Ultimate Guide for Enterprises 2026](https://morsoftware.com/blog/blockchain-interoperability)  ·  дата публикации: не установлена
- **Цитата дословно**: «A well-known example is Polkadot, which uses a central relay chain to coordinate consensus among its parachains, keeping all network states synchronized and verifiable.»
- **Предложенный тип дефекта**: `review_not_new_result` — источник — обзор или подборка, а не сообщение о новом результате
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 38. выбор архитектуры машинного обучения (случайный лес, нейронные сети, градиентный бустинг) для систем оценки кредитного риска

- **ID**: `77e76a0beb96eda62cc25f2c`  ·  область: Финтех
- **Механизм**: сравнение и выбор архитектур машинного обучения (Random Forests, Neural Networks, Gradient Boosting Machines) на основе требований к интерпретируемости, производительности и регуляторным нормам
- **Применение**: системы оценки кредитного риска
- **Источник**: [The New Era of Lending: From Static Scores to AI Intelligence - DEV Community](https://dev.to/interconnect/the-new-era-of-lending-from-static-scores-to-ai-intelligence-58d6)  ·  дата публикации: 2026-03-05
- **Цитата дословно**: «The selection of appropriate machine learning architecture fundamentally determines both the performance and explainability of credit risk systems.»
- **Предложенный тип дефекта**: `wrong_date_or_scale` — машинная причина отказа: «отбраковано: термину 30 лет при 3176 упоминаниях — это не зарождающееся понятие» — возраст термина не соответствует заявленной новизне механизма
- **Вердикт сервиса**: отбраковано: термину 30 лет при 3176 упоминаниях — это не зарождающееся понятие
- **Решение человека**: _не принято_

## 39. инференс-атаки на конфиденциальность

- **ID**: `b27c29142b604810358684c3`  ·  область: Защита ИИ
- **Механизм**: восстановление чувствительных обучающих данных или определение факта включения конкретных точек данных в обучение
- **Применение**: конфиденциальные обучающие данные
- **Источник**: [AI Model Security for Startups - Swiss Startup Association](https://swissstartupassociation.ch/2026/04/08/ai-model-security-for-startups-real-risks-practical-solutions-and-investor-expectations/)  ·  дата публикации: 2026-04-08
- **Цитата дословно**: «There are also confidentiality risks, such as model inversion or membership inference, where attackers attempt to recover sensitive training data or infer whether specific data points were included in training.»
- **Предложенный тип дефекта**: `attack_instead_of_defense` — в названии описан способ атаки, а запрос был о защите
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 40. оркестрация платежных потоков и маршрутизация транзакций

- **ID**: `f5960e341093f3415fa39911`  ·  область: Финтех
- **Механизм**: маршрутизация запросов, управление повторными попытками, ведение единого реестра и аудит для обеспечения видимости и операционного контроля
- **Применение**: платежные транзакции и финансовые данные
- **Источник**: [Embedded Finance in 2026: 5 Key Insights Every Business Should Know](https://smartpaynet.com/embedded-finance-2026-insights/)  ·  дата публикации: 2026-08-31
- **Цитата дословно**: «SmartPayNet provides orchestration, routing and audit trails for visibility and operational controls and metrics.»
- **Предложенный тип дефекта**: `measurement_failure_not_card_defect` — фильтр отказал по причине «громкость не измерена: нет канонического термина»: это состояние замера, а не установленный дефект карточки
- **Вердикт сервиса**: громкость не измерена: нет канонического термина
- **Решение человека**: _не принято_

## 41. руководство по выявлению критических рисков безопасности для приложений на базе больших языковых моделей

- **ID**: `52ba4a43bdd1680d50637891`  ·  область: Защита ИИ
- **Механизм**: идентификация и смягчение наиболее критических рисков безопасности приложений, управляемых LLM, на основе обновленных рейтингов и анализа реальных инцидентов
- **Применение**: приложения на базе больших языковых моделей (LLM)
- **Источник**: [OWASP GenAI Security Project Unveils 2026 Top 10 for LLM Applications, New Agent Control Standard and Sponsors as Community Tops 30,000 Members - OWASP Gen AI Security Project](https://genai.owasp.org/2026/09/01/owasp-genai-security-project-unveils-2026-top-10-for-llm-applications-new-agent-control-standard-and-sponsors-as-community-tops-30000-members/)  ·  дата публикации: 2026-09-02  ·  дата события из извлечения: 2026-09-02
- **Цитата дословно**: «The OWASP GenAI Security Project’s Top 10 for LLM Applications 2026 is the latest edition of the project’s flagship guidance for identifying and mitigating the most critical security risks facing applications powered by large language models.»
- **Предложенный тип дефекта**: `general_advice_not_technology` — в названии слово «руководств»: описан подход или рамка, а не способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 42. валидация выходных данных LLM по схемам и фильтрация контента

- **ID**: `459aa5d263c68a6f65e0b4c1`  ·  область: Защита ИИ
- **Механизм**: проверка структуры ответа (JSON schema), фильтрация PII и валидация набора вызываемых инструментов с отклонением аномалий
- **Применение**: выводы языковых моделей
- **Источник**: [Prompt Injection Defense 2026: Production Engineering Guide | ZTABS](https://ztabs.co/blog/prompt-injection-defense-2026)  ·  дата публикации: не установлена
- **Цитата дословно**: «Validate every model output against expected structure / content. Reject and retry on mismatch.»
- **Предложенный тип дефекта**: `promise_not_event` — цитата говорит о планах или ожиданиях, а не о состоявшемся событии
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 43. Системы противовоздушной обороны и наведения

- **ID**: `9b6b9bc513c0c1518eb32c5c`  ·  область: Защита ИИ
- **Механизм**: разработка систем обнаружения и перехвата угроз
- **Применение**: радары, сенсорная интеграция, системы наведения
- **Источник**: [CEE’s biggest checks: 10 standout startup raises of 2026 | EU-Startups](https://www.eu-startups.com/2026/09/cees-biggest-checks-10-standout-startup-raises-of-2026/)  ·  дата публикации: 2026-09-07  ·  дата события из извлечения: 2026-02
- **Цитата дословно**: «Frankenburg Technologies is a DefenceTech company developing missile defence and rapid response systems. The company focuses on radar, sensor fusion, tracking, and guidance technologies designed to detect and intercept incoming threats.»
- **Предложенный тип дефекта**: `broad_topic_no_mechanism` — механизм длиной 47 знаков не описывает способ действия
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_

## 44. интегрированная платформа управления рисками, комплаенсом и аудитом

- **ID**: `1e04dd40430236f37eab89c4`  ·  область: Финтех
- **Механизм**: объединение функций управления рисками, комплаенсом, аудитом и устойчивостью в единую платформу для устранения разрозненности данных и обеспечения сквозной видимости
- **Применение**: процессы управления рисками и комплаенса в финансовых учреждениях
- **Источник**: [Outgrowing Check-the-Box: Banking Risk Management’s Better Way Forward · Riskonnect](https://riskonnect.com/enterprise-risk-management/outgrowing-banking-risk-management/)  ·  дата публикации: 2025-08-18
- **Цитата дословно**: «Overall, software enables true enterprise risk visibility; not just a list of risks, but how they connect and influence business objectives across teams.»
- **Предложенный тип дефекта**: `review_not_new_result` — источник — обзор или подборка, а не сообщение о новом результате
- **Вердикт сервиса**: выдан в карточки
- **Решение человека**: _не принято_
