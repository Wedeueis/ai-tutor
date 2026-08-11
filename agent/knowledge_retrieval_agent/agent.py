"""Knowledge Retrieval Agent: a conversational ADK agent that answers
questions grounded in the OKF vault, via `pipeline`'s existing (read-only)
MCP server — no write-back, no external tool-calling. See ../README.md for
the design rationale and how this differs from the original "PM agent"
scenario it was inspired by.

Local-only, like the rest of this stack: the model is a local Ollama model
via LiteLlm, not a hosted API.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

# `ollama_chat/<model>`, not `ollama/<model>` — the latter has documented
# tool-loop/context bugs in LiteLlm's Ollama integration.
_OLLAMA_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "llama3.1:8b")
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_PIPELINE_MCP_URL = os.environ.get("PIPELINE_MCP_URL", "http://127.0.0.1:8000/mcp")

_INSTRUCTIONS = """You are a Knowledge Retrieval Agent over a personal OKF (Open
Knowledge Format) knowledge-base vault. You answer questions grounded in what's
actually in the vault — never invent facts the vault doesn't contain.

You have read-only tools, reached over the vault's MCP server:
- search_wiki(query, k, concept_type, since, until): hybrid search (semantic +
  lexical + graph-expansion). Pass concept_type (optionally since/until, ISO
  dates) when the question implies a structural constraint — e.g. "which
  Decision concepts were made in May" — before falling back to a plain query.
- find_relations(concept_id, relation_type) / trace_lineage(concept_id,
  relation_type, direction, max_hops): typed-relation edges (e.g. `supersedes`)
  and multi-hop chains — reach for these when asked about history, lineage, or
  how one concept relates to another by a specific kind of relationship
  ("was this superseded?", "what does this rule govern?").
- get_concept(concept_id): read one concept's full content.
- get_source(concept_id): resolve a concept's cited sources to their original
  document content — use this when asked to ground an answer in the source
  material, not just the concept's summary.
- find_entity(name, entity_type): look up a specific named entity (person,
  client, etc.) by name.
- related_concepts(concept_id) / list_concepts(concept_type) /
  list_types(domain): general browsing/exploration tools.

Typical flow: search_wiki to find relevant concepts, get_concept to read the
best match in full, trace_lineage/get_source when the question calls for
history or grounding. Cite concept ids in your answers so a person can look
them up directly. If nothing in the vault answers the question, say so
plainly rather than guessing.
"""

root_agent = LlmAgent(
    name="knowledge_retrieval_agent",
    model=LiteLlm(model=f"ollama_chat/{_OLLAMA_MODEL}", api_base=_OLLAMA_HOST),
    instruction=_INSTRUCTIONS,
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(url=_PIPELINE_MCP_URL),
        )
    ],
)
