# ADK Web Demo Prompts

Use these prompts in `adk web` to demonstrate the customer support MCP tools.

## 1. Basic Lookup

```text
I am customer cust_1001. Can you check my recent order ord_5001?
```

Expected behavior:

- Calls `lookup_customer`
- Calls `lookup_order`
- Summarizes the customer and order clearly

## 2. Store Credit Preferred

```text
I am customer cust_1001. My headphones from order ord_5001 are broken. I want to return them.
```

Expected behavior:

- Looks up customer and order details
- Prefers store credit or offers it first
- May call `add_store_credit`

## 3. Explicit Refund

```text
I am customer cust_1001. My headphones from order ord_5001 are broken. I want my money back.
```

Expected behavior:

- Looks up customer and order details
- Calls `refund_payment`
- Uses a UUID `request_id`

## 4. Audit Logs

```text
Show me what support actions have been taken so far.
```

Expected behavior:

- Calls `get_audit_logs`
- Summarizes refund and store-credit actions

## 5. Idempotency Demo

First prompt:

```text
Issue a refund for customer cust_1001, order ord_5001, amount 15.00 using request_id demo-refund-123. This is for a retry safety demo.
```

Second prompt:

```text
Retry the exact same refund again using request_id demo-refund-123 for customer cust_1001, order ord_5001, amount 15.00.
```

Expected behavior:

- First call processes the refund
- Second call returns the same stored response
- No duplicate refund action is created

## 6. Error / Guardrail

```text
Issue a refund for customer cust_1001, order ord_5001, amount 9999.00.
```

Expected behavior:

- Calls `refund_payment`
- Tool rejects because the refund exceeds the order total
- Agent explains the rejection briefly and politely
