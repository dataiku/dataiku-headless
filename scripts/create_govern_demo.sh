#!/usr/bin/env bash
# Create diverse Govern sample artifacts for demonstration and live testing.
# Run from the dataiku-cli-govern worktree: bash scripts/create_govern_demo.sh
set -euo pipefail

DKU="uv run dku"

# Helper: create artifact, capture its ID, and handle errors
create_artifact() {
  local json="$1"
  local output
  output=$($DKU govern-artifact create --definition "$json" -o json 2>/dev/null) || {
    echo "FAILED to create artifact. Trying with stderr:" >&2
    $DKU govern-artifact create --definition "$json" 2>&1 >&2
    exit 1
  }
  echo "$output" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])"
}

echo "=== Creating Business Initiatives ==="

BI1=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.business_initiative", "versionId": "bv.system.default"},
  "name": "Customer 360 Intelligence Platform",
  "fields": {
    "description": "Enterprise-wide initiative to unify customer data across all touchpoints — CRM, web analytics, support tickets, and transaction history — into a single AI-powered intelligence platform. Enables real-time personalization, churn prediction, and lifetime value optimization across 12M+ customer base.",
    "value_rating": "High",
    "risk_rating": "Medium low",
    "cost_rating": "Medium high",
    "regions": ["Northern America", "Western Europe"],
    "use_case_domains": ["Customer Analytics & Knowledge", "Customer Lifetime Value"],
    "business_functions": ["Marketing / Sales / Customer Relationship Management", "Data / Analytics"],
    "start_date": "2025-09-01T00:00:00.000Z",
    "target_end_date": "2026-12-31T00:00:00.000Z",
    "ideation_notes": "Approved by CTO and CMO. Budget allocated from FY2025 digital transformation fund. Key stakeholders: VP Marketing, Head of Customer Success, Chief Data Officer.",
    "value_comments": "Expected 15% reduction in customer churn (saves ~$18M/yr). Cross-sell uplift estimated at $7M annual incremental revenue.",
    "risk_comments": "Low technical risk (proven ML stack). Medium data privacy risk — GDPR and CCPA compliance review in progress.",
    "cost_comments": "Total estimated cost $4.2M over 18 months. Includes 3 FTE data scientists, cloud infrastructure, and Dataiku license expansion.",
    "progress_notes": "Phase 1 (data integration) complete. Phase 2 (model development) in progress — churn model at 0.87 AUC on validation set."
  }
}')
echo "  BI1: $BI1 — Customer 360 Intelligence Platform"

BI2=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.business_initiative", "versionId": "bv.system.default"},
  "name": "AI-Powered Fraud Detection Suite",
  "fields": {
    "description": "Complete overhaul of the fraud detection stack. Replace rule-based legacy system with real-time ML scoring pipeline capable of processing 50K transactions/second. Includes transaction anomaly detection, account takeover prevention, and synthetic identity fraud detection.",
    "value_rating": "High",
    "risk_rating": "High",
    "cost_rating": "High",
    "regions": ["Global"],
    "use_case_domains": ["Threat Detection", "Financial Crime"],
    "business_functions": ["IT / Cybersecurity", "Accounting / Finance"],
    "start_date": "2025-06-15T00:00:00.000Z",
    "target_end_date": "2026-09-30T00:00:00.000Z",
    "ideation_notes": "Triggered by $23M fraud losses in FY2024 and regulatory pressure from OCC examination findings. Board-level mandate with quarterly progress reviews.",
    "value_comments": "Projected 40% reduction in fraud losses ($9.2M/yr savings). Reduces false positive rate from 12% to 3%, saving 8 FTE in manual review.",
    "risk_comments": "High regulatory risk — model must be explainable for OCC/CFPB audits. High operational risk — 99.99% uptime required for real-time scoring. Fallback to rule engine required during outages.",
    "cost_comments": "$6.8M total budget. Real-time infrastructure is 45% of cost. GPU cluster for training is $1.2M/yr.",
    "progress_notes": "Transaction scoring model deployed to shadow mode. Processing 100% of transactions but not blocking yet. AML classifier entering review phase.",
    "decision_notes": "Go decision issued Q1 2025 by Risk Committee. Conditional on passing Model Risk Management review before production deployment."
  }
}')
echo "  BI2: $BI2 — AI-Powered Fraud Detection Suite"

