---
type: Metric
title: Retrieval Augmented Generation (RAG)
description: A technique that uses retrieval to augment generation in text-based applications.
tags:
- natural language processing
- machine learning
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
domain: domains/machine-learning
eval:
  passed: true
  average_score: 0.825
  scores:
  - rubric_id: traceable
    score: 0.8
    rationale: Most claims are supported by the raw note, but the mention of 'text-based
      applications' in the description is not explicitly stated in the raw note.
  - rubric_id: not_verbatim
    score: 0.9
    rationale: The body adds some structure and clarity to the raw note by rephrasing
      it in a more formal tone.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body says.
  - rubric_id: substantial
    score: 0.6
    rationale: While the body is not extremely long or detailed, it does provide a
      clear explanation of RAG that stands on its own without referencing the raw
      note, thus meeting this criterion minimally.
---

RAG is a technique used in natural language processing and machine learning to use retrieval to augment generation. It involves retrieving relevant information from a database of text documents and using it to inform the generation process.

Retrieval-Augmented Generation (RAG) has emerged as a practical framework for enhancing large language models (LLMs) by grounding their outputs in external knowledge sources. In a standard RAG pipeline, a user query triggers the retrieval of semantically relevant passages from a document corpus using dense-vector techniques.

Graph-based RAG (GraphRAG) addresses the limitations of traditional RAG by constructing a structured knowledge graph from the source corpus to enable semantically aware retrieval and multi-hop reasoning.

To address these gaps, the GraphRAG paradigm was introduced, embedding a structured knowledge graph between the retrieval and generation stages [20]. Microsoft's GraphRAG demonstrated that constructing entity-relation graphs from retrieved passages and summarizing them into semantic communities improved QA performance.

The DocumentParser takes input documents in various formats such as PDF, HTML, XLSX, CSV, etc. and converts them into a unified intermediate representation using the Docling library. This representation retains layout, tables, and structural metadata, facilitating downstream GraphRAG processing.

The SentenceSegmenter takes input text chunks and segments them into individual sentences using language-specific delimiters. This is done to improve LLM performance and facilitate syntactic parsing, allowing for filtering content based on linguistic structure.

**Efficient Graph Retrieval Process**

The major components in our indexing and retrieval pipeline include:
* Query Entity Identification: An optimized variant of SpaCy's noun phrase extractor is used to pinpoint key concepts within the query, followed by a similarity search between the full query and node embeddings.
* Graph Query Execution: Starting from seed query nodes, we use case insensitive exact match to query the graph for relevant relations. Once a node is matched with a query node, it performs 1-hop traversal of all neighbors and filtered by a neighbor controlling parameter.
* Relevance Ranking and Context Selection: Candidate relations are obtained through case insensitive exact match and graph traversal, then split into two groups: entity-to-entity relations and entity-to-chunk relations. Both chunk and relation embeddings are retrieved from the Milvus vector DB, which are then used to compute cosine similarity with the query.
* Context Integration with LLM: Once the top chunks and top relations are produced, they along with query entities as the context for LLM to consume and generate answers.

**GraphRAG Indexing and Retrieval Architecture**

Figure 3 above illustrates the major components in our indexing and retrieval pipeline. During indexing, the knowledge graph is stored in both Vector DB and Graph DB.

GraphRAG is a retrieval model that leverages the power of graphs to extract relevant information from large datasets. By using either GPT-4 or dependency graphs for triplet extraction, GraphRAG can significantly improve context precision and coverage measurement compared to dense vector retrieval.

GraphRAG-based retrieval methods have been shown to generate fewer hallucinations and more accurate function definitions compared to dense vector retrieval. This is likely due to the ability of GraphRAG to capture complex relationships between code elements.

FastRAG is a retrieval augmented generation system designed for semi-structured data. It was proposed by Amar Abane, Anis Bekri, and Abdella Battou in their 2024 paper titled "FastRAG: Retrieval Augmented Generation for Semi-structured Data."

The Fast-GraphRAG is a fast and modular graph-based retrieval augmented generation (RAG) framework. It was proposed by Circlemind AI in 2025.

Scott Barnett, Stefanus Kurniawan, Srikanth Thudumu, Zach Brannelly, and Mohamed Abdelrazek proposed seven common failure points when engineering a retrieval augmented generation system in their 2024 paper titled "Seven failure points when engineering a retrieval augmented generation system."

Lightrag is a simple and fast retrieval-augmented generation model. It was introduced in the paper [18] by Zirui Guo et al. in 2024.

LightRAG is an improved version of the Lightrag model, introduced in the paper [19] by Zirui Guo et al. in 2025. It offers simple and fast retrieval-augmented generation capabilities.

Graph retrieval-augmented generation (G-RAG) is a technique that uses graph-based data structures to augment and enhance the performance of language models. G-RAG involves retrieving relevant information from graphs and using it to inform the generation of text.

Retrieval-augmented generation (RAG) is a technique that uses external knowledge sources to inform and enhance the performance of language models. RAG involves retrieving relevant information from these sources and using it to generate text.

RGL is a framework that uses graph-based structures to enable efficient and effective retrieval-augmented generation. This can involve using various techniques, such as graph partitioning or graph sampling, to improve the performance of language models.

Context for Retrieval-Augmented Generation is a framework that utilizes contextual information to enhance the performance of retrieval-augmented generative models. This approach involves integrating contextual data into the model's architecture, allowing it to better understand the nuances of the input and generate more accurate output.

## Related

- [Beam search](/beam-search.md) — RAG can be used as a component in beam search algorithms to select and augment generated text.
- [Long Short-Term Memory (LSTM)](/long-short-term-memory-lstm.md) — Both RAG and LSTM are techniques used in natural language processing and machine learning, making them relevant connections.
- [EntityRelationNormalizer](/entityrelationnormalizer.md) — All three involve using context to improve entity identification and management
- [Scalable GraphRAG Construction](/scalable-graphrag-construction.md) — The draft concept is about constructing scalable GraphRAG systems, which are related to Retrieval Augmented Generation (RAG) models.


## Categories

- [GraphRAG Systems](/categories/graphrag-systems.md)
- [Knowledge Graph Construction](/categories/knowledge-graph-construction.md)
- [Subgraph Retrieval](/categories/subgraph-retrieval.md)
