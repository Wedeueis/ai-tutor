# **PRD: AI Tutor System & Knowledge Engine (OKF \+ Hermes Harness)**

**Documento de Requisitos de Produto (PRD)**  
**Versão:** 2.0  
**Arquitetura:** Hexagonal (Ports & Adapters) \+ Domain-Driven Design (DDD)  
**Metodologia de Execução:** Desenvolvimento Aumentado por Agentes (Estilo Matt Pocock)

## **1\. Visão Geral e Problema**

### **1.1 Contexto**

O sistema atual opera como uma Wiki LLM baseada no padrão Open Knowledge Framework (OKF) da Google, armazenando notas atômicas em Markdown com frontmatter estruturado em um *vault*. Embora sistemas como o Google NotebookLM ofereçam busca e síntese eficazes sobre fontes pontuais, eles falham no aprendizado de longo prazo por integrarem uma arquitetura *stateless* (sem estado do estudante, sem rastreamento de maestria e sem adaptação metodológica).

### **1.2 Solução**

Evoluir o PKM para um **AI Tutor Stateful** e adaptativo. O sistema deve:

> 1. Ingerir e curar fontes heterogêneas (livros-texto em PDF/EPUB, artigos acadêmicos, slides, notas Markdown e transcrições do YouTube).  
> 2. Estruturar o conhecimento ingerido em nós OKF no *vault*.  
> 3. Instanciar um **Hermes Agent Harness** para aplicar estratégias pedagógicas personalizadas por domínio de conhecimento (ex.: Engenharia de Software vs. Biologia vs. Humanidades).  
> 4. Manter um **Learner Model** persistente (SQLite) com rastreamento de conhecimento (Knowledge Tracing), algoritmos de Repetição Espaçada (SRS), quizzes e diálogos socráticos.

## **2\. Princípios de Arquitetura e Design (Modelo Hexagonal)**

O projeto segue estritamente a Arquitetura Hexagonal para garantir testabilidade isolada e substituição de dependências sem alteração de regras de negócio.

                 \+-------------------------------------------------+  
                 |                DRIVING ADAPTERS                 |  
                 |  (CLI / MCP Server / Rest API / Test Harness)   |  
                 \+------------------------+------------------------+  
                                          |  
                                          v  
                 \+-------------------------------------------------+  
                 |            APPLICATION / USE CASES              |  
                 | (IngestMaterial, GeneratePlan, EvaluateLearner) |  
                 \+------------------------+------------------------+  
                                          |  
                                          v  
\+---------------------------------------------------------------------------------+  
|                                 DOMAIN CORE                                     |  
|  Entidades: Concept, StudyPlan, LearnerModel, SourceMaterial, AssessmentItem   |  
|  Services: HermesDomainOrchestrator, SpacedRepetitionEngine, RelevanceCurator   |  
\+---------------------------------------------------------------------------------+  
                                          ^  
                                          |  
                 \+------------------------+------------------------+  
                 |            DRIVEN PORTS & ADAPTERS              |  
                 | (Docling, ChromaDB, SQLite, MarkdownVault, Ollama) |  
                 \+-------------------------------------------------+

## **3\. Modelo de Domínio e Linguagem Ubíqua**

### **3.1 Entidades do Core (src/pipeline/domain/)**

* **Concept**: Nó atômico da Wiki OKF.  
  * *Atributos:* id, slug, title, summary, domain\_type, prerequisites: List\[Slug\], related\_concepts: List\[Slug\], content\_md, confidence\_score.  
* **SourceMaterial**: Representação genérica de conteúdo ingerido.  
  * *Atributos:* id, uri, source\_type (PDF, EPUB, YOUTUBE, SLIDES, PAPER, MD), raw\_content, extracted\_concepts: List\[Concept\], relevance\_score.  
* **StudyPlan**: Grafo Direcionado Acíclico (DAG) de aprendizado.  
  * *Atributos:* id, target\_topic, nodes: List\[Concept\], edges: List\[Tuple\[Slug, Slug\]\], created\_at.  