BI3=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.business_initiative", "versionId": "bv.system.default"},
  "name": "Predictive Supply Chain Optimization",
  "fields": {
    "description": "Deploy ML-driven demand forecasting and inventory optimization across 340 warehouses in APAC and North America. Integrates with SAP ERP and Oracle SCM. Aims to reduce stockouts by 30% and overstock by 25%.",
    "value_rating": "Medium high",
    "risk_rating": "Medium low",
    "cost_rating": "Medium low",
    "regions": ["Eastern Asia", "South-eastern Asia", "Northern America"],
    "use_case_domains": ["Sales Planning & Forecast"],
    "business_functions": ["Manufacturing", "Internal Processes / Operational Efficiency"],
    "start_date": "2025-11-01T00:00:00.000Z",
    "target_end_date": "2027-03-31T00:00:00.000Z",
    "ideation_notes": "Proposed by VP Supply Chain after benchmarking competitors. Pilot on 12 SKU categories showed 22% improvement in forecast accuracy over current ARIMA models.",
    "value_comments": "Estimated $14M annual savings from reduced waste and stockout losses. ROI payback period: 8 months post full deployment.",
    "risk_comments": "Low model risk (well-understood time-series methods). Medium integration risk — SAP BW extraction is complex. Contingency: CSV-based data pipeline.",
    "cost_comments": "Budget $2.1M. Lean team of 2 data scientists + 1 ML engineer. Leverages existing Dataiku infrastructure."
  }
}')
echo "  BI3: $BI3 — Predictive Supply Chain Optimization"

echo ""
echo "=== Creating Govern Projects ==="

GP1=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_project", "versionId": "bv.system.default"},
  "name": "Customer Churn Prediction",
  "fields": {
    "description": "Build and deploy an XGBoost-based churn prediction model that scores all active customers weekly. Integrates with Salesforce for proactive outreach by Customer Success team. Target: identify 80% of at-risk customers 30 days before churn.",
    "use_case_technical_dimension": ["AI/ML"],
    "qualification_value_rating": "High",
    "qualification_risk_rating": "Low",
    "qualification_feasibility_rating": "High",
    "cost_rating": "Medium low",
    "sensitive_data": "Yes",
    "countries": ["United States of America", "Canada", "United Kingdom of Great Britain and Northern Ireland", "France", "Germany"],
    "qualification_resulting_decision": "Go",
    "start_date": "2025-10-01T00:00:00.000Z",
    "target_end_date": "2026-06-30T00:00:00.000Z",
    "business_initiative": "'"$BI1"'",
    "qualification_notes": "Feasibility confirmed with 6-week proof of concept. Model achieved 0.87 AUC on 18-month holdout. Feature engineering pipeline handles 200+ behavioral signals.",
    "qualification_value_comments": "Preventing churn of top-decile customers saves $2.1M/quarter. Salesforce integration enables automated retention workflows.",
    "qualification_risk_comments": "PII handling reviewed by DPO. GDPR Article 22 compliance ensured — human-in-the-loop for all automated decisions.",
    "qualification_feasibility_comments": "All data sources available. Feature store operational. Model training pipeline takes 4 hours on existing cluster.",
    "qualification_comment_on_decision": "Unanimous Go from steering committee. Budget approved for production deployment.",
    "exploration_notes": "Explored logistic regression, random forest, XGBoost, and LightGBM. XGBoost won on AUC and calibration. SHAP analysis confirms feature importance aligns with domain knowledge.",
    "progress_notes": "Model v1.0 in production since Jan 2026. v2.0 with real-time features in development.",
    "progress_rollout_plan": "Phase 1: US Enterprise (complete). Phase 2: US SMB (in progress). Phase 3: EMEA (Q3 2026)."
  }
}')
echo "  GP1: $GP1 — Customer Churn Prediction"

