# MCP Customer Support Demo

This project is a teaching demo for production practices for MCP tool design.

The use case is a simple customer support workflow for broken or returned products. A customer can ask to look up an order, receive store credit, request a refund, or review previous support actions. The business logic is exposed through MCP and consumed by a Google ADK agent.

The main teaching point is this: **MCP tools should be safe, typed, well-described wrappers around real business logic.** The agent should use tools; it should not contain the business rules itself.

## Architecture At A Glance

The project uses a clean multi-tiered architecture where business rules are decoupled from the Model Context Protocol (MCP) interface:

### System Architecture Flow

```mermaid
graph TD
    classDef client fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef agent fill:#efebe9,stroke:#4e342e,stroke-width:2px;
    classDef server fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    classDef core fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef db fill:#eceff1,stroke:#37474f,stroke-width:2px;
    classDef obs fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;

    User["Customer (ADK Web Client)"]:::client
    Agent["Google ADK Agent"]:::agent
    MCP["FastMCP Server"]:::server
    Service["CustomerSupportService"]:::core
    Repo["SupportRepository"]:::core
    DB[("SQLite Database")]:::db
    Audit["AuditLogger"]:::core
    Phoenix["Phoenix Observability"]:::obs

    User -->|"Sends prompts / messages"| Agent
    Agent -->|"Invokes tools over HTTP SSE/JSON"| MCP
    MCP -->|"Delegates to business logic"| Service
    Service -->|"Uses transactional queries"| Repo
    Repo -->|"Reads/writes orders, customers, processed_responses"| DB
    Service -->|"Logs business outcomes"| Audit
    Audit -->|"Writes audit logs"| DB
    Agent -.->|"OpenTelemetry Traces"| Phoenix
    MCP -.->|"OpenTelemetry Traces"| Phoenix

    subgraph Business Logic Layer
        Service
        Repo
        Audit
    end
```

### Sequence Flow Diagram

Here is a typical execution sequence when a customer requests a transaction refund or store credit adjustment:

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer / ADK Web
    participant Agent as Google ADK Agent
    participant MCP as FastMCP Server
    participant Service as CustomerSupportService
    participant Repo as SupportRepository
    participant DB as SQLite DB
    participant Audit as AuditLogger
    participant Phoenix as Phoenix Observability

    Customer->>Agent: Prompt: "Refund order ord_5001"
    note over Agent: Agent checks instructions & decides tool strategy
    Agent->>MCP: POST /mcp (lookup_order)
    MCP->>Service: lookup_order(order_id)
    Service->>Repo: get_order(order_id)
    Repo->>DB: SELECT * FROM orders WHERE order_id = ?
    DB-->>Repo: Order record
    Repo-->>Service: Order data dict
    Service-->>MCP: Order Pydantic Model
    MCP-->>Agent: JSON Response (Order info)
    note over Agent: Agent confirms order exists and checks payment status

    Agent->>MCP: POST /mcp (refund_payment with request_id)
    MCP->>Service: refund_payment(RefundRequest)
    
    rect rgb(240, 248, 255)
        note over Service, DB: Transaction Begins
        Service->>Repo: get_processed_response(request_id)
        Repo->>DB: SELECT response FROM processed_responses WHERE request_id = ?
        alt Request Already Processed (Idempotency Hit)
            DB-->>Repo: Stored JSON response
            Repo-->>Service: Stored JSON response
            Service-->>MCP: RefundResponse Pydantic Model
            MCP-->>Agent: JSON Response (Duplicated response)
        else New Request (Idempotency Miss)
            DB-->>Repo: None
            Repo-->>Service: None
            Service->>Repo: get_customer_for_update(customer_id)
            Repo->>DB: SELECT * FROM customers WHERE customer_id = ?
            DB-->>Repo: Customer record
            Repo-->>Service: Customer data dict
            Service->>Repo: get_order_for_update(order_id)
            Repo->>DB: SELECT * FROM orders WHERE order_id = ?
            DB-->>Repo: Order record
            Repo-->>Service: Order data dict
            note over Service: Validate business rules (e.g. amount limits, ownership)
            
            alt Valid Request
                Service->>Repo: insert_refund(...)
                Repo->>DB: INSERT INTO refunds (...)
                Service->>Repo: save_processed_response(...)
                Repo->>DB: INSERT INTO processed_responses (...)
                Service->>Audit: log(action="refund", status="approved")
                Audit->>Repo: insert_audit_log(...)
                Repo->>DB: INSERT INTO audit_logs (...)
            else Invalid Request
                Service->>Repo: save_processed_response(...)
                Repo->>DB: INSERT INTO processed_responses (...)
                Service->>Audit: log(action="refund", status="rejected")
                Audit->>Repo: insert_audit_log(...)
                Repo->>DB: INSERT INTO audit_logs (...)
            end
            note over Service, DB: Transaction Commits
        end
    end

    Service-->>MCP: RefundResponse Pydantic Model
    MCP-->>Agent: JSON Response (Refund status)
    Agent-->>Customer: Text: "Refund approved for order ord_5001"

    opt Observability Trace
        Agent-->>Phoenix: Send execution trace (OTel)
        MCP-->>Phoenix: Send tool execution trace (OTel)
    end