* **LearnerModel**: Estado de conhecimento do estudante.  
  * *Atributos:* user\_id, concept\_mastery: Dict\[Slug, MasteryScore\], srs\_schedules: Dict\[Slug, SRSMetadata\].  
* **AssessmentItem**: Item de avaliação gerado atrelado a um conceito.  
  * *Atributos:* id, concept\_slug, item\_type (FLASHCARD, MULTIPLE\_CHOICE, SOCRATIC\_PROMPT), question, rubric, answer.

### **3.2 Objetos de Valor (Value Objects)**

* **MasteryScore**: Float $\[0.0, 1.0\]$ acompanhado de histórico de tentativas e timestamp de atualização.  
* **DomainType**: Enum (SOFTWARE\_ENGINEERING, BIOLOGY, HUMANITIES, GENERIC).  
* **SRSMetadata**: Parâmetros de Repetição Espaçada (Fator de Facilidade $EF$, Intervalo $I$, Próxima Revisão $Due$).

## **4\. Requisitos Funcionais e Épicos**

### **Epic 1: Ingestão Multi-Fonte, Curadoria e Roteamento OKF**

| ID | Requisito Funcional | Descrição Técnica | Porta / Adaptador Envolvido |
| :---- | :---- | :---- | :---- |
| **RF1.1** | Extração Complexa | Processar PDFs/EPUBs mantendo estrutura, fórmulas e tabelas. | DocumentParserPort / DoclingAdapter  |
| **RF1.2** | Ingestão Transcrita | Extrair transcrições de vídeos do YouTube com marcação temporal. | DocumentParserPort / YouTubeTranscriptAdapter |
| **RF1.3** | Parsing Acadêmico | Extrair Resumo, Metodologia e Resultados de artigos científicos (PDF/ArXiv). | DocumentParserPort / GrobidAdapter |
| **RF1.4** | Curadoria e Scoring | Ranquear o impacto de cada fonte antes de fundi-la ao *vault*. | RelevanceCurator (Domain Service) |
| **RF1.5** | Síntese OKF | Converter trechos aprovados em arquivos .md com frontmatter válido. | ConceptRepositoryPort / MarkdownWikiAdapter  |

### **Epic 2: Hermes Agent Harness & Personalização por Domínio**

| ID | Requisito Funcional | Descrição Técnica | Porta / Adaptador Envolvido |
| :---- | :---- | :---- | :---- |
| **RF2.1** | Seleção de Persona | O harness altera as diretrizes de prompt de acordo com o DomainType. | HermesDomainOrchestrator |
| **RF2.2** | Software Strategy | Abordagem PBL (Problem-Based Learning), cenários de debugging e código interativo. | HermesDomainOrchestrator / MCPToolRegistry |
| **RF2.3** | Biology Strategy | Mapeamento de diagramas de processo, cadeias de causa-efeito e taxonomia. | HermesDomainOrchestrator / MermaidTool |
| **RF2.4** | Humanities Strategy | Tutoria Socrática, debates dialéticos e análise crítica de fontes. | HermesDomainOrchestrator / SocraticDialogueEngine |
| **RF2.5** | MCP Tool Injection | Injeção dinâmica de ferramentas MCP conforme o domínio da sessão. | MCPServerAdapter  |

### **Epic 3: Planejador de Estudos e Rastreamento de Estado**

| ID | Requisito Funcional | Descrição Técnica | Porta / Adaptador Envolvido |
| :---- | :---- | :---- | :---- |
| **RF3.1** | Construção de DAG | Gerar plano de estudos identificando pré-requisitos na Wiki. | GenerateStudyPlanPort / StudyPlanUseCase |
| **RF3.2** | Knowledge Tracing | Registrar e atualizar a maestria do estudante por nó no banco SQLite. | LearnerStateRepositoryPort / SQLiteLearnerRepository  |
| **RF3.3** | Re-roteamento | Recalcular o plano de estudos caso o estudante falhe em conceitos de base. | StudyPlanUseCase |