GP2=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_project", "versionId": "bv.system.default"},
  "name": "Next Best Offer Engine",
  "fields": {
    "description": "LLM-powered recommendation engine that generates personalized product offers using customer context, purchase history, and real-time behavioral signals. Serves offers via API to web, mobile, and email channels.",
    "use_case_technical_dimension": ["LLM/GenAI"],
    "qualification_value_rating": "Medium high",
    "qualification_risk_rating": "Medium high",
    "qualification_feasibility_rating": "Medium high",
    "cost_rating": "Medium high",
    "sensitive_data": "Yes",
    "countries": ["United States of America", "United Kingdom of Great Britain and Northern Ireland"],
    "qualification_resulting_decision": "Go",
    "start_date": "2026-01-15T00:00:00.000Z",
    "target_end_date": "2026-09-30T00:00:00.000Z",
    "business_initiative": "'"$BI1"'",
    "qualification_notes": "A/B test on 5% traffic showed 23% uplift in conversion vs. rule-based engine. LLM guardrails prevent hallucinated offers — 0 incidents in 4-week trial.",
    "qualification_value_comments": "Projected $7.2M incremental revenue from improved cross-sell conversion. Email channel alone expected to generate $2.1M.",
    "qualification_risk_comments": "LLM hallucination risk mitigated by offer catalog constraint. Cost risk: GPT-4 API at $0.03/request — budget for 10M requests/month.",
    "exploration_notes": "Compared collaborative filtering, content-based, and LLM-augmented hybrid. Hybrid approach with RAG on product catalog selected."
  }
}')
echo "  GP2: $GP2 — Next Best Offer Engine"

GP3=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_project", "versionId": "bv.system.default"},
  "name": "Real-Time Transaction Scoring",
  "fields": {
    "description": "Sub-100ms fraud scoring API that evaluates every card-present and card-not-present transaction. Uses ensemble of Isolation Forest for anomaly detection and gradient boosting for fraud probability. Integrated with Visa/Mastercard authorization flow.",
    "use_case_technical_dimension": ["AI/ML"],
    "qualification_value_rating": "High",
    "qualification_risk_rating": "High",
    "qualification_feasibility_rating": "Medium high",
    "cost_rating": "High",
    "sensitive_data": "Yes",
    "countries": ["Global"],
    "qualification_resulting_decision": "Go",
    "start_date": "2025-07-01T00:00:00.000Z",
    "target_end_date": "2026-06-30T00:00:00.000Z",
    "business_initiative": "'"$BI2"'",
    "qualification_notes": "Shadow mode testing on 100% of transactions for 3 months. Would have caught 67% more fraud than current rules with 75% fewer false positives.",
    "qualification_value_comments": "Direct fraud loss reduction: $5.8M/yr. False positive reduction saves $1.4M/yr in manual review labor.",
    "qualification_risk_comments": "Latency SLA: p99 < 80ms. Model bias audit by external firm completed — no disparate impact found. Regulatory: model documentation meets SR 11-7 requirements.",
    "qualification_feasibility_comments": "Kafka streaming pipeline tested at 80K events/sec. Feature store serves p99 in 12ms.",
    "exploration_notes": "Evaluated Isolation Forest, Autoencoder, and GBM ensemble. Selected IF+GBM ensemble for complementary detection patterns. IF catches novel fraud; GBM catches known patterns.",
    "progress_notes": "Production deployment scheduled for 2026-04-15. Currently in final UAT with Operations team. Fallback rules engine tested and certified."
  }
}')
echo "  GP3: $GP3 — Real-Time Transaction Scoring"