```

### Internal Component Flow (Google ADK & FastMCP)

#### What is FastMCP?
**FastMCP** is a high-level Python framework designed to simplify the creation of Model Context Protocol (MCP) servers. Rather than managing low-level JSON-RPC protocol parsing, schema creation, and network transport details manually, FastMCP:
1. **Registers Python functions** as tools using simple decorators (e.g., `@mcp.tool`).
2. **Generates JSON Schemas** automatically from Python type hints and Pydantic model annotations.
3. **Manages Transports** (such as HTTP Server-Sent Events / SSE or Standard Input/Output / Stdio) to receive and reply to messages.

#### Component Interaction & Invocation Order

When the Google ADK Agent decides it needs to use a tool, the invocation flows through the following components:

```mermaid
graph TD
    classDef adk fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef fastmcp fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef tool fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;
    classDef logic fill:#fafafa,stroke:#9e9e9e,stroke-width:2px;

    %% 1. ADK Agent Component
    subgraph GoogleADKAgent ["1. Google ADK Agent Client"]
        ADK["LlmAgent<br/>(Orchestrator)"]:::adk
        Toolset["MCPToolset<br/>(HTTP Client / Connector)"]:::adk
        ADK -->|Invokes Tool Request| Toolset
    end

    %% 2. FastMCP Server internals
    subgraph FastMCPServer ["2. FastMCP Server (Internals)"]
        Transport["SSE / HTTP Transport Layer<br/>(Listens at /mcp)"]:::fastmcp
        Router["JSON-RPC Router<br/>(Parses tools/call)"]:::fastmcp
        Registry["Tool Registry<br/>(Matches name to function)"]:::fastmcp
        Validator["Pydantic Input Validator<br/>(Validates parameters)"]:::fastmcp

        Transport -->|Sends Payload| Router
        Router -->|Looks Up Tool Name| Registry
        Router -->|Performs Validation| Validator
    end

    %% 3. MCP Tool Function & Business Logic
    subgraph MCPTool ["3. MCP Tool Layer"]
        DecoFunc["Registered Python Function<br/>(decorated with @mcp.tool)"]:::tool
    end

    subgraph BusinessLayer ["4. Core Business Layer"]
        Service["CustomerSupportService"]:::logic
        Repo["SupportRepository"]:::logic
    end

    %% Invocation Flow arrows
    Toolset -->|"Step A: POST /mcp<br/>(SSE JSON-RPC Request)"| Transport
    Validator -->|"Step B: Runs Validated Arguments"| DecoFunc
    DecoFunc -->|"Step C: Calls Business Logic"| Service
    Service -->|"Step D: Query database"| Repo

    %% Styling subgraphs
    style GoogleADKAgent fill:#f1f8e9,stroke:#558b2f,stroke-dasharray: 5 5;
    style FastMCPServer fill:#e3f2fd,stroke:#0d47a1,stroke-dasharray: 5 5;
    style MCPTool fill:#fff8e1,stroke:#ff8f00,stroke-dasharray: 5 5;
    style BusinessLayer fill:#f5f5f5,stroke:#37474f,stroke-dasharray: 5 5;