### **Epic 4: Avaliação, Quizzes e Repetição Espaçada (SRS)**

| ID | Requisito Funcional | Descrição Técnica | Porta / Adaptador Envolvido |
| :---- | :---- | :---- | :---- |
| **RF4.1** | Geração de Quizzes | Criar testes baseados em rubricas JSON sobre nós da Wiki. | LLMInferencePort / QuizGeneratorSkill  |
| **RF4.2** | Flashcards e SRS | Gerar flashcards e agendar revisões via algoritmo FSRS/SM-2. | SpacedRepetitionEngine / SQLiteLearnerRepository  |
| **RF4.3** | Avaliação Discursiva | Avaliar respostas abertas utilizando rubricas formais de correção. | EvaluateAssessmentPort / QualityEvalSkill  |

## **5\. Mapeamento da Arquitetura Hexagonal (Contratos de Código)**

### **5.1 Outbound Ports (Contratos para a Infraestrutura)**

Python  
\# src/pipeline/application/ports/outbound/document\_parser.py  
from typing import Protocol  
from pipeline.domain.source\_material import SourceMaterial

class DocumentParserPort(Protocol):  
    def parse(self, uri: str) \-\> SourceMaterial:  
        """Processa fontes externas e retorna a estrutura unificada de SourceMaterial."""  
        ...

\# src/pipeline/application/ports/outbound/learner\_repository.py  
from typing import Protocol, Optional  
from pipeline.domain.learner\_model import LearnerModel, MasteryScore, SRSMetadata

class LearnerStateRepositoryPort(Protocol):  
    def get\_learner\_model(self, user\_id: str) \-\> LearnerModel: ...  
    def save\_mastery(self, user\_id: str, concept\_slug: str, score: MasteryScore) \-\> None: ...  
    def update\_srs(self, user\_id: str, concept\_slug: str, srs\_data: SRSMetadata) \-\> None: ...

### **5.2 Inbound Ports (Casos de Uso)**

Python  
\# src/pipeline/application/ports/inbound/hermes\_session.py  
from typing import Protocol, Generator  
from pipeline.domain.value\_objects import DomainType

class ExecuteHermesSessionPort(Protocol):  
    def start\_session(self, user\_id: str, topic\_slug: str, domain: DomainType) \-\> Generator\[str, None, None\]:  
        """Inicia uma sessão interativa de tutoria aplicando o harness adequado."""  
        ...

## **6\. Requisitos Não-Funcionais e Guardrails**

> 1. **Execução Local/Privada (Local-First):** Suporte nativo ao processamento offline via Ollama e banco relacional SQLite local.  
> 2. **Ancoragem Estrita (Grounding):** O tutor deve utilizar estritamente o contexto dos nós da Wiki e materiais curados para evitar alucinações.  
> 3. **Desempenho de Ingestão:** O tempo de parsing de PDFs complexos via Docling deve ser assíncrono em relação à interface do usuário.  
> 4. **Cobertura de Testes:** Todo código das camadas domain e application deve ter no mínimo 85% de cobertura de testes unitários sem mocks de I/O na camada de domínio.

## **7\. Roadmap de Execução para Agentes de IA (Matt Pocock Model)**

Este roadmap foi desenhado em tarefas atômicas e incrementais, prontas para execução via Claude Code, Aider, Cursor ou Windsurf. Cada tarefa deve ser finalizada e validada antes de avançar para a próxima.