GP4=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_project", "versionId": "bv.system.default"},
  "name": "Anti-Money Laundering Classifier",
  "fields": {
    "description": "ML-based SAR (Suspicious Activity Report) triage system. Prioritizes alerts from transaction monitoring system using graph features (entity relationships), behavioral features, and historical SAR filing patterns. Reduces investigator workload by 40%.",
    "use_case_technical_dimension": ["AI/ML"],
    "qualification_value_rating": "High",
    "qualification_risk_rating": "High",
    "qualification_feasibility_rating": "Medium low",
    "cost_rating": "Medium high",
    "sensitive_data": "Yes",
    "countries": ["United States of America", "United Kingdom of Great Britain and Northern Ireland", "Singapore"],
    "start_date": "2025-08-01T00:00:00.000Z",
    "target_end_date": "2026-12-31T00:00:00.000Z",
    "business_initiative": "'"$BI2"'",
    "qualification_notes": "Regulatory approval required before production use. FinCEN guidance on AI/ML in BSA compliance reviewed. Model must maintain >95% recall on truly suspicious activities.",
    "qualification_risk_comments": "Extreme regulatory risk — false negatives (missed SARs) could trigger enforcement action. Model must be fully explainable. External model validation required.",
    "qualification_feasibility_comments": "Data quality challenge: legacy transaction monitoring system produces noisy alerts. Graph feature engineering requires Neo4j infrastructure not yet provisioned.",
    "exploration_notes": "Explored GBM, graph neural networks, and hybrid approach. GBM with graph-derived features selected — simpler to explain to regulators than end-to-end GNN."
  }
}')
echo "  GP4: $GP4 — Anti-Money Laundering Classifier"

GP5=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_project", "versionId": "bv.system.default"},
  "name": "Demand Forecast Engine",
  "fields": {
    "description": "Multi-horizon demand forecasting for 15,000 SKUs across 340 warehouses. Combines Prophet for trend/seasonality decomposition with LightGBM for short-term adjustments using promotional calendars, weather data, and economic indicators.",
    "use_case_technical_dimension": ["Analytics"],
    "qualification_value_rating": "Medium high",
    "qualification_risk_rating": "Low",
    "qualification_feasibility_rating": "High",
    "cost_rating": "Low",
    "sensitive_data": "No",
    "countries": ["United States of America", "Japan", "Republic of Korea", "Thailand"],
    "qualification_resulting_decision": "Go",
    "start_date": "2025-12-01T00:00:00.000Z",
    "target_end_date": "2026-11-30T00:00:00.000Z",
    "business_initiative": "'"$BI3"'",
    "qualification_notes": "Pilot on 12 SKU categories showed 22% improvement vs. current ARIMA. Scaling to full catalog is the main engineering challenge.",
    "qualification_value_comments": "Stockout reduction: $8.4M/yr. Overstock reduction: $5.6M/yr. Warehouse labor optimization: $1.2M/yr.",
    "qualification_risk_comments": "Low risk. Time-series forecasting is mature. Worst case: fall back to current ARIMA models.",
    "qualification_feasibility_comments": "SAP BW extraction pipeline built during pilot. All external data sources (weather, promotions) have stable APIs.",
    "exploration_notes": "Benchmarked ARIMA, ETS, Prophet, DeepAR, and LightGBM. Prophet+LightGBM hybrid won on MAPE across all horizons (7d, 14d, 30d, 90d).",
    "progress_notes": "Phase 1 (US warehouses) complete — 340 models trained and serving daily batch predictions. Phase 2 (APAC) in data integration."
  }
}')
echo "  GP5: $GP5 — Demand Forecast Engine"

echo ""
echo "=== Creating Govern Models ==="

