# SparkLens AI Agent - Project Roadmap 🗺️

This document outlines the strategic vision, milestones, and development roadmap for the **SparkLens AI Agent**.

---

## 1. Visual Roadmap & Milestones

```mermaid
gantt
    title SparkLens AI Agent Development Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1: MVP & MCP
    Dynamic Schema Compilation & FastMCP Bridge :done, p1_1, 2026-08-01, 2026-08-20
    Streaming UI & Real-Time Tool Call Indicators :done, p1_2, 2026-08-21, 2026-08-26
    Request-Local ContextVar Isolation & Resiliency :done, p1_3, 2026-08-27, 2026-09-02
    
    section Phase 2: Deep Tuning
    WholeStageCodegen & Memory Spill Profiler   :active, p2_1, 2026-09-03, 2026-09-25
    Automated Spark Config Optimizer (Parallelism/RAM) :p2_2, 2026-09-20, 2026-10-15
    Multi-Turn Diagnostic Graphs & Memory Persistence :p2_3, 2026-10-01, 2026-10-30

    section Phase 3: Live Cluster
    Spark Connect & Livy Live Session Introspection :p3_1, 2026-11-01, 2026-11-30
    Autonomous Data Skew & Partition Rebalance AI   :p3_2, 2026-11-15, 2026-12-15

    section Phase 4: Enterprise
    Kubernetes Operator & Prometheus Metrics Export :p4_1, 2027-01-01, 2027-02-15
    RBAC, Audit Logging & Multi-Tenant Isolation    :p4_2, 2027-02-01, 2027-03-30
```

---

## 2. Detailed Phase Breakdown

### ✅ Phase 1: MVP & Dynamic MCP Diagnostics (Completed)
- [x] Establish dynamic FastMCP SSE connection protocol.
- [x] Dynamic tool schema translation from JSON Schema to Pydantic models.
- [x] Real-time token streaming with live tool-calling execution pills in UI.
- [x] Request-local MCP session lifecycle management using Python `contextvars`.
- [x] Standalone package structure with UV and Hatchling.
- [x] Resilient startup with lazy on-demand MCP compiler fallback.

---

### 🚧 Phase 2: Deep Diagnostics & Configuration Tuning (In Progress)
- [ ] **Automated WholeStageCodegen Analysis:** Breakdown sub-operator execution times in SQL queries (Filter, HashAggregate, BroadcastExchange).
- [ ] **Config Optimization Advisor:** Recommend exact `spark.sql.shuffle.partitions`, `spark.executor.memory`, and `spark.default.parallelism` values based on observed task spills and stage runtime percentiles.
- [ ] **Persistent Memory Checkpointing:** Support Redis / PostgreSQL checkpointers for persisting diagnostic session histories across restarts.
- [ ] **Log Parsing & Exception Stack Traces:** Direct log file extraction for executor JVM crashes and GC pause spikes.

---

### 🔮 Phase 3: Live Spark Cluster Integrations (Planned)
- [ ] **Spark Connect Integration:** Direct connectivity with Spark 3.4+ and Spark 4.x Connect endpoints for live DataFrame introspection.
- [ ] **Livy Session Controller:** Trigger interactive diagnostic statements and explain plans on active Livy sessions.
- [ ] **Autonomous Skew Mitigation:** Generate ready-to-run PySpark and Spark SQL code patches (e.g. `salting` or `broadcast` join hints) to remediate detected data skew.

---

### 🏢 Phase 4: Enterprise & Production Readiness (Future)
- [ ] **Kubernetes & Cloud Support:** Integration with the Spark-on-K8s Operator, Amazon EMR, and Databricks.
- [ ] **Prometheus Metrics Exporter:** Export diagnostic activity and token usage metrics to Prometheus / Grafana.
- [ ] **Role-Based Access Control (RBAC):** Authenticate queries and restrict access to sensitive environment parameters.
- [ ] **Multi-Model Support:** Configurable fallback between Google Gemini, Anthropic Claude, and local Ollama models.

---

## 3. Feedback & Contributions

Contributions and ideas are welcome! Please open an issue or pull request in the repository to propose new features or diagnostic tools.
