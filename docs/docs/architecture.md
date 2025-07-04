## Solution Architecture. 

In this workshop, you will create the Zava Sales Agent: a conversational agent designed to answer questions about sales data, generate charts, provide product recommendations, and support image-based product searches for Zava's retail DIY business.

## Components of the Agent App

1. **Microsoft Azure services**

    This agent is built on Microsoft Azure services.

      - **Generative AI model**: The underlying LLM powering this app is the [Azure OpenAI gpt-4o](https://learn.microsoft.com/azure/ai-services/openai/concepts/models?tabs=global-standard%2Cstandard-chat-completions#gpt-4o-and-gpt-4-turbo){:target="_blank"} LLM.

      - **Control Plane**: The app and its architectural components are managed and monitored using the [Azure AI Foundry](https://ai.azure.com){:target="_blank"} portal, accessible via the browser.

2. **Azure AI Foundry (SDK)**

    The workshop is offered in [Python](https://learn.microsoft.com/python/api/overview/azure/ai-projects-readme?view=azure-python-preview&context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext){:target="_blank"} using the Azure AI Foundry SDK. The SDK supports key features of the Azure AI Agents service, including [Code Interpreter](https://learn.microsoft.com/azure/ai-services/agents/how-to/tools/code-interpreter?view=azure-python-preview&tabs=python&pivots=overview){:target="_blank"} and [Model Context Protocol (MCP)](https://modelcontextprotocol.io/){:target="_blank"} integration.

3. **Database**

    The app is powered by the Zava Sales Database, a [Azure Database for PostgreSQL flexible server](https://www.postgresql.org/){:target="_blank"} with pgvector extension containing comprehensive sales data for Zava's retail DIY operations. The database includes:
    
     - **50,000+ customer records** across Washington State and online
     - **300+ DIY products** including tools, outdoor equipment, and home improvement supplies  
     - **200,000+ order transactions** with detailed sales history
     - **Vector embeddings** for product images enabling AI-powered similarity searches
     
     The Model Context Protocol (MCP) server securely provides structured access to this data by dynamically retrieving database schemas, generating, and executing optimized queries based on agent requests.

### Architecture
pgvector

## Extending the Workshop Solution

The workshop solution is highly adaptable to various scenarios, such as customer support, by modifying the database and tailoring the Foundry Agent Service instructions to suit specific use cases. It is intentionally designed to be interface-agnostic, allowing you to focus on the core functionality of the AI Agent Service with MCP integration and apply the foundational concepts to build your own conversational agent.

## Best Practices Demonstrated in the App

The app also demonstrates some best practices for efficiency and user experience.

- **Asynchronous APIs**:
  In the workshop sample, both the Foundry Agent Service and PostgreSQL use asynchronous APIs, optimizing resource efficiency and scalability. This design choice becomes especially advantageous when deploying the application with asynchronous web frameworks like FastAPI, ASP.NET, Chainlit, or Streamlit.

- **Token Streaming**:
  Token streaming is implemented to improve user experience by reducing perceived response times for the LLM-powered agent app.
