## 🚀 Usage

### Running the Sales Analysis Agentß

Once you have the development environment set up:

1. **Start the Agent**:

   Press `F5` in VS Code or run the following command in the terminal:

   ```bash
   cd /workspace/src/python/workshop
   python main.py
   ```

2. **Interact with the Agent**:
   The agent supports rich streaming conversations with real-time responses:

   ```
   🤖 Zava Sales Analysis Agent Ready!
   Connected to Azure AI Foundry
   Available tools: PostgreSQL schema tools + sales query execution
   =========================================================================
   
   You: What were our top-selling product categories last quarter?
   
   Agent: Let me analyze your sales data...
   [Real-time streaming response with formatted tables and insights]
   ```

3. **Example Queries to Try**:
   - **Sales Performance**: "Show me revenue by product category for 2024 as a bar chart"
   - **Regional Analysis**: "Which stores performed best last quarter?"
   - **Customer Insights**: "Who are our top 10 customers by order value?"
   - **Product Search**: "Find products similar to camping equipment"
   - **Trend Analysis**: "Show me seasonal sales patterns"
   - **Inventory Reports**: "What's our current stock level by store?"

4. **Advanced Features**:
   - **Multi-language**: Ask questions in different languages for localized responses
   - **Data Export**: Request data in CSV format (presented as markdown tables)
   - **Complex Queries**: The agent can join multiple tables and perform sophisticated analysis