\+-------------------------------------------------------------------------------+  
|                           ROADMAP DE IMPLEMENTAÇÃO                            |  
|                                                                               |  
|  \[FASE 1: CORE DE DOMÍNIO E REPOSITÓRIOS DO ESTUDANTE\]                         |  
|   Task 1.1: Entidades LearnerModel, MasteryScore & SRSMetadata                |  
|   Task 1.2: Adaptador SQLite do Learner Model                                 |  
|                                                                               |  
|  \[FASE 2: EXTENSÃO DA INGESTÃO MULTI-FONTE\]                                   |  
|   Task 2.1: Porta DocumentParserPort & Adaptador YouTubeTranscript            |  
|   Task 2.2: RelevanceCurator Domain Service                                   |  
|                                                                               |  
|  \[FASE 3: HERMES AGENT HARNESS & ESTRATÉGIAS DE DOMÍNIO\]                      |  
|   Task 3.1: HermesDomainOrchestrator e Prompts de Persona                     |  
|   Task 3.2: Injeção Dinâmica de Ferramentas via MCP Adapter                   |  
|                                                                               |  
|  \[FASE 4: MOTOR DE ESTUDO, QUIZZES E SRS\]                                     |  
|   Task 4.1: SpacedRepetitionEngine (FSRS/SM-2)                                |  
|   Task 4.2: Caso de Uso EvaluateLearner & Geração de Avaliações               |  
\+-------------------------------------------------------------------------------+

### **FASE 1: Core de Domínio e Repositórios do Estudante**

#### **Task 1.1: Entidades LearnerModel, MasteryScore e SRSMetadata**

* **Objetivo:** Criar os Value Objects e Entidades de estado do estudante no domínio puro.  
* **Arquivos a Criar:**  
  * src/pipeline/domain/learner\_model.py  
  * tests/domain/test\_learner\_model.py  
* **Contrato:**  
  * Class MasteryScore(value: float, confidence: float, last\_updated: datetime)  
  * Class SRSMetadata(interval: int, repetitions: int, ease\_factor: float, due\_date: datetime)  
  * Class LearnerModel(user\_id: str, mastery\_map: Dict\[str, MasteryScore\], srs\_map: Dict\[str, SRSMetadata\])  
* **Critérios de Aceite:**  
  * MasteryScore deve validar limites $\[0.0, 1.0\]$.  
  * Lógica de atualização de maestria baseada em novas tentativas.  
  * Zero dependências de frameworks externos na camada de domínio.  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/domain/test\_learner\_model.py

#### **Task 1.2: Adaptador SQLite do Learner Model**

* **Objetivo:** Persistir o estado do estudante no banco de dados SQLite existente.  
* **Arquivos a Criar/Modificar:**  
  * src/pipeline/adapters/sqlite/schema.sql (adicionar tabelas learner\_mastery e srs\_schedules)  
  * src/pipeline/adapters/sqlite/sqlite\_learner\_repository.py  
  * tests/adapters/test\_sqlite\_learner\_repository.py  
* **Critérios de Aceite:**  
  * Criar schema SQL com índices nos campos user\_id e concept\_slug.  
  * Implementar métodos get\_learner\_model e save\_mastery.  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/adapters/test\_sqlite\_learner\_repository.py

### **FASE 2: Extensão da Ingestão Multi-Fonte**

#### **Task 2.1: Porta DocumentParserPort e Adaptador YouTubeTranscriptAdapter**

* **Objetivo:** Permitir a ingestão e extração estruturada de transcrições de vídeos do YouTube.  
* **Arquivos a Criar:**  
  * src/pipeline/application/ports/outbound/document\_parser.py  
  * src/pipeline/adapters/youtube/youtube\_transcript\_adapter.py  
  * tests/adapters/test\_youtube\_transcript\_adapter.py  
* **Critérios de Aceite:**  
  * Extrair legendas de URLs do YouTube.  
  * Retornar um objeto SourceMaterial com timestamps e texto limpo.  
  * Tratar erros de vídeo sem legenda ou privado de forma graciosa.  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/adapters/test\_youtube\_transcript\_adapter.py

#### **Task 2.2: Serviço de Domínio RelevanceCurator**