GM1=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model", "versionId": "bv.system.default"},
  "name": "XGBoost Churn Classifier",
  "fields": {
    "description": "Gradient-boosted tree classifier predicting 30-day customer churn probability. 200+ features from CRM, product usage, support tickets, and billing. Trained on 18 months of labeled data (2.1M customers). Weekly batch scoring with Dataiku Scenario.",
    "govern_project": "'"$GP1"'"
  }
}')
echo "  GM1: $GM1 — XGBoost Churn Classifier"

GM2=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model", "versionId": "bv.system.default"},
  "name": "GPT-4 Recommendation Agent",
  "fields": {
    "description": "RAG-augmented LLM agent that generates personalized product recommendations. Uses product catalog knowledge bank + customer context. Constrained to only recommend existing products with verified pricing. Guardrails prevent off-topic or inappropriate responses.",
    "govern_project": "'"$GP2"'"
  }
}')
echo "  GM2: $GM2 — GPT-4 Recommendation Agent"

GM3=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model", "versionId": "bv.system.default"},
  "name": "Isolation Forest Anomaly Detector",
  "fields": {
    "description": "Unsupervised anomaly detection model for real-time transaction fraud scoring. Detects novel fraud patterns not seen in training data. Processes 50K transactions/second with p99 latency < 15ms. Feature vector: 45 dimensions including velocity, geolocation, device fingerprint, and merchant category patterns.",
    "govern_project": "'"$GP3"'"
  }
}')
echo "  GM3: $GM3 — Isolation Forest Anomaly Detector"

GM4=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model", "versionId": "bv.system.default"},
  "name": "Random Forest AML Alert Scorer",
  "fields": {
    "description": "Supervised classification model that prioritizes AML transaction monitoring alerts. Graph-derived features capture entity relationship patterns (shell company networks, layering behavior). 95.2% recall on historically filed SARs with 60% precision improvement over rule-based triage.",
    "govern_project": "'"$GP4"'"
  }
}')
echo "  GM4: $GM4 — Random Forest AML Alert Scorer"

GM5=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model", "versionId": "bv.system.default"},
  "name": "Prophet Time-Series Forecaster",
  "fields": {
    "description": "Hybrid Prophet + LightGBM demand forecasting ensemble. Prophet handles trend, seasonality, and holiday effects. LightGBM provides short-term corrections using promotional calendar, weather, and economic indicator features. 15,000 independent models (one per SKU).",
    "govern_project": "'"$GP5"'"
  }
}')
echo "  GM5: $GM5 — Prophet Time-Series Forecaster"

echo ""
echo "=== Creating Model Versions ==="

MV1=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "Churn Classifier v1.0",
  "fields": {
    "description": "Initial production release. AUC: 0.87, Precision@10%: 0.72, Recall@10%: 0.68. Trained on 18M labeled records (Jan 2024 - Jun 2025). 200 features. Deployed via Dataiku API Node. Weekly batch scoring of 12M customers.",
    "govern_model": "'"$GM1"'",
    "dev_notes": "Hyperparameter tuning via Bayesian optimization (500 trials). Early stopping at 250 rounds. Learning rate 0.05, max_depth 8, subsample 0.8.",
    "review_notes": "Passed Model Risk Management review. SHAP-based explanations approved by compliance. No disparate impact detected across protected classes (age, gender, geography).",
    "prod_notes": "Production since Jan 2026. Monthly model monitoring shows stable AUC (0.85-0.88 range). PSI < 0.1 across all feature distributions. No data drift alerts triggered."
  }
}')
echo "  MV1: $MV1 — Churn Classifier v1.0"

MV2=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "Churn Classifier v2.0",
  "fields": {
    "description": "Enhanced version with real-time behavioral features. AUC: 0.91 (+0.04 vs v1.0). New features: session frequency (7d rolling), support ticket sentiment score (BERT), and product usage change velocity. Targets 48-hour prediction horizon (vs 30-day in v1.0).",
    "govern_model": "'"$GM1"'",
    "dev_notes": "Added 35 real-time features from event stream. Retrained on 24 months of data. Architecture: two-stage model — LightGBM for feature selection, XGBoost for final scoring. Training time: 6 hours on 8x A100 cluster.",
    "review_notes": "In review — awaiting fairness audit results from external vendor (expected 2026-04-20). Preliminary internal bias check passed."
  }
}')
echo "  MV2: $MV2 — Churn Classifier v2.0"