```


## Run The Demo



### 1. Start Phoenix

Start Phoenix first so traces are captured while you run the MCP server and ADK agent:

```bash
uv run phoenix serve
```

Open Phoenix at:

```text
http://localhost:6006
```



### 2. Start The MCP Server

In a second terminal, from the repository root:

```bash
uv run src/customer_support/mcp/server.py
```

The MCP server runs as Streamable HTTP at:

```text
http://127.0.0.1:9000/mcp
```



### 3. Start ADK Web

In a third terminal, from the repository root:

```bash
cd src
adk web 
```

Select the `customer_support` agent in ADK Web.

### 4. Use Demo Prompts

Open [DEMO_PROMPTS.md](DEMO_PROMPTS.md) and copy/paste the prompts into ADK Web.

Recommended flow:

1. Basic lookup
2. Store credit preferred
3. Explicit refund
4. Audit logs
5. Idempotency retry
6. Guardrail/error case



## Project Structure

```text
src/customer_support/
  core/
    models.py          Pydantic request, response, and domain models
    database.py        SQLite schema creation, connection setup, seed data
    repository.py      All SQL and database persistence operations
    support_service.py Business rules for lookup, store credit, refund
    audit.py           Business audit log helpers
  mcp/
    server.py          FastMCP server entrypoint and tool wrappers
  adk_client/
    agent.py           Google ADK root agent and MCP toolset wiring
    prompts.py         Agent instruction prompt
    run_demo.py        Scripted ADK + MCP demo scenarios
```



## Important Practices Demonstrated



### 1. Keep Business Logic Out Of MCP

The business rules live in `core/support_service.py`.

The MCP layer in `mcp/server.py` only:

- validates input
- delegates to the service
- returns structured response models
- provides tool metadata

This keeps the same business layer reusable from ADK, LangGraph, tests, or any future client.

### 2. Use Typed Request And Response Models

Pydantic models make the tool contract explicit. The agent receives predictable structured outputs instead of raw database rows.

Examples:

- `RefundRequest`
- `RefundResponse`
- `StoreCreditRequest`
- `StoreCreditResponse`
- `AuditEntry`



### 3. Write Tool Descriptions For LLM Behavior

Tool descriptions are part of the product. They guide the agent on when to use a tool.

For example:

- `add_store_credit` says store credit is preferred, fast, and non-destructive.
- `refund_payment` says to use refunds only when the customer explicitly asks for money back.
- Mutating tools explain that retries are safe when the same `request_id` is reused.



### 4. Make Mutating Tools Idempotent

Store credit and refund operations require a `request_id`.

Before processing, the service checks whether that `request_id` already exists. If it does, the previously stored response is returned exactly as before.

This prevents duplicate refunds or duplicate credits when an agent retries a call.

### 5. Separate Business Audit From Observability

SQLite `audit_logs` answer business questions:

- What action happened?
- For which customer/order?
- What amount?
- Was it approved, issued, or rejected?

Phoenix answers engineering questions:

- What did the agent do?
- Which tools were called?
- What were the inputs and outputs?
- How long did calls take?
- Where did errors happen?

Both are useful, but they serve different purposes.

### 6. Keep Tool Outputs Concise

The tools return response models, not raw rows. This makes outputs easier for LLMs to consume and safer to expose.

### 7. Test The Tool Contract Independently

The deterministic tests verify business and tool behavior without depending on the LLM making good decisions.

This separates software correctness from agent behavior.



## Closing idea:

> Good MCP design is not just exposing functions. It is exposing safe, typed, well-described capabilities that agents can use reliably.

