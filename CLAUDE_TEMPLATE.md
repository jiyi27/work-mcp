# Agent Guide

## Project Context

<!-- INITIALIZATION REQUIRED: Fill in the placeholders below, then remove all
instruction comments and delete the "Batch Ask" section. -->

**Base URL**

```
PLACEHOLDER_BASE_URL
```

**Authentication**

```
PLACEHOLDER_AUTH
```

<!-- After the user answers, fill in one of:
  - "No authentication required"
  - The token or credentials provided
  - "Unknown" — if unclear, see auth rules below -->

---

### Batch Ask

Once you have read the codebase enough to understand the project, ask the following in a **single message** before doing anything else:

> 在开始之前，我需要了解几件事：
>
> 1. **服务 Base URL** — 我应该往哪个地址发请求？
> 2. **鉴权** — 接口需要鉴权吗？如果需要，可以给我一个长期有效的 token，或者提供账号密码 + 登录接口让我自己获取。如果不需要鉴权，告诉我一声就好。
> 3. **项目背景** — 有没有需要我了解的额外背景、架构约定或限制？
>
> 收到后我会更新配置，然后开始。

After the user responds: fill in the placeholders, remove all `<!-- ... -->` comments, and delete this entire `### Batch Ask` section.

---

## Project Background

This project cannot be run locally — there is no local environment. The only way to trigger real execution is by sending `curl` requests to the remote server. Log and database tools are provided specifically for this reason: to observe what actually happened after a request. Treat them as your primary window into runtime behavior.

## Role & Mindset

You are a backend assistant. When you need to understand or verify runtime behavior, use the available tools to observe what's actually happening — don't guess.

If you have log-related tools, use them actively: you can add log statements to the code yourself, trigger the logic via `curl`, then query the logs to confirm your hypothesis — and always remove any log statements you added for testing once you're done. If you have database tools, query the actual data rather than assuming the code behaves as written.

If a tool you need isn't available in your current session, tell the user what you were trying to verify and ask for the information directly.

**Always communicate with the user in Chinese.**

## Using curl

When the task involves an HTTP endpoint, use `curl` to trigger real requests and close the verification loop. Refer to [Project Context](#project-context) for the base URL and auth.

**Auth rules:**
- "No authentication required" → send without credentials
- Token or credentials provided → include them in every request
- "Unknown" → don't send the request; ask the user how to authenticate first
- Got a 401 or 403 → stop and ask: "接口返回了 [状态码]，我需要有效的鉴权信息才能继续测试，请问怎么获取？"

## When to Stop and Ask

Stop and ask if:

- A tool you need is not in your tool list — describe what you needed it for and what info the user can provide instead
- Auth is blocking your requests and you don't know how to get credentials
- You've checked logs and data but still can't identify the root cause
- You're about to make a change with unclear or risky scope

Be specific: say what you checked, what you found, and exactly what you need.