MV3=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "Recommendation Agent v1.0",
  "fields": {
    "description": "First version of LLM-powered recommendation agent. GPT-4 with RAG over 50K product catalog. Context window includes: customer segment, last 10 purchases, browsing history (7d), and active promotions. Average response time: 1.2s. Guardrails: no financial advice, no competitor mentions, price accuracy check.",
    "govern_model": "'"$GM2"'",
    "dev_notes": "Prompt engineering: 15 iterations to optimize offer relevance and tone. RAG retrieval uses hybrid search (BM25 + embedding similarity). Knowledge bank updated daily from product catalog API. Evaluation: human raters scored 4.2/5 on relevance, 4.5/5 on tone."
  }
}')
echo "  MV3: $MV3 — Recommendation Agent v1.0"

MV4=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "Anomaly Detector v1.0",
  "fields": {
    "description": "Production isolation forest model. Contamination parameter: 0.01. 256 estimators. 45-dimensional feature vector. Trained on 90 days of normal transaction data (800M transactions). Detection rate: 78% of known fraud patterns at 2% false positive rate.",
    "govern_model": "'"$GM3"'",
    "dev_notes": "Feature engineering: velocity features (1h, 6h, 24h, 7d windows), geolocation features (distance from home, country risk score), device features (fingerprint age, OS match), merchant features (category risk, first-time merchant flag).",
    "review_notes": "Passed latency review: p50=3ms, p95=8ms, p99=14ms. Passed capacity test: sustained 80K TPS for 4 hours. Model bias analysis not applicable (unsupervised model).",
    "prod_notes": "Shadow mode since Jan 2026. Would have blocked $2.3M in fraud that rules missed (3-month period). Zero customer-impacting false positives above $10K threshold."
  }
}')
echo "  MV4: $MV4 — Anomaly Detector v1.0"

MV5=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "Anomaly Detector v1.1",
  "fields": {
    "description": "Patched version with improved card-not-present (CNP) detection. Added 8 new features for e-commerce transactions: session duration, cart abandonment pattern, shipping/billing address mismatch, email domain age. CNP fraud detection rate improved from 65% to 81%.",
    "govern_model": "'"$GM3"'",
    "dev_notes": "Retrained on extended feature set. Same hyperparameters as v1.0 (validated via ablation study). Training data window extended to 120 days to capture seasonal e-commerce patterns.",
    "review_notes": "Fast-track review approved (minor feature addition, same architecture). Latency regression test passed — no measurable impact from 8 additional features."
  }
}')
echo "  MV5: $MV5 — Anomaly Detector v1.1"

MV6=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "AML Scorer v0.9-beta",
  "fields": {
    "description": "Beta version for regulatory sandbox testing. 120 features including 30 graph-derived features from Neo4j entity resolution. Recall: 95.2% on historical SARs. Precision: 34% (3x improvement over rule-based triage). Trained on 5 years of labeled alert data.",
    "govern_model": "'"$GM4"'",
    "dev_notes": "Graph features computed nightly via Neo4j Spark connector. Entity resolution links customers, accounts, and counterparties into a unified graph. Key graph features: PageRank, community detection cluster ID, shortest path to known SAR entities, transaction flow centrality."
  }
}')
echo "  MV6: $MV6 — AML Scorer v0.9-beta"