* **Objetivo:** Avaliar e pontuar a relevância de conteúdos ingeridos antes de integrá-los ao vault.  
* **Arquivos a Criar:**  
  * src/pipeline/domain/services/relevance\_curator.py  
  * tests/domain/test\_relevance\_curator.py  
* **Critérios de Aceite:**  
  * Receber um SourceMaterial e um nó de conceito Concept.  
  * Calcular a densidade de palavras-chave e relevância semântica.  
  * Retornar relevance\_score: float e determinar se o material deve ser aceito ou rejeitado.  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/domain/test\_relevance\_curator.py

### **FASE 3: Hermes Agent Harness & Estratégias de Domínio**

#### **Task 3.1: Servidor de Orquestração HermesDomainOrchestrator**

* **Objetivo:** Injetar regras pedagógicas no LLM com base na disciplina do conhecimento.  
* **Arquivos a Criar:**  
  * src/pipeline/domain/services/hermes\_orchestrator.py  
  * tests/domain/test\_hermes\_orchestrator.py  
* **Contrato:**  
  * get\_system\_prompt(domain: DomainType, concept: Concept) \-\> str  
* **Comportamento:**  
  * SOFTWARE\_ENGINEERING: Força explicações orientadas a código, identificação de bugs e sugestões de exercícios práticos.  
  * BIOLOGY: Força construção de fluxogramas de processos bioquímicos e analogias estruturais.  
  * HUMANITIES: Força estilo Socrático (perguntas reflexivas, tese/antítese).  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/domain/test\_hermes\_orchestrator.py

#### **Task 3.2: Integração com o MCP Server (mcp/server.py)**

* **Objetivo:** Expor as novas ferramentas de tutoria para clientes MCP.  
* **Arquivos a Modificar:**  
  * src/pipeline/mcp/server.py

  * tests/mcp/test\_mcp\_server.py  
* **Ferramentas MCP a Adicionar:**  
  * get\_study\_plan(topic: str)  
  * get\_due\_flashcards(user\_id: str)  
  * submit\_assessment\_answer(user\_id: str, concept\_slug: str, answer: str)  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/mcp/test\_mcp\_server.py

### **FASE 4: Motor de Estudo, Quizzes e Repetição Espaçada (SRS)**

#### **Task 4.1: Serviço de Domínio SpacedRepetitionEngine**

* **Objetivo:** Calcular os próximos prazos de revisão de conceitos com base no desempenho do usuário.  
* **Arquivos a Criar:**  
  * src/pipeline/domain/services/srs\_engine.py  
  * tests/domain/test\_srs\_engine.py  
* **Contrato:**  
  * calculate\_next\_review(current\_srs: SRSMetadata, rating: int) \-\> SRSMetadata (Onde rating varia de 1 a 4: Errei, Difícil, Bom, Fácil).  
* **Critérios de Aceite:**  
  * Ajustar o ease\_factor e o interval corretamente.  
  * Garantir ordenação determinística das revisões atrasadas.  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/domain/test\_srs\_engine.py

#### **Task 4.2: Caso de Uso EvaluateLearnerUseCase**

* **Objetivo:** Avaliar a resposta do estudante, atualizar o LearnerModel no SQLite e reprogramar a revisão.  
* **Arquivos a Criar:**  
  * src/pipeline/application/use\_cases/evaluate\_learner.py  
  * tests/application/test\_evaluate\_learner.py  
* **Critérios de Aceite:**  
  * Integração entre QualityEvalSkill, LearnerStateRepositoryPort e SpacedRepetitionEngine.  
  * Testes com dublês/fakes para garantir execução rápida e isolada.  
* **Comando de Verificação:**  
  Bash  
  uv run pytest tests/application/test\_evaluate\_learner.py

## **8\. Verificação de Integridade da Suíte**

Após a execução de cada fase pelos agentes de IA, a suíte completa de testes e análise estática do projeto deve passar sem avisos ou falhas:

Bash  
\# Validação do Pipeline Completo  
uv run pytest \--cov=src/pipeline  
uv run mypy src/pipeline  
