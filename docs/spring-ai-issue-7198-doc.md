# Spring AI Issue #7198: ToolCallingAdvisor.advisorOrder field javadoc inverts the sort direction

Filed: October 18, 2026 — https://github.com/spring-projects/spring-ai/issues/7198
Repo: spring-projects/spring-ai · module: spring-ai-client-chat · version: 2.0.1

## Problem

The `advisorOrder` **field** javadoc in `ToolCallingAdvisor` (v2.0.1) tells users to set the order "close to `Ordered#LOWEST_PRECEDENCE` to ensure an advisor is executed first in the chain (first for request processing, last for response processing)." That is backwards. (The Builder method `advisorOrder(int)` javadoc is neutral — this cites the field.)

## Why it is wrong

Advisors in the `ChatClient` chain are ordered by Spring's standard ordering convention: ascending order value, lower value = higher priority = executed first (`Ordered.LOWEST_PRECEDENCE` is `Integer.MAX_VALUE`, i.e. the lowest priority, so it runs **last**).

A concrete witness from the same class: `ToolCallingAdvisor.DEFAULT_ORDER = HIGHEST_PRECEDENCE + 300` — verified as `-2147483348` via `javap`. The tool loop deliberately sits near-first, which only makes sense under ascending sort; an advisor ordered at `DEFAULT_ORDER + 1` runs immediately after it on every loop iteration (verified behavior on 2.0.1, used to place a custom `CallAdvisor` inside the loop).

Anyone following the javadoc's advice would put their advisor near `LOWEST_PRECEDENCE` — which places it last, the opposite of "executed first."

## Suggested fix

Change the field javadoc to describe the direction correctly, e.g.: "set the order close to `HIGHEST_PRECEDENCE` to ensure an advisor is executed first in the chain (first for request processing, last for response processing)."

## Found while

Building a custom `CallAdvisor` on Spring AI 2.0.1 (Spring Boot 4) that inspects each iteration of the tool loop; the inversion surfaced while positioning it relative to `ToolCallingAdvisor.DEFAULT_ORDER`.