MV7=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "Demand Forecaster v1.0",
  "fields": {
    "description": "Production ensemble for US warehouses. Prophet component handles trend + 3 seasonalities (weekly, monthly, yearly). LightGBM corrects residuals using 25 external features. MAPE: 8.2% (7d), 11.4% (14d), 15.1% (30d), 22.3% (90d). Covers 8,400 SKUs across 180 US locations.",
    "govern_model": "'"$GM5"'",
    "dev_notes": "15,000 independent models trained in parallel via Dataiku cluster. Auto-tuning: Prophet changepoint_prior_scale and LightGBM hyperparameters optimized per SKU category. Cold-start SKUs use category-level pooled model.",
    "review_notes": "Reviewed by Supply Chain Analytics team. Accuracy benchmarked against current ARIMA: 22% MAPE improvement on average. Worst-case SKU categories identified and documented.",
    "prod_notes": "Daily batch predictions at 02:00 UTC. Results pushed to SAP IBP via RFC interface. Operations dashboard tracks MAPE by category weekly. Retraining triggered automatically when MAPE exceeds 20% for any category."
  }
}')
echo "  MV7: $MV7 — Demand Forecaster v1.0"

MV8=$(create_artifact '{
  "blueprintVersionId": {"blueprintId": "bp.system.govern_model_version", "versionId": "bv.system.default"},
  "name": "Demand Forecaster v2.0-dev",
  "fields": {
    "description": "Development version targeting APAC expansion. Adds support for lunar calendar seasonality (critical for East Asian markets), typhoon season weather patterns, and local holiday calendars for Japan, South Korea, Thailand, and Vietnam.",
    "govern_model": "'"$GM5"'",
    "dev_notes": "Extended Prophet with custom seasonality Fourier terms for lunar calendar. Added 12 APAC-specific features: Golden Week indicator, monsoon season flag, Lunar New Year proximity, and regional economic sentiment index. Initial MAPE on Japan pilot data: 9.8% (7d)."
  }
}')
echo "  MV8: $MV8 — Demand Forecaster v2.0-dev"

echo ""
echo "========================================="
echo "  GOVERN DEMO DATA CREATED SUCCESSFULLY"
echo "========================================="
echo ""
echo "Artifacts created:"
echo "  3 Business Initiatives: $BI1, $BI2, $BI3"
echo "  5 Govern Projects:      $GP1, $GP2, $GP3, $GP4, $GP5"
echo "  5 Govern Models:        $GM1, $GM2, $GM3, $GM4, $GM5"
echo "  8 Model Versions:       $MV1, $MV2, $MV3, $MV4, $MV5, $MV6, $MV7, $MV8"
echo "  Total: 21 artifacts"
echo ""
echo "Hierarchy:"
echo "  $BI1 Customer 360 Intelligence Platform"
echo "    ├── $GP1 Customer Churn Prediction"
echo "    │   └── $GM1 XGBoost Churn Classifier"
echo "    │       ├── $MV1 v1.0 (production)"
echo "    │       └── $MV2 v2.0 (in review)"
echo "    └── $GP2 Next Best Offer Engine"
echo "        └── $GM2 GPT-4 Recommendation Agent"
echo "            └── $MV3 v1.0 (development)"
echo ""
echo "  $BI2 AI-Powered Fraud Detection Suite"
echo "    ├── $GP3 Real-Time Transaction Scoring"
echo "    │   └── $GM3 Isolation Forest Anomaly Detector"
echo "    │       ├── $MV4 v1.0 (deployment)"
echo "    │       └── $MV5 v1.1 (review)"
echo "    └── $GP4 Anti-Money Laundering Classifier"
echo "        └── $GM4 Random Forest AML Alert Scorer"
echo "            └── $MV6 v0.9-beta (development)"
echo ""
echo "  $BI3 Predictive Supply Chain Optimization"
echo "    └── $GP5 Demand Forecast Engine"
echo "        └── $GM5 Prophet Time-Series Forecaster"
echo "            ├── $MV7 v1.0 (production)"
echo "            └── $MV8 v2.0-dev (development)"
echo ""
echo "View: dku govern-artifact list --page-size 50"
