Build a modern, production-ready **RAG chatbot frontend using Next.js**. The backend will be developed and integrated later using **FastAPI**, so keep the frontend modular and API-driven.

Requirements:

* Stateless chatbot (no conversation history or memory).
* ChatGPT-like interface with a query input and streaming AI responses.
* Stream responses token-by-token with Markdown and code block support.
* Display retrieved sources below each response, including **file name, relevance score, page number, and chunk ID**.
* Clicking a source should open the corresponding document at the **exact page/chunk** using metadata returned by the FastAPI backend.
* Show workflow progress (Retrieving Documents → Reranking → Generating Response).
* Gracefully handle errors (network failures, API errors, interrupted streams) with a **Retry** button that resumes from the last backend checkpoint instead of restarting the workflow, assuming the FastAPI backend supports checkpointing.
* Include loading states, auto-scroll, copy response button, responsive design, and light/dark mode.

Design the frontend to be clean, responsive, and easily extensible for future FastAPI integration, using best practices for Next.js and component-based architecture.