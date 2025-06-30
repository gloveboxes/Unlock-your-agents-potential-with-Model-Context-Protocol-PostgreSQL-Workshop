## Introduction

Tracing helps you understand and debug your agent's behavior by showing the sequence of steps, inputs, and outputs during execution. In Azure AI Foundry, tracing lets you observe how your agent processes requests, calls tools, and generates responses. You can use the Azure AI Foundry portal or integrate with OpenTelemetry and Application Insights to collect and analyze trace data, making it easier to troubleshoot and optimize your agent.

## Lab Exercise

1. Open the Azure AI Foundry portal and navigate to the Agents playground.
2. Start a new conversation with your agent and interact with it.
3. Select **Thread info** in the active thread to view the trace, including steps, tool calls, and data exchanged.
4. (Optional) Enable Metrics to evaluate your agent's performance.
5. For advanced tracing, install OpenTelemetry and the Azure SDK tracing plugin in your environment:

   ```bash
   pip install opentelemetry-sdk azure-core-tracing-opentelemetry opentelemetry-exporter-otlp
   ```

6. Configure your agent to export traces to Application Insights or view them in the console.
7. Review the trace data to understand your agent's execution flow and identify any issues.